import os
import logging
import random
from pathlib import Path
from dotenv import load_dotenv
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
)
from db import init_db, save_test, get_test, get_teacher_tests

load_dotenv()
init_db()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CODE = "2308"

logging.basicConfig(level=logging.INFO)

(
    SELECT_ROLE,
    SHOW_MENU,
    AWAITING_FILE,
    ENTER_KEY,
    ENTER_TEST_CODE,
    STUDENT_MENU,
    HANDLE_ANSWERS,
    SELECT_FEEDBACK_TYPE,
) = range(8)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [["Я учитель", "Я ученик"]]
    await update.message.reply_text(
        "Здравствуйте! Выберите, кто вы:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return SELECT_ROLE


async def select_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = update.message.text
    user_data = context.user_data

    if role == "Я учитель":
        await update.message.reply_text("Введите код учителя:")
        return SHOW_MENU
    elif role == "Я ученик":
        user_data["role"] = "student"
        await update.message.reply_text("Введите код теста:")
        return ENTER_TEST_CODE
    else:
        await update.message.reply_text("Пожалуйста, выберите вариант с клавиатуры.")
        return SELECT_ROLE


async def show_teacher_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == ADMIN_CODE:
        context.user_data["role"] = "teacher"
        keyboard = [["Мои тесты", "Добавить тест"], ["О себе"]]
        await update.message.reply_text(
            "Добро пожаловать, учитель!",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        )
        return SHOW_MENU
    else:
        context.user_data["role"] = "student"
        await update.message.reply_text("Код неверный. Вы ученик. Введите код теста:")
        return ENTER_TEST_CODE


async def handle_teacher_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "Добавить тест":
        await update.message.reply_text("Пришлите файл теста (PDF или изображение):")
        return AWAITING_FILE
    elif text == "Мои тесты":
        teacher_id = update.effective_user.id
        tests = get_teacher_tests(teacher_id)
        if not tests:
            await update.message.reply_text("У вас пока нет загруженных тестов.")
        else:
            message = "Ваши тесты:\n"
            for code, key in tests:
                count = len(key)
                message += f"Код: {code} — {count} вопросов\n"
            await update.message.reply_text(message)
        return SHOW_MENU
    elif text == "О себе":
        await update.message.reply_text(f"Ваш ID: {update.effective_user.id}")
        return SHOW_MENU
    else:
        await update.message.reply_text("Выберите действие с клавиатуры.")
        return SHOW_MENU


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    folder = f"tests/{user_id}"
    os.makedirs(folder, exist_ok=True)

    code = str(random.randint(10000, 99999))
    context.user_data["test_code"] = code

    test_path = f"{folder}/{code}"
    os.makedirs(test_path, exist_ok=True)

    file = update.message.document or update.message.photo[-1]
    file_path = f"{test_path}/test.pdf" if update.message.document else f"{test_path}/image.jpg"
    await file.get_file().download_to_drive(file_path)

    await update.message.reply_text("Теперь введите правильные ответы (например: ABACD...):")
    return ENTER_KEY


async def handle_key_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = update.message.text.strip().upper()
    if not key.isalpha():
        await update.message.reply_text("Ответы должны содержать только буквы.")
        return ENTER_KEY

    test_code = context.user_data["test_code"]
    teacher_id = update.effective_user.id
    
    save_test(test_code, teacher_id, key, "short") # По умолчанию ставим "short"

    buttons = [
        [
            InlineKeyboardButton("Короткий", callback_data="short"),
            InlineKeyboardButton("Развернутый", callback_data="detailed"),
            InlineKeyboardButton("Полный", callback_data="full"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        f"Тест сохранён. Кол-во вопросов: {len(key)}\nВыберите формат обратной связи:",
        reply_markup=reply_markup,
    )
    return SELECT_FEEDBACK_TYPE


async def select_feedback_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    feedback_type = query.data

    test_code = context.user_data["test_code"]
    teacher_id = update.effective_user.id
    
    cur.execute("UPDATE tests SET feedback_mode = %s WHERE test_code = %s AND teacher_id = %s",
                 (feedback_type, test_code, teacher_id))
    conn.commit()

    await query.edit_message_text(
        f"Формат обратной связи выбран: {feedback_type}. Тест полностью сохранён."
    )
    return SHOW_MENU


async def handle_test_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    test_data = get_test(code)

    if not test_data:
        await update.message.reply_text("Тест с таким кодом не найден.")
        return ENTER_TEST_CODE
    
    teacher_id, key, feedback_mode = test_data
    context.user_data["test_data"] = {"key": key, "feedback_mode": feedback_mode}
    
    test_path = f"tests/{teacher_id}/{code}"
    context.user_data["test_path"] = test_path

    # Отправка файла ученику
    for file in Path(test_path).iterdir():
        if file.suffix == ".pdf":
            await update.message.reply_document(file_path=file)
        elif file.suffix in [".jpg", ".jpeg", ".png"]:
            await update.message.reply_photo(photo=open(file, "rb"))

    await update.message.reply_text("Просмотрите тест и введите ответы (например: ABACD...):")
    return HANDLE_ANSWERS


async def handle_student_answers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answers = update.message.text.strip().upper()
    test_data = context.user_data.get("test_data")

    if not test_data:
        await update.message.reply_text("Ответы к тесту не найдены.")
        return STUDENT_MENU
    
    key = test_data["key"].strip().upper()
    feedback_mode = test_data["feedback_mode"]

    if len(answers) != len(key):
        await update.message.reply_text(f"Вы ввели {len(answers)} ответов, а должно быть {len(key)}.")
        return HANDLE_ANSWERS

    correct = 0
    detailed = []
    for i, (a, k) in enumerate(zip(answers, key), 1):
        if a == k:
            correct += 1
            detailed.append(f"{i}) ✅ {a}")
        else:
            detailed.append(f"{i}) ❌ {a} → {k}")

    if feedback_mode == "short":
        await update.message.reply_text(f"✅ Ваш результат: {correct} из {len(key)}.")
    elif feedback_mode == "detailed":
        await update.message.reply_text(
            f"Ваш результат: {correct} из {len(key)}.\n" + "\n".join(
                [line.split("→")[0] for line in detailed]
            )
        )
    elif feedback_mode == "full":
        await update.message.reply_text(
            f"Ваш результат: {correct} из {len(key)}.\n" + "\n".join(detailed)
        )
    return STUDENT_MENU


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    return await start(update, context)


if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
    SELECT_ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_role)],
    SHOW_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, show_teacher_menu)],
    AWAITING_FILE: [MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file)],
    ENTER_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_key_input)],
    SELECT_FEEDBACK_TYPE: [CallbackQueryHandler(select_feedback_type)],
    ENTER_TEST_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_test_code)],
    HANDLE_ANSWERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_student_answers)],
    STUDENT_MENU: [],
},

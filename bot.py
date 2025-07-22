import os
import logging
import random
from pathlib import Path
from dotenv import load_dotenv
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
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

load_dotenv()

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
        folder = f"tests/{update.effective_user.id}"
        if not os.path.exists(folder):
            await update.message.reply_text("У вас пока нет загруженных тестов.")
            return SHOW_MENU
        message = "Ваши тесты:\n"
        for code in os.listdir(folder):
            test_path = os.path.join(folder, code)
            if os.path.isdir(test_path):
                key_path = os.path.join(test_path, "key.txt")
                if os.path.exists(key_path):
                    with open(key_path) as f:
                        key = f.read().strip()
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
    user_id = update.effective_user.id
    folder = f"tests/{user_id}/{test_code}"

    with open(f"{folder}/key.txt", "w") as f:
        f.write(key)

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
    user_id = update.effective_user.id
    folder = f"tests/{user_id}/{test_code}"

    with open(f"{folder}/feedback.mode", "w") as f:
        f.write(feedback_type)

    await query.edit_message_text(
        f"Формат обратной связи выбран: {feedback_type}. Тест полностью сохранён."
    )
    return SHOW_MENU


async def handle_test_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_code_for_result"):
        context.user_data.pop("awaiting_code_for_result")
        await update.message.reply_text("Показ результата по этому тесту — в разработке.")
        return STUDENT_MENU

    code = update.message.text.strip()
    found = False
    for teacher_folder in Path("tests").iterdir():
        test_path = teacher_folder / code
        if test_path.exists():
            context.user_data["test_path"] = str(test_path)
            found = True
            break
    if not found:
        await update.message.reply_text("Тест с таким кодом не найден.")
        return ENTER_TEST_CODE

    for file in Path(context.user_data["test_path"]).iterdir():
        if file.suffix == ".pdf":
            await update.message.reply_document(file_path=file)
        elif file.suffix in [".jpg", ".jpeg", ".png"]:
            await update.message.reply_photo(photo=open(file, "rb"))

    await update.message.reply_text("Просмотрите тест и введите ответы (например: ABACD...):")
    return HANDLE_ANSWERS


async def handle_student_answers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answers = update.message.text.strip().upper()
    test_path = context.user_data["test_path"]
    key_path = f"{test_path}/key.txt"
    mode_path = f"{test_path}/feedback.mode"

    if not os.path.exists(key_path):
        await update.message.reply_text("Ответы к тесту не найдены.")
        return STUDENT_MENU

    with open(key_path) as f:
        key = f.read().strip().upper()

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

    feedback_mode = "short"
    if os.path.exists(mode_path):
        with open(mode_path) as f:
            feedback_mode = f.read().strip()

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


async def show_student_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Мои результаты", "Результат по коду"], ["О себе"]]
    await update.message.reply_text(
        "Главное меню ученика:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )
    return STUDENT_MENU


async def handle_student_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()

    if text == "главное меню":
        return await show_student_menu(update, context)

    elif text == "мои результаты":
        await update.message.reply_text("Ваши последние 3 результата (в разработке).")
        return STUDENT_MENU

    elif text == "результат по коду":
        await update.message.reply_text("Введите код теста для просмотра результатов:")
        context.user_data["awaiting_code_for_result"] = True
        return ENTER_TEST_CODE

    elif text == "о себе":
        user = update.effective_user
        await update.message.reply_text(f"Ваш Telegram ID: {user.id}")
        return STUDENT_MENU

    else:
        await update.message.reply_text("Пожалуйста, выберите пункт меню.")
        return STUDENT_MENU


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    return await start(update, context)


if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8443))
    WEBHOOK_URL = f"https://{os.environ.get('RAILWAY_STATIC_URL')}"

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
            STUDENT_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_student_menu)],
        },
        fallbacks=[CommandHandler("reset", reset)],
        per_message=True,
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("reset", reset))

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL
    )

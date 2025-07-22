import os
import logging
import random
import datetime
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

# Загрузка токена из переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Включаем логирование
logging.basicConfig(level=logging.INFO)

# Состояния ConversationHandler
(
    SELECT_ROLE, SHOW_MENU, AWAITING_FILE, ENTER_KEY,
    SELECT_FEEDBACK_TYPE, ENTER_TEST_CODE, HANDLE_ANSWERS, STUDENT_MENU
) = range(8)

BASE_DIR = Path("tests")
TEACHER_CODE = "2308"
MAX_ATTEMPTS = 2

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    keyboard = [[KeyboardButton("Учитель")], [KeyboardButton("Ученик")]]
    await update.message.reply_text("Выберите свою роль:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return SELECT_ROLE

# Выбор роли
async def select_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = update.message.text.lower()
    context.user_data.clear()
    if role == "учитель":
        await update.message.reply_text("Введите код учителя:", reply_markup=ReplyKeyboardRemove())
        return SHOW_MENU
    else:
        context.user_data["role"] = "student"
        await update.message.reply_text("Введите код теста:", reply_markup=ReplyKeyboardRemove())
        return ENTER_TEST_CODE

# Меню учителя
async def show_teacher_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text != TEACHER_CODE:
        context.user_data["role"] = "student"
        await update.message.reply_text("Неверный код. Назначена роль ученика. Введите код теста:")
        return ENTER_TEST_CODE

    context.user_data["role"] = "teacher"
    keyboard = [[KeyboardButton("Мои тесты")], [KeyboardButton("Добавить тест")], [KeyboardButton("О себе")]]
    await update.message.reply_text("Меню учителя:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return SHOW_MENU

# Обработка меню учителя
async def handle_teacher_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "Добавить тест":
        await update.message.reply_text("Отправьте файл (PDF или изображение) с тестом:")
        return AWAITING_FILE
    elif text == "Мои тесты":
        teacher_dir = BASE_DIR / str(update.message.from_user.id)
        if teacher_dir.exists():
            tests = list(teacher_dir.iterdir())
            if tests:
                message = "\n".join(f"📄 {test.name}" for test in tests if test.is_dir())
                await update.message.reply_text(f"Ваши тесты:\n{message}")
            else:
                await update.message.reply_text("У вас пока нет загруженных тестов.")
        else:
            await update.message.reply_text("У вас пока нет загруженных тестов.")
    elif text == "О себе":
        await update.message.reply_text("Вы вошли как учитель.")
    return SHOW_MENU

# Обработка файла от учителя
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    test_code = str(random.randint(1000, 9999))
    test_dir = BASE_DIR / str(user_id) / test_code
    test_dir.mkdir(parents=True, exist_ok=True)

    if update.message.document:
        file = await update.message.document.get_file()
        file_ext = Path(update.message.document.file_name).suffix
    else:
        file = await update.message.photo[-1].get_file()
        file_ext = ".jpg"

    file_path = test_dir / f"test{file_ext}"
    await file.download_to_drive(file_path)

    context.user_data["test_dir"] = test_dir
    context.user_data["test_code"] = test_code

    await update.message.reply_text("Отправьте ключ ответов (например: 1а,2в,3г,...):")
    return ENTER_KEY

# Обработка ключа ответов
async def handle_key_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key_text = update.message.text.replace(" ", "").lower()
    key = key_text.split(",")
    test_dir = context.user_data["test_dir"]

    with open(test_dir / "key.txt", "w") as f:
        f.write(",".join(key))

    await update.message.reply_text(
        f"Выберите формат обратной связи:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Краткий", callback_data="short")],
            [InlineKeyboardButton("Развернутый", callback_data="detailed")],
            [InlineKeyboardButton("Полный", callback_data="full")]
        ])
    )
    return SELECT_FEEDBACK_TYPE

# Выбор типа обратной связи
async def select_feedback_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mode = query.data
    test_dir = context.user_data["test_dir"]
    with open(test_dir / "feedback.mode", "w") as f:
        f.write(mode)
    await query.edit_message_text(f"Тест успешно сохранён ✅\nКод теста: {context.user_data['test_code']}")
    return SHOW_MENU

# Ученик — ввод кода теста
async def handle_test_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    test_code = update.message.text.strip()
    found = False
    for teacher in BASE_DIR.iterdir():
        path = teacher / test_code
        if path.exists():
            context.user_data["test_dir"] = path
            found = True
            break

    if not found:
        await update.message.reply_text("Тест не найден. Повторите ввод.")
        return ENTER_TEST_CODE

    context.user_data["test_code"] = test_code
    context.user_data["attempts"] = context.user_data.get("attempts", 0)
    context.user_data["start_time"] = datetime.datetime.now().isoformat()
    await update.message.reply_text("Введите ответы через запятую:")
    return HANDLE_ANSWERS

# Ученик — проверка ответов
async def handle_student_answers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answers = [a.strip().lower() for a in update.message.text.split(",")]
    test_dir = context.user_data["test_dir"]
    with open(test_dir / "key.txt") as f:
        correct = f.read().split(",")
    feedback = (test_dir / "feedback.mode").read_text().strip()

    result = []
    score = 0
    for i, ans in enumerate(answers):
        correct_ans = correct[i] if i < len(correct) else "-"
        if ans == correct_ans:
            score += 1
            result.append(f"{i+1}. ✅")
        else:
            if feedback == "short":
                continue
            elif feedback == "detailed":
                result.append(f"{i+1}. ❌")
            elif feedback == "full":
                result.append(f"{i+1}. ❌ (Правильный: {correct_ans})")

    attempts = context.user_data.get("attempts", 0) + 1
    context.user_data["attempts"] = attempts

    summary = f"Ваш результат: {score} из {len(correct)}\n"
    if feedback != "short":
        summary += "\n".join(result)

    await update.message.reply_text(summary)

    if attempts >= MAX_ATTEMPTS:
        await update.message.reply_text("Вы использовали все попытки.")
        return ConversationHandler.END
    else:
        await update.message.reply_text(f"Осталось попыток: {MAX_ATTEMPTS - attempts}")
        return HANDLE_ANSWERS

# Меню ученика
async def handle_student_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Функция в разработке.")
    return STUDENT_MENU

# Команда /reset
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Роль и данные сброшены. Введите /start")
    return ConversationHandler.END

# ============== WEBHOOK ЗАПУСК ==============
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8443))
    WEBHOOK_URL = f"https://{os.environ.get('RAILWAY_STATIC_URL')}"

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_role)],
            SHOW_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_teacher_menu)],
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

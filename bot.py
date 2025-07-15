import os
import logging
import random
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler
)

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Загрузка токена
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TEACHER_CODE = "2308"

# Состояния бота
SELECT_ROLE, TEACHER_AUTH, HANDLE_TEST_UPLOAD, SELECT_FEEDBACK = range(4)

# Каталог для тестов
BASE_DIR = Path("tests")
BASE_DIR.mkdir(exist_ok=True)

# Генерация 4-значного кода теста
def generate_test_id():
    return str(random.randint(1000, 9999))

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [["👨‍🏫 Я учитель", "🧑‍🎓 Я ученик"]]
    await update.message.reply_text(
        "Выберите вашу роль:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return SELECT_ROLE

# Выбор роли
async def select_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    role = update.message.text
    if role == "👨‍🏫 Я учитель":
        await update.message.reply_text("Введите код для подтверждения:")
        return TEACHER_AUTH
    else:
        await update.message.reply_text("✅ Вы зарегистрированы как ученик.")
        return ConversationHandler.END

# Подтверждение кода учителя
async def teacher_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == TEACHER_CODE:
        context.user_data["role"] = "teacher"
        context.user_data["test_id"] = generate_test_id()
        await update.message.reply_text(
            "✅ Вы зарегистрированы как учитель.\n\n"
            "Пожалуйста, отправьте файл теста (PDF или изображение).\n\n"
            "Если вы отправляете PDF, убедитесь, что весь тест в одном файле."
        )
        return HANDLE_TEST_UPLOAD
    else:
        await update.message.reply_text("Неверный код. Вы зарегистрированы как ученик.")
        return ConversationHandler.END

# Обработка загрузки файла
async def handle_test_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    test_id = context.user_data["test_id"]
    test_dir = BASE_DIR / str(user_id) / test_id
    test_dir.mkdir(parents=True, exist_ok=True)

    if update.message.document:
        file = update.message.document
    elif update.message.photo:
        file = update.message.photo[-1]
    else:
        await update.message.reply_text("Пожалуйста, отправьте PDF-файл или изображение.")
        return HANDLE_TEST_UPLOAD

    file_obj = await file.get_file()
    file_name = file.file_name if hasattr(file, "file_name") and file.file_name else f"{file.file_id}.jpg"
    file_path = test_dir / file_name
    await file_obj.download_to_drive(custom_path=str(file_path))

    await update.message.reply_text(
        f"✅ Тест сохранён как *{file_name}*.\nКод теста: `{test_id}`",
        parse_mode="Markdown"
    )

    await update.message.reply_text(
        "Файл загружен.\n\nВыберите формат обратной связи для ученика:",
        reply_markup=ReplyKeyboardMarkup(
            [["📊 Короткий", "📋 Развернутый", "📘 Полный"]],
            one_time_keyboard=True,
            resize_keyboard=True,
        )
    )
    return SELECT_FEEDBACK

# Обработка выбора формата обратной связи
async def select_feedback_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    mode_text = update.message.text
    test_id = context.user_data["test_id"]
    user_id = update.message.from_user.id
    test_dir = BASE_DIR / str(user_id) / test_id

    if mode_text == "📊 Короткий":
        mode = "short"
    elif mode_text == "📋 Развернутый":
        mode = "detailed"
    elif mode_text == "📘 Полный":
        mode = "full"
    else:
        await update.message.reply_text("Пожалуйста, выберите один из предложенных вариантов.")
        return SELECT_FEEDBACK

    with open(test_dir / "feedback.mode", "w", encoding="utf-8") as f:
        f.write(mode)

    await update.message.reply_text(
        f"✅ Формат обратной связи выбран: {mode_text}.\n"
        f"Теперь введите ключ ответов с помощью команды:\n"
        f"`/key {test_id} <ключ_ответов>`",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# Команда /key
async def save_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("role") != "teacher":
        await update.message.reply_text("❌ Только учитель может сохранять ключи ответов.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "❗ Пожалуйста, введите команду в формате:\n"
            "`/key <код_теста> <ключ_ответов>`",
            parse_mode="Markdown"
        )
        return

    test_code = context.args[0]
    answers = "".join(context.args[1:]).strip()
    found = False

    for user_folder in BASE_DIR.iterdir():
        test_folder = user_folder / test_code
        if test_folder.exists():
            found = True
            break

    if not found:
        await update.message.reply_text("❌ Тест с указанным кодом не найден. Убедитесь, что код верный.")
        return

    key_path = test_folder / "answers.key"
    with open(key_path, "w", encoding="utf-8") as f:
        f.write(answers)

    await update.message.reply_text(
        f"✅ Ключ для теста {test_code} успешно сохранён.\n"
        f"Ответы: `{answers}`\n"
        f"Тест состоит из {len(answers)} ответов на вопросы.",
        parse_mode="Markdown"
    )

# Команда /reset
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await start(update, context)

# Точка входа
def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_ROLE: [MessageHandler(filters.TEXT, select_role)],
            TEACHER_AUTH: [MessageHandler(filters.TEXT, teacher_auth)],
            HANDLE_TEST_UPLOAD: [MessageHandler(filters.Document.ALL | filters.PHOTO, handle_test_upload)],
            SELECT_FEEDBACK: [MessageHandler(filters.TEXT, select_feedback_mode)],
        },
        fallbacks=[CommandHandler("reset", reset)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("key", save_key))

    application.run_polling()

if __name__ == "__main__":
    main()

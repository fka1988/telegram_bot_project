import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from uuid import uuid4
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TEACHER_CODE = "2308"

SELECT_ROLE, TEACHER_AUTH, HANDLE_TEST_UPLOAD, AWAIT_NEXT_ACTION = range(4)

BASE_DIR = Path("tests")
BASE_DIR.mkdir(exist_ok=True)

# ⬇ /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [["👨‍🏫 Я учитель", "🧑‍🎓 Я ученик"]]
    await update.message.reply_text(
        "Выберите вашу роль:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return SELECT_ROLE

# ⬇ Выбор роли
async def select_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    role = update.message.text
    if role == "👨‍🏫 Я учитель":
        await update.message.reply_text("Введите код для подтверждения:")
        return TEACHER_AUTH
    else:
        await update.message.reply_text("✅ Вы зарегистрированы как ученик.")
        return ConversationHandler.END

# ⬇ Проверка кода учителя
async def teacher_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == TEACHER_CODE:
        context.user_data["role"] = "teacher"
        context.user_data["test_id"] = str(uuid4().int)[:4]  # Генерация 4-значного кода
        await update.message.reply_text(
            "✅ Вы зарегистрированы как учитель.\n\n"
            "📄 Если вы отправляете PDF-файл, он должен содержать весь тест в одном файле.\n"
            "🖼 Если вы отправляете изображение, вы сможете добавить ещё или перейти к вводу ключа.\n\n"
            "Пожалуйста, отправьте файл теста (PDF или изображение)."
        )
        return HANDLE_TEST_UPLOAD
    else:
        await update.message.reply_text("Неверный код. Вы зарегистрированы как ученик.")
        return ConversationHandler.END

# ⬇ Загрузка файла теста
async def handle_test_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    test_id = context.user_data.get("test_id")
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

    keyboard = [["➕ Добавить ещё изображение", "✅ Ввести ключ ответов"]]
    await update.message.reply_text(
        f"✅ Файл *{file_name}* сохранён.\nКод теста: `{test_id}`\n\n"
        "Что хотите сделать дальше?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return AWAIT_NEXT_ACTION

# ⬇ Обработка действия после загрузки файла
async def await_next_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    choice = update.message.text
    if choice == "➕ Добавить ещё изображение":
        await update.message.reply_text("Пожалуйста, отправьте дополнительное изображение теста.")
        return HANDLE_TEST_UPLOAD
    elif choice == "✅ Ввести ключ ответов":
        await update.message.reply_text(
            "Введите ключ с помощью команды:\n`/key <код_теста> <ключ_ответов>`",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text("Пожалуйста, выберите один из предложенных вариантов.")
        return AWAIT_NEXT_ACTION

# ⬇ Сохранение ключа ответов
async def save_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("role") != "teacher":
        await update.message.reply_text("❌ Только учитель может сохранять ключи ответов.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❗ Пожалуйста, введите команду в формате:\n`/key <код_теста> <ключ_ответов>`", parse_mode="Markdown")
        return

    test_code = context.args[0]
    answers = " ".join(context.args[1:])

    found = False
    for user_folder in BASE_DIR.iterdir():
        test_folder = user_folder / test_code
        if test_folder.exists() and test_folder.is_dir():
            found = True
            break

    if not found:
        await update.message.reply_text("❌ Тест с указанным кодом не найден. Убедитесь, что вы указали правильный код.")
        return

    key_path = test_folder / "answers.key"
    with open(key_path, "w", encoding="utf-8") as f:
        f.write(answers)

    await update.message.reply_text(f"✅ Ключ для теста *{test_code}* успешно сохранён.\nОтветы: `{answers}`", parse_mode="Markdown")

# ⬇ Команда /reset
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await start(update, context)

# ⬇ Точка входа
def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_ROLE: [MessageHandler(filters.TEXT, select_role)],
            TEACHER_AUTH: [MessageHandler(filters.TEXT, teacher_auth)],
            HANDLE_TEST_UPLOAD: [MessageHandler(filters.Document.ALL | filters.PHOTO, handle_test_upload)],
            AWAIT_NEXT_ACTION: [MessageHandler(filters.TEXT, await_next_action)],
        },
        fallbacks=[CommandHandler("reset", reset)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("key", save_key))

    application.run_polling()

if __name__ == "__main__":
    main()

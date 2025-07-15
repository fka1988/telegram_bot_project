import os
import logging
from uuid import uuid4
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, ConversationHandler

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TEACHER_CODE = "2308"

SELECT_ROLE, TEACHER_AUTH, HANDLE_TEST_UPLOAD = range(3)

BASE_DIR = Path("tests")
BASE_DIR.mkdir(exist_ok=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [["👨‍🏫 Я учитель", "🧑‍🎓 Я ученик"]]
    await update.message.reply_text(
        "Выберите вашу роль:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return SELECT_ROLE

async def select_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    role = update.message.text
    if role == "👨‍🏫 Я учитель":
        await update.message.reply_text("Введите код для подтверждения:")
        return TEACHER_AUTH
    else:
        await update.message.reply_text("✅ Вы зарегистрированы как ученик.")
        return ConversationHandler.END

async def teacher_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == TEACHER_CODE:
        context.user_data["role"] = "teacher"
        context.user_data["test_id"] = str(uuid4())
        await update.message.reply_text(
            "✅ Вы зарегистрированы как учитель.\n\nПожалуйста, отправьте файл теста (PDF или изображение)."
        )
        return HANDLE_TEST_UPLOAD
    else:
        await update.message.reply_text("Неверный код. Вы зарегистрированы как ученик.")
        return ConversationHandler.END

async def handle_test_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    test_id = context.user_data.get("test_id", str(uuid4()))
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
    return ConversationHandler.END

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await start(update, context)

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_ROLE: [MessageHandler(filters.TEXT, select_role)],
            TEACHER_AUTH: [MessageHandler(filters.TEXT, teacher_auth)],
            HANDLE_TEST_UPLOAD: [MessageHandler(filters.Document.ALL | filters.PHOTO, handle_test_upload)],
        },
        fallbacks=[CommandHandler("reset", reset)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("reset", reset))

    application.run_polling()

if __name__ == "__main__":
    main()

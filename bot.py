
import os
import json
import random
import string
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CODE = "2308"
DATA_FILE = "tests.json"

# Структура для хранения данных о тестах
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({}, f)


def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def generate_test_code(length=4):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("👨‍🏫 Я учитель"), KeyboardButton("👨‍🎓 Я ученик")]
    ]
    await update.message.reply_text(
        "Выберите вашу роль:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )


async def handle_role_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "👨‍🏫 Я учитель":
        await update.message.reply_text("Введите код доступа:")
        context.user_data["awaiting_admin_code"] = True
    elif text == "👨‍🎓 Я ученик":
        await update.message.reply_text("Введите код теста:")
        context.user_data["role"] = "student"


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if context.user_data.get("awaiting_admin_code"):
        if text == ADMIN_CODE:
            context.user_data["role"] = "teacher"
            await update.message.reply_text("Добро пожаловать, учитель! Отправьте PDF или изображение теста.")
        else:
            context.user_data["role"] = "student"
            await update.message.reply_text("Неверный код. Вы назначены как ученик. Введите код теста:")
        context.user_data["awaiting_admin_code"] = False
    elif context.user_data.get("role") == "student":
        test_code = text.strip().upper()
        data = load_data()
        if test_code in data:
            file_id = data[test_code]["file_id"]
            await update.message.reply_text("Вот ваш тест:")
            await update.message.reply_document(file_id)
        else:
            await update.message.reply_text("Неверный код теста.")
    else:
        await update.message.reply_text("Пожалуйста, нажмите /start для начала.")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("role") != "teacher":
        await update.message.reply_text("Только учителя могут загружать тесты.")
        return

    document = update.message.document
    file_id = document.file_id
    file_name = document.file_name or "тест"

    test_code = generate_test_code()
    data = load_data()
    data[test_code] = {
        "file_id": file_id,
        "file_name": file_name
    }
    save_data(data)

    await update.message.reply_text(
        f"✅ Тест сохранён как *{file_name}*.
Код теста: `{test_code}`",
        parse_mode="Markdown"
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("role") != "teacher":
        await update.message.reply_text("Только учителя могут загружать тесты.")
        return

    photo = update.message.photo[-1]
    file_id = photo.file_id

    test_code = generate_test_code()
    data = load_data()
    data[test_code] = {
        "file_id": file_id,
        "file_name": "изображение"
    }
    save_data(data)

    await update.message.reply_text(
        f"✅ Изображение теста сохранено.
Код теста: `{test_code}`",
        parse_mode="Markdown"
    )


async def resset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await start(update, context)


if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resset", resset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex("👨‍🏫 Я учитель|👨‍🎓 Я ученик"), handle_role_selection))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    app.run_polling()

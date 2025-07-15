
import os
import json
import random
import string
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Document
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, filters, CallbackQueryHandler
)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
TEACHER_CODE = "2308"
TESTS_FILE = "tests.json"

def generate_code(length=4):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def save_test(code, file_id, file_name, uploaded_by):
    if os.path.exists(TESTS_FILE):
        with open(TESTS_FILE, "r") as f:
            data = json.load(f)
    else:
        data = {}
    data[code] = {
        "file_id": file_id,
        "file_name": file_name,
        "uploaded_by": uploaded_by,
        "timestamp": datetime.now().isoformat()
    }
    with open(TESTS_FILE, "w") as f:
        json.dump(data, f, indent=2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Я ученик", callback_data='role_student')],
        [InlineKeyboardButton("Я учитель", callback_data='role_teacher')]
    ]
    await update.message.reply_text(
        "👋 Привет! Пожалуйста, выберите вашу роль:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    role = query.data

    if role == "role_teacher":
        await query.edit_message_text("🔐 Введите код учителя для подтверждения:")
        context.user_data["awaiting_code"] = True
    else:
        context.user_data["role"] = "student"
        await query.edit_message_text("✅ Вы выбрали роль *Ученик*.", parse_mode="Markdown")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_code"):
        if update.message.text.strip() == TEACHER_CODE:
            context.user_data["role"] = "teacher"
            await update.message.reply_text("✅ Код верный. Роль *Учитель* установлена.", parse_mode="Markdown")
        else:
            context.user_data["role"] = "student"
            await update.message.reply_text("❌ Код неверный. Назначена роль *Ученик*.", parse_mode="Markdown")
        context.user_data["awaiting_code"] = False
    else:
        role = context.user_data.get("role", "не установлена")
        await update.message.reply_text(f"🔎 Ваша роль: *{role}*", parse_mode="Markdown")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = context.user_data.get("role")
    if role != "teacher":
        await update.message.reply_text("⛔️ Только учитель может загружать тесты.")
        return

    doc: Document = update.message.document
    file_id = doc.file_id
    file_name = doc.file_name
    code = generate_code()
    save_test(code, file_id, file_name, update.effective_user.id)

    await update.message.reply_text(
        f"✅ Тест сохранён как *{file_name}*.
Код для учеников: `{code}`",
        parse_mode="Markdown"
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🔄 Роль сброшена. Напишите /start для начала заново.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_role))
    app.add_handler(CommandHandler("resset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.run_polling()

if __name__ == "__main__":
    main()

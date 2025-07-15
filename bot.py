
import os
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
TEACHER_CODE = "2308"

ROLE, AUTH_TEACHER, HANDLE_FILE = range(3)

user_roles = {}

start_keyboard = [[KeyboardButton("👨‍🏫 Я учитель")], [KeyboardButton("🎓 Я ученик")]]
start_markup = ReplyKeyboardMarkup(start_keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите вашу роль:", reply_markup=start_markup)
    return ROLE

async def role_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = update.message.text
    user_id = update.effective_user.id

    if role == "👨‍🏫 Я учитель":
        await update.message.reply_text("Введите код учителя:")
        return AUTH_TEACHER
    else:
        user_roles[user_id] = "student"
        await update.message.reply_text("Вы зарегистрированы как ученик.")
        return ConversationHandler.END

async def auth_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    code = update.message.text.strip()

    if code == TEACHER_CODE:
        user_roles[user_id] = "teacher"
        await update.message.reply_text("✅ Вы зарегистрированы как учитель.

Отправьте файл с тестом (PDF или изображение).")
        return HANDLE_FILE
    else:
        user_roles[user_id] = "student"
        await update.message.reply_text("Неверный код. Вы зарегистрированы как ученик.")
        return ConversationHandler.END

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_roles.get(user_id) != "teacher":
        await update.message.reply_text("⛔️ Только учителя могут загружать тесты.")
        return ConversationHandler.END

    file = update.message.document or update.message.photo[-1] if update.message.photo else None

    if not file:
        await update.message.reply_text("Пожалуйста, отправьте PDF или изображение.")
        return HANDLE_FILE

    file_id = file.file_id
    file_obj = await context.bot.get_file(file_id)

    folder_path = f"uploaded_tests/{user_id}"
    os.makedirs(folder_path, exist_ok=True)

    file_name = update.message.document.file_name if update.message.document else f"image_{file_id}.jpg"
    file_path = os.path.join(folder_path, file_name)

    await file_obj.download_to_drive(file_path)

    await update.message.reply_text(f"✅ Тест сохранён как *{file_name}*.", parse_mode="Markdown")
    return ConversationHandler.END

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Пожалуйста, нажмите /start для начала.", reply_markup=start_markup)
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ROLE: [MessageHandler(filters.TEXT, role_chosen)],
            AUTH_TEACHER: [MessageHandler(filters.TEXT & ~filters.COMMAND, auth_teacher)],
            HANDLE_FILE: [MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file)],
        },
        fallbacks=[CommandHandler("resset", reset)],
    )

    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()

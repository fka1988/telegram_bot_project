import os
import logging
import random
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TEACHER_CODE = "2308"

SELECT_ROLE, TEACHER_AUTH, HANDLE_TEST_UPLOAD, CHOOSE_NEXT_ACTION, ASK_FEEDBACK_TYPE = range(5)

BASE_DIR = Path("tests")
BASE_DIR.mkdir(exist_ok=True)

def generate_test_id() -> str:
    return str(random.randint(1000, 9999))

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
        context.user_data["role"] = "student"
        await update.message.reply_text("✅ Вы зарегистрированы как ученик.\nПожалуйста, введите код теста.")
        return ConversationHandler.END

async def teacher_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == TEACHER_CODE:
        context.user_data["role"] = "teacher"
        context.user_data["test_id"] = generate_test_id()
        await update.message.reply_text(
            "✅ Вы зарегистрированы как учитель.\n\n"
            "📌 Если вы отправляете PDF-файл, убедитесь, что он содержит весь тест.\n"
            "Если у вас изображения — вы сможете добавить несколько.\n\n"
            "📎 Пожалуйста, отправьте файл теста (PDF или изображение)."
        )
        return HANDLE_TEST_UPLOAD
    else:
        context.user_data["role"] = "student"
        await update.message.reply_text("Неверный код. Вы зарегистрированы как ученик.\nПожалуйста, введите код теста.")
        return ConversationHandler.END

async def handle_test_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    test_id = context.user_data.get("test_id", generate_test_id())
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

    keyboard = [["➕ Добавить ещё", "✅ Перейти к вводу ключа"]]
    await update.message.reply_text(
        f"✅ Файл {file_name} сохранён.\nКод теста: `{test_id}`\n\n"
        f"Хотите загрузить ещё изображение или перейти к вводу ключа?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return CHOOSE_NEXT_ACTION

async def handle_next_action_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if text == "✅ Перейти к вводу ключа":
        await update.message.reply_text(
            "Выберите тип обратной связи, которую будет получать ученик после прохождения теста:",
            reply_markup=ReplyKeyboardMarkup(
                [["📊 Краткий"], ["📋 Развёрнутый"], ["📚 Полный"]],
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return ASK_FEEDBACK_TYPE
    elif text == "➕ Добавить ещё":
        await update.message.reply_text("📎 Пожалуйста, отправьте ещё изображение.")
        return HANDLE_TEST_UPLOAD
    else:
        await update.message.reply_text("❗ Пожалуйста, выберите действие с помощью кнопок.")
        return CHOOSE_NEXT_ACTION

async def set_feedback_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    feedback_mode = update.message.text
    test_id = context.user_data.get("test_id")
    user_id = update.message.from_user.id
    test_dir = BASE_DIR / str(user_id) / test_id

    if feedback_mode == "📊 Краткий":
        mode = "short"
    elif feedback_mode == "📋 Развёрнутый":
        mode = "detailed"
    elif feedback_mode == "📚 Полный":
        mode = "full"
    else:
        await update.message.reply_text("❗ Неверный выбор. Выберите тип обратной связи.")
        return ASK_FEEDBACK_TYPE

    with open(test_dir / "feedback.mode", "w", encoding="utf-8") as f:
        f.write(mode)

    await update.message.reply_text(
        f"✅ Тип обратной связи установлен: {feedback_mode}\n"
        f"Теперь отправьте команду:\n`/key {test_id} <ключ_ответов>`",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

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

    await update.message.reply_text(
        f"✅ Ключ для теста {test_code} успешно сохранён.\n"
        f"Ответы: {answers}\n"
        f"Тест состоит из {len(answers)} ответов на вопросы."
    )

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
            CHOOSE_NEXT_ACTION: [MessageHandler(filters.TEXT, handle_next_action_choice)],
            ASK_FEEDBACK_TYPE: [MessageHandler(filters.TEXT, set_feedback_type)],
        },
        fallbacks=[CommandHandler("reset", reset)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("key", save_key))

    application.run_polling()

if __name__ == "__main__":
    main()

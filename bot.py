import os
import logging
import random
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TEACHER_CODE = "2308"

# Состояния
SELECT_ROLE, TEACHER_AUTH, HANDLE_TEST_UPLOAD, WAIT_FOR_NEXT_FILE_OR_KEY = range(4)

BASE_DIR = Path("tests")
BASE_DIR.mkdir(exist_ok=True)

# Словарь для соответствия test_id ↔ user_id
TEST_ID_TO_USER = {}

def generate_test_id():
    return str(random.randint(1000, 9999))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [["👨‍🏫 Я учитель", "🧑‍🎓 Я ученик"]]
    await update.message.reply_text(
        "Выберите вашу роль:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return SELECT_ROLE

async def select_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()

    if "учитель" in text:
        await update.message.reply_text("Введите код для подтверждения:")
        return TEACHER_AUTH

    elif "ученик" in text:
        context.user_data["role"] = "student"
        await update.message.reply_text(
            "✅ Вы зарегистрированы как ученик.\nПожалуйста, введите код теста:"
        )
        return ConversationHandler.END

    else:
        await update.message.reply_text("Пожалуйста, выберите одну из ролей с клавиатуры.")
        return SELECT_ROLE

async def teacher_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text.strip() == TEACHER_CODE:
        context.user_data["role"] = "teacher"
        test_id = generate_test_id()
        context.user_data["test_id"] = test_id
        user_id = update.message.from_user.id
        TEST_ID_TO_USER[test_id] = user_id

        await update.message.reply_text(
            "✅ Вы зарегистрированы как учитель.\n\n"
            "📌 Если вы отправляете PDF-файл, убедитесь, что он содержит весь тест.\n"
            "Если у вас изображения — вы сможете добавить несколько.\n\n"
            "📎 Пожалуйста, отправьте файл теста (PDF или изображение)."
        )
        return HANDLE_TEST_UPLOAD
    else:
        await update.message.reply_text("Неверный код. Вы зарегистрированы как ученик.")
        context.user_data["role"] = "student"
        await update.message.reply_text("Пожалуйста, введите код теста:")
        return ConversationHandler.END

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

    keyboard = [["✅ Загрузить ещё", "✅ Перейти к вводу ключа"]]
    await update.message.reply_text(
        f"✅ Файл {file_name} сохранён.\nКод теста: {test_id}\n\n"
        "Хотите загрузить ещё изображение или перейти к вводу ключа?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return WAIT_FOR_NEXT_FILE_OR_KEY

async def wait_for_more_or_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.lower().strip()
    if "загрузить" in text:
        await update.message.reply_text("📎 Пожалуйста, отправьте ещё один файл теста (PDF или изображение).")
        return HANDLE_TEST_UPLOAD
    elif "перейти" in text:
        await update.message.reply_text("✏️ Введите ключ ответов к тесту:")
        return ConversationHandler.END
    else:
        await update.message.reply_text("Пожалуйста, выберите один из вариантов.")
        return WAIT_FOR_NEXT_FILE_OR_KEY

async def save_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("role") != "teacher":
        await update.message.reply_text("❌ Только учитель может сохранять ключи ответов.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❗ Введите команду в формате:\n/key <код_теста> <ключ_ответов>", parse_mode="Markdown")
        return

    test_code = context.args[0]
    answers = "".join(context.args[1:]).strip()

    user_id = TEST_ID_TO_USER.get(test_code)
    if not user_id:
        await update.message.reply_text("❌ Тест с указанным кодом не найден.")
        return

    test_folder = BASE_DIR / str(user_id) / test_code
    if not test_folder.exists():
        await update.message.reply_text("❌ Папка теста не найдена.")
        return

    key_path = test_folder / "answers.key"
    feedback_path = test_folder / "feedback.mode"

    with open(key_path, "w", encoding="utf-8") as f:
        f.write(answers)

    await update.message.reply_text(
        f"✅ Ключ для теста {test_code} успешно сохранён.\n"
        f"Ответы: {answers}\n"
        f"Тест состоит из {len(answers)} ответов на вопросы.\n\n"
        f"✳️ Теперь выберите формат обратной связи для ученика:\n"
        f"1️⃣ Короткий (только итог)\n"
        f"2️⃣ Развернутый (✅ или ❌ по каждому ответу)\n"
        f"3️⃣ Полный (✅/❌ и правильный ответ при ошибке)\n\n"
        f"Введите цифру от 1 до 3."
    )
    context.user_data["awaiting_feedback_choice"] = (test_folder,)

async def feedback_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "awaiting_feedback_choice" not in context.user_data:
        return

    text = update.message.text.strip()
    if text not in {"1", "2", "3"}:
        await update.message.reply_text("❗ Пожалуйста, введите цифру 1, 2 или 3.")
        return

    feedback_mode = {"1": "short", "2": "detailed", "3": "full"}[text]
    test_folder = context.user_data.pop("awaiting_feedback_choice")[0]
    feedback_path = test_folder / "feedback.mode"

    with open(feedback_path, "w", encoding="utf-8") as f:
        f.write(feedback_mode)

    await update.message.reply_text("✅ Формат обратной связи успешно сохранён.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    return await start(update, context)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_ROLE: [MessageHandler(filters.TEXT, select_role)],
            TEACHER_AUTH: [MessageHandler(filters.TEXT, teacher_auth)],
            HANDLE_TEST_UPLOAD: [MessageHandler(filters.Document.ALL | filters.PHOTO, handle_test_upload)],
            WAIT_FOR_NEXT_FILE_OR_KEY: [MessageHandler(filters.TEXT, wait_for_more_or_key)],
        },
        fallbacks=[CommandHandler("reset", reset)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("key", save_key))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_choice))

    app.run_polling()

if __name__ == "__main__":
    main()

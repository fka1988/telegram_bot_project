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
    ConversationHandler,
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TEACHER_CODE = "2308"

SELECT_ROLE, TEACHER_AUTH, HANDLE_TEST_UPLOAD, ASK_FEEDBACK_TYPE, ENTER_TEST_CODE, ENTER_ANSWERS = range(6)

BASE_DIR = Path("tests")
BASE_DIR.mkdir(exist_ok=True)

FEEDBACK_MODES = {
    "Короткий": "short",
    "Развернутый": "detailed",
    "Полный": "full",
}


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
        await update.message.reply_text("✅ Вы зарегистрированы как ученик.\nПожалуйста, введите код теста:")
        return ENTER_TEST_CODE


async def teacher_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == TEACHER_CODE:
        context.user_data["role"] = "teacher"
        test_code = str(random.randint(1000, 9999))
        context.user_data["test_code"] = test_code
        await update.message.reply_text(
            "✅ Вы зарегистрированы как учитель.\n\nПожалуйста, отправьте файл теста (PDF или изображение).\n\nЕсли вы отправляете PDF — убедитесь, что он содержит весь тест в одном файле."
        )
        return HANDLE_TEST_UPLOAD
    else:
        await update.message.reply_text("Неверный код. Вы зарегистрированы как ученик.")
        context.user_data["role"] = "student"
        await update.message.reply_text("✅ Вы зарегистрированы как ученик.\nПожалуйста, введите код теста:")
        return ENTER_TEST_CODE


# Здесь позже будет обработка тестов и ответов
async def enter_test_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    code = update.message.text.strip()
    found = False
    for user_folder in BASE_DIR.iterdir():
        test_folder = user_folder / code
        if test_folder.exists():
            found = True
            context.user_data["test_code"] = code
            context.user_data["test_folder"] = test_folder
            break

    if not found:
        await update.message.reply_text("❌ Тест с таким кодом не найден. Пожалуйста, введите корректный 4-значный код.")
        return ENTER_TEST_CODE

    # Отправка файла теста ученику (PDF или изображение)
    for file in test_folder.iterdir():
        if file.suffix in [".pdf", ".jpg", ".jpeg", ".png"]:
            await update.message.reply_document(document=file.open("rb"))

    await update.message.reply_text("✏️ Введите ваши ответы:")
    return ENTER_ANSWERS


# Остальной код (handle_test_upload, save_key, reset, и main) будет добавлен дальше

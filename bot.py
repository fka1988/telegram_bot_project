import os
import logging
import random
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes,
    filters, ConversationHandler
)

# Логирование
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TEACHER_CODE = "2308"

# Состояния
SELECT_ROLE, TEACHER_AUTH, HANDLE_TEST_UPLOAD, ADD_OR_KEY, ENTER_FEEDBACK_MODE = range(5)

# Путь для хранения тестов
BASE_DIR = Path("tests")
BASE_DIR.mkdir(exist_ok=True)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [["👨‍🏫 Я учитель", "🧑‍🎓 Я ученик"]]
    await update.message.reply_text(
        "Выберите вашу роль:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return SELECT_ROLE

# Выбор роли
async def select_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    if text == "👨‍🏫 Я учитель":
        await update.message.reply_text("Введите код для подтверждения:")
        return TEACHER_AUTH

    elif text == "🧑‍🎓 Я ученик":
        context.user_data["role"] = "student"
        await update.message.reply_text(
            "✅ Вы зарегистрированы как ученик.\nПожалуйста, введите код теста:"
        )
        return ConversationHandler.END

    else:
        await update.message.reply_text("Пожалуйста, выберите одну из ролей с клавиатуры.")
        return SELECT_ROLE

# Аутентификация учителя
async def teacher_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == TEACHER_CODE:
        context.user_data["role"] = "teacher"
        test_id = str(random.randint(1000, 9999))
        context.user_data["test_id"] = test_id
        await update.message.reply_text(
            "✅ Вы зарегистрированы как учитель.\n\n📌 Если вы отправляете PDF-файл, убедитесь, что он содержит весь тест.\nЕсли у вас изображения — вы сможете добавить несколько.\n\n📎 Пожалуйста, отправьте файл теста (PDF или изображение).",
            reply_markup=ReplyKeyboardRemove()
        )
        return HANDLE_TEST_UPLOAD
    else:
        await update.message.reply_text("Неверный код. Вы зарегистрированы как ученик.\nПожалуйста, введите код теста:")
        context.user_data["role"] = "student"
        return ConversationHandler.END

# Обработка загрузки теста
async def handle_test_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    test_id = context.user_data["test_id"]
    test_dir = BASE_DIR / str(user_id) / test_id
    test_dir.mkdir(parents=True, exist_ok=True)

    file = update.message.document or (update.message.photo[-1] if update.message.photo else None)
    if not file:
        await update.message.reply_text("Пожалуйста, отправьте PDF-файл или изображение.")
        return HANDLE_TEST_UPLOAD

    file_obj = await file.get_file()
    file_name = getattr(file, "file_name", f"{file.file_id}.jpg")
    file_path = test_dir / file_name
    await file_obj.download_to_drive(custom_path=str(file_path))

    await update.message.reply_text(
        f"✅ Файл {file_name} сохранён.\nКод теста: {test_id}\n\nХотите загрузить ещё изображение или перейти к вводу ключа?",
        reply_markup=ReplyKeyboardMarkup([["➕ Загрузить ещё", "✅ Перейти к вводу ключа"]], resize_keyboard=True)
    )
    return ADD_OR_KEY

# Добавить ещё или ввести ключ
async def add_or_enter_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()

    if "ещё" in text:
        await update.message.reply_text("Отправьте следующее изображение.")
        return HANDLE_TEST_UPLOAD

    elif "ключ" in text:
        await update.message.reply_text(
            "Введите ключ ответов (например: abcdabcdabcd):",
            reply_markup=ReplyKeyboardRemove()
        )
        return ENTER_FEEDBACK_MODE

    else:
        await update.message.reply_text("Пожалуйста, выберите один из предложенных вариантов.")
        return ADD_OR_KEY

# Ввод ключа и выбор обратной связи
async def enter_feedback_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["answers"] = update.message.text.strip()

    keyboard = [
        ["📊 Короткий (только результат)"],
        ["📋 Развернутый (верно/неверно)"],
        ["📘 Полный (верно/неверно + правильный ответ)"]
    ]
    await update.message.reply_text(
        "Выберите формат обратной связи для ученика:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ConversationHandler.END

# /key — сохранить ключ вручную
async def save_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("role") != "teacher":
        await update.message.reply_text("❌ Только учитель может сохранять ключи.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❗ Формат:\n`/key <код_теста> <ключ_ответов>`", parse_mode="Markdown")
        return

    test_code, answers = context.args[0], "".join(context.args[1:])
    found = False

    for user_folder in BASE_DIR.iterdir():
        test_folder = user_folder / test_code
        if test_folder.exists():
            found = True
            break

    if not found:
        await update.message.reply_text("❌ Тест с указанным кодом не найден.")
        return

    key_path = test_folder / "answers.key"
    with open(key_path, "w", encoding="utf-8") as f:
        f.write(answers)

    count = len(answers)
    await update.message.reply_text(
        f"✅ Ключ для теста {test_code} успешно сохранён.\nОтветы: {answers}\nТест состоит из {count} ответов на вопросы."
    )

# /reset
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    return await start(update, context)

# Запуск
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_role)],
            TEACHER_AUTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, teacher_auth)],
            HANDLE_TEST_UPLOAD: [
                MessageHandler(filters.Document.ALL | filters.PHOTO, handle_test_upload),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_or_enter_key),  # 👈 важно
            ],
            ADD_OR_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_or_enter_key)],
            ENTER_FEEDBACK_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_feedback_mode)],
        },
        fallbacks=[CommandHandler("reset", reset)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("key", save_key))
    app.add_handler(CommandHandler("reset", reset))
    app.run_polling()

if __name__ == "__main__":
    main()

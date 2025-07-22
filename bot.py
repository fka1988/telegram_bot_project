# bot.py

import os
import logging
import random
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
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
SELECT_ROLE, TEACHER_AUTH, HANDLE_TEST_UPLOAD, ADD_OR_KEY, ENTER_FEEDBACK_MODE, STUDENT_ENTER_CODE, STUDENT_ENTER_ANSWERS = range(7)

# Путь для хранения тестов
BASE_DIR = Path("tests")
BASE_DIR.mkdir(exist_ok=True)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
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
        await update.message.reply_text("✅ Вы зарегистрированы как ученик.\nПожалуйста, введите код теста:")
        return STUDENT_ENTER_CODE
    else:
        await update.message.reply_text("Пожалуйста, выберите одну из ролей с клавиатуры.")
        return SELECT_ROLE

# Проверка кода учителя
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
        await update.message.reply_text("Неверный код. Вы зарегистрированы как ученик.")
        context.user_data["role"] = "student"
        return STUDENT_ENTER_CODE

# Загрузка теста
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

# Добавить файл или ввести ключ
async def add_or_enter_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if "ещё" in text:
        await update.message.reply_text("Отправьте следующее изображение.")
        return HANDLE_TEST_UPLOAD
    elif "ключ" in text.lower():
        await update.message.reply_text(
            "Введите ключ ответов (например: abcdabcdabcd):",
            reply_markup=ReplyKeyboardRemove()
        )
        return ENTER_FEEDBACK_MODE
    else:
        await update.message.reply_text("Пожалуйста, выберите один из предложенных вариантов.")
        return ADD_OR_KEY

# Ввод ключа
async def enter_feedback_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answers = update.message.text.strip()
    context.user_data["answers"] = answers

    user_id = update.message.from_user.id
    test_id = context.user_data["test_id"]
    test_dir = BASE_DIR / str(user_id) / test_id
    test_dir.mkdir(parents=True, exist_ok=True)

    with open(test_dir / "answers.key", "w", encoding="utf-8") as f:
        f.write(answers)

    await update.message.reply_text(
        "Выберите формат обратной связи для ученика:",
        reply_markup=ReplyKeyboardMarkup([
            ["📊 Короткий (только результат)"],
            ["📋 Развернутый (верно/неверно)"],
            ["📘 Полный (верно/неверно + правильный ответ)"]
        ], one_time_keyboard=True, resize_keyboard=True)
    )
    return ENTER_FEEDBACK_MODE

# Выбор обратной связи
async def feedback_mode_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    mode = update.message.text.strip()
    user_id = update.message.from_user.id
    test_id = context.user_data["test_id"]
    test_dir = BASE_DIR / str(user_id) / test_id

    if "только результат" in mode:
        mode_value = "short"
    elif "развернутый" in mode.lower():
        mode_value = "detailed"
    else:
        mode_value = "full"

    with open(test_dir / "feedback.mode", "w", encoding="utf-8") as f:
        f.write(mode_value)

    count = len(context.user_data["answers"])
    author_name = update.effective_user.full_name or update.effective_user.username or "Неизвестно"
    now = datetime.now()
    date_str = now.strftime("%d.%m.%Y")
    time_str = now.strftime("%H:%M")

    summary = (
        "✅ Тест добавлен в базу.\n"
        f"👨‍🏫 АВТОР: {author_name}\n"
        f"✍️ КОД ТЕСТА: {test_id}\n"
        f"🔹 ВОПРОСОВ: {count} ta\n"
        f"📆 {date_str} ⏰ {time_str}"
    )

    await update.message.reply_text(
        summary,
        reply_markup=ReplyKeyboardMarkup(
            [["🔁 Добавить ещё тест", "🏠 Вернуться на главную"]],
            resize_keyboard=True, one_time_keyboard=True
        )
    )
    return SELECT_ROLE

# Ученик вводит код
async def student_enter_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    test_code = update.message.text.strip()
    context.user_data["test_code"] = test_code
    await update.message.reply_text("📨 Пожалуйста, отправьте свои ответы (например: abcdabcdabcd):")
    return STUDENT_ENTER_ANSWERS

# Проверка ответов
async def student_enter_answers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    student_answers = update.message.text.strip()
    test_code = context.user_data.get("test_code")
    found = False

    for user_folder in BASE_DIR.iterdir():
        test_folder = user_folder / test_code
        if test_folder.exists():
            found = True
            break

    if not found:
        await update.message.reply_text("❌ Ключ для этого теста не найден. Сообщите учителю.")
        return ConversationHandler.END

    try:
        with open(test_folder / "answers.key", "r", encoding="utf-8") as f:
            correct_answers = f.read().strip()

        with open(test_folder / "feedback.mode", "r", encoding="utf-8") as f:
            mode = f.read().strip()
    except FileNotFoundError:
        await update.message.reply_text("❌ Данные теста неполные. Сообщите учителю.")
        return ConversationHandler.END

    if len(student_answers) != len(correct_answers):
        await update.message.reply_text("❗ Количество ответов не совпадает с ключом.")
        return ConversationHandler.END

    correct_count = sum(sa == ca for sa, ca in zip(student_answers, correct_answers))

    if mode == "short":
        await update.message.reply_text(f"✅ Ваш результат: {correct_count} из {len(correct_answers)}")
    elif mode == "detailed":
        result = [f"{i}) {'✅' if sa == ca else '❌'}" for i, (sa, ca) in enumerate(zip(student_answers, correct_answers), 1)]
        await update.message.reply_text("\n".join(result))
    elif mode == "full":
        result = [f"{i}) {'✅' if sa == ca else f'❌ (правильный: {ca})'}" for i, (sa, ca) in enumerate(zip(student_answers, correct_answers), 1)]
        await update.message.reply_text("\n".join(result))
    else:
        await update.message.reply_text("❗ Неизвестный формат обратной связи.")

    return ConversationHandler.END

# /reset
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    return await start(update, context)

# /mytests
async def mytests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_dir = BASE_DIR / str(user_id)

    if not user_dir.exists():
        await update.message.reply_text("У вас пока нет загруженных тестов.")
        return

    test_dirs = sorted(user_dir.iterdir())
    if not test_dirs:
        await update.message.reply_text("У вас пока нет загруженных тестов.")
        return

    mode_names = {
        "short": "короткий",
        "detailed": "развернутый",
        "full": "полный"
    }

    messages = []
    for test_dir in test_dirs:
        test_id = test_dir.name
        key_path = test_dir / "answers.key"
        mode_path = test_dir / "feedback.mode"

        if not key_path.exists():
            continue

        try:
            with open(key_path, "r", encoding="utf-8") as f:
                answers = f.read().strip()
            count = len(answers)
        except:
            count = "?"

        try:
            with open(mode_path, "r", encoding="utf-8") as f:
                mode_code = f.read().strip()
            mode = mode_names.get(mode_code, "не указан")
        except:
            mode = "не указан"

        try:
            creation_time = datetime.fromtimestamp(test_dir.stat().st_ctime)
            date_str = creation_time.strftime("%d.%m.%Y")
        except:
            date_str = "неизв."

        messages.append(f"📘 Тест {test_id}: {count} вопр. • 📆 {date_str} • 🔧 Обратная связь: {mode}")

    await update.message.reply_text("📚 Ваши тесты:\n\n" + "\n".join(messages))

# main
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_role)],
            TEACHER_AUTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, teacher_auth)],
            HANDLE_TEST_UPLOAD: [MessageHandler(filters.Document.ALL | filters.PHOTO, handle_test_upload)],
            ADD_OR_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_or_enter_key)],
            ENTER_FEEDBACK_MODE: [
                MessageHandler(filters.Regex("^(📊|📋|📘)"), feedback_mode_selection),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_feedback_mode),
            ],
            STUDENT_ENTER_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, student_enter_code)],
            STUDENT_ENTER_ANSWERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, student_enter_answers)],
        },
        fallbacks=[CommandHandler("reset", reset)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("mytests", mytests))
    app.run_polling()

if __name__ == "__main__":
    main()

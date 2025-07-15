import os
import logging
import random
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters
)

# Настройка логгирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Загрузка токена
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TEACHER_CODE = "2308"

# Состояния
SELECT_ROLE, TEACHER_AUTH, HANDLE_TEST_UPLOAD, ASK_FEEDBACK_TYPE, ENTER_TEST_CODE = range(5)

# Папка с тестами
BASE_DIR = Path("tests")
BASE_DIR.mkdir(exist_ok=True)

# Хранилище для активной сессии загрузки
pending_uploads = {}

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [["👨‍🏫 Я учитель", "🧑‍🎓 Я ученик"]]
    await update.message.reply_text(
        "Выберите вашу роль:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return SELECT_ROLE

# Выбор роли
async def select_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    role = update.message.text
    if role == "👨‍🏫 Я учитель":
        await update.message.reply_text("Введите код для подтверждения:")
        return TEACHER_AUTH
    else:
        context.user_data["role"] = "student"
        await update.message.reply_text("✅ Вы зарегистрированы как ученик.")
        await update.message.reply_text("Пожалуйста, введите код теста:")
        return ENTER_TEST_CODE

# Проверка кода учителя
async def teacher_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == TEACHER_CODE:
        context.user_data["role"] = "teacher"

        # Генерация уникального 4-значного кода теста
        existing_codes = {
            folder.name
            for user_folder in BASE_DIR.iterdir()
            if user_folder.is_dir()
            for folder in user_folder.iterdir()
        }
        while True:
            test_id = str(random.randint(1000, 9999))
            if test_id not in existing_codes:
                break

        context.user_data["test_id"] = test_id
        context.user_data["test_files"] = []

        await update.message.reply_text(
            "✅ Вы зарегистрированы как учитель.\n\n"
            "📌 Если вы отправляете PDF-файл, убедитесь, что он содержит весь тест.\n"
            "Если у вас изображения — вы сможете добавить несколько.\n\n"
            "📎 Пожалуйста, отправьте файл теста (PDF или изображение)."
        )
        return HANDLE_TEST_UPLOAD
    else:
        context.user_data["role"] = "student"
        await update.message.reply_text("Неверный код. Вы зарегистрированы как ученик.")
        await update.message.reply_text("Пожалуйста, введите код теста:")
        return ENTER_TEST_CODE

# Загрузка файлов теста
async def handle_test_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    test_id = context.user_data["test_id"]
    test_dir = BASE_DIR / str(user_id) / test_id
    test_dir.mkdir(parents=True, exist_ok=True)

    text = update.message.text

    # 👉 Проверяем, выбрал ли пользователь переход к ключу
    if text == "✅ Перейти к вводу ключа":
        # Предлагаем выбрать формат обратной связи
        keyboard = [["📊 Краткий", "📋 Развёрнутый", "📚 Полный"]]
        await update.message.reply_text(
            "Выберите тип обратной связи, которую будет получать ученик после прохождения теста:",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return ASK_FEEDBACK_TYPE

    # 👉 Если нажал "➕ Добавить ещё" — просто просим отправить файл
    if text == "➕ Добавить ещё":
        await update.message.reply_text("📎 Пожалуйста, отправьте ещё один файл (изображение или PDF).")
        return HANDLE_TEST_UPLOAD

    # Загрузка файла
    if update.message.document:
        file = update.message.document
    elif update.message.photo:
        file = update.message.photo[-1]
    else:
        await update.message.reply_text("Пожалуйста, отправьте PDF или изображение.")
        return HANDLE_TEST_UPLOAD

    file_obj = await file.get_file()
    file_name = file.file_name if hasattr(file, "file_name") and file.file_name else f"{file.file_unique_id}.jpg"
    file_path = test_dir / file_name
    await file_obj.download_to_drive(str(file_path))
    context.user_data["test_files"].append(file_name)

    keyboard = [["➕ Добавить ещё", "✅ Перейти к вводу ключа"]]
    await update.message.reply_text(
        f"✅ Файл *{file_name}* сохранён.\n"
        f"Код теста: `{test_id}`\n\n"
        "Хотите загрузить ещё изображение или перейти к вводу ключа?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return HANDLE_TEST_UPLOAD


# Сохранение ключей
async def save_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("role") != "teacher":
        await update.message.reply_text("❌ Только учитель может сохранять ключи.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❗ Используйте:\n`/key <код_теста> <ключ_ответов>`", parse_mode="Markdown")
        return

    test_code = context.args[0]
    answers = "".join(context.args[1:])

    found = False
    for user_folder in BASE_DIR.iterdir():
        test_folder = user_folder / test_code
        if test_folder.exists():
            found = True
            break

    if not found:
        await update.message.reply_text("❌ Тест с таким кодом не найден.")
        return

    with open(test_folder / "answers.key", "w", encoding="utf-8") as f:
        f.write(answers)

    feedback_path = test_folder / "feedback.mode"
    feedback_mode = context.user_data.get("feedback_mode", "short")
    with open(feedback_path, "w", encoding="utf-8") as f:
        f.write(feedback_mode)

    await update.message.reply_text(
        f"✅ Ключ для теста {test_code} успешно сохранён.\n"
        f"Ответы: `{answers}`\n"
        f"Тест состоит из {len(answers)} ответов на вопросы.",
        parse_mode="Markdown"
    )

# Ввод кода теста учеником
async def enter_test_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    test_code = update.message.text.strip()
    context.user_data["role"] = "student"
    context.user_data["entered_code"] = test_code

    found = False
    for user_folder in BASE_DIR.iterdir():
        test_folder = user_folder / test_code
        if test_folder.exists():
            found = True
            break

    if not found:
        await update.message.reply_text("❌ Тест с таким кодом не найден.")
        return ENTER_TEST_CODE

    await update.message.reply_text(
        f"Тест с кодом `{test_code}` найден. Введите ответы в формате:\n"
        "`/answer <код> <ответы>`", parse_mode="Markdown"
    )
    return ConversationHandler.END

# Команда reset
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    return await start(update, context)

# Заглушка под /answer (если хочешь — могу дописать сразу)
async def answer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Функция проверки ответов скоро будет добавлена.")

# Главная функция
def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_role)],
            TEACHER_AUTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, teacher_auth)],
            HANDLE_TEST_UPLOAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_test_upload),
                                 MessageHandler(filters.Document.ALL | filters.PHOTO, handle_test_upload)],
            ENTER_TEST_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_test_code)],
        },
        fallbacks=[CommandHandler("reset", reset)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("key", save_key))
    application.add_handler(CommandHandler("answer", answer_command))
    application.run_polling()

if __name__ == "__main__":
    main()

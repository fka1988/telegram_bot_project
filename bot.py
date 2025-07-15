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
    ConversationHandler,
    filters,
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TEACHER_CODE = "2308"

# Состояния
SELECT_ROLE, TEACHER_AUTH, HANDLE_TEST_UPLOAD, CHOOSE_NEXT_ACTION, ASK_FEEDBACK_TYPE = range(5)

# Каталог хранения тестов
BASE_DIR = Path("tests")
BASE_DIR.mkdir(exist_ok=True)

# Генерация 4-значного кода
def generate_test_code():
    return str(random.randint(1000, 9999))

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    keyboard = [["👨‍🏫 Я учитель", "🧑‍🎓 Я ученик"]]
    await update.message.reply_text(
        "Выберите вашу роль:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return SELECT_ROLE

# Роль
async def select_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    role = update.message.text
    if role == "👨‍🏫 Я учитель":
        await update.message.reply_text("Введите код для подтверждения:")
        return TEACHER_AUTH
    else:
        context.user_data["role"] = "student"
        await update.message.reply_text(
            "✅ Вы зарегистрированы как ученик.\nПожалуйста, введите код теста:"
        )
        return ConversationHandler.END

# Авторизация учителя
async def teacher_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == TEACHER_CODE:
        context.user_data["role"] = "teacher"
        context.user_data["test_code"] = generate_test_code()
        await update.message.reply_text(
            "✅ Вы зарегистрированы как учитель.\n\n"
            "📌 Если вы отправляете PDF-файл, убедитесь, что он содержит весь тест.\n"
            "Если у вас изображения — вы сможете добавить несколько.\n\n"
            "📎 Пожалуйста, отправьте файл теста (PDF или изображение)."
        )
        return HANDLE_TEST_UPLOAD
    else:
        context.user_data["role"] = "student"
        await update.message.reply_text("Неверный код. Вы зарегистрированы как ученик.\nВведите код теста:")
        return ConversationHandler.END

# Обработка загрузки
async def handle_test_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    test_code = context.user_data.get("test_code", generate_test_code())
    context.user_data["test_code"] = test_code
    test_dir = BASE_DIR / str(user_id) / test_code
    test_dir.mkdir(parents=True, exist_ok=True)

    file = update.message.document or update.message.photo[-1]
    file_obj = await file.get_file()
    file_name = file.file_name if hasattr(file, "file_name") and file.file_name else f"{file.file_id}.jpg"
    file_path = test_dir / file_name
    await file_obj.download_to_drive(custom_path=str(file_path))

    await update.message.reply_text(
        f"✅ Файл {file_name} сохранён.\nКод теста: {test_code}\n\n"
        "Хотите загрузить ещё изображение или перейти к вводу ключа?",
        reply_markup=ReplyKeyboardMarkup(
            [["➕ Добавить ещё", "✅ Перейти к вводу ключа"]],
            one_time_keyboard=True,
            resize_keyboard=True,
        ),
    )
    return CHOOSE_NEXT_ACTION

# Обработка выбора после загрузки
async def handle_next_action_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    choice = update.message.text
    if choice == "➕ Добавить ещё":
        await update.message.reply_text("📎 Отправьте ещё изображение.")
        return HANDLE_TEST_UPLOAD
    elif choice == "✅ Перейти к вводу ключа":
        await update.message.reply_text(
            "✏️ Пожалуйста, отправьте команду вида:\n"
            "`/key <код_теста> <ответы>`\n"
            f"Пример: `/key {context.user_data['test_code']} abcdabcdabcd`",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text("Выберите действие с клавиатуры.")
        return CHOOSE_NEXT_ACTION

# Сохранение ключа
async def save_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("role") != "teacher":
        await update.message.reply_text("❌ Только учитель может сохранять ключи ответов.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❗ Введите команду в формате:\n`/key <код_теста> <ключ_ответов>`", parse_mode="Markdown")
        return

    test_code, *answers_list = context.args
    answers = "".join(answers_list)
    answer_count = len(answers)

    # Ищем путь к тесту
    test_folder = None
    for user_folder in BASE_DIR.iterdir():
        possible = user_folder / test_code
        if possible.exists():
            test_folder = possible
            break

    if not test_folder:
        await update.message.reply_text("❌ Тест с указанным кодом не найден.")
        return

    (test_folder / "answers.key").write_text(answers, encoding="utf-8")

    # Переход к выбору формата обратной связи
    context.user_data["current_test_path"] = str(test_folder)
    context.user_data["key_length"] = answer_count

    await update.message.reply_text(
        f"✅ Ключ для теста {test_code} успешно сохранён.\n"
        f"Ответы: {answers}\n"
        f"📝 Тест состоит из {answer_count} ответов на вопросы.\n\n"
        "Выберите формат обратной связи для ученика:",
        reply_markup=ReplyKeyboardMarkup(
            [["📊 Короткий", "📋 Развернутый", "📘 Полный"]],
            one_time_keyboard=True,
            resize_keyboard=True,
        )
    )
    return ASK_FEEDBACK_TYPE

# Сохраняем выбор обратной связи
async def set_feedback_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    mode_map = {
        "📊 Короткий": "short",
        "📋 Развернутый": "detailed",
        "📘 Полный": "full"
    }
    choice = update.message.text
    mode = mode_map.get(choice)

    if not mode:
        await update.message.reply_text("Выберите вариант с клавиатуры.")
        return ASK_FEEDBACK_TYPE

    test_path = Path(context.user_data["current_test_path"])
    (test_path / "feedback.mode").write_text(mode, encoding="utf-8")

    await update.message.reply_text("✅ Формат обратной связи сохранён.")
    return ConversationHandler.END

# /reset
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    return await start(update, context)

# Основная функция
def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_role)],
            TEACHER_AUTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, teacher_auth)],
            HANDLE_TEST_UPLOAD: [MessageHandler(filters.Document.ALL | filters.PHOTO, handle_test_upload)],
            CHOOSE_NEXT_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_next_action_choice)],
            ASK_FEEDBACK_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_feedback_type)],
        },
        fallbacks=[CommandHandler("reset", reset)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("key", save_key))

    application.run_polling()

if __name__ == "__main__":
    main()

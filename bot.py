import os
import logging
import random
from pathlib import Path
from dotenv import load_dotenv
from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ConversationHandler, ContextTypes, CallbackQueryHandler
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TEACHER_CODE = os.getenv("TEACHER_CODE", "2308")

BASE_DIR = Path("tests")
BASE_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHOOSING_ROLE, WAITING_FOR_CODE, UPLOADING_TEST, ADDING_MORE_FILES, ENTERING_KEY, CHOOSING_FEEDBACK = range(6)

FEEDBACK_OPTIONS = {
    "short": "Краткий (только итоговый балл)",
    "detailed": "Развёрнутый (верно/неверно)",
    "full": "Полный (с правильными ответами)"
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    keyboard = [["Я учитель", "Я ученик"]]
    await update.message.reply_text(
        "Добро пожаловать! Выберите свою роль:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return CHOOSING_ROLE


async def choose_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = update.message.text
    if role == "Я учитель":
        await update.message.reply_text("Пожалуйста, введите код учителя:", reply_markup=ReplyKeyboardRemove())
        return WAITING_FOR_CODE
    else:
        context.user_data["role"] = "student"
        await update.message.reply_text("Введите код теста:")
        return handle_student_test_code_prompt(update, context)


async def handle_teacher_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code == TEACHER_CODE:
        context.user_data["role"] = "teacher"
        context.user_data["tests"] = []
        await update.message.reply_text("Код верный. Загрузите файл теста (PDF или изображение).")
        return UPLOADING_TEST
    else:
        context.user_data["role"] = "student"
        await update.message.reply_text("Код неверный. Вы назначены как ученик. Введите код теста:")
        return handle_student_test_code_prompt(update, context)


async def handle_student_test_code_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return ConversationHandler.END


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = context.user_data.get("role")
    if role != "teacher":
        return

    file = update.message.document or update.message.photo[-1]
    file_id = file.file_id
    test_code = context.user_data.get("test_code")

    if not test_code:
        test_code = str(random.randint(1000, 9999))
        context.user_data["test_code"] = test_code
        test_dir = BASE_DIR / test_code
        test_dir.mkdir(exist_ok=True)
        context.user_data["test_dir"] = test_dir

    test_dir = context.user_data["test_dir"]
    number = len(list(test_dir.glob("*"))) + 1
    ext = ".pdf" if update.message.document else ".jpg"
    filename = test_dir / f"{number}{ext}"
    await file.get_file().download_to_drive(str(filename))

    if ext == ".pdf":
        await update.message.reply_text("PDF-файл загружен. Введите ключ ответов (например: ABBCD...):")
        return ENTERING_KEY

    keyboard = [["Добавить ещё", "Ввести ключ"]]
    await update.message.reply_text("Файл загружен. Хотите добавить ещё файл или перейти к вводу ключа?",
                                    reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return ADDING_MORE_FILES


async def adding_more_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    if choice == "Добавить ещё":
        await update.message.reply_text("Загрузите следующий файл.")
        return UPLOADING_TEST
    else:
        await update.message.reply_text("Введите ключ ответов (например: ABBCD...):", reply_markup=ReplyKeyboardRemove())
        return ENTERING_KEY


async def entering_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = update.message.text.strip().upper()
    if not key.isalpha():
        await update.message.reply_text("Ключ должен содержать только буквы. Попробуйте снова.")
        return ENTERING_KEY

    test_dir = context.user_data["test_dir"]
    with open(test_dir / "key.txt", "w") as f:
        f.write(key)

    context.user_data["key_length"] = len(key)
    keyboard = [
        [InlineKeyboardButton(v, callback_data=k)]
        for k, v in FEEDBACK_OPTIONS.items()
    ]
    await update.message.reply_text(
        f"Ключ сохранён. Тест состоит из {len(key)} вопросов.\nВыберите формат обратной связи:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_FEEDBACK


async def save_feedback_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mode = query.data
    test_dir = context.user_data["test_dir"]
    with open(test_dir / "feedback.mode", "w") as f:
        f.write(mode)

    await query.edit_message_text(
        f"Тест успешно создан. Код теста: {context.user_data['test_code']}"
    )
    return ConversationHandler.END


async def my_tests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("role") != "teacher":
        await update.message.reply_text("Команда доступна только учителям.")
        return

    lines = []
    for folder in BASE_DIR.iterdir():
        key_file = folder / "key.txt"
        if key_file.exists():
            with open(key_file) as f:
                length = len(f.read().strip())
            lines.append(f"Код: {folder.name} — {length} вопрос(ов)")

    if lines:
        await update.message.reply_text("\n".join(lines))
    else:
        await update.message.reply_text("У вас нет загруженных тестов.")


async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        parts = update.message.text.strip().split()
        if len(parts) != 3:
            await update.message.reply_text("Формат: /answer <код_теста> <ваши_ответы>")
            return

        _, test_code, user_answers = parts
        test_dir = BASE_DIR / test_code

        if not test_dir.exists():
            await update.message.reply_text("Тест не найден.")
            return

        with open(test_dir / "key.txt") as f:
            correct = f.read().strip().upper()

        user_answers = user_answers.upper()
        if len(user_answers) != len(correct):
            await update.message.reply_text(f"Количество ответов не совпадает с ключом. Ожидается {len(correct)} ответов.")
            return

        feedback_mode = "short"
        feedback_file = test_dir / "feedback.mode"
        if feedback_file.exists():
            feedback_mode = feedback_file.read_text().strip()

        result = []
        score = 0
        for i, (u, c) in enumerate(zip(user_answers, correct), 1):
            if u == c:
                score += 1
                if feedback_mode != "short":
                    result.append(f"{i}) ✅ Верно")
            else:
                if feedback_mode == "detailed":
                    result.append(f"{i}) ❌ Неверно")
                elif feedback_mode == "full":
                    result.append(f"{i}) ❌ Неверно. Правильный ответ: {c}")

        result.insert(0, f"✅ Ваш результат: {score} из {len(correct)}")
        await update.message.reply_text("\n".join(result))
    except Exception as e:
        logger.error(f"Ошибка в /answer: {e}")
        await update.message.reply_text("Произошла ошибка при проверке ответа.")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    return await start(update, context)


if __name__ == "__main__":
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_ROLE: [MessageHandler(filters.TEXT, choose_role)],
            WAITING_FOR_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_teacher_code)],
            UPLOADING_TEST: [MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file)],
            ADDING_MORE_FILES: [MessageHandler(filters.TEXT, adding_more_files)],
            ENTERING_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, entering_key)],
            CHOOSING_FEEDBACK: [CallbackQueryHandler(save_feedback_mode)]
        },
        fallbacks=[CommandHandler("reset", reset)],
        allow_reentry=True
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("mytests", my_tests))
    application.add_handler(CommandHandler("answer", answer))
    application.add_handler(CommandHandler("reset", reset))

    application.run_polling()

import os
import logging
from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ConversationHandler,
    filters, ContextTypes
)
import random

# Включаем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TEACHER_CODE = "2308"
CHOOSING_ROLE, VERIFY_CODE, WAIT_FOR_FILE, MORE_IMAGES, ENTER_ANSWER_KEY, SELECT_FEEDBACK_MODE, WAIT_FOR_TEST_CODE, WAIT_FOR_ANSWERS = range(8)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/start от {update.effective_user.username}")
    context.user_data.clear()
    keyboard = [["👨‍🏫 Я учитель", "🧑‍🎓 Я ученик"]]
    await update.message.reply_text("Выберите вашу роль:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return CHOOSING_ROLE

async def choose_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = update.message.text
    context.user_data["role"] = "teacher" if "учитель" in role else "student"
    logger.info(f"Роль выбрана: {context.user_data['role']}")

    if context.user_data["role"] == "teacher":
        await update.message.reply_text("Введите код для подтверждения:", reply_markup=ReplyKeyboardRemove())
        return VERIFY_CODE
    else:
        await update.message.reply_text("✅ Вы зарегистрированы как ученик.\nПожалуйста, введите код теста:", reply_markup=ReplyKeyboardRemove())
        return WAIT_FOR_TEST_CODE

async def verify_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code == TEACHER_CODE:
        await update.message.reply_text(
            "✅ Вы зарегистрированы как учитель.\n\n📌 Если вы отправляете PDF-файл, убедитесь, что он содержит весь тест.\n"
            "Если у вас изображения — вы сможете добавить несколько.\n\n📎 Пожалуйста, отправьте файл теста (PDF или изображение)."
        )
        return WAIT_FOR_FILE
    else:
        context.user_data["role"] = "student"
        await update.message.reply_text("Неверный код. Вы зарегистрированы как ученик.\nВведите код теста:")
        return WAIT_FOR_TEST_CODE

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Вызван handle_file")
    message = update.message

    if message.document:
        file = message.document
        filename = file.file_name or f"{file.file_id}.pdf"
    elif message.photo:
        file = message.photo[-1]
        filename = f"{file.file_id}.jpg"
    else:
        await message.reply_text("❌ Файл не распознан.")
        return WAIT_FOR_FILE

    test_id = str(random.randint(1000, 9999))
    context.user_data["test_id"] = test_id
    os.makedirs(test_id, exist_ok=True)

    file_path = os.path.join(test_id, filename)
    await file.get_file().download_to_drive(file_path)
    logger.info(f"Файл сохранён: {file_path}")

    # Если это PDF, сразу переходим к вводу ключа
    if filename.lower().endswith(".pdf"):
        await message.reply_text(f"✅ Файл {filename} загружен.\nТеперь введите ключ ответов (например: abcdabcd):")
        return ENTER_ANSWER_KEY
    else:
        await message.reply_text(f"✅ Изображение загружено.\nХотите добавить ещё или перейти к вводу ключа?",
                                 reply_markup=ReplyKeyboardMarkup([["➕ Добавить ещё", "✅ Перейти к вводу ключа"]], one_time_keyboard=True))
        return MORE_IMAGES

async def more_images_or_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "добавить" in update.message.text.lower():
        await update.message.reply_text("Пожалуйста, отправьте ещё один файл.")
        return WAIT_FOR_FILE
    else:
        await update.message.reply_text("Введите ключ ответов (например: abcdabcd):", reply_markup=ReplyKeyboardRemove())
        return ENTER_ANSWER_KEY

async def save_answer_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = update.message.text.strip().lower()
    test_id = context.user_data["test_id"]
    with open(os.path.join(test_id, "key.txt"), "w") as f:
        f.write(key)
    context.user_data["key"] = key

    keyboard = [["📊 Короткий (только результат)", "📋 Развёрнутый (верно/неверно)"],
                ["📘 Полный (с правильными ответами)"]]
    await update.message.reply_text("Выберите формат обратной связи для ученика:",
                                    reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return SELECT_FEEDBACK_MODE

async def save_feedback_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = update.message.text
    test_id = context.user_data["test_id"]
    selected_mode = (
        "short" if "короткий" in mode.lower()
        else "detailed" if "развёрнут" in mode.lower()
        else "full"
    )
    with open(os.path.join(test_id, "feedback.mode"), "w") as f:
        f.write(selected_mode)

    await update.message.reply_text(f"✅ Ключ сохранён. Тест состоит из {len(context.user_data['key'])} вопросов.")
    return ConversationHandler.END

async def receive_test_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    test_id = update.message.text.strip()
    context.user_data["test_id"] = test_id
    if not os.path.exists(os.path.join(test_id, "key.txt")):
        await update.message.reply_text("❌ Ключ для этого теста не найден. Сообщите учителю.")
        return ConversationHandler.END

    await update.message.reply_text("📨 Пожалуйста, отправьте свои ответы (например: abcdabcdabcd):")
    return WAIT_FOR_ANSWERS

async def receive_answers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answers = update.message.text.strip().lower()
    test_id = context.user_data["test_id"]
    key_path = os.path.join(test_id, "key.txt")
    mode_path = os.path.join(test_id, "feedback.mode")

    if not os.path.exists(key_path):
        await update.message.reply_text("❌ Ключ для этого теста не найден.")
        return ConversationHandler.END

    with open(key_path) as f:
        key = f.read().strip().lower()

    if len(answers) != len(key):
        await update.message.reply_text("❗ Количество ответов не совпадает с ключом.")
        return ConversationHandler.END

    score = sum(1 for a, k in zip(answers, key) if a == k)
    mode = "short"
    if os.path.exists(mode_path):
        with open(mode_path) as f:
            mode = f.read().strip()

    if mode == "short":
        text = f"✅ Ваш результат: {score} из {len(key)}"
    elif mode == "detailed":
        text = "\n".join([f"{i + 1}) {'✅' if a == k else '❌'}" for i, (a, k) in enumerate(zip(answers, key))])
    else:
        text = "\n".join([f"{i + 1}) {'✅' if a == k else f'❌ Правильный ответ: {k}'}" for i, (a, k) in enumerate(zip(answers, key))])

    await update.message.reply_text(text)
    return ConversationHandler.END

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    return await start(update, context)

def main():
    import dotenv
    dotenv.load_dotenv()
    token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_ROLE: [MessageHandler(filters.TEXT, choose_role)],
            VERIFY_CODE: [MessageHandler(filters.TEXT, verify_code)],
            # Временно включаем все сообщения для отладки:
            WAIT_FOR_FILE: [MessageHandler(filters.ALL, handle_file)],
            MORE_IMAGES: [MessageHandler(filters.TEXT, more_images_or_key)],
            ENTER_ANSWER_KEY: [MessageHandler(filters.TEXT, save_answer_key)],
            SELECT_FEEDBACK_MODE: [MessageHandler(filters.TEXT, save_feedback_mode)],
            WAIT_FOR_TEST_CODE: [MessageHandler(filters.TEXT, receive_test_code)],
            WAIT_FOR_ANSWERS: [MessageHandler(filters.TEXT, receive_answers)],
        },
        fallbacks=[CommandHandler("reset", reset)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()

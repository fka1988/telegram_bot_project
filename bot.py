import os
import logging
import random
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TEACHER_CODE = "2308"

SELECT_ROLE, TEACHER_AUTH, HANDLE_TEST_UPLOAD, ADD_MORE_IMAGES, ENTER_TEST_CODE, ENTER_ANSWERS = range(6)

BASE_DIR = Path("tests")
BASE_DIR.mkdir(exist_ok=True)


def generate_test_code():
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
        await update.message.reply_text("Введите код теста, который вам дал учитель:")
        return ENTER_TEST_CODE


async def teacher_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == TEACHER_CODE:
        context.user_data["role"] = "teacher"
        test_id = generate_test_code()
        context.user_data["test_id"] = test_id
        await update.message.reply_text(
            f"✅ Вы зарегистрированы как учитель.\n\nПожалуйста, отправьте файл теста (PDF или изображение).\n\nЕсли вы отправляете PDF — загрузите весь тест одним файлом."
        )
        return HANDLE_TEST_UPLOAD
    else:
        await update.message.reply_text("Неверный код. Вы зарегистрированы как ученик.")
        context.user_data["role"] = "student"
        return ENTER_TEST_CODE


async def handle_test_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    test_id = context.user_data["test_id"]
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

    await update.message.reply_text(
        f"✅ Файл сохранён как *{file_name}*.\nКод теста: `{test_id}`",
        parse_mode="Markdown"
    )

    keyboard = [["➕ Добавить ещё изображение", "📝 Ввести ключ ответов"]]
    await update.message.reply_text(
        "Хотите ли вы добавить ещё изображение или перейти к вводу ключа?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ADD_MORE_IMAGES


async def ask_more_or_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    choice = update.message.text
    if "добавить" in choice.lower():
        await update.message.reply_text("Отправьте следующее изображение.")
        return HANDLE_TEST_UPLOAD
    else:
        await update.message.reply_text("Введите ключ ответов в формате:\n`/key <код_теста> <ключ_ответов>`", parse_mode="Markdown")
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
        f"✅ Ключ для теста *{test_code}* успешно сохранён.\nОтветы: `{answers}`",
        parse_mode="Markdown"
    )


async def handle_student_test_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    code = update.message.text.strip()
    found = False
    for user_folder in BASE_DIR.iterdir():
        test_folder = user_folder / code
        if test_folder.exists():
            found = True
            context.user_data["test_folder"] = str(test_folder)
            context.user_data["test_code"] = code
            for file_path in test_folder.iterdir():
                if file_path.name.endswith(".key"):
                    continue
                await update.message.reply_document(document=open(file_path, "rb"))
            await update.message.reply_text("📥 Введите ваши ответы (например: abcdabcdabcd):")
            return ENTER_ANSWERS
    if not found:
        await update.message.reply_text("❌ Тест с таким кодом не найден. Попробуйте снова:")
        return ENTER_TEST_CODE


async def handle_student_answers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answers = update.message.text.strip()
    test_folder = Path(context.user_data["test_folder"])
    key_file = test_folder / "answers.key"

    if not key_file.exists():
        await update.message.reply_text("❗ Ключ к этому тесту ещё не добавлен учителем.")
        return ConversationHandler.END

    with open(key_file, "r", encoding="utf-8") as f:
        correct_answers = f.read().strip()

    score = sum(a == b for a, b in zip(answers, correct_answers))
    total = len(correct_answers)
    await update.message.reply_text(f"✅ Ваш результат: {score} из {total}")
    return ConversationHandler.END


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    return await start(update, context)


def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_ROLE: [MessageHandler(filters.TEXT, select_role)],
            TEACHER_AUTH: [MessageHandler(filters.TEXT, teacher_auth)],
            HANDLE_TEST_UPLOAD: [MessageHandler(filters.Document.ALL | filters.PHOTO, handle_test_upload)],
            ADD_MORE_IMAGES: [MessageHandler(filters.TEXT, ask_more_or_key)],
            ENTER_TEST_CODE: [MessageHandler(filters.TEXT, handle_student_test_code)],
            ENTER_ANSWERS: [MessageHandler(filters.TEXT, handle_student_answers)],
        },
        fallbacks=[CommandHandler("reset", reset)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("key", save_key))

    application.run_polling()


if __name__ == "__main__":
    main()

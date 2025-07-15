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

# Настройка логирования
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Загрузка токена
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TEACHER_CODE = "2308"

# Состояния диалога
SELECT_ROLE, TEACHER_AUTH, HANDLE_TEST_UPLOAD, AWAITING_MORE_FILES = range(4)

# Каталог для хранения тестов
BASE_DIR = Path("tests")
BASE_DIR.mkdir(exist_ok=True)

# Генерация уникального 4-значного кода
def generate_test_code():
    while True:
        code = str(random.randint(1000, 9999))
        if not any((user_dir / code).exists() for user_dir in BASE_DIR.iterdir()):
            return code

# Команда /start
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
        return ConversationHandler.END

# Подтверждение учителя
async def teacher_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == TEACHER_CODE:
        context.user_data["role"] = "teacher"
        context.user_data["test_code"] = generate_test_code()
        await update.message.reply_text(
            "✅ Вы зарегистрированы как учитель.\n\nПожалуйста, отправьте файл теста (PDF или изображение).\n\nЕсли вы отправляете PDF — добавьте все задания в один файл.\nЕсли изображения — вы сможете загрузить их по одному."
        )
        return HANDLE_TEST_UPLOAD
    else:
        context.user_data["role"] = "student"
        await update.message.reply_text("Неверный код. Вы зарегистрированы как ученик.")
        return ConversationHandler.END

# Обработка загрузки теста
async def handle_test_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    test_code = context.user_data["test_code"]
    test_dir = BASE_DIR / str(user_id) / test_code
    test_dir.mkdir(parents=True, exist_ok=True)

    if update.message.document:
        file = update.message.document
        file_obj = await file.get_file()
        file_name = file.file_name or f"{file.file_id}.pdf"
        file_path = test_dir / file_name
        await file_obj.download_to_drive(custom_path=str(file_path))

        await update.message.reply_text(
            f"✅ Тест сохранён как *{file_name}*.\nКод теста: `{test_code}`\n\nТеперь введите ключ с ответами командой:\n`/key {test_code} <ответы>`",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    elif update.message.photo:
        file = update.message.photo[-1]
        file_obj = await file.get_file()
        file_path = test_dir / f"{file.file_unique_id}.jpg"
        await file_obj.download_to_drive(custom_path=str(file_path))

        keyboard = [["➕ Добавить ещё", "➡️ Перейти к ключу"]]
        await update.message.reply_text(
            f"✅ Изображение добавлено.\nКод теста: `{test_code}`\n\nХотите загрузить ещё или перейти к ключу?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return AWAITING_MORE_FILES

    else:
        await update.message.reply_text("Пожалуйста, отправьте PDF-файл или изображение.")
        return HANDLE_TEST_UPLOAD

# Ожидание дополнительных изображений или переход к ключу
async def awaiting_more_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if text == "➕ Добавить ещё":
        await update.message.reply_text("Пожалуйста, отправьте следующее изображение.")
        return HANDLE_TEST_UPLOAD
    else:
        test_code = context.user_data["test_code"]
        await update.message.reply_text(
            f"Введите ключ к тесту командой:\n`/key {test_code} <ответы>`",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

# Сохранение ключа
async def save_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("role") != "teacher":
        await update.message.reply_text("❌ Только учитель может сохранять ключи ответов.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❗ Введите команду в формате:\n/key <код_теста> <ключ_ответов>", parse_mode="Markdown")
        return

    test_code = context.args[0]
    answers = "".join(context.args[1:])
    found = False

    for user_dir in BASE_DIR.iterdir():
        test_folder = user_dir / test_code
        if test_folder.exists():
            key_path = test_folder / "answers.key"
            with open(key_path, "w", encoding="utf-8") as f:
                f.write(answers)
            await update.message.reply_text(
                f"✅ Ключ для теста {test_code} успешно сохранён.\nОтветы: `{answers}`\nТест состоит из {len(answers)} ответов на вопросы.",
                parse_mode="Markdown"
            )
            found = True
            break

    if not found:
        await update.message.reply_text("❌ Тест с указанным кодом не найден. Убедитесь, что вы указали правильный код.")

# Команда /answer
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("❗ Используйте формат: `/answer <код_теста> <ваши_ответы>`", parse_mode="Markdown")
        return

    test_code = context.args[0]
    student_answers = "".join(context.args[1:])
    found = False

    for user_dir in BASE_DIR.iterdir():
        test_folder = user_dir / test_code
        key_path = test_folder / "answers.key"
        if test_folder.exists() and key_path.exists():
            with open(key_path, encoding="utf-8") as f:
                correct_answers = f.read().strip()

            if len(student_answers) != len(correct_answers):
                await update.message.reply_text(
                    f"❗ Кол-во ваших ответов ({len(student_answers)}) не совпадает с количеством вопросов ({len(correct_answers)})."
                )
                return

            result = []
            correct_count = 0
            for i, (s, c) in enumerate(zip(student_answers, correct_answers), start=1):
                if s == c:
                    result.append(f"{i}) ✅")
                    correct_count += 1
                else:
                    result.append(f"{i}) ❌ (правильно: {c})")

            result_text = "\n".join(result)
            await update.message.reply_text(
                f"📊 Результат:\n{result_text}\n\nВсего правильно: {correct_count}/{len(correct_answers)}"
            )
            found = True
            break

    if not found:
        await update.message.reply_text("❌ Тест с указанным кодом не найден.")

# Команда /reset
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await start(update, context)

# Основной запуск
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_ROLE: [MessageHandler(filters.TEXT, select_role)],
            TEACHER_AUTH: [MessageHandler(filters.TEXT, teacher_auth)],
            HANDLE_TEST_UPLOAD: [MessageHandler(filters.Document.ALL | filters.PHOTO, handle_test_upload)],
            AWAITING_MORE_FILES: [MessageHandler(filters.TEXT, awaiting_more_files)],
        },
        fallbacks=[CommandHandler("reset", reset)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("key", save_key))
    app.add_handler(CommandHandler("answer", handle_answer))

    app.run_polling()

if __name__ == "__main__":
    main()

import os
import sqlite3
import datetime
import random
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import dateparser
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()  # читає .env при локальному запуску (не комітити .env)

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN не знайдено в змінних середовища. Задайте BOT_TOKEN.")

DB = "birthdays.db"
GROUP_ID_FILE = "group_id.txt"
ASK_BDAY = 1

def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS birthdays (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    birthday TEXT)""")
    conn.commit()
    conn.close()

def save_group_id(chat_id: int):
    with open(GROUP_ID_FILE, "w") as f:
        f.write(str(chat_id))

def load_group_id():
    if os.path.exists(GROUP_ID_FILE):
        with open(GROUP_ID_FILE, "r") as f:
            return int(f.read().strip())
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Додати день народження"]]
    await update.message.reply_text(
        "Привіт! Я бот, що збирає дні народження та вітає у групі 🎂",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def add_bday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Напиши дату свого ДН (01.12, 1 грудня, 2006-12-01 тощо).")
    return ASK_BDAY

async def save_bday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    parsed_date = dateparser.parse(text, languages=['uk', 'ru', 'en'])
    if not parsed_date:
        await update.message.reply_text("Не вдалося розпізнати дату. Спробуй інший формат.")
        return ASK_BDAY
    bday_str = parsed_date.strftime("%d-%m")
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("REPLACE INTO birthdays VALUES (?, ?, ?, ?)",
                (user.id, user.username, user.full_name, bday_str))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"Зберегла твій день народження: {bday_str}")
    return ConversationHandler.END

async def get_group_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type in ["group", "supergroup"]:
        save_group_id(chat.id)
        await update.message.reply_text(f"Group ID збережено: {chat.id}")
    else:
        await update.message.reply_text("Ця команда працює тільки в групах.")

async def check_birthdays(app):
    today = datetime.date.today().strftime("%d-%m")
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT username, full_name FROM birthdays WHERE birthday = ?", (today,))
    results = cur.fetchall()
    conn.close()
    if not results:
        return
    group_id = load_group_id()
    if not group_id:
        return
    for username, name in results:
        greetings = [
            f"🎂 Сьогодні день народження у {name or '@'+(username or '')}! Вітаємо!",
            f"🥳 Ура! {name or '@'+(username or '')} святкує сьогодні!"
        ]
        msg = random.choice(greetings)
        if os.path.isdir("images") and os.listdir("images"):
            img = random.choice(os.listdir("images"))
            await app.bot.send_message(group_id, msg)
            await app.bot.send_photo(group_id, photo=open(f"images/{img}", "rb"))
        else:
            await app.bot.send_message(group_id, msg)

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Додати день народження$"), add_bday)],
        states={ASK_BDAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_bday)]},
        fallbacks=[CommandHandler("start", start)]
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("getid", get_group_id))

    scheduler = AsyncIOScheduler(timezone="Europe/Kiev")
    scheduler.add_job(check_birthdays, "cron", hour=9, args=[app])
    scheduler.start()

    app.run_polling()

if __name__ == "__main__":
    main()

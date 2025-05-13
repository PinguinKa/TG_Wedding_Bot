# bot.py  – работает только через HTTP-API сайта
import os, asyncio, httpx
from datetime import datetime, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ─────────────────────── переменные окружения ─────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
BRIDE_CHAT_ID = int(os.getenv("BRIDE_CHAT_ID", "0"))
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
SITE_URL = os.getenv("SITE_URL")  # https://yourname.pythonanywhere.com
BOT_SECRET = os.getenv("BOT_SECRET")  # длинная строка

if not all([BOT_TOKEN, SITE_URL, BOT_SECRET]):
    raise RuntimeError("BOT_TOKEN / SITE_URL / BOT_SECRET не заданы!")

HEADERS = {"X-Bot-Key": BOT_SECRET}
ISO = "%Y-%m-%dT%H:%M:%S.%f%z"  # ISO-8601 с tz


# ───────────────────────── /start ─────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>Добро пожаловать, Надя! 💍</b>\n\n"
        "Вот что я умею:\n"
        "1. Автоматически присылать отклики на приглашение\n"
        "2. Показать список гостей — /guests\n\n"
        "Спасибо, что доверила мне такую важную миссию 🤍",
        parse_mode=ParseMode.HTML,
    )


# ───────────────────────── /guests ────────────────────────
async def cmd_guests(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{SITE_URL}/api/guests", params={"attending": "yes"}, headers=HEADERS
        )
        guests = r.json()

    if not guests:
        await update.message.reply_text("Пока никто не подтвердил участие 😢")
        return

    lines = ["📋 <b>Гости:</b>"]
    for idx, g in enumerate(guests, 1):
        line = f"<b>{idx}) {g['name']}</b>"
        if g.get("partner"):
            line += f"<b> + {g['partner'].strip()}</b>"
        if g.get("wishes"):
            line += f". <i>Пожелания: {g['wishes'].strip()}</i>"
        lines.append(line)

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ───────────── фоновая проверка новых гостей ──────────────
last_ts = "1970-01-01T00:00:00.000000+0000"  # ISO-строка


async def check_new_guests(ctx: ContextTypes.DEFAULT_TYPE):
    global last_ts

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{SITE_URL}/api/guests",
            params={"after": last_ts},
            headers=HEADERS,
        )
        new_guests = r.json()

    if not new_guests:
        return

    # сортировка уже по created; берём последний ts сразу
    last_ts = new_guests[-1]["created"]

    # шлём сообщения
    for g in new_guests:
        txt = (
            f"💌 <b>Ответ на приглашение</b>\n"
            f"👤 <b>Гость:</b> {g['name']}\n"
            f"✅ <b>Будет:</b> {'Да' if g['attending'] else 'Нет'}\n"
            f"💑 <b>Партнёр:</b> {g['partner'].strip() if g['partner'] else 'Нет'}\n"
            f"📝 <b>Пожелания:</b> {g['wishes'].strip() if g['wishes'] else 'Нет'}"
        )
        await ctx.bot.send_message(BRIDE_CHAT_ID, txt, parse_mode="HTML")
        await ctx.bot.send_message(ADMIN_CHAT_ID, txt, parse_mode="HTML")

    # сообщаем сайту, что гостей можно пометить notified=true
    ids = [g["id"] for g in new_guests]
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"{SITE_URL}/api/guests/mark_notified", json={"ids": ids}, headers=HEADERS
        )


# ─────────────────────── запуск бота ──────────────────────
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("guests", cmd_guests))
    app.job_queue.run_repeating(check_new_guests, interval=5, first=0)
    print("🚀 Bot is starting (long polling)…")
    app.run_polling()


if __name__ == "__main__":
    main()

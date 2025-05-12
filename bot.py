# bot.py  ─ минимальный, но рабочий
import os
from datetime import datetime, timezone

from telegram import Update
from telegram.constants import ParseMode  # только ParseMode – больше ничего не нужно
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
)
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker

# ─────────────── переменные окружения ───────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
BRIDE_CHAT_ID = int(os.getenv("BRIDE_CHAT_ID", "0"))
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
DB_URL = os.getenv("DATABASE_URL", "sqlite:///guests.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан!")

# ─────────────── База данных ───────────────
engine = create_engine(DB_URL, echo=False, pool_pre_ping=True)
Session = scoped_session(sessionmaker(bind=engine))
Base = declarative_base()


class Guest(Base):
    __tablename__ = "guests"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    partner = Column(String(128))
    wishes = Column(String(512))
    attending = Column(Boolean, default=True)
    notified = Column(Boolean, default=False)
    created = Column(DateTime, default=lambda: datetime.now(timezone.utc))


Base.metadata.create_all(engine)


# ─────────────── Команды ───────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>Добро пожаловать, Надя! 💍</b>\n\n"
        "Вот что я умею:\n"
        "1. Автоматически присылать отклики на приглашение\n"
        "2. Показать список гостей — /guests\n\n"
        "Спасибо, что доверила мне такую важную миссию 🤍",
        parse_mode=ParseMode.HTML,
    )


async def cmd_guests(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = Session()
    try:
        guests = db.query(Guest).filter_by(attending=True).order_by(Guest.created).all()
        if not guests:
            await update.message.reply_text("Пока никто не подтвердил участие 😢")
            return

        lines = ["📋 <b>Гости:</b>"]
        for idx, g in enumerate(guests, 1):
            line = f"<b>{idx}) {g.name}</b>"
            if g.partner:
                line += f"<b> + {g.partner.strip()}</b>"
            if g.wishes:
                line += f". <i>Пожелания: {g.wishes.strip()}</i>"
            lines.append(line)

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
    finally:
        db.close()


# ─────────────── Проверка новых гостей ───────────────
async def check_new_guests(ctx: ContextTypes.DEFAULT_TYPE):
    db = Session()
    try:
        fresh = db.query(Guest).filter_by(notified=False).all()
        for g in fresh:
            text = (
                f"💌 <b>Ответ на приглашение</b>\n"
                f"👤 <b>Гость:</b> {g.name}\n"
                f"✅ <b>Будет:</b> {'Да' if g.attending else 'Нет'}\n"
                f"💑 <b>Партнёр:</b> {g.partner.strip() if g.partner else 'Нет'}\n"
                f"📝 <b>Пожелания:</b> {g.wishes.strip() if g.wishes else 'Нет'}"
            )
            try:
                await ctx.bot.send_message(BRIDE_CHAT_ID, text, parse_mode="HTML")
                await ctx.bot.send_message(ADMIN_CHAT_ID, text, parse_mode="HTML")
                g.notified = True
                db.commit()
            except Exception:
                db.rollback()
    finally:
        db.close()


# ─────────────── Старт приложения ───────────────
def main() -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("guests", cmd_guests))

    app.job_queue.run_repeating(check_new_guests, interval=5, first=0)

    print("🚀 Bot is starting (long polling)…")
    app.run_polling()  # ← без лишних аргументов!


if __name__ == "__main__":
    main()

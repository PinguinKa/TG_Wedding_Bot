# bot.py
import os
import asyncio
from datetime import datetime, timezone

from telegram import Update
from telegram.constants import UpdateType
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    JobQueue,
)


from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

# ──────────────────────────────── конфиг ────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
BRIDE_CHAT_ID = int(os.getenv("BRIDE_CHAT_ID", "0"))
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

# ───────────────────────────── база данных ─────────────────────────────
DB_URL = os.getenv("DATABASE_URL", "sqlite:///guests.db")
engine = create_engine(DB_URL, echo=False, pool_pre_ping=True)
Session = scoped_session(sessionmaker(bind=engine, autoflush=False))
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

    def __repr__(self) -> str:
        return f"<Guest {self.name}>"


Base.metadata.create_all(engine)


# ───────────────────────────── хендлеры ──────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "<b>Добро пожаловать, Надя! 💍</b>\n\n"
        "Вот что я умею:\n"
        "1. Автоматически присылать отклики на приглашение\n"
        "2. Показать список гостей — /guests\n\n"
        "Спасибо, что доверила мне такую важную миссию 🤍",
        parse_mode=constants.ParseMode.HTML,
    )


async def cmd_guests(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
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

        await update.message.reply_text(
            "\n".join(lines), parse_mode=constants.ParseMode.HTML
        )
    finally:
        db.close()


# ────────────────────── фоновая проверка новых гостей ───────────────────
async def check_new_guests(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    db = Session()
    try:
        new_guests = db.query(Guest).filter_by(notified=False).all()
        for g in new_guests:
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
            except Exception as exc:
                # если Телеграм временно недоступен — не ставим notified, повторим позже
                print("Ошибка при отправке:", exc)
                db.rollback()
    finally:
        db.close()


# ───────────────────────────── старт приложения ─────────────────────────
def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Переменная окружения BOT_TOKEN не задана!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("guests", cmd_guests))

    # JobQueue — проверка новых гостей каждые 5 сек
    app.job_queue.run_repeating(check_new_guests, interval=5, first=0)

    # long polling
    print("🚀 Bot is starting (long polling)…")
    app.run_polling()


if __name__ == "__main__":
    main()

import asyncio
import logging
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from bot.handlers import router
from core.config import get_settings
from core.db import init_pool, close_pool
from core.logging import setup_logging

load_dotenv()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def db_lifespan():
    """Керування життєвим циклом бази даних для бота."""
    setup_logging()
    await init_pool()
    try:
        yield  # Тут бот крутиться і приймає повідомлення
    finally:
        await close_pool()


async def main():
    settings = get_settings()
    if not settings.bot_token:
        raise ValueError("BOT_TOKEN не знайдено у змінних середовища!")

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    async with db_lifespan():
        print("🤖 Бот запущений. Чекаю на посилання...")
        await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Бот зупинений користувачем")
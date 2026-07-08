import asyncio
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv


from bot.handlers import router
import logging
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)

    print(" Чекаю на посилання...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Configure logging to view errors in the console
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(" Бот зупинений")
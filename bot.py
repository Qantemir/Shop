import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import config
from database.mongodb import db
from handlers import user_handlers, admin_handlers  # Предполагается, что это модули с Router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    # Initialize bot and dispatcher
    bot = Bot(token=config.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Connect to MongoDB
    try:
        await db.connect()
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        return

    # Register handlers
    dp.include_router(admin_handlers.router)
    dp.include_router(user_handlers.router)

    try:
        logger.info("Starting bot...")
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"Error while running bot: {e}")
    finally:
        await db.close()
        await bot.session.close()
        logger.info("Bot stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user")

import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramAPIError

import config
from database import db
from handlers import user_handlers, admin_handlers

logging.getLogger("aiogram").setLevel(logging.WARNING)

def setup_logging():
    """Configure logging for the bot"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

async def on_startup():
    """Perform startup actions"""
    try:
        # Initialize database connection
        await db.connect()
        logging.info("Database connection established")
    except Exception as e:
        logging.error(f"Error during startup: {e}")
        raise

async def on_shutdown():
    """Perform cleanup actions"""
    try:
        # Close database connection
        await db.close()
        logging.info("Database connection closed")
    except Exception as e:
        logging.error(f"Error during shutdown: {e}")

async def main():
    # Setup logging
    logger = setup_logging()
    
    try:
        # Initialize bot and dispatcher
        bot = Bot(token=config.BOT_TOKEN)
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)
        
        # Register routers
        dp.include_router(user_handlers.router)
        dp.include_router(admin_handlers.router)
        
        # Запуск периодической очистки rate limit и корзин
        await user_handlers.init_rate_limit_cleanup(bot)
        # Register startup and shutdown handlers
        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)
        
        # Start polling
        logger.info("Starting bot...")
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.critical(f"Critical error while running bot: {e}")
        sys.exit(1)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")

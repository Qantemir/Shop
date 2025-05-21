import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramAPIError

import config
from database import db
from handlers import user_handlers, admin_handlers, flavor_handlers, sleep_mode

def setup_logging():
    """Configure logging for the bot"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('bot.log')
        ]
    )
    return logging.getLogger(__name__)

async def on_startup(bot: Bot, logger):
    """Perform startup actions"""
    try:
        # Send startup notification to admin
        await bot.send_message(
            chat_id=config.ADMIN_ID,
            text="🟢 Бот запущен и готов к работе!"
        )
        logger.info("Startup notification sent to admin")
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise

async def on_shutdown(bot: Bot, logger):
    """Perform cleanup actions"""
    try:
        # Send shutdown notification to admin
        try:
            await bot.send_message(
                chat_id=config.ADMIN_ID,
                text="🔴 Бот остановлен!"
            )
        except TelegramAPIError:
            pass  # Ignore Telegram API errors during shutdown
            
        # Close bot session
        await bot.session.close()
        logger.info("Bot session closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

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
        dp.include_router(flavor_handlers.router)
        dp.include_router(sleep_mode.router)
        
        # Register startup and shutdown handlers
        dp.startup.register(lambda: on_startup(bot, logger))
        dp.shutdown.register(lambda: on_shutdown(bot, logger))
        
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

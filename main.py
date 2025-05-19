import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from handlers import user_handlers, admin_handlers, cleanup

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Register handlers
dp.include_router(user_handlers.router)
dp.include_router(admin_handlers.router)

async def main():
    # Start cleanup scheduler
    asyncio.create_task(cleanup.start_cleanup_scheduler())
    
    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main()) 
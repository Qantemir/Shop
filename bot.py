import asyncio
import logging

from aiogram import Bot, Dispatcher

import config
from handlers import user_handlers, admin_handlers  # Предполагается, что это модули с Router

logging.basicConfig(level=logging.INFO)

async def main():
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()

    # Подключаем роутеры из модулей
    dp.include_router(user_handlers.user_router)
    dp.include_router(admin_handlers.admin_router)

    try:
        logging.info("Запуск бота...")
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())

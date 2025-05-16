from aiogram import Bot, Dispatcher, executor
import logging
import config
from handlers import user_handlers, admin_handlers

# Логирование
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(bot)

# Регистрация обработчиков
user_handlers.register_handlers(dp)
admin_handlers.register_handlers(dp)

# Запуск бота
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)

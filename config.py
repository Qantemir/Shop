import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")  # Токен бота
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # ID администратора
DB_PATH = "data/database.db"  # Путь к базе данных

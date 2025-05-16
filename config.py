import os
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN")
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))  # добавлен fallback на случай отсутствия
DB_PATH: str = "data/database.db"

from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

def require_env_var(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise ValueError(f"Переменная окружения '{name}' не установлена.")
    return value

# Bot Configuration
BOT_TOKEN: str = require_env_var("BOT_TOKEN")
ADMIN_ID: int = int(require_env_var("ADMIN_ID"))
ADMIN_CARD: str = os.getenv("ADMIN_CARD", "")  # OK — по умолчанию пустая строка
ADMIN_SWITCHING: int = int(require_env_var("ADMIN_SWITCHING"))
ADMIN_CARD_NAME: str = os.getenv("ADMIN_CARD_NAME", "")  # OK

# MongoDB Configuration
MONGODB_URI: str = require_env_var("MONGODB_URI")
DB_NAME: str = "vapeshop_db"

# Shop Configuration
SHOP_NAME: str = "VapeShop"
# Product Categories
CATEGORIES = [
    "Одноразовые устройства",
    "Жидкости",
    "Снюс",
    "Аксессуары"
]

# Order Statuses
ORDER_STATUSES = {
    "pending": "🕒 Ожидает подтверждения",
    "confirmed": "✅ Подтвержден",
    "cancelled": "❌ Отменен",
    "completed": "🎉 Выполнен"
}

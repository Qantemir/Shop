import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN: str = os.getenv("BOT_TOKEN")
ADMIN_ID: int = int(os.getenv("ADMIN_ID"))
ADMIN_CARD: str = os.getenv("ADMIN_CARD", "")  # Card number for payments
ADMIN_SWITCHING: int = int(os.getenv("ADMIN_SWITCHING", "20"))  # Number of approved orders before sleep mode

# MongoDB Configuration
MONGODB_URI: str = os.getenv("MONGODB_URI")
DB_NAME: str = os.getenv("DB_NAME", "vapeshop_db")

# Shop Configuration
SHOP_NAME: str = os.getenv("SHOP_NAME", "VapeShop")
CURRENCY: str = os.getenv("CURRENCY", "RUB")

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

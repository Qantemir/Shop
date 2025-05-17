import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN: str = os.getenv("BOT_TOKEN")
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "1088067370"))
ADMIN_CARD: str = os.getenv("ADMIN_CARD", "")  # Card number for payments

# MongoDB Configuration
MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME: str = os.getenv("DB_NAME", "vapeshop_db")

# Shop Configuration
SHOP_NAME: str = os.getenv("SHOP_NAME", "VapeShop")
CURRENCY: str = os.getenv("CURRENCY", "RUB")

# Product Categories
CATEGORIES = [
    "Одноразовые устройства",
    "Многоразовые устройства",
    "Жидкости",
    "Расходники",
    "Аксессуары"
]

# Order Statuses
ORDER_STATUSES = {
    "pending": "🕒 Ожидает оплаты",
    "paid": "💰 Оплачен",
    "confirmed": "✅ Подтвержден",
    "cancelled": "❌ Отменен",
    "completed": "🎉 Выполнен"
}

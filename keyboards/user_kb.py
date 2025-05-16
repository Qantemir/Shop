from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from config import CATEGORIES

def main_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🛍 Каталог"))
    kb.add(KeyboardButton("🛒 Корзина"))
    kb.add(KeyboardButton("📱 Мои заказы"), KeyboardButton("ℹ️ Помощь"))
    return kb

def catalog_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    for category in CATEGORIES:
        kb.add(InlineKeyboardButton(category, callback_data=f"category_{category}"))
    return kb

def product_actions_kb(product_id: str, in_cart: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    if not in_cart:
        kb.add(InlineKeyboardButton("🛒 В корзину", callback_data=f"add_to_cart_{product_id}"))
    kb.add(
        InlineKeyboardButton("📝 Подробнее", callback_data=f"product_info_{product_id}"),
        InlineKeyboardButton("🔙 Назад", callback_data="back_to_catalog")
    )
    return kb

def cart_actions_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Оформить заказ", callback_data="checkout"),
        InlineKeyboardButton("🗑 Очистить корзину", callback_data="clear_cart"),
        InlineKeyboardButton("🔙 Вернуться в каталог", callback_data="back_to_catalog")
    )
    return kb

def cart_item_kb(item_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=3)
    kb.row(
        InlineKeyboardButton("➖", callback_data=f"decrease_{item_id}"),
        InlineKeyboardButton("❌", callback_data=f"remove_{item_id}"),
        InlineKeyboardButton("➕", callback_data=f"increase_{item_id}")
    )
    return kb

def confirm_order_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_order"),
        InlineKeyboardButton("❌ Отменить", callback_data="cancel_order")
    )
    return kb

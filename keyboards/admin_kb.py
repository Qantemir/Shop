from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from config import CATEGORIES, ORDER_STATUSES

def admin_main_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📦 Управление товарами"))
    kb.add(KeyboardButton("📊 Заказы"))
    kb.add(KeyboardButton("📈 Статистика"))
    kb.add(KeyboardButton("📢 Рассылка"))
    return kb

def product_management_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ Добавить товар", callback_data="add_product"),
        InlineKeyboardButton("📝 Редактировать", callback_data="edit_products"),
        InlineKeyboardButton("❌ Удалить товар", callback_data="delete_product"),
        InlineKeyboardButton("📋 Список товаров", callback_data="list_products"),
        InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin_menu")
    )
    return kb

def categories_kb(for_adding: bool = True) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    for category in CATEGORIES:
        callback_data = f"add_to_{category}" if for_adding else f"view_{category}"
        kb.add(InlineKeyboardButton(category, callback_data=callback_data))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_product_management"))
    return kb

def order_management_kb(order_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    for status_key, status_text in ORDER_STATUSES.items():
        kb.add(InlineKeyboardButton(
            status_text,
            callback_data=f"order_status_{order_id}_{status_key}"
        ))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_orders"))
    return kb

def confirm_action_kb(action: str, item_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Да", callback_data=f"confirm_{action}_{item_id}"),
        InlineKeyboardButton("❌ Нет", callback_data=f"cancel_{action}")
    )
    return kb

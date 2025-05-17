from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from config import CATEGORIES, ORDER_STATUSES

def admin_main_menu() -> ReplyKeyboardMarkup:
    """Главное меню администратора"""
    keyboard = [
        [
            KeyboardButton(text="📦 Управление товарами"),
            KeyboardButton(text="📊 Заказы")
        ],
        [
            KeyboardButton(text="📢 Рассылка"),
            KeyboardButton(text="😴 Режим сна")
        ],
        [KeyboardButton(text="❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def product_management_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить товар", callback_data="add_product"),
            InlineKeyboardButton(text="📝 Редактировать", callback_data="edit_products")
        ],
        [
            InlineKeyboardButton(text="❌ Удалить товар", callback_data="delete_product"),
            InlineKeyboardButton(text="🌈 Вкусы", callback_data="manage_flavors")
        ],
        [
            InlineKeyboardButton(text="📋 Список товаров", callback_data="list_products"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin_menu")
        ]
    ])

def categories_kb(for_adding: bool = True) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=category,
            callback_data=f"add_to_{category}" if for_adding else f"view_{category}"
        )]
        for category in CATEGORIES
    ]
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_product_management")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def order_management_kb(order_id: str, status: str = "pending") -> InlineKeyboardMarkup:
    keyboard = []
    
    if status == "pending":
        keyboard.append([
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_confirm_{order_id}"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"admin_cancel_{order_id}")
        ])
    else:
        # For completed, cancelled, or confirmed orders
        keyboard.append([
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_order_{order_id}")
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def confirm_action_kb(action: str, item_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}_{item_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"cancel_{action}")
        ]
    ])

def sleep_mode_kb(is_enabled: bool) -> InlineKeyboardMarkup:
    """Клавиатура управления режимом сна"""
    button_text = "❌ Выключить режим сна" if is_enabled else "✅ Включить режим сна"
    
    keyboard = [
        [InlineKeyboardButton(text=button_text, callback_data="toggle_sleep_mode")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

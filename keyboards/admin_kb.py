from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from config import CATEGORIES, ORDER_STATUSES

def admin_main_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Управление товарами")],
            [KeyboardButton(text="📊 Заказы")],
            [KeyboardButton(text="📈 Статистика")],
            [KeyboardButton(text="📢 Рассылка")]
        ],
        resize_keyboard=True
    )
    return kb

def product_management_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить товар", callback_data="add_product"),
            InlineKeyboardButton(text="📝 Редактировать", callback_data="edit_products")
        ],
        [
            InlineKeyboardButton(text="❌ Удалить товар", callback_data="delete_product"),
            InlineKeyboardButton(text="📋 Список товаров", callback_data="list_products")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin_menu")]
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

def order_management_kb(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data=f"order_status_{order_id}_paid")
        ],
        [
            InlineKeyboardButton(text="📦 Подтвердить заказ", callback_data=f"order_status_{order_id}_confirmed"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"order_status_{order_id}_cancelled")
        ],
        [
            InlineKeyboardButton(text="🎉 Завершить", callback_data=f"order_status_{order_id}_completed")
        ]
    ])

def confirm_action_kb(action: str, item_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}_{item_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"cancel_{action}")
        ]
    ])

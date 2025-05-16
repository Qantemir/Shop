from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from config import CATEGORIES

def main_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛍 Каталог")],
            [KeyboardButton(text="🛒 Корзина"), KeyboardButton(text="ℹ️ Помощь")]
        ],
        resize_keyboard=True
    )
    return kb

def catalog_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=category, callback_data=f"category_{category}")]
        for category in CATEGORIES
    ])
    return kb

def product_actions_kb(product_id: str, in_cart: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    if not in_cart:
        buttons.append([InlineKeyboardButton(
            text="🛒 В корзину",
            callback_data=f"add_to_cart_{product_id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_catalog")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def cart_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout"),
            InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear_cart")
        ],
        [InlineKeyboardButton(text="🔙 Вернуться в каталог", callback_data="back_to_catalog")]
    ])

def cart_item_kb(item_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="➖", callback_data=f"decrease_{item_id}"),
        InlineKeyboardButton(text="❌", callback_data=f"remove_{item_id}"),
        InlineKeyboardButton(text="➕", callback_data=f"increase_{item_id}")
    ]])

def confirm_order_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_order"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order")
        ]
    ])

def help_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 Контакты", callback_data="help_contacts")],
        [InlineKeyboardButton(text="❓ Как сделать заказ", callback_data="help_how_to_order")],
        [InlineKeyboardButton(text="💳 Оплата", callback_data="help_payment")],
        [InlineKeyboardButton(text="🚚 Доставка", callback_data="help_delivery")]
    ])

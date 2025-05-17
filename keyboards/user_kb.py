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

def product_actions_kb(product_id: str, in_cart: bool = False, flavors: list = None) -> InlineKeyboardMarkup:
    buttons = []
    print(f"[DEBUG] Creating keyboard for product {product_id} with flavors: {flavors}")
    
    if flavors and not in_cart:
        # Add flavor selection buttons in rows of 3
        row = []
        for i, flavor in enumerate(flavors, 1):
            callback_data = f"select_flavor_{product_id}_{flavor}"
            print(f"[DEBUG] Creating flavor button with callback_data: {callback_data}")
            row.append(InlineKeyboardButton(
                text=f"{i}. {flavor}",
                callback_data=callback_data
            ))
            
            # Create new row after every 3 buttons
            if len(row) == 3:
                buttons.append(row)
                row = []
        
        # Add remaining buttons if any
        if row:
            buttons.append(row)
    elif not in_cart:
        callback_data = f"add_to_cart_{product_id}"
        print(f"[DEBUG] Creating add to cart button with callback_data: {callback_data}")
        buttons.append([
            InlineKeyboardButton(
                text="🛒 В корзину",
                callback_data=callback_data
            )
        ])
    
    # Always add back button at the bottom
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_catalog")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def cart_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout"),
        ],
        [
            InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="confirm_clear_cart"),
            InlineKeyboardButton(text="🛍 Продолжить покупки", callback_data="back_to_catalog")
        ]
    ])

def confirm_clear_cart_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, очистить", callback_data="clear_cart"),
            InlineKeyboardButton(text="❌ Нет, оставить", callback_data="cancel_clear_cart")
        ]
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

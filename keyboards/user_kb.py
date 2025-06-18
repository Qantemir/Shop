from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from config import CATEGORIES

def main_menu() -> ReplyKeyboardMarkup:#основная клавиатура юсера
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛍 Каталог")],
            [KeyboardButton(text="🛒 Корзина")], 
            [KeyboardButton(text="ℹ️ Помощь")]
        ],
        resize_keyboard=True
    )
    return kb

def catalog_menu() -> InlineKeyboardMarkup:#кнокпи категории юсера
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=category, callback_data=f"category_{category}")]
        for category in CATEGORIES
    ] + [
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    return kb

def product_actions_kb(product_id: str, in_cart: bool = False, flavors: list = None) -> InlineKeyboardMarkup:
    buttons = []

    if flavors and not in_cart:
        for i, flavor in enumerate(flavors, 1):
            flavor_name = flavor.get('name', '') if isinstance(flavor, dict) else flavor
            flavor_quantity = flavor.get('quantity', 0) if isinstance(flavor, dict) else 0

            if flavor_quantity > 0:
                callback_data = f"sf_{product_id}_{i}"

                buttons.append([
                    InlineKeyboardButton(
                        text=f"{i}. {flavor_name} ({flavor_quantity} шт.)",
                        callback_data=callback_data
                    )
                ])

    # Кнопки навигации
    buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_catalog"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def cart_actions_kb() -> InlineKeyboardMarkup:#кнопки корзины
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout"),
        ],
        [
            InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear_cart"),
            InlineKeyboardButton(text="🛍 Продолжить покупки", callback_data="back_to_catalog")
        ],
        [
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
        ]
    ])

def help_menu() -> InlineKeyboardMarkup:#Хелп кнопки
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❓ Как сделать заказ", callback_data="help_how_to_order")],
        [InlineKeyboardButton(text="💳 Оплата", callback_data="help_payment")],
        [InlineKeyboardButton(text="🚚 Доставка", callback_data="help_delivery")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])

def cart_full_kb(cart_items: list) -> InlineKeyboardMarkup:#клавиатура для товара в корзине
    keyboard = []

    for item in cart_items:
        item_id = item['product_id']
        keyboard.append([
            InlineKeyboardButton(text=f"➖ {item['name']}", callback_data=f"decrease_{item_id}"),
            InlineKeyboardButton(text=f"➕ {item['name']}",callback_data=f"increase_{item_id}")
        ])

    # Добавляем основные действия корзины
    keyboard.extend(cart_actions_kb().inline_keyboard)

    return InlineKeyboardMarkup(inline_keyboard=keyboard)
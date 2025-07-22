from cgitb import text
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, keyboard_button
)
from config import CATEGORIES

# 🔹 Универсальная кнопка "Главное меню"
def main_menu_button() -> list:
    return [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]

# 🔹 Главное меню пользователя
def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛍 Каталог")],
            [KeyboardButton(text="🛒 Корзина")],
            [KeyboardButton(text="ℹ️ Помощь")]
        ],
        resize_keyboard=True
    )

# 🔹 Меню с категориями
def catalog_menu() -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton(text=category, callback_data=f"category_{category}")]
          for category in CATEGORIES]
    kb.append(main_menu_button())
    return InlineKeyboardMarkup(inline_keyboard=kb)

# 🔹 Кнопки выбора вкуса и действий с товаром
def product_actions_kb(product_id: str, in_cart: bool = False, flavors: list = None) -> InlineKeyboardMarkup:
    buttons = []

    if not in_cart and flavors:
        for i, flavor in enumerate(flavors, 1):
            if isinstance(flavor, dict):
                name = flavor.get('name', '')
                quantity = flavor.get('quantity', 0)
            else:
                name = flavor
                quantity = 1  # По умолчанию считаем что вкус доступен

            if quantity > 0:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"{i}. {name} ({quantity} шт.)",
                        callback_data=f"sf_{product_id}_{i}"
                    )
                ])

    buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_catalog"),
        *main_menu_button()
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

# 🔹 Кнопки действий в корзине
def cart_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout")],
        [
            InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear_cart"),
            InlineKeyboardButton(text="🛍 Продолжить покупки", callback_data="back_to_catalog")
        ],
        main_menu_button()
    ])

# 🔹 Меню помощи
def help_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❓ Как сделать заказ", callback_data="help_how_to_order")],
        [InlineKeyboardButton(text="💳 Оплата", callback_data="help_payment")],
        [InlineKeyboardButton(text="🚚 Доставка", callback_data="help_delivery")],
        [InlineKeyboardButton(text="🤙Поддержка", callback_data="help_contact")],
        main_menu_button()
        ])

# 🔹 Кнопки управления товарами в корзине
def cart_full_kb(cart_items: list) -> InlineKeyboardMarkup:
    keyboard = []

    for item in cart_items:
        item_id = item['product_id']
        keyboard.append([
            InlineKeyboardButton(text="➖", callback_data=f"decrease_{item_id}"),
            InlineKeyboardButton(text=item['name'], callback_data="noop"),
            InlineKeyboardButton(text="➕", callback_data=f"increase_{item_id}")
        ])

    keyboard.extend(cart_actions_kb().inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# 🔹 Одиночная кнопка помощи
def help_button_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="show_help")]
    ])

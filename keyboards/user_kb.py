from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def categories_keyboard(categories):
    """Создает клавиатуру с основными категориями товаров."""
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for category in categories:
        kb.add(KeyboardButton(category))
    return kb

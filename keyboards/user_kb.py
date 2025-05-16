from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def categories_keyboard(categories: list[str]) -> ReplyKeyboardMarkup:
    """Создает клавиатуру с основными категориями товаров."""
    keyboard = [
        [KeyboardButton(text=category)] for category in categories
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите категорию"
    )

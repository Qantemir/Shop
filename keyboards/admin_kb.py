from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def admin_menu() -> ReplyKeyboardMarkup:
    """Создает клавиатуру с админ-функциями."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Просмотр базы данных")],
            [KeyboardButton(text="Обработка заказов")]
        ],
        resize_keyboard=True
    )

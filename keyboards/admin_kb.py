from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def admin_menu():
    """Создает клавиатуру с админ-функциями."""
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Просмотр базы данных"))
    kb.add(KeyboardButton("Обработка заказов"))
    return kb

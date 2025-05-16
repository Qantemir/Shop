from aiogram import types, Dispatcher
from keyboards.user_kb import categories_keyboard
from utils.message_manager import store_message_id

async def start_handler(message: types.Message):
    """Обрабатывает команду /start, отправляет категории и запоминает ID сообщений."""
    categories = [
        "Подсистемы", "Одноразки", "Жидкости", "Картриджи",
        "Испарители", "Аксессуары", "Солевые жидкости", "Бесплатные вкусы"
    ]

    msg = await message.answer(
        "Выберите категорию:", reply_markup=categories_keyboard(categories)
    )

    # Запоминание message_id для последующего удаления
    await store_message_id(message.chat.id, msg.message_id)

def register_handlers(dp: Dispatcher):
    """Регистрирует обработчики команд."""
    dp.register_message_handler(start_handler, commands=["start"])

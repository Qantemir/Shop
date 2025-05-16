from aiogram import Router, F
from aiogram.types import Message
from keyboards.user_kb import categories_keyboard
from utils.message_manager import store_message_id

user_router = Router()

@user_router.message(F.text == "/start")
async def start_handler(message: Message):
    """Обрабатывает команду /start, отправляет категории и запоминает ID сообщений."""
    categories = [
        "Подсистемы", "Одноразки", "Жидкости", "Картриджи",
        "Испарители", "Аксессуары", "Солевые жидкости", "Бесплатные вкусы"
    ]

    msg = await message.answer(
        "Выберите категорию:", reply_markup=categories_keyboard(categories)
    )

    await store_message_id(message.chat.id, msg.message_id)

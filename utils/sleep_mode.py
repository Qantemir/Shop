from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import db
from config import ADMIN_SWITCHING
import logging
from datetime import datetime, timedelta
from typing import Union

sleep_log = logging.getLogger(__name__)

async def check_sleep_mode(obj: Union[Message, CallbackQuery]) -> bool:
    """Проверка режима сна. Возвращает True, если магазин спит и сообщение показано"""

    try:
        # Проверка, нужно ли включить режим сна
        approved_count = await db.count_approved_orders()
        if approved_count >= ADMIN_SWITCHING:
            sleep_data = await db.get_sleep_mode()
            if not sleep_data or not sleep_data.get("enabled", False):
                end_time = (datetime.now() + timedelta(hours=2)).strftime("%H:%M")
                await db.set_sleep_mode(True, end_time)
                sleep_data = {"enabled": True, "end_time": end_time}

        # Проверка, активен ли режим сна
        sleep_data = await db.get_sleep_mode()
        if sleep_data is None:
            sleep_log.warning("Не удалось получить данные sleep_mode")
            return False

        if sleep_data.get("enabled", False):
            end_time = sleep_data.get("end_time", "Не указано")
            help_button = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="show_help")]
            ])

            text = (
                f"😴 Магазин временно не работает.\n"
                f"Работа возобновится в {end_time}.\n"
                f"Пожалуйста, используйте /start когда время придет."
            )

            # Отправка сообщения — в зависимости от типа объекта
            if isinstance(obj, Message):
                await obj.answer(text, reply_markup=help_button)
            elif isinstance(obj, CallbackQuery):
                await obj.answer(text, reply_markup=help_button, show_alert=True)

            return True

        return False

    except Exception as e:
        sleep_log.exception(f"Ошибка при проверке режима сна: {e}")
        return False

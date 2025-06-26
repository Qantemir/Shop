from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

async def safe_delete_message(message_or_bot, chat_id=None, message_id=None):
    """
    Удаляет сообщение безопасно.
    Можно передать либо объект Message, либо bot, chat_id, message_id.
    """
    try:
        if isinstance(message_or_bot, Message):
            await message_or_bot.delete()
        else:
            bot = message_or_bot
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest as e:
        if "message to delete not found" in str(e):
            pass
        else:
            raise
    except Exception:
        pass 
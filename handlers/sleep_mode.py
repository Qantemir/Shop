from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import db
from config import ADMIN_SWITCHING
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
router = Router()

async def check_sleep_mode(message: Message) -> bool:
    """Check if sleep mode is active and handle it if needed"""
    try:
        # First check if we need to enable sleep mode based on approved orders
        approved_count = await db.count_approved_orders()
        if approved_count >= ADMIN_SWITCHING:
            # Set sleep mode for 2 hours if not already set
            sleep_data = await db.get_sleep_mode()
            if not sleep_data or not sleep_data.get("enabled", False):
                end_time = (datetime.now() + timedelta(hours=2)).strftime("%H:%M")
                await db.set_sleep_mode(True, end_time)
                sleep_data = {"enabled": True, "end_time": end_time}

        # Now check if sleep mode is active
        sleep_data = await db.get_sleep_mode()
        if sleep_data is None:
            logger.warning("Failed to get sleep mode data")
            return False
            
        if sleep_data.get("enabled", False):
            end_time = sleep_data.get("end_time", "Не указано")
            help_button = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="show_help")]
            ])
            await message.answer(
                f"😴 Магазин временно не работает.\n"
                f"Работа возобновится в {end_time}.\n"
                f"Пожалуйста, используйте /start когда время придет.",
                reply_markup=help_button
            )
            return True
        return False
    except Exception as e:
        logger.error(f"Error checking sleep mode: {str(e)}")
        return False

async def check_sleep_mode_callback(callback: CallbackQuery) -> bool:
    """Check if sleep mode is active and handle it if needed for callbacks"""
    try:
        # First check if we need to enable sleep mode based on approved orders
        approved_count = await db.count_approved_orders()
        if approved_count >= ADMIN_SWITCHING:
            # Set sleep mode for 2 hours if not already set
            sleep_data = await db.get_sleep_mode()
            if not sleep_data or not sleep_data.get("enabled", False):
                end_time = (datetime.now() + timedelta(hours=2)).strftime("%H:%M")
                await db.set_sleep_mode(True, end_time)
                sleep_data = {"enabled": True, "end_time": end_time}

        # Now check if sleep mode is active
        sleep_data = await db.get_sleep_mode()
        if sleep_data is None:
            logger.warning("Failed to get sleep mode data")
            return False
            
        if sleep_data.get("enabled", False):
            end_time = sleep_data.get("end_time", "Не указано")
            help_button = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="show_help")]
            ])
            await callback.message.answer(
                f"😴 Магазин временно не работает.\n"
                f"Работа возобновится в {end_time}.\n"
                f"Пожалуйста, используйте /start когда время придет.",
                reply_markup=help_button
            )
            await callback.answer()
            return True
        return False
    except Exception as e:
        logger.error(f"Error checking sleep mode: {str(e)}")
        return False 

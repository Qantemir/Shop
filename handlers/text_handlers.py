from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
import logging

from config import ADMIN_ID
from utils.security import security_manager, check_admin_session
from utils.text_manager import (
    load_texts, get_text, update_text, get_all_texts, 
    get_text_info, EDITABLE_TEXT_KEYS, initialize_texts, is_cache_empty, is_cache_loaded
)

router = Router()
logger = logging.getLogger(__name__)

class TextEditStates(StatesGroup):
    waiting_for_text_key = State()
    waiting_for_new_text = State()

@router.message(Command("texts"))
@check_admin_session
async def show_texts_menu(message: Message):
    """Показывает меню управления текстами"""
    try:
        # Загружаем тексты если кэш не загружен
        if not is_cache_loaded():
            await load_texts()
        
        keyboard = []
        for key in EDITABLE_TEXT_KEYS:
            # Получаем текущее значение для отображения
            current_text = get_text(key, "Текст не найден")
            # Обрезаем для отображения в кнопке
            display_text = current_text[:30] + "..." if len(current_text) > 30 else current_text
            display_text = display_text.replace('\n', ' ').strip()
            
            keyboard.append([
                InlineKeyboardButton(
                    text=f"📝 {key}",
                    callback_data=f"view_text_{key}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton(text="🔄 Обновить кэш", callback_data="refresh_texts_cache")
        ])
        
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await message.answer(
            "📝 Управление текстами\n\n"
            "Выберите текст для просмотра и редактирования:",
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Ошибка в show_texts_menu: {e}")
        await message.answer("❌ Произошла ошибка при загрузке текстов")

@router.callback_query(F.data == "refresh_texts_cache")
@check_admin_session
async def refresh_texts_cache(callback: CallbackQuery):
    """Обновляет кэш текстов"""
    try:
        success = await load_texts()
        if success:
            await callback.answer("✅ Кэш текстов обновлен")
        else:
            await callback.answer("❌ Ошибка при обновлении кэша")
    except Exception as e:
        logger.error(f"Ошибка при обновлении кэша: {e}")
        await callback.answer("❌ Произошла ошибка")

@router.callback_query(F.data.startswith("view_text_"))
@check_admin_session
async def view_text(callback: CallbackQuery):
    """Показывает текст для редактирования"""
    try:
        key = callback.data.replace("view_text_", "")
        
        if key not in EDITABLE_TEXT_KEYS:
            await callback.answer("❌ Неизвестный ключ текста")
            return
        
        text_info = get_text_info(key)
        if not text_info:
            await callback.answer("❌ Текст не найден")
            return
        
        current_text = text_info['value']
        hash_value = text_info['hash']
        
        # Создаем клавиатуру для редактирования
        keyboard = [
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_text_{key}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_texts_menu")]
        ]
        
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        # Обрезаем текст для отображения если он слишком длинный
        display_text = current_text
        if len(display_text) > 1000:
            display_text = display_text[:1000] + "\n\n... (текст обрезан для отображения)"
        
        await callback.message.edit_text(
            f"📝 <b>{key}</b>\n\n"
            f"Текущий текст:\n\n"
            f"<code>{display_text}</code>\n\n"
            f"Хеш: <code>{hash_value}</code>",
            reply_markup=markup,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Ошибка в view_text: {e}")
        await callback.answer("❌ Произошла ошибка при просмотре текста")

@router.callback_query(F.data.startswith("edit_text_"))
@check_admin_session
async def start_edit_text(callback: CallbackQuery, state: FSMContext):
    """Начинает редактирование текста"""
    try:
        key = callback.data.replace("edit_text_", "")
        
        if key not in EDITABLE_TEXT_KEYS:
            await callback.answer("❌ Неизвестный ключ текста")
            return
        
        text_info = get_text_info(key)
        if not text_info:
            await callback.answer("❌ Текст не найден")
            return
        
        current_text = text_info['value']
        
        # Сохраняем ключ в состояние
        await state.update_data(editing_text_key=key)
        
        # Создаем клавиатуру с кнопкой отмены
        keyboard = [
            [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"view_text_{key}")]
        ]
        
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await callback.message.edit_text(
            f"✏️ Редактирование текста: <b>{key}</b>\n\n"
            f"Текущий текст:\n\n"
            f"<code>{current_text}</code>\n\n"
            f"Отправьте новый текст:",
            reply_markup=markup,
            parse_mode="HTML"
        )
        
        await state.set_state(TextEditStates.waiting_for_new_text)
        
    except Exception as e:
        logger.error(f"Ошибка в start_edit_text: {e}")
        await callback.answer("❌ Произошла ошибка при начале редактирования")

@router.message(TextEditStates.waiting_for_new_text)
@check_admin_session
async def save_new_text(message: Message, state: FSMContext):
    """Сохраняет новый текст"""
    try:
        data = await state.get_data()
        key = data.get('editing_text_key')
        
        if not key or key not in EDITABLE_TEXT_KEYS:
            await message.answer("❌ Ошибка: неизвестный ключ текста")
            await state.clear()
            return
        
        new_text = message.text.strip()
        if not new_text:
            await message.answer("❌ Текст не может быть пустым. Попробуйте снова.")
            return
        
        # Сохраняем новый текст
        success = await update_text(key, new_text)
        
        if success:
            # Создаем клавиатуру для возврата
            keyboard = [
                [InlineKeyboardButton(text="🔙 Назад к текстам", callback_data="back_to_texts_menu")]
            ]
            markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            
            await message.answer(
                f"✅ Текст <b>{key}</b> успешно обновлен!\n\n"
                f"Новый текст:\n\n"
                f"<code>{new_text}</code>",
                reply_markup=markup,
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ Ошибка при сохранении текста")
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка в save_new_text: {e}")
        await message.answer("❌ Произошла ошибка при сохранении текста")
        await state.clear()

@router.callback_query(F.data == "back_to_texts_menu")
@check_admin_session
async def back_to_texts_menu(callback: CallbackQuery):
    """Возврат к меню текстов"""
    try:
        keyboard = []
        for key in EDITABLE_TEXT_KEYS:
            current_text = get_text(key, "Текст не найден")
            display_text = current_text[:30] + "..." if len(current_text) > 30 else current_text
            display_text = display_text.replace('\n', ' ').strip()
            
            keyboard.append([
                InlineKeyboardButton(
                    text=f"📝 {key}",
                    callback_data=f"view_text_{key}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton(text="🔄 Обновить кэш", callback_data="refresh_texts_cache")
        ])
        
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await callback.message.edit_text(
            "📝 Управление текстами\n\n"
            "Выберите текст для просмотра и редактирования:",
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Ошибка в back_to_texts_menu: {e}")
        await callback.answer("❌ Произошла ошибка")

@router.message(Command("init_texts"))
@check_admin_session
async def initialize_texts_command(message: Message):
    """Команда для инициализации текстов в базе"""
    try:
        await message.answer("🔄 Инициализация текстов в базе данных...")
        
        success = await initialize_texts()
        if success:
            await load_texts()  # Загружаем в кэш
            await message.answer("✅ Тексты успешно инициализированы в базе данных")
        else:
            await message.answer("❌ Ошибка при инициализации текстов")
            
    except Exception as e:
        logger.error(f"Ошибка при инициализации текстов: {e}")
        await message.answer("❌ Произошла ошибка при инициализации текстов") 
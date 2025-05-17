from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime, timedelta
import asyncio

from config import ADMIN_ID
from database.mongodb import db
from keyboards.admin_kb import (
    admin_main_menu,
    product_management_kb,
    categories_kb,
    order_management_kb,
    confirm_action_kb,
    sleep_mode_kb
)
from keyboards.user_kb import main_menu
from utils.security import security_manager

router = Router()

class AdminStates(StatesGroup):
    waiting_password = State()
    adding_product = State()
    editing_product = State()
    setting_name = State()
    setting_price = State()
    setting_description = State()
    setting_image = State()
    broadcasting = State()
    confirm_broadcast = State()
    adding_flavor = State()
    editing_flavors = State()
    setting_sleep_time = State()  # Новое состояние для времени сна

# Helper function to format price with decimal points
def format_price(price):
    return f"{float(price):.2f}"

# Защищаем все админские функции проверкой сессии
def check_admin_session(func):
    from functools import wraps
    
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Получаем event из первого аргумента (Message или CallbackQuery)
        event = args[0] if args else None
        if not event:
            print("[DEBUG] check_admin_session - No event object found")
            return
        
        user_id = event.from_user.id
        print(f"[DEBUG] check_admin_session - User ID: {user_id}")
        print(f"[DEBUG] check_admin_session - Is admin: {user_id == ADMIN_ID}")
        print(f"[DEBUG] check_admin_session - Session valid: {security_manager.is_admin_session_valid(user_id)}")
        
        if user_id != ADMIN_ID or not security_manager.is_admin_session_valid(user_id):
            print("[DEBUG] check_admin_session - Access denied")
            if isinstance(event, Message):
                await event.answer("Необходима авторизация. Используйте /admin")
            elif isinstance(event, CallbackQuery):
                await event.answer("Необходима авторизация", show_alert=True)
            return
        print("[DEBUG] check_admin_session - Access granted")
        
        # Удаляем dispatcher из kwargs если он есть
        kwargs.pop('dispatcher', None)
        return await func(*args, **kwargs)
    return wrapper

@router.message(Command("admin"))
async def admin_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    print(f"[DEBUG] admin_start - User ID: {user_id}")
    print(f"[DEBUG] admin_start - ADMIN_ID: {ADMIN_ID}")
    
    # Проверяем, является ли пользователь администратором
    if user_id != ADMIN_ID:
        print("[DEBUG] admin_start - Not an admin")
        await message.answer("У вас нет прав администратора.")
        return

    # Проверяем, не заблокирован ли пользователь
    if not security_manager.check_failed_attempts(user_id):
        print("[DEBUG] admin_start - User is blocked")
        remaining_time = security_manager.get_block_time_remaining(user_id)
        await message.answer(
            f"Слишком много неудачных попыток. Попробуйте снова через {remaining_time.seconds // 60} минут."
        )
        return

    # Если сессия уже активна, показываем меню админа
    if security_manager.is_admin_session_valid(user_id):
        print("[DEBUG] admin_start - Session is valid, showing menu")
        await message.answer("Панель администратора", reply_markup=admin_main_menu())
        return

    # Запрашиваем пароль
    print("[DEBUG] admin_start - Requesting password")
    await message.answer("Введите пароль администратора:")
    await state.set_state(AdminStates.waiting_password)

@router.message(AdminStates.waiting_password)
async def check_admin_password(message: Message, state: FSMContext):
    user_id = message.from_user.id
    print(f"[DEBUG] check_admin_password - User ID: {user_id}")
    
    if user_id != ADMIN_ID:
        print("[DEBUG] check_admin_password - Not an admin")
        return

    # Проверяем пароль
    print("[DEBUG] check_admin_password - Verifying password")
    if security_manager.verify_password(message.text):
        print("[DEBUG] check_admin_password - Password correct")
        security_manager.create_admin_session(user_id)
        security_manager.reset_attempts(user_id)
        await message.answer("Доступ разрешен.", reply_markup=admin_main_menu())
        await state.clear()
    else:
        print("[DEBUG] check_admin_password - Password incorrect")
        security_manager.add_failed_attempt(user_id)
        attempts_left = security_manager.max_attempts - security_manager.failed_attempts.get(user_id, 0)
        
        if attempts_left > 0:
            await message.answer(f"Неверный пароль. Осталось попыток: {attempts_left}")
        else:
            block_time = security_manager.block_time.seconds // 60
            await message.answer(f"Доступ заблокирован на {block_time} минут.")
            await state.clear()

@router.message(Command("logout"))
@check_admin_session
async def admin_logout(message: Message):
    try:
        user_id = message.from_user.id
        security_manager.remove_admin_session(user_id)
        await message.answer(
            "✅ Вы успешно вышли из панели администратора.\n"
            "Для повторного входа используйте /admin",
            reply_markup=main_menu()
        )
    except Exception as e:
        print(f"[ERROR] Error in admin_logout: {str(e)}")
        await message.answer(
            "Произошла ошибка при выходе из панели администратора",
            reply_markup=main_menu()
        )

@router.message(F.text == "📦 Управление товарами")
async def product_management(message: Message, **kwargs):
    print("[DEBUG] Entering product_management handler")
    print(f"[DEBUG] User ID: {message.from_user.id}")
    print(f"[DEBUG] kwargs: {kwargs}")
    
    # Проверка прав администратора
    user_id = message.from_user.id
    if user_id != ADMIN_ID or not security_manager.is_admin_session_valid(user_id):
        print("[DEBUG] Access denied")
        await message.answer("Необходима авторизация. Используйте /admin")
        return
    
    try:
        await message.answer(
            "Выберите действие для управления товарами:",
            reply_markup=product_management_kb()
        )
        print("[DEBUG] Successfully sent product management menu")
    except Exception as e:
        print(f"[ERROR] Error in product_management: {str(e)}")

@router.callback_query(F.data == "back_to_admin_menu")
@check_admin_session
async def back_to_admin_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "Возврат в главное меню",
        reply_markup=None
    )
    await callback.message.answer(
        "Панель администратора",
        reply_markup=admin_main_menu()
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_product_management")
@check_admin_session
async def back_to_product_management(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выберите действие для управления товарами:",
        reply_markup=product_management_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "list_products")
@check_admin_session
async def list_products(callback: CallbackQuery):
    products = await db.get_all_products()
    if not products:
        await callback.message.edit_text(
            "Товары отсутствуют",
            reply_markup=product_management_kb()
        )
        await callback.answer()
        return
    
    text = "Список товаров:\n\n"
    for product in products:
        text += f"📦 {product['name']}\n"
        text += f"💰 {product['price']} Tg\n"
        text += f"📝 {product['description']}\n"
        text += "➖➖➖➖➖➖➖➖\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=product_management_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "add_product")
@check_admin_session
async def add_product_start(callback: CallbackQuery, state: FSMContext):
    print("[DEBUG] Entering add_product_start handler")
    print(f"[DEBUG] User ID: {callback.from_user.id}")
    try:
        # Очищаем предыдущее состояние, если оно было
        await state.clear()
        await callback.message.edit_text(
            "Выберите категорию товара:",
            reply_markup=categories_kb(True)
        )
        await state.set_state(AdminStates.setting_name)
        print(f"[DEBUG] State set to: {AdminStates.setting_name}")
        await callback.answer()
        print("[DEBUG] Successfully showed categories menu")
    except Exception as e:
        print(f"[ERROR] Error in add_product_start: {str(e)}")
        await callback.message.edit_text(
            "Произошла ошибка. Попробуйте снова.",
            reply_markup=product_management_kb()
        )

@router.callback_query(F.data == "edit_products")
@check_admin_session
async def edit_products_list(callback: CallbackQuery):
    products = await db.get_all_products()
    if not products:
        await callback.message.edit_text(
            "Товары отсутствуют",
            reply_markup=product_management_kb()
        )
        await callback.answer()
        return
    
    text = "Выберите товар для редактирования:\n\n"
    keyboard = []
    for product in products:
        text += f"📦 {product['name']} - {product['price']} Tg\n"
        keyboard.append([InlineKeyboardButton(
            text=f"✏️ {product['name']}",
            callback_data=f"edit_product_{product['_id']}"
        )])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_product_management")])
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()

@router.callback_query(F.data == "delete_product")
@check_admin_session
async def delete_product_list(callback: CallbackQuery):
    products = await db.get_all_products()
    if not products:
        await callback.message.edit_text(
            "Товары отсутствуют",
            reply_markup=product_management_kb()
        )
        await callback.answer()
        return
    
    text = "Выберите товар для удаления:\n\n"
    keyboard = []
    for product in products:
        text += f"📦 {product['name']} - {product['price']} Tg\n"
        keyboard.append([InlineKeyboardButton(
            text=f"❌ {product['name']}",
            callback_data=f"confirm_delete_{product['_id']}"
        )])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_product_management")])
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_delete_"))
@check_admin_session
async def confirm_delete_product(callback: CallbackQuery):
    product_id = callback.data.replace("confirm_delete_", "")
    await db.delete_product(product_id)
    await callback.message.edit_text(
        "Товар успешно удален!",
        reply_markup=product_management_kb()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("edit_product_"))
@check_admin_session
async def edit_product_menu(callback: CallbackQuery, state: FSMContext):
    try:
        product_id = callback.data.replace("edit_product_", "")
        product = await db.get_product(product_id)
        if not product:
            await callback.answer("Товар не найден")
            return
        
        await state.update_data(editing_product_id=product_id)
        keyboard = [
            [InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"edit_name_{product_id}")],
            [InlineKeyboardButton(text="💰 Изменить цену", callback_data=f"edit_price_{product_id}")],
            [InlineKeyboardButton(text="📝 Изменить описание", callback_data=f"edit_description_{product_id}")],
            [InlineKeyboardButton(text="🖼 Изменить фото", callback_data=f"edit_photo_{product_id}")],
            [InlineKeyboardButton(text="🌈 Управление вкусами", callback_data=f"manage_flavors_{product_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_product_management")]
        ]
        
        text = f"Редактирование товара:\n\n"
        text += f"📦 Название: {product['name']}\n"
        text += f"💰 Цена: {format_price(product['price'])} Tg\n"
        text += f"📝 Описание: {product['description']}\n"
        
        if 'flavors' in product and product['flavors']:
            text += "\n🌈 Доступные вкусы:\n"
            for flavor in product['flavors']:
                text += f"• {flavor}\n"
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
    except Exception as e:
        print(f"[ERROR] Error in edit_product_menu: {str(e)}")
        await callback.answer("Произошла ошибка")

@router.message(AdminStates.setting_name)
@check_admin_session
async def process_edit_name(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        
        # Проверяем, добавляем ли мы новый товар
        if data.get('is_adding_product'):
            print("[DEBUG] Processing new product name")
            await state.update_data(name=message.text)
            await message.answer("Введите цену товара (только число):")
            await state.set_state(AdminStates.setting_price)
            return
            
        # Если это редактирование существующего товара
        product_id = data.get('editing_product_id')
        if not product_id:
            await message.answer("Ошибка: товар не найден")
            await state.clear()
            return
            
        # Update product name
        await db.update_product(product_id, {'name': message.text})
        
        # Get updated product info
        product = await db.get_product(product_id)
        if not product:
            await message.answer("Ошибка: товар не найден")
            await state.clear()
            return
        
        # Show updated product info
        keyboard = [
            [InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"edit_name_{product_id}")],
            [InlineKeyboardButton(text="💰 Изменить цену", callback_data=f"edit_price_{product_id}")],
            [InlineKeyboardButton(text="📝 Изменить описание", callback_data=f"edit_description_{product_id}")],
            [InlineKeyboardButton(text="🖼 Изменить фото", callback_data=f"edit_photo_{product_id}")],
            [InlineKeyboardButton(text="🌈 Управление вкусами", callback_data=f"manage_flavors_{product_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_product_management")]
        ]
        
        text = f"✅ Название успешно изменено!\n\n"
        text += f"📦 Название: {product['name']}\n"
        text += f"💰 Цена: {product['price']} Tg\n"
        text += f"📝 Описание: {product['description']}\n"
        
        if 'flavors' in product and product['flavors']:
            text += "\n🌈 Доступные вкусы:\n"
            for flavor in product['flavors']:
                text += f"• {flavor}\n"
        
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await state.clear()
        
    except Exception as e:
        print(f"[ERROR] Error in process_edit_name: {str(e)}")
        await message.answer("Произошла ошибка при обновлении названия")
        await state.clear()

@router.message(AdminStates.adding_product)
@check_admin_session
async def add_product_name(message: Message, state: FSMContext):
    print("[DEBUG] Entering add_product_name handler")
    print(f"[DEBUG] Received name: {message.text}")
    try:
        data = await state.get_data()
        if 'category' not in data:
            print("[ERROR] No category in state data")
            await message.answer(
                "Ошибка: категория не выбрана. Начните сначала.",
                reply_markup=product_management_kb()
            )
            await state.clear()
            return

        await state.update_data(name=message.text)
        await message.answer("Введите цену товара (только число):")
        await state.set_state(AdminStates.setting_price)
        print(f"[DEBUG] State set to: {AdminStates.setting_price}")
    except Exception as e:
        print(f"[ERROR] Error in add_product_name: {str(e)}")
        await message.answer(
            "Произошла ошибка. Попробуйте снова.",
            reply_markup=product_management_kb()
        )
        await state.clear()

@router.message(AdminStates.setting_price)
@check_admin_session
async def process_edit_price(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit():
            await message.answer("Пожалуйста, введите только число для цены:")
            print("[DEBUG] Invalid price format")
            return
            
        data = await state.get_data()
        
        # Проверяем, добавляем ли мы новый товар
        if data.get('is_adding_product'):
            print("[DEBUG] Processing new product price")
            await state.update_data(price=int(message.text))
            await message.answer("Введите описание товара:")
            await state.set_state(AdminStates.setting_description)
            return
            
        # Если это редактирование существующего товара
        product_id = data.get('editing_product_id')
        if not product_id:
            await message.answer("Ошибка: товар не найден")
            await state.clear()
            return
            
        # Update product price
        await db.update_product(product_id, {'price': int(message.text)})
        
        # Get updated product info
        product = await db.get_product(product_id)
        if not product:
            await message.answer("Ошибка: товар не найден")
            await state.clear()
            return
        
        # Show updated product info
        keyboard = [
            [InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"edit_name_{product_id}")],
            [InlineKeyboardButton(text="💰 Изменить цену", callback_data=f"edit_price_{product_id}")],
            [InlineKeyboardButton(text="📝 Изменить описание", callback_data=f"edit_description_{product_id}")],
            [InlineKeyboardButton(text="🖼 Изменить фото", callback_data=f"edit_photo_{product_id}")],
            [InlineKeyboardButton(text="🌈 Управление вкусами", callback_data=f"manage_flavors_{product_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_product_management")]
        ]
        
        text = f"✅ Цена успешно изменена!\n\n"
        text += f"📦 Название: {product['name']}\n"
        text += f"💰 Цена: {format_price(product['price'])} Tg\n"
        text += f"📝 Описание: {product['description']}\n"
        
        if 'flavors' in product and product['flavors']:
            text += "\n🌈 Доступные вкусы:\n"
            for flavor in product['flavors']:
                text += f"• {flavor}\n"
        
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await state.clear()
        
    except Exception as e:
        print(f"[ERROR] Error in process_edit_price: {str(e)}")
        await message.answer("Произошла ошибка при обновлении цены")
        await state.clear()

@router.message(AdminStates.setting_description)
@check_admin_session
async def process_edit_description(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        
        # Проверяем, добавляем ли мы новый товар
        if data.get('is_adding_product'):
            print("[DEBUG] Processing new product description")
            await state.update_data(description=message.text)
            await message.answer("Отправьте фотографию товара:")
            await state.set_state(AdminStates.setting_image)
            return
            
        # Если это редактирование существующего товара
        product_id = data.get('editing_product_id')
        if not product_id:
            await message.answer("Ошибка: товар не найден")
            await state.clear()
            return
            
        # Update product description
        await db.update_product(product_id, {'description': message.text})
        
        # Get updated product info
        product = await db.get_product(product_id)
        if not product:
            await message.answer("Ошибка: товар не найден")
            await state.clear()
            return
        
        # Show updated product info
        keyboard = [
            [InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"edit_name_{product_id}")],
            [InlineKeyboardButton(text="💰 Изменить цену", callback_data=f"edit_price_{product_id}")],
            [InlineKeyboardButton(text="📝 Изменить описание", callback_data=f"edit_description_{product_id}")],
            [InlineKeyboardButton(text="🖼 Изменить фото", callback_data=f"edit_photo_{product_id}")],
            [InlineKeyboardButton(text="🌈 Управление вкусами", callback_data=f"manage_flavors_{product_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_product_management")]
        ]
        
        text = f"✅ Описание успешно изменено!\n\n"
        text += f"📦 Название: {product['name']}\n"
        text += f"💰 Цена: {product['price']} Tg\n"
        text += f"📝 Описание: {product['description']}\n"
        
        if 'flavors' in product and product['flavors']:
            text += "\n🌈 Доступные вкусы:\n"
            for flavor in product['flavors']:
                text += f"• {flavor}\n"
        
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await state.clear()
        
    except Exception as e:
        print(f"[ERROR] Error in process_edit_description: {str(e)}")
        await message.answer("Произошла ошибка при обновлении описания")
        await state.clear()

@router.message(AdminStates.setting_image, F.photo)
@check_admin_session
async def process_edit_photo(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        
        # Проверяем, добавляем ли мы новый товар
        if data.get('is_adding_product'):
            print("[DEBUG] Processing new product photo")
            photo_id = message.photo[-1].file_id
            
            # Собираем все данные для нового товара
            product_data = {
                "name": data["name"],
                "category": data["category"],
                "price": data["price"],
                "description": data["description"],
                "photo": photo_id,
                "available": True
            }
            
            # Добавляем новый товар в базу данных
            await db.add_product(product_data)
            
            await message.answer(
                "✅ Товар успешно добавлен!",
                reply_markup=product_management_kb()
            )
            await state.clear()
            return
            
        # Если это редактирование существующего товара
        product_id = data.get('editing_product_id')
        if not product_id:
            await message.answer("Ошибка: товар не найден")
            await state.clear()
            return
            
        # Update product photo
        photo_id = message.photo[-1].file_id
        await db.update_product(product_id, {'photo': photo_id})
        
        # Get updated product info
        product = await db.get_product(product_id)
        if not product:
            await message.answer("Ошибка: товар не найден")
            await state.clear()
            return
        
        # Show updated product info
        keyboard = [
            [InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"edit_name_{product_id}")],
            [InlineKeyboardButton(text="💰 Изменить цену", callback_data=f"edit_price_{product_id}")],
            [InlineKeyboardButton(text="📝 Изменить описание", callback_data=f"edit_description_{product_id}")],
            [InlineKeyboardButton(text="🖼 Изменить фото", callback_data=f"edit_photo_{product_id}")],
            [InlineKeyboardButton(text="🌈 Управление вкусами", callback_data=f"manage_flavors_{product_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_product_management")]
        ]
        
        text = f"✅ Фото успешно изменено!\n\n"
        text += f"📦 Название: {product['name']}\n"
        text += f"💰 Цена: {product['price']} Tg\n"
        text += f"📝 Описание: {product['description']}\n"
        
        if 'flavors' in product and product['flavors']:
            text += "\n🌈 Доступные вкусы:\n"
            for flavor in product['flavors']:
                text += f"• {flavor}\n"
        
        # Send new photo with updated info
        await message.answer_photo(
            photo=photo_id,
            caption=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await state.clear()
        
    except Exception as e:
        print(f"[ERROR] Error in process_edit_photo: {str(e)}")
        await message.answer("Произошла ошибка при обновлении фото")
        await state.clear()

async def cleanup_old_orders():
    """Clean up orders that are older than 24 hours and have been completed or cancelled"""
    cutoff_time = datetime.utcnow() - timedelta(hours=24)
    await db.delete_old_orders(cutoff_time)

@router.message(F.text == "📊 Заказы")
@check_admin_session
async def show_orders(message: Message):
    try:
        # Clean up old orders first
        await cleanup_old_orders()
        
        orders = await db.get_all_orders()
        if not orders:
            await message.answer("Заказы отсутствуют")
            return
        
        ORDER_STATUSES = {
            'pending': '⏳ Ожидает обработки',
            'confirmed': '✅ Подтвержден',
            'cancelled': '❌ Отменен',
            'completed': '✅ Выполнен'
        }
        
        for order in orders:
            status = order.get('status', 'pending')
            status_text = ORDER_STATUSES.get(status, "Статус неизвестен")
            
            text = f"Заказ #{order['_id']}\n"
            text += f"От: {order.get('username', 'Неизвестно')} ({order['user_id']})\n"
            if order.get('phone'):
                text += f"📱 Телефон: {order['phone']}\n"
            if order.get('address'):
                text += f"📍 Адрес: {order['address']}\n"
            text += f"Статус: {status_text}\n\n"
            text += "Товары:\n"
            
            total = 0
            for item in order['items']:
                subtotal = item['price'] * item['quantity']
                text += f"- {item['name']}"
                if 'flavor' in item:
                    text += f" (🌈 {item['flavor']})"
                text += f" x{item['quantity']} = {format_price(subtotal)} Tg\n"
                total += subtotal
            
            text += f"\nИтого: {format_price(total)} Tg"
            
            # If order has cancellation reason, show it
            if status == 'cancelled' and order.get('cancellation_reason'):
                text += f"\n\nПричина отмены: {order['cancellation_reason']}"
            
            await message.answer(
                text,
                reply_markup=order_management_kb(str(order['_id']), status)
            )
    except Exception as e:
        print(f"[ERROR] Error in show_orders: {str(e)}")
        await message.answer("Произошла ошибка при получении заказов")

@router.callback_query(F.data.startswith("order_status_"))
async def update_order_status(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    _, order_id, status = callback.data.split("_")
    await db.update_order_status(order_id, status)
    await callback.message.edit_text(
        f"Статус заказа #{order_id} обновлен на: {status}",
        reply_markup=order_management_kb(order_id)
    )
    await callback.answer()

@router.message(F.text == "📈 Статистика")
@check_admin_session
async def show_statistics(message: Message):
    # Получаем статистику
    products = await db.get_all_products()
    orders = await db.get_all_orders()
    users = await db.get_all_users()
    
    # Считаем общую сумму заказов
    total_revenue = sum(order.get('total', 0) for order in orders)
    
    # Считаем статистику по статусам заказов
    status_counts = {}
    for order in orders:
        status = order.get('status', 'unknown')
        status_counts[status] = status_counts.get(status, 0) + 1
    
    # Формируем текст статистики
    stats_text = "📊 Статистика магазина:\n\n"
    stats_text += f"📦 Всего товаров: {len(products)}\n"
    stats_text += f"👥 Всего пользователей: {len(users)}\n"
    stats_text += f"🛍 Всего заказов: {len(orders)}\n"
    stats_text += f"💰 Общая сумма заказов: {total_revenue} RUB\n\n"
    
    stats_text += "📋 Статусы заказов:\n"
    for status, count in status_counts.items():
        stats_text += f"- {status}: {count}\n"
    
    await message.answer(stats_text)

@router.message(F.text == "📢 Рассылка")
@check_admin_session
async def broadcast_start(message: Message, state: FSMContext):
    await message.answer(
        "Введите текст рассылки или отправьте /cancel для отмены:"
    )
    await state.set_state(AdminStates.broadcasting)

@router.message(Command("cancel"))
@check_admin_session
async def cancel_broadcast(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == AdminStates.broadcasting:
        await state.clear()
        await message.answer(
            "Рассылка отменена.",
            reply_markup=admin_main_menu()
        )

@router.message(AdminStates.broadcasting)
@check_admin_session
async def prepare_broadcast(message: Message, state: FSMContext):
    await state.update_data(broadcast_text=message.text)
    await message.answer(
        f"Подтвердите отправку сообщения:\n\n{message.text}\n\n"
        "Отправить? (да/нет)"
    )
    await state.set_state(AdminStates.confirm_broadcast)

@router.message(AdminStates.confirm_broadcast)
@check_admin_session
async def confirm_broadcast(message: Message, state: FSMContext):
    if message.text.lower() == "да":
        data = await state.get_data()
        broadcast_text = data.get("broadcast_text")
        
        if not broadcast_text:
            await message.answer("Ошибка: текст рассылки не найден")
            await state.clear()
            return
        
        users = await db.get_all_users()
        sent_count = 0
        failed_count = 0
        
        for user in users:
            try:
                await message.bot.send_message(
                    chat_id=user['user_id'],
                    text=broadcast_text
                )
                sent_count += 1
                await asyncio.sleep(0.05)  # Небольшая задержка между отправками
            except Exception as e:
                print(f"[ERROR] Failed to send broadcast to user {user['user_id']}: {str(e)}")
                failed_count += 1
                continue
        
        status_text = f"✅ Рассылка завершена!\n\n"
        status_text += f"📨 Отправлено: {sent_count}\n"
        if failed_count > 0:
            status_text += f"❌ Не доставлено: {failed_count}\n"
        
        await message.answer(
            status_text,
            reply_markup=admin_main_menu()
        )
    else:
        await message.answer(
            "Рассылка отменена.",
            reply_markup=admin_main_menu()
        )
    
    await state.clear()

@router.callback_query(F.data.startswith("add_to_"))
@check_admin_session
async def add_product_category(callback: CallbackQuery, state: FSMContext):
    print("[DEBUG] Entering add_product_category handler")
    print(f"[DEBUG] Callback data: {callback.data}")
    try:
        await state.clear()  # Очищаем состояние перед началом
        category = callback.data.replace("add_to_", "")

        print(f"[DEBUG] Selected category: {category}")
        
        # Сохраняем категорию и переходим к вводу названия
        await state.update_data(category=category, is_adding_product=True)  # Добавляем флаг
        await callback.message.edit_text(
            "Введите название товара:",
            reply_markup=None  # Убираем клавиатуру для ввода текста
        )
        await state.set_state(AdminStates.setting_name)
        print(f"[DEBUG] State set to: {AdminStates.setting_name}")
        await callback.answer()
    except Exception as e:
        print(f"[ERROR] Error in add_product_category: {str(e)}")
        await callback.message.edit_text(
            "Произошла ошибка. Попробуйте снова.",
            reply_markup=product_management_kb()
        )

@router.message(AdminStates.setting_price)
@check_admin_session
async def add_product_price(message: Message, state: FSMContext):
    print("[DEBUG] Entering add_product_price handler")
    print(f"[DEBUG] Received price: {message.text}")
    try:
        if not message.text.isdigit():
            await message.answer("Пожалуйста, введите только число для цены:")
            print("[DEBUG] Invalid price format")
            return

        data = await state.get_data()
        if 'name' not in data or 'category' not in data:
            print("[ERROR] Missing required state data")
            await message.answer(
                "Ошибка: недостаточно данных. Начните сначала.",
                reply_markup=product_management_kb()
            )
            await state.clear()
            return

        await state.update_data(price=int(message.text))
        await message.answer("Введите описание товара:")
        await state.set_state(AdminStates.setting_description)
        print(f"[DEBUG] State set to: {AdminStates.setting_description}")
    except Exception as e:
        print(f"[ERROR] Error in add_product_price: {str(e)}")
        await message.answer(
            "Произошла ошибка. Попробуйте снова.",
            reply_markup=product_management_kb()
        )
        await state.clear()

@router.message(AdminStates.setting_description)
@check_admin_session
async def add_product_description(message: Message, state: FSMContext):
    print("[DEBUG] Entering add_product_description handler")
    try:
        data = await state.get_data()
        if not all(key in data for key in ['name', 'category', 'price']):
            print("[ERROR] Missing required state data")
            await message.answer(
                "Ошибка: недостаточно данных. Начните сначала.",
                reply_markup=product_management_kb()
            )
            await state.clear()
            return

        await state.update_data(description=message.text)
        await message.answer("Отправьте фотографию товара:")
        await state.set_state(AdminStates.setting_image)
        print(f"[DEBUG] State set to: {AdminStates.setting_image}")
    except Exception as e:
        print(f"[ERROR] Error in add_product_description: {str(e)}")
        await message.answer(
            "Произошла ошибка. Попробуйте снова.",
            reply_markup=product_management_kb()
        )
        await state.clear()

@router.message(AdminStates.setting_image, F.photo)
@check_admin_session
async def finish_adding_product(message: Message, state: FSMContext):
    print("[DEBUG] Entering finish_adding_product handler")
    try:
        data = await state.get_data()
        print(f"[DEBUG] State data: {data}")
        
        # Проверяем наличие всех необходимых данных
        required_fields = ['name', 'category', 'price', 'description']
        if not all(field in data for field in required_fields):
            print("[ERROR] Missing required state data")
            await message.answer(
                "Ошибка: недостаточно данных. Начните сначала.",
                reply_markup=product_management_kb()
            )
            await state.clear()
            return

        photo_id = message.photo[-1].file_id
        print(f"[DEBUG] Received photo_id: {photo_id}")
        
        product_data = {
            "name": data["name"],
            "category": data["category"],
            "price": data["price"],
            "description": data["description"],
            "photo": photo_id,
            "available": True
        }
        print(f"[DEBUG] Product data prepared: {product_data}")
        
        await db.add_product(product_data)
        print("[DEBUG] Product added to database")
        
        await message.answer(
            "Товар успешно добавлен!",
            reply_markup=product_management_kb()
        )
        await state.clear()
        print("[DEBUG] State cleared, product addition completed")
    except Exception as e:
        print(f"[ERROR] Error in finish_adding_product: {str(e)}")
        await message.answer(
            "Произошла ошибка при добавлении товара. Попробуйте снова.",
            reply_markup=product_management_kb()
        )
        await state.clear()

# Добавляем обработчик для отмены операции
@router.message(Command("cancel"))
@check_admin_session
async def cancel_operation(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        await message.answer(
            "Операция отменена. Возвращаемся в меню управления товарами.",
            reply_markup=product_management_kb()
        )

@router.callback_query(F.data.startswith("edit_name_"))
@check_admin_session
async def start_edit_name(callback: CallbackQuery, state: FSMContext):
    try:
        product_id = callback.data.replace("edit_name_", "")
        product = await db.get_product(product_id)
        
        if not product:
            await callback.answer("Товар не найден")
            return
            
        await state.update_data(editing_product_id=product_id)
        await callback.message.edit_text(
            f"Текущее название: {product['name']}\n\n"
            "Введите новое название товара:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Отмена", callback_data=f"edit_product_{product_id}")
            ]])
        )
        await state.set_state(AdminStates.setting_name)
        await callback.answer()
    except Exception as e:
        print(f"[ERROR] Error in start_edit_name: {str(e)}")
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data.startswith("edit_price_"))
@check_admin_session
async def start_edit_price(callback: CallbackQuery, state: FSMContext):
    try:
        product_id = callback.data.replace("edit_price_", "")
        product = await db.get_product(product_id)
        
        if not product:
            await callback.answer("Товар не найден")
            return
            
        await state.update_data(editing_product_id=product_id)
        await callback.message.edit_text(
            f"Текущая цена: {format_price(product['price'])} Tg\n\n"
            "Введите новую цену товара (только число):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Отмена", callback_data=f"edit_product_{product_id}")
            ]])
        )
        await state.set_state(AdminStates.setting_price)
        await callback.answer()
    except Exception as e:
        print(f"[ERROR] Error in start_edit_price: {str(e)}")
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data.startswith("edit_description_"))
@check_admin_session
async def start_edit_description(callback: CallbackQuery, state: FSMContext):
    try:
        product_id = callback.data.replace("edit_description_", "")
        product = await db.get_product(product_id)
        
        if not product:
            await callback.answer("Товар не найден")
            return
            
        await state.update_data(editing_product_id=product_id)
        await callback.message.edit_text(
            f"Текущее описание: {product['description']}\n\n"
            "Введите новое описание товара:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Отмена", callback_data=f"edit_product_{product_id}")
            ]])
        )
        await state.set_state(AdminStates.setting_description)
        await callback.answer()
    except Exception as e:
        print(f"[ERROR] Error in start_edit_description: {str(e)}")
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data.startswith("edit_photo_"))
@check_admin_session
async def start_edit_photo(callback: CallbackQuery, state: FSMContext):
    try:
        product_id = callback.data.replace("edit_photo_", "")
        product = await db.get_product(product_id)
        
        if not product:
            await callback.answer("Товар не найден")
            return
            
        await state.update_data(editing_product_id=product_id)
        await callback.message.edit_text(
            "Отправьте новую фотографию товара:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Отмена", callback_data=f"edit_product_{product_id}")
            ]])
        )
        await state.set_state(AdminStates.setting_image)
        await callback.answer()
    except Exception as e:
        print(f"[ERROR] Error in start_edit_photo: {str(e)}")
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data.startswith("manage_flavors_"))
@check_admin_session
async def manage_flavors(callback: CallbackQuery, state: FSMContext):
    try:
        product_id = callback.data.replace("manage_flavors_", "")
        product = await db.get_product(product_id)
        
        if not product:
            await callback.answer("Товар не найден")
            return
            
        # Save product ID in state
        await state.update_data(editing_product_id=product_id)
        
        # Create keyboard for flavor management
        keyboard = []
        flavors = product.get('flavors', [])
        
        # Add button for each flavor with delete option
        for i, flavor in enumerate(flavors):
            keyboard.append([
                InlineKeyboardButton(
                    text=f"❌ {flavor}",
                    callback_data=f"delete_flavor_{product_id}_{i}"
                )
            ])
        
        # Add buttons for adding new flavor and going back
        keyboard.extend([
            [InlineKeyboardButton(text="➕ Добавить вкус", callback_data=f"add_flavor_{product_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"edit_product_{product_id}")]
        ])
        
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        # Show current flavors and options
        text = "🌈 Управление вкусами\n\n"
        if flavors:
            text += "Текущие вкусы:\n"
            for i, flavor in enumerate(flavors, 1):
                text += f"{i}. {flavor}\n"
        else:
            text += "У товара пока нет вкусов\n"
        
        text += "\nНажмите на вкус чтобы удалить его, или добавьте новый"
        
        await callback.message.edit_text(text, reply_markup=markup)
        await callback.answer()
        
    except Exception as e:
        print(f"[ERROR] Error in manage_flavors: {str(e)}")
        await callback.answer("Произошла ошибка при управлении вкусами")

@router.callback_query(F.data.startswith("delete_flavor_"))
@check_admin_session
async def delete_flavor(callback: CallbackQuery):
    try:
        # Format: delete_flavor_PRODUCTID_INDEX
        _, product_id, index = callback.data.rsplit("_", 2)
        index = int(index)
        
        # Get product
        product = await db.get_product(product_id)
        if not product:
            await callback.answer("Товар не найден")
            return
            
        # Remove flavor
        flavors = product.get('flavors', [])
        if 0 <= index < len(flavors):
            removed_flavor = flavors.pop(index)
            await db.update_product(product_id, {'flavors': flavors})
            
            # Update keyboard
            keyboard = []
            for i, flavor in enumerate(flavors):
                keyboard.append([
                    InlineKeyboardButton(
                        text=f"❌ {flavor}",
                        callback_data=f"delete_flavor_{product_id}_{i}"
                    )
                ])
            keyboard.extend([
                [InlineKeyboardButton(text="➕ Добавить вкус", callback_data=f"add_flavor_{product_id}")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data=f"edit_product_{product_id}")]
            ])
            
            markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            
            # Update message
            text = "🌈 Управление вкусами\n\n"
            if flavors:
                text += "Текущие вкусы:\n"
                for i, flavor in enumerate(flavors, 1):
                    text += f"{i}. {flavor}\n"
            else:
                text += "У товара пока нет вкусов\n"
            
            text += "\nНажмите на вкус чтобы удалить его, или добавьте новый"
            
            await callback.message.edit_text(text, reply_markup=markup)
            await callback.answer(f"Вкус {removed_flavor} удален")
        else:
            await callback.answer("Вкус не найден")
            
    except Exception as e:
        print(f"[ERROR] Error in delete_flavor: {str(e)}")
        await callback.answer("Произошла ошибка при удалении вкуса")

@router.callback_query(F.data.startswith("add_flavor_"))
@check_admin_session
async def start_add_flavor(callback: CallbackQuery, state: FSMContext):
    try:
        product_id = callback.data.replace("add_flavor_", "")
        product = await db.get_product(product_id)
        
        if not product:
            await callback.answer("Товар не найден")
            return
            
        await state.update_data(editing_product_id=product_id)
        await callback.message.edit_text(
            "Введите новый вкус для товара.\n"
            "Для отмены нажмите кнопку Отмена.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Отмена", callback_data=f"manage_flavors_{product_id}")
            ]])
        )
        await state.set_state(AdminStates.adding_flavor)
        await callback.answer()
    except Exception as e:
        print(f"[ERROR] Error in start_add_flavor: {str(e)}")
        await callback.answer("Произошла ошибка")

@router.message(AdminStates.adding_flavor)
@check_admin_session
async def process_add_flavor(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        product_id = data.get('editing_product_id')
        
        if not product_id:
            await message.answer("Ошибка: товар не найден")
            await state.clear()
            return
            
        # Get current product
        product = await db.get_product(product_id)
        if not product:
            await message.answer("Товар не найден")
            await state.clear()
            return
            
        # Add new flavor
        flavors = product.get('flavors', [])
        new_flavor = message.text.strip()
        
        if new_flavor in flavors:
            await message.answer(
                "Такой вкус уже существует!\n"
                "Введите другой вкус или нажмите Отмена для возврата.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🔙 Отмена", callback_data=f"manage_flavors_{product_id}")
                ]])
            )
            return
            
        flavors.append(new_flavor)
        await db.update_product(product_id, {'flavors': flavors})
        
        # Show updated flavors list
        keyboard = []
        for i, flavor in enumerate(flavors):
            keyboard.append([
                InlineKeyboardButton(
                    text=f"❌ {flavor}",
                    callback_data=f"delete_flavor_{product_id}_{i}"
                )
            ])
        keyboard.extend([
            [InlineKeyboardButton(text="➕ Добавить вкус", callback_data=f"add_flavor_{product_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"edit_product_{product_id}")]
        ])
        
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        text = "🌈 Управление вкусами\n\n"
        text += "Текущие вкусы:\n"
        for i, flavor in enumerate(flavors, 1):
            text += f"{i}. {flavor}\n"
        
        text += f"\n✅ Вкус '{new_flavor}' успешно добавлен!"
        
        await message.answer(text, reply_markup=markup)
        await state.clear()
        
    except Exception as e:
        print(f"[ERROR] Error in process_add_flavor: {str(e)}")
        await message.answer("Произошла ошибка при добавлении вкуса")
        await state.clear()

@router.callback_query(F.data == "manage_flavors")
@check_admin_session
async def show_products_for_flavors(callback: CallbackQuery):
    try:
        # Get all products
        products = await db.get_all_products()
        
        if not products:
            await callback.answer("Нет доступных товаров")
            return
            
        # Create keyboard with product list
        keyboard = []
        for product in products:
            flavor_count = len(product.get('flavors', []))
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{product['name']} ({flavor_count} вкусов)",
                    callback_data=f"manage_flavors_{str(product['_id'])}"
                )
            ])
        
        # Add back button
        keyboard.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_product_management")
        ])
        
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await callback.message.edit_text(
            "Выберите товар для управления вкусами:",
            reply_markup=markup
        )
        await callback.answer()
        
    except Exception as e:
        print(f"[ERROR] Error in show_products_for_flavors: {str(e)}")
        await callback.answer("Произошла ошибка при загрузке списка товаров")

@router.message(F.text == "❓ Помощь")
@check_admin_session
async def show_admin_help(message: Message):
    help_text = """
<b>🔰 АДМИН-ПАНЕЛЬ: КРАТКОЕ РУКОВОДСТВО</b>

<b>🔑 ОСНОВНОЕ УПРАВЛЕНИЕ</b>
• /admin - Вход в панель администратора
• /logout - Выход из панели
• /cancel - Отмена текущей операции

<b>📦 УПРАВЛЕНИЕ ТОВАРАМИ</b>
1️⃣ <b>Добавление товара:</b>
   • Выберите категорию
   • Укажите название
   • Установите цену
   • Добавьте описание
   • Загрузите фото

2️⃣ <b>Редактирование товара:</b>
   • Изменение названия
   • Корректировка цены
   • Обновление описания
   • Замена фото
   • Управление вкусами

3️⃣ <b>Управление вкусами:</b>
   • Добавление новых вкусов
   • Удаление существующих
   • Просмотр списка вкусов

<b>📊 ЗАКАЗЫ</b>
• Просмотр всех заказов
• Подтверждение заказов
• Отмена заказов
• Автоматическая очистка старых заказов (24ч)

<b>📢 РАССЫЛКА</b>
• Создание сообщения
• Предпросмотр
• Подтверждение отправки
• Статистика доставки

<b>⚠️ ВАЖНЫЕ ЗАМЕТКИ</b>
• Цены указываются в Tg
• Подтверждайте удаление товаров
• Указывайте причину отмены заказов
• Сессия активна до выхода

<b>💡 СОВЕТЫ</b>
• Регулярно проверяйте заказы
• Своевременно обновляйте информацию
• Используйте качественные фото
• Пишите понятные описания
"""
    
    await message.answer(
        help_text,
        parse_mode="HTML",
        reply_markup=admin_main_menu()
    )

@router.callback_query(F.data == "admin_help")
@check_admin_session
async def admin_help_callback(callback: CallbackQuery):
    help_text = """
<b>🔰 АДМИН-ПАНЕЛЬ: КРАТКОЕ РУКОВОДСТВО</b>

<b>🔑 ОСНОВНОЕ УПРАВЛЕНИЕ</b>
• /admin - Вход в панель администратора
• /logout - Выход из панели
• /cancel - Отмена текущей операции

<b>📦 УПРАВЛЕНИЕ ТОВАРАМИ</b>
1️⃣ <b>Добавление товара:</b>
   • Выберите категорию
   • Укажите название
   • Установите цену
   • Добавьте описание
   • Загрузите фото

2️⃣ <b>Редактирование товара:</b>
   • Изменение названия
   • Корректировка цены
   • Обновление описания
   • Замена фото
   • Управление вкусами

3️⃣ <b>Управление вкусами:</b>
   • Добавление новых вкусов
   • Удаление существующих
   • Просмотр списка вкусов

<b>📊 ЗАКАЗЫ</b>
• Просмотр всех заказов
• Подтверждение заказов
• Отмена заказов
• Автоматическая очистка старых заказов (24ч)

<b>📢 РАССЫЛКА</b>
• Создание сообщения
• Предпросмотр
• Подтверждение отправки
• Статистика доставки

<b>⚠️ ВАЖНЫЕ ЗАМЕТКИ</b>
• Цены указываются в Tg
• Подтверждайте удаление товаров
• Указывайте причину отмены заказов
• Сессия активна до выхода

<b>💡 СОВЕТЫ</b>
• Регулярно проверяйте заказы
• Своевременно обновляйте информацию
• Используйте качественные фото
• Пишите понятные описания
"""
    
    await callback.message.edit_text(
        help_text,
        parse_mode="HTML",
        reply_markup=admin_main_menu()
    )
    await callback.answer()

@router.message(F.text == "😴 Режим сна")
@check_admin_session
async def sleep_mode_menu(message: Message):
    try:
        # Получаем текущий статус режима сна
        sleep_data = await db.get_sleep_mode()
        status = "✅ Включен" if sleep_data["enabled"] else "❌ Выключен"
        end_time = sleep_data.get("end_time", "Не указано")
        
        text = f"🌙 Режим сна магазина\n\n"
        text += f"Текущий статус: {status}\n"
        if sleep_data["enabled"] and end_time:
            text += f"Время работы возобновится: {end_time}\n"
        text += f"\nВ режиме сна пользователи не смогут делать заказы."
        
        await message.answer(
            text,
            reply_markup=sleep_mode_kb(sleep_data["enabled"])
        )
    except Exception as e:
        print(f"[ERROR] Error in sleep_mode_menu: {str(e)}")
        await message.answer("Произошла ошибка при получении статуса режима сна")

@router.callback_query(F.data == "toggle_sleep_mode")
@check_admin_session
async def toggle_sleep_mode(callback: CallbackQuery, state: FSMContext):
    try:
        # Получаем текущий статус
        sleep_data = await db.get_sleep_mode()
        current_mode = sleep_data["enabled"]
        
        if not current_mode:  # Если включаем режим сна
            await callback.message.edit_text(
                "🕒 Введите время, до которого магазин будет закрыт\n"
                "Формат: ЧЧ:ММ (например, 10:00)",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_admin_menu")
                ]])
            )
            await state.set_state(AdminStates.setting_sleep_time)
        else:  # Если выключаем режим сна
            await db.set_sleep_mode(False, None)
            await callback.message.edit_text(
                "🌙 Режим сна магазина\n\n"
                "Текущий статус: ❌ Выключен\n\n"
                "В режиме сна пользователи не смогут делать заказы.",
                reply_markup=sleep_mode_kb(False)
            )
        
        await callback.answer()
        
    except Exception as e:
        print(f"[ERROR] Error in toggle_sleep_mode: {str(e)}")
        await callback.answer("Произошла ошибка при изменении режима сна")

@router.message(AdminStates.setting_sleep_time)
@check_admin_session
async def process_sleep_time(message: Message, state: FSMContext):
    try:
        # Проверяем формат времени
        time_text = message.text.strip()
        if not time_text or len(time_text.split(':')) != 2:
            await message.answer(
                "❌ Неверный формат времени. Пожалуйста, используйте формат ЧЧ:ММ (например, 10:00)"
            )
            return
            
        hours, minutes = map(int, time_text.split(':'))
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            await message.answer(
                "❌ Неверное время. Часы должны быть от 0 до 23, минуты от 0 до 59"
            )
            return
            
        # Включаем режим сна с указанным временем
        await db.set_sleep_mode(True, time_text)
        
        await message.answer(
            f"🌙 Режим сна включен!\n\n"
            f"Магазин будет закрыт до {time_text}\n"
            f"Текущий статус: ✅ Включен",
            reply_markup=sleep_mode_kb(True)
        )
        await state.clear()
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат времени. Пожалуйста, используйте формат ЧЧ:ММ (например, 10:00)"
        )
    except Exception as e:
        print(f"[ERROR] Error in process_sleep_time: {str(e)}")
        await message.answer("Произошла ошибка при установке времени")
        await state.clear()

@router.callback_query(F.data == "back_to_admin_menu")
@check_admin_session
async def back_to_admin_menu_from_sleep(callback: CallbackQuery):
    await callback.message.edit_text(
        "Панель администратора",
        reply_markup=admin_main_menu()
    )
    await callback.answer()

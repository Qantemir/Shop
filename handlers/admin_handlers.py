from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime, timedelta
import asyncio
import logging

from config import ADMIN_ID, ADMIN_SWITCHING
from database.mongodb import db
from keyboards.admin_kb import (
    admin_main_menu,
    product_management_kb,
    categories_kb,
    order_management_kb,
    sleep_mode_kb
)
from keyboards.user_kb import main_menu
from utils.security import security_manager, check_admin_session, return_items_to_inventory
from utils.message_utils import safe_delete_message

router = Router()

logger = logging.getLogger(__name__)

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
    setting_flavor_quantity = State()  # Новое состояние для количества вкуса

class CancellationStates(StatesGroup):
    waiting_for_reason = State()

# Helper function to format price with decimal points
def format_price(price):
    return f"{float(price):.2f}"

@router.message(Command("admin"))#Обработка команды /admin/
async def admin_start(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if user_id != ADMIN_ID:
        logger.warning(f"Unauthorized /admin access by user {user_id}")
        await message.answer("У вас нет прав администратора.")
        return

    if not security_manager.check_failed_attempts(user_id):
        minutes = security_manager.get_block_time_remaining(user_id).seconds // 60
        logger.info(f"Blocked admin access for {user_id}. Wait {minutes} min")
        await message.answer(f"Слишком много неудачных попыток. Попробуйте снова через {minutes} минут.")
        return

    if security_manager.is_admin_session_valid(user_id):
        await message.answer("Добро пожаловать в админ-панель", reply_markup=admin_main_menu())
        return

    await message.answer("Введите пароль администратора:")
    await state.set_state(AdminStates.waiting_password)

@router.message(AdminStates.waiting_password)#Ожидание пароля
async def check_admin_password(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if user_id != ADMIN_ID:
        logger.warning(f"Unauthorized password attempt from user {user_id}")
        return

    result = security_manager.try_admin_login(user_id, message.text or "")
    
    if result['success']:
        logger.info(f"Admin login success for {user_id}")
        await message.answer("Доступ разрешен.", reply_markup=admin_main_menu())
        await state.clear()
    elif result['blocked']:
        logger.warning(f"Admin access temporarily blocked for {user_id}")
        await message.answer(f"Доступ заблокирован на {result['block_time']} минут.")
        await state.clear()
    else:
        logger.warning(f"Incorrect password for {user_id}. Attempts left: {result['attempts_left']}")
        await message.answer(f"Неверный пароль. Осталось попыток: {result['attempts_left']}")

@router.message(Command("logout"))#Обработка команды /logout
@check_admin_session
async def admin_logout(message: Message):
    user_id = message.from_user.id

    try:
        security_manager.remove_admin_session(user_id)
    except Exception as e:
        logger.error(f"Ошибка при выходе администратора {user_id}: {e}")
        await message.answer(
            "Произошла ошибка при выходе из панели администратора.",
            reply_markup=main_menu()
        )
        return

    await message.answer(
        "✅ Вы успешно вышли из панели администратора.\n"
        "Для повторного входа используйте /admin",
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
            text += "\n🌈 Доступно:\n"
            for flavor in product['flavors']:
                flavor_name = flavor.get('name', '')
                flavor_quantity = flavor.get('quantity', 0)
                text += f"• {flavor_name} - {flavor_quantity} шт.\n"
        
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
            text += "\n🌈 Доступно:\n"
            for flavor in product['flavors']:
                flavor_name = flavor.get('name', '')
                flavor_quantity = flavor.get('quantity', 0)
                text += f"• {flavor_name} - {flavor_quantity} шт.\n"
        
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
            text += "\n🌈 Доступно:\n"
            for flavor in product['flavors']:
                flavor_name = flavor.get('name', '')
                flavor_quantity = flavor.get('quantity', 0)
                text += f"• {flavor_name} - {flavor_quantity} шт.\n"
        
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
            text += "\n🌈 Доступно:\n"
            for flavor in product['flavors']:
                flavor_name = flavor.get('name', '')
                flavor_quantity = flavor.get('quantity', 0)
                text += f"• {flavor_name} - {flavor_quantity} шт.\n"
        
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
            text += "\n🌈 Доступно:\n"
            for flavor in product['flavors']:
                flavor_name = flavor.get('name', '')
                flavor_quantity = flavor.get('quantity', 0)
                text += f"• {flavor_name} - {flavor_quantity} шт.\n"
        
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

@router.message(F.text == "📊 Заказы")
@check_admin_session
async def show_orders(message: Message):
    try:
        # Ensure database connection
        await db.ensure_connected()
        
        # Get all orders
        orders = await db.get_all_orders()
        
        if not orders:
            await message.answer("Нет активных заказов")
            return
            
        # Count active orders (pending + confirmed)
        active_count = len([order for order in orders if order.get('status') in ['pending', 'confirmed']])
        
        # Create keyboard with delete all orders button
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить все заказы", callback_data="delete_all_orders")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_menu")]
        ])

        # Show active orders count
        await message.answer(
            f"📊 Статистика заказов:\n"
            f"📦 Активных заказов: {active_count}/{ADMIN_SWITCHING}\n"
            f"⚠️ Магазин уйдет в режим сна при достижении {ADMIN_SWITCHING} активных заказов",
            reply_markup=keyboard
        )

        # Check if we need to enable sleep mode
        if active_count >= ADMIN_SWITCHING:
            # Set sleep mode for 2 hours
            end_time = (datetime.now() + timedelta(hours=2)).strftime("%H:%M")
            await db.set_sleep_mode(True, end_time)
            await message.answer(
                f"⚠️ Внимание! Достигнут лимит активных заказов ({active_count}).\n"
                f"Магазин переведен в режим сна до {end_time}."
            )
            
        # Show orders list
        for order in orders:
            # Ensure we have user data
            user_data = {
                'full_name': order.get('username', 'Не указано'),
                'username': order.get('username', 'Не указано')
            }
            
            order_text = await format_order_notification(
                str(order["_id"]),
                user_data,
                order,
                order.get("items", []),
                order.get("total_amount", 0)
            )
            
            # Add status to the order text
            status_text = {
                'pending': '⏳ Ожидает обработки',
                'confirmed': '✅ Подтвержден',
                'cancelled': '❌ Отменен',
                'completed': '✅ Выполнен'
            }.get(order.get('status', 'pending'), 'Статус неизвестен')
            
            order_text += f"\n\nСтатус: {status_text}"
            
            # Send order with appropriate management buttons
            await message.answer(
                order_text,
                parse_mode="HTML",
                reply_markup=order_management_kb(str(order["_id"]), order.get('status', 'pending'))
            )

    except Exception as e:
        logger.error(f"Error showing orders: {str(e)}")
        await message.answer("Произошла ошибка при получении списка заказов.")

@router.callback_query(F.data == "delete_all_orders")
@check_admin_session
async def delete_all_orders(callback: CallbackQuery):
    try:
        # Ensure database connection
        await db.ensure_connected()
        
        # Get all orders
        orders = await db.get_all_orders()
        
        if not orders:
            await callback.answer("Нет заказов для удаления")
            return
            
        # Delete all orders
        for order in orders:
            # Return items to inventory if order was confirmed
            if order.get('status') == 'confirmed':
                for item in order.get('items', []):
                    if 'flavor' in item:
                        try:
                            await db.update_product_flavor_quantity(
                                item['product_id'],
                                item['flavor'],
                                item['quantity']  # Return the full quantity
                            )
                        except Exception as e:
                            logger.error(f"Error returning item to inventory: {str(e)}")
                            continue
            
            try:
                # Delete the order
                await db.delete_order(str(order['_id']))
            except Exception as e:
                logger.error(f"Error deleting order {order['_id']}: {str(e)}")
                continue
        
        # Notify admin
        await callback.message.edit_text(
            "✅ Все заказы успешно удалены",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_menu")]
            ])
        )
        await callback.answer("Все заказы удалены")
        
    except Exception as e:
        logger.error(f"Error deleting all orders: {str(e)}")
        await callback.answer("Произошла ошибка при удалении заказов")

@router.callback_query(F.data == "confirm_delete_all_orders")
@check_admin_session
async def confirm_delete_all_orders(callback: CallbackQuery):
    try:
        # Delete all orders
        success = await db.delete_all_orders()
        if success:
            # Disable sleep mode since orders are cleared
            await db.set_sleep_mode(False)
            await callback.message.edit_text(
                "✅ Все заказы успешно удалены.\n"
                "Магазин снова открыт для работы."
            )
        else:
            await callback.message.edit_text(
                "❌ Произошла ошибка при удалении заказов."
            )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in confirm_delete_all_orders: {str(e)}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data == "cancel_delete_all_orders")
@check_admin_session
async def cancel_delete_all_orders(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            "❌ Удаление заказов отменено."
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in cancel_delete_all_orders: {str(e)}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("order_status_"))
@check_admin_session
async def update_order_status(callback: CallbackQuery):
    try:
        _, order_id, new_status = callback.data.split("_")
        order = await db.get_order(order_id)
        
        if not order:
            await callback.answer("Заказ не найден")
            return
            
        # Check if order is already cancelled
        if order.get('status') == 'cancelled':
            await callback.answer("Нельзя изменить статус отмененного заказа", show_alert=True)
            return
            
        # Handle flavor quantities based on status change
        if new_status == 'confirmed' and order.get('status') != 'confirmed':
            # Deduct flavors from inventory
            for item in order['items']:
                product = await db.get_product(item['product_id'])
                if product and 'flavor' in item:
                    flavors = product.get('flavors', [])
                    flavor = next((f for f in flavors if f.get('name') == item['flavor']), None)
                    if flavor:
                        # Check if we have enough quantity
                        if flavor.get('quantity', 0) < item['quantity']:
                            await callback.answer("Недостаточно товара на складе", show_alert=True)
                            return
                        try:
                            flavor['quantity'] -= item['quantity']
                            await db.update_product(item['product_id'], {'flavors': flavors})
                        except Exception as e:
                            print(f"[ERROR] Failed to update flavor quantity: {str(e)}")
                            await callback.answer("Ошибка при обновлении количества товара", show_alert=True)
                            return
        elif new_status == 'cancelled' and order.get('status') == 'confirmed':
            # Return flavors to inventory
            for item in order['items']:
                product = await db.get_product(item['product_id'])
                if product and 'flavor' in item:
                    flavors = product.get('flavors', [])
                    flavor = next((f for f in flavors if f.get('name') == item['flavor']), None)
                    if flavor:
                        try:
                            flavor['quantity'] += item['quantity']
                            await db.update_product(item['product_id'], {'flavors': flavors})
                        except Exception as e:
                            print(f"[ERROR] Failed to return flavor to inventory: {str(e)}")
                            await callback.answer("Ошибка при возврате вкусов в инвентарь", show_alert=True)
                            return
        
        # Update order status
        await db.update_order(order_id, {'status': new_status})
        
        # Notify user about status change
        status_messages = {
            "paid": (
                "💰 Оплата подтверждена!\n\n"
                "Ваш заказ передан в обработку. "
                "Ожидайте подтверждения от администратора."
            ),
            "confirmed": (
                "✅ Ваш заказ подтвержден и будет отправлен в течение 1-2 часов!\n\n"
                "Спасибо за ваш заказ. Мы отправим вам уведомление, "
                "как только заказ будет передан в доставку."
            ),
            "cancelled": (
                "❌ К сожалению, ваш заказ был отменен.\n"
                "Пожалуйста, свяжитесь с администратором для уточнения деталей."
            ),
            "completed": (
                "🎉 Ваш заказ выполнен и передан в доставку!\n"
                "Спасибо за покупку в нашем магазине!"
            )
        }
        
        if new_status in status_messages:
            try:
                # Send status update to user
                await callback.bot.send_message(
                    chat_id=order['user_id'],
                    text=f"📦 Обновление статуса заказа #{order_id}:\n\n{status_messages[new_status]}"
                )
                
                # If order is confirmed, send additional delivery info
                if new_status == "confirmed":
                    delivery_info = (
                        "🚚 Информация о доставке:\n\n"
                        "• Доставка осуществляется в течение 1-2 часов\n"
                        "• Курьер свяжется с вами перед доставкой\n"
                        "• Пожалуйста, подготовьте документ, удостоверяющий личность\n\n"
                        "По всем вопросам обращайтесь к администратору."
                    )
                    await callback.bot.send_message(
                        chat_id=order['user_id'],
                        text=delivery_info
                    )
            except Exception as e:
                print(f"[ERROR] Failed to notify user about order status: {str(e)}")
        
        # Update admin's message
        ORDER_STATUSES = {
            'pending': '⏳ Ожидает обработки',
            'confirmed': '✅ Подтвержден',
            'cancelled': '❌ Отменен',
            'completed': '✅ Выполнен'
        }
        status_text = ORDER_STATUSES.get(new_status, "Статус неизвестен")
        await callback.message.edit_text(
            f"{callback.message.text.split('Статус:')[0]}\nСтатус: {status_text}",
            reply_markup=order_management_kb(order_id)
        )
        await callback.answer(f"Статус заказа обновлен: {status_text}")
        
    except Exception as e:
        print(f"[ERROR] Error in update_order_status: {str(e)}")
        await callback.answer("Произошла ошибка при обновлении статуса")

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
            flavor_name = flavor.get('name', '')
            flavor_quantity = flavor.get('quantity', 0)
            keyboard.append([
                InlineKeyboardButton(
                    text=f"❌ {flavor_name} ({flavor_quantity} шт.)",
                    callback_data=f"delete_flavor_{product_id}_{i}"
                )
            ])
            keyboard.append([
                InlineKeyboardButton(
                    text=f"➕ Добавить количество для {flavor_name}",
                    callback_data=f"add_flavor_quantity_{product_id}_{i}"
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
            text += "В наличии:\n"
            for i, flavor in enumerate(flavors, 1):
                flavor_name = flavor.get('name', '')
                flavor_quantity = flavor.get('quantity', 0)
                text += f"{i}. {flavor_name} - {flavor_quantity} шт.\n"
        else:
            text += "Товара пока нет в наличии\n"
        
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
            removed_flavor = flavors[index].get('name', '')
            flavors.pop(index)
            await db.update_product(product_id, {'flavors': flavors})
            
            # Update keyboard
            keyboard = []
            for i, flavor in enumerate(flavors):
                flavor_name = flavor.get('name', '')
                flavor_quantity = flavor.get('quantity', 0)
                keyboard.append([
                    InlineKeyboardButton(
                        text=f"❌ {flavor_name} ({flavor_quantity} шт.)",
                        callback_data=f"delete_flavor_{product_id}_{i}"
                    )
                ])
                keyboard.append([
                    InlineKeyboardButton(
                        text=f"➕ Добавить количество для {flavor_name}",
                        callback_data=f"add_flavor_quantity_{product_id}_{i}"
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
                    flavor_name = flavor.get('name', '')
                    flavor_quantity = flavor.get('quantity', 0)
                    text += f"{i}. {flavor_name} - {flavor_quantity} шт.\n"
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

@router.callback_query(F.data.startswith("add_flavor_quantity_"))
@check_admin_session
async def start_add_flavor_quantity(callback: CallbackQuery, state: FSMContext):
    try:
        # Format: add_flavor_quantity_PRODUCTID_INDEX
        _, product_id, index = callback.data.rsplit("_", 2)
        index = int(index)
        
        # Get product
        product = await db.get_product(product_id)
        if not product:
            await callback.answer("Товар не найден")
            return
            
        flavors = product.get('flavors', [])
        if 0 <= index < len(flavors):
            flavor = flavors[index]
            await state.update_data(
                editing_product_id=product_id,
                editing_flavor_index=index
            )
            
            await callback.message.edit_text(
                f"Текущее количество для вкуса '{flavor.get('name')}': {flavor.get('quantity', 0)} шт.\n\n"
                "Введите новое количество (только число):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🔙 Отмена", callback_data=f"manage_flavors_{product_id}")
                ]])
            )
            await state.set_state(AdminStates.setting_flavor_quantity)
            await callback.answer()
        else:
            await callback.answer("Вкус не найден")
            
    except Exception as e:
        print(f"[ERROR] Error in start_add_flavor_quantity: {str(e)}")
        await callback.answer("Произошла ошибка")

@router.message(AdminStates.setting_flavor_quantity)
@check_admin_session
async def process_flavor_quantity(message: Message, state: FSMContext):
    try:
        if not message.text.isdigit():
            await message.answer("Пожалуйста, введите только число")
            return
            
        quantity = int(message.text)
        data = await state.get_data()
        product_id = data.get('editing_product_id')
        flavor_index = data.get('editing_flavor_index')
        
        if not product_id or flavor_index is None:
            await message.answer("Ошибка: информация о товаре не найдена")
            await state.clear()
            return
            
        # Get product
        product = await db.get_product(product_id)
        if not product:
            await message.answer("Товар не найден")
            await state.clear()
            return
            
        flavors = product.get('flavors', [])
        if 0 <= flavor_index < len(flavors):
            flavors[flavor_index]['quantity'] = quantity
            await db.update_product(product_id, {'flavors': flavors})
            
            # Create keyboard for flavor management
            keyboard = []
            for i, flavor in enumerate(flavors):
                flavor_name = flavor.get('name', '')
                flavor_quantity = flavor.get('quantity', 0)
                keyboard.append([
                    InlineKeyboardButton(
                        text=f"❌ {flavor_name} ({flavor_quantity} шт.)",
                        callback_data=f"delete_flavor_{product_id}_{i}"
                    )
                ])
                keyboard.append([
                    InlineKeyboardButton(
                        text=f"➕ Добавить количество для {flavor_name}",
                        callback_data=f"add_flavor_quantity_{product_id}_{i}"
                    )
                ])
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
                    flavor_name = flavor.get('name', '')
                    flavor_quantity = flavor.get('quantity', 0)
                    text += f"{i}. {flavor_name} - {flavor_quantity} шт.\n"
            else:
                text += "У товара пока нет вкусов\n"
            
            text += "\nНажмите на вкус чтобы удалить его, или добавьте новый"
            
            await message.answer(text, reply_markup=markup)
        else:
            await message.answer("Вкус не найден")
            
        await state.clear()
        
    except Exception as e:
        print(f"[ERROR] Error in process_flavor_quantity: {str(e)}")
        await message.answer("Произошла ошибка при обновлении количества")
        await state.clear()

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
            "Введите название нового вкуса:",
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
        
        # Check if flavor name already exists
        if any(flavor.get('name') == new_flavor for flavor in flavors):
            await message.answer(
                "Такой вкус уже существует!\n"
                "Введите другой вкус или нажмите Отмена для возврата.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🔙 Отмена", callback_data=f"manage_flavors_{product_id}")
                ]])
            )
            return
            
        # Add new flavor with initial quantity 0
        flavors.append({
            'name': new_flavor,
            'quantity': 0
        })
        
        # Update product with new flavor
        await db.update_product(product_id, {'flavors': flavors})
        
        # Create keyboard for flavor management
        keyboard = []
        for i, flavor in enumerate(flavors):
            flavor_name = flavor.get('name', '')
            flavor_quantity = flavor.get('quantity', 0)
            keyboard.append([
                InlineKeyboardButton(
                    text=f"❌ {flavor_name} ({flavor_quantity} шт.)",
                    callback_data=f"delete_flavor_{product_id}_{i}"
                )
            ])
            keyboard.append([
                InlineKeyboardButton(
                    text=f"➕ Добавить количество для {flavor_name}",
                    callback_data=f"add_flavor_quantity_{product_id}_{i}"
                )
            ])
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
                flavor_name = flavor.get('name', '')
                flavor_quantity = flavor.get('quantity', 0)
                text += f"{i}. {flavor_name} - {flavor_quantity} шт.\n"
        else:
            text += "У товара пока нет вкусов\n"
        
        text += "\nНажмите на вкус чтобы удалить его, или добавьте новый"
        
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
   • Настройте вкусы и их количество

2️⃣ <b>Редактирование товара:</b>
   • Изменение названия
   • Корректировка цены
   • Обновление описания
   • Замена фото
   • Управление вкусами и их количеством

3️⃣ <b>Управление вкусами:</b>
   • Добавление новых вкусов
   • Удаление существующих вкусов
   • Установка количества для каждого вкуса
   • Просмотр текущих вкусов и их количества

<b>📊 ЗАКАЗЫ</b>
• Просмотр всех заказов
• Подтверждение заказов
• Отмена заказов с указанием причины
• Удаление выполненных/отмененных заказов
• Автоматическая очистка старых заказов (24ч)
• Просмотр адреса с 2GIS ссылкой
• Просмотр чеков оплаты

<b>📢 РАССЫЛКА</b>
• Создание сообщения
• Предпросмотр перед отправкой
• Подтверждение отправки
• Статистика доставки сообщений

<b>😴 РЕЖИМ СНА</b>
• Включение/выключение режима сна
• Установка времени автоматического включения
• Блокировка заказов в нерабочее время

<b>⚠️ ВАЖНЫЕ ЗАМЕТКИ</b>
• Цены указываются в Tg
• Подтверждайте удаление товаров
• Указывайте причину отмены заказов
• Сессия активна до выхода
• Регулярно проверяйте количество товаров
• Следите за режимом сна магазина

<b>💡 СОВЕТЫ</b>
• Регулярно проверяйте заказы
• Своевременно обновляйте информацию о товарах
• Используйте качественные фото
• Пишите понятные описания
• Следите за количеством вкусов
• Проверяйте статус режима сна
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
   • Настройте вкусы и их количество

2️⃣ <b>Редактирование товара:</b>
   • Изменение названия
   • Корректировка цены
   • Обновление описания
   • Замена фото
   • Управление вкусами и их количеством

3️⃣ <b>Управление вкусами:</b>
   • Добавление новых вкусов
   • Удаление существующих вкусов
   • Установка количества для каждого вкуса
   • Просмотр текущих вкусов и их количества

<b>📊 ЗАКАЗЫ</b>
• Просмотр всех заказов
• Подтверждение заказов
• Отмена заказов с указанием причины
• Удаление выполненных/отмененных заказов
• Автоматическая очистка старых заказов (24ч)
• Просмотр адреса с 2GIS ссылкой
• Просмотр чеков оплаты

<b>📢 РАССЫЛКА</b>
• Создание сообщения
• Предпросмотр перед отправкой
• Подтверждение отправки
• Статистика доставки сообщений

<b>😴 РЕЖИМ СНА</b>
• Включение/выключение режима сна
• Установка времени автоматического включения
• Блокировка заказов в нерабочее время

<b>⚠️ ВАЖНЫЕ ЗАМЕТКИ</b>
• Цены указываются в Tg
• Подтверждайте удаление товаров
• Указывайте причину отмены заказов
• Сессия активна до выхода
• Регулярно проверяйте количество товаров
• Следите за режимом сна магазина

<b>💡 СОВЕТЫ</b>
• Регулярно проверяйте заказы
• Своевременно обновляйте информацию о товарах
• Используйте качественные фото
• Пишите понятные описания
• Следите за количеством вкусов
• Проверяйте статус режима сна
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
        if sleep_data is None:
            await message.answer("❌ Ошибка при получении статуса режима сна")
            return
            
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
        logger.error(f"Error in sleep_mode_menu: {str(e)}")
        await message.answer("❌ Произошла ошибка при получении статуса режима сна")

@router.callback_query(F.data == "toggle_sleep_mode")
@check_admin_session
async def toggle_sleep_mode(callback: CallbackQuery, state: FSMContext):
    try:
        # Получаем текущий статус
        sleep_data = await db.get_sleep_mode()
        if sleep_data is None:
            await callback.message.edit_text("❌ Ошибка при получении статуса режима сна")
            await callback.answer()
            return
            
        current_mode = sleep_data["enabled"]
        
        if not current_mode:  # Если включаем режим сна
            await callback.message.edit_text(
                "🕒 Введите время, до которого магазин будет закрыт\n"
                "❗❗МАГАЗИН НЕ ВЫХОДИТ ИЗ РЕЖИМА СНА АВТОМАТИЧЕСКИ❗❗\n"
                "Формат: ЧЧ:ММ (например, 10:00)",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_admin_menu")
                ]])
            )
            await state.set_state(AdminStates.setting_sleep_time)
        else:  # Если выключаем режим сна
            try:
                await db.set_sleep_mode(False, None)
                await callback.message.edit_text(
                    "🌙 Режим сна магазина\n\n"
                    "Текущий статус: ❌ Выключен\n\n"
                    "В режиме сна пользователи не смогут делать заказы.",
                    reply_markup=sleep_mode_kb(False)
                )
            except Exception as e:
                logger.error(f"Error setting sleep mode: {str(e)}")
                await callback.message.edit_text("❌ Ошибка при выключении режима сна")
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in toggle_sleep_mode: {str(e)}")
        await callback.answer("❌ Произошла ошибка при изменении режима сна")

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
        try:
            await db.set_sleep_mode(True, time_text)
            await message.answer(
                f"🌙 Режим сна включен!\n\n"
                f"Магазин будет закрыт до {time_text}\n"
                f"Текущий статус: ✅ Включен",
                reply_markup=sleep_mode_kb(True)
            )
        except Exception as e:
            logger.error(f"Error setting sleep mode: {str(e)}")
            await message.answer("❌ Ошибка при включении режима сна")
            
        await state.clear()
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат времени. Пожалуйста, используйте формат ЧЧ:ММ (например, 10:00)"
        )
    except Exception as e:
        logger.error(f"Error in process_sleep_time: {str(e)}")
        await message.answer("❌ Произошла ошибка при установке времени режима сна")
        await state.clear()

@router.callback_query(F.data == "back_to_admin_menu")
@check_admin_session
async def back_to_admin_menu_from_sleep(callback: CallbackQuery):
    await callback.message.edit_text(
        "Панель администратора",
        reply_markup=admin_main_menu()
    )
    await callback.answer()

async def format_order_notification(order_id: str, user_data: dict, order_data: dict, cart: list, total: float) -> str:
    """Format order notification for admin"""
    # Safely get user data with fallbacks
    full_name = user_data.get('full_name', 'Не указано')
    username = user_data.get('username', 'Не указано')
    
    text = (
        f"🆕 Новый заказ #{order_id}\n\n"
        f"👤 От: {full_name} (@{username})\n"
        f"📱 Телефон: {order_data.get('phone', 'Не указано')}\n"
        f"📍 Адрес: {order_data.get('address', 'Не указано')}\n"
        f"🗺 2GIS: {order_data.get('gis_link', 'Не указано')}\n\n"
        f"🛍 Товары:\n"
    )
    
    for item in cart:
        subtotal = item['price'] * item['quantity']
        text += f"- {item['name']}"
        if 'flavor' in item:
            text += f" (🌈 {item['flavor']})"
        text += f" x{item['quantity']} = {format_price(subtotal)} Tg\n"
    
    text += f"\n💰 Итого: {format_price(total)} Tg"
    return text

@router.callback_query(F.data.startswith("admin_confirm_"))
async def admin_confirm_order(callback: CallbackQuery):
    try:
        order_id = callback.data.replace("admin_confirm_", "")
        order = await db.get_order(order_id)
        
        if not order:
            await callback.answer("Заказ не найден")
            return
            
        # Check if order is already cancelled
        if order.get('status') == 'cancelled':
            await callback.answer("Нельзя подтвердить отмененный заказ", show_alert=True)
            return
            
        # Список товаров, которые нужно проверить на удаление
        products_to_check = set()
        
        # Update product quantities
        for item in order['items']:
            product = await db.get_product(item['product_id'])
            if product and 'flavor' in item:
                flavors = product.get('flavors', [])
                flavor = next((f for f in flavors if f.get('name') == item['flavor']), None)
                if flavor:
                    try:
                        flavor['quantity'] -= item['quantity']
                        await db.update_product(item['product_id'], {'flavors': flavors})
                        products_to_check.add(item['product_id'])
                    except Exception as e:
                        print(f"[ERROR] Failed to update flavor quantity: {str(e)}")
                        await callback.answer("Ошибка при обновлении количества товара", show_alert=True)
                        return

        # Удаляем карточку товара, если все вкусы закончились
        for product_id in products_to_check:
            product = await db.get_product(product_id)
            if product:
                flavors = product.get('flavors', [])
                if all(f.get('quantity', 0) == 0 for f in flavors):
                    try:
                        await db.delete_product(product_id)
                    except Exception as e:
                        print(f"[ERROR] Failed to delete empty product: {str(e)}")
        
        # Update order status
        try:
            await db.update_order(order_id, {'status': 'confirmed'})
            
            # Notify user about confirmation
            user_notification = (
                "✅ Ваш заказ подтверждён и будет отправлен в течение часа!\n\n"
                "❗❗❗ Стоимость доставки: 1000 Tg (оплачивается курьеру при получении) ❗❗❗\n"
                "🔍 Отслеживать посылку можно будет в приложении Яндекс, в аккаунте, привязанном к номеру, указанному при оформлении доставки.\n"
                "⚠️ ВАЖНО: Встречайте курьера лично - возврат средств за неполученный заказ не производится\n"
                "Спасибо за ваш заказ! ❤️\n"
            )
            
            try:
                await callback.bot.send_message(
                    chat_id=order['user_id'],
                    text=user_notification
                )
            except Exception as e:
                print(f"[ERROR] Failed to notify user about order confirmation: {str(e)}")
            
            # Delete the original message
            await safe_delete_message(callback.message)
            
            # Send confirmation to admin
            await callback.message.answer(
                f"✅ Заказ #{order_id} подтвержден передайте заказ курьеру в течение часа"
            )
            
            await callback.answer("Заказ подтвержден передайте заказ курьеру в течение часа")
        except Exception as e:
            print(f"[ERROR] Failed to update order status: {str(e)}")
            await callback.answer("Ошибка при подтверждении заказа", show_alert=True)
            return
            
    except Exception as e:
        print(f"[ERROR] Error in admin_confirm_order: {str(e)}")
        await callback.answer("Произошла ошибка при подтверждении заказа", show_alert=True)

@router.callback_query(F.data.startswith("delete_order_"))
@check_admin_session
async def delete_order(callback: CallbackQuery):
    try:
        logger.info("Starting delete_order handler")
        order_id = callback.data.replace("delete_order_", "")
        logger.info(f"Order ID to delete: {order_id}")
        
        # Get order details
        order = await db.get_order(order_id)
        if not order:
            logger.error(f"Order not found: {order_id}")
            await callback.answer("Заказ не найден")
            return
            
        logger.info(f"Found order: {order}")
        
        # Return all flavors to inventory using common function
        success = await return_items_to_inventory(order.get('items', []))
        if not success:
            await callback.answer("Ошибка при возврате товара на склад", show_alert=True)
            return
        
        # Delete the order
        logger.info("Deleting order from database")
        delete_result = await db.delete_order(order_id)
        if not delete_result:
            logger.error("Failed to delete order")
            await callback.answer("Ошибка при удалении заказа")
            return
        
        # Notify user about order cancellation
        try:
            await callback.bot.send_message(
                chat_id=order['user_id'],
                text="❌ Ваш заказ был отменен администратором."
            )
            logger.info(f"Sent cancellation notification to user {order['user_id']}")
        except Exception as e:
            logger.error(f"Error notifying user about order cancellation: {e}")
        
        # Update admin message
        await callback.message.edit_text(
            "✅ Заказ успешно отменен\nВсе товары возвращены на склад",
            reply_markup=order_management_kb()
        )
        await callback.answer("Заказ отменен")
        logger.info("Order successfully cancelled and items restored to inventory")
        
    except Exception as e:
        logger.error(f"Error in delete_order: {str(e)}", exc_info=True)
        await callback.answer("Произошла ошибка при отмене заказа")

@router.callback_query(F.data.startswith("admin_cancel_"))
@check_admin_session
async def admin_cancel_order(callback: CallbackQuery, state: FSMContext):
    try:
        order_id = callback.data.replace("admin_cancel_", "")
        order = await db.get_order(order_id)
        
        if not order:
            await callback.answer("Заказ не найден")
            return
            
        # Check if order is already cancelled
        if order.get('status') == 'cancelled':
            await callback.answer("Заказ уже отменен", show_alert=True)
            return
            
        # Save order info in state for cancellation reason
        await state.update_data({
            'order_id': order_id,
            'message_id': callback.message.message_id,
            'chat_id': callback.message.chat.id
        })
        
        # Ask for cancellation reason
        await callback.message.edit_text(
            f"❌ Отмена заказа #{order_id}\n\n"
            "Пожалуйста, укажите причину отмены заказа:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"back_to_order_{order_id}")]
            ])
        )
        
        await state.set_state(CancellationStates.waiting_for_reason)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in admin_cancel_order: {str(e)}")
        await callback.answer("Произошла ошибка при отмене заказа", show_alert=True)

@router.message(Command("admin_help"))
async def show_admin_help(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
        
    help_text = """🔧 Помощь по управлению магазином:

1️⃣ Управление товарами:
   • Добавление новых товаров
   • Редактирование существующих товаров
   • Управление количеством и вкусами
   • Удаление товаров

2️⃣ Управление заказами:
   • Просмотр новых заказов
   • Подтверждение заказов
   • Отмена заказов
   • Отслеживание статуса доставки

3️⃣ Режим сна:
   • Магазин автоматически уходит в сон при достижении 25 заказов
   • Ручное включение/выключение режима сна
   • Установка времени возобновления работы

4️⃣ Статистика:
   • Количество заказов
   • Популярные товары
   • Статусы доставки

⚠️ ВАЖНО:
• Следите за количеством заказов
• Своевременно обрабатывайте новые заказы
• Проверяйте статусы доставки
• При необходимости включайте режим сна"""
    
    await message.answer(help_text)

@router.message(Command("admin_guide"))
async def show_admin_guide(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
        
    guide_text = """📖 Руководство администратора:

1. Управление товарами:
   • Используйте /add_product для добавления товара
   • /edit_product для редактирования
   • /delete_product для удаления

2. Управление заказами:
   • /orders показывает все заказы
   • /pending показывает ожидающие заказы
   • Используйте кнопки управления для каждого заказа

3. Режим сна:
   • /sleep_mode для управления режимом
   • Автоматически включается при 25 заказах
   • Можно включить вручную при необходимости

4. Статистика:
   • /stats показывает общую статистику
   • /sales показывает продажи
   • /popular показывает популярные товары

⚠️ ВАЖНО:
• Регулярно проверяйте новые заказы
• Следите за количеством товаров
• Контролируйте статусы доставки
• При необходимости включайте режим сна"""
    
    await message.answer(guide_text)

@router.callback_query(F.data.startswith("back_to_order_"))
@check_admin_session
async def back_to_order_from_cancel(callback: CallbackQuery, state: FSMContext):
    try:
        order_id = callback.data.replace("back_to_order_", "")
        order = await db.get_order(order_id)
        
        if not order:
            await callback.answer("Заказ не найден")
            return
            
        # Format order text
        user_data = {
            'full_name': order.get('username', 'Не указано'),
            'username': order.get('username', 'Не указано')
        }
        
        order_text = await format_order_notification(
            str(order["_id"]),
            user_data,
            order,
            order.get("items", []),
            order.get("total_amount", 0)
        )
        
        # Add status to the order text
        status_text = {
            'pending': '⏳ Ожидает обработки',
            'confirmed': '✅ Подтвержден',
            'cancelled': '❌ Отменен',
            'completed': '✅ Выполнен'
        }.get(order.get('status', 'pending'), 'Статус неизвестен')
        
        order_text += f"\n\nСтатус: {status_text}"
        
        # Restore original order message
        await callback.message.edit_text(
            order_text,
            parse_mode="HTML",
            reply_markup=order_management_kb(str(order["_id"]), order.get('status', 'pending'))
        )
        
        await state.clear()
        await callback.answer("Отмена отмены заказа")
        
    except Exception as e:
        logger.error(f"Error in back_to_order_from_cancel: {str(e)}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.message(CancellationStates.waiting_for_reason)
async def admin_finish_cancel_order(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        order_id = data.get('order_id')
        original_message_id = data.get('message_id')
        chat_id = data.get('chat_id')
        
        if not order_id:
            await message.answer("Ошибка: не найден ID заказа")
            await state.clear()
            return
            
        order = await db.get_order(order_id)
        if not order:
            await message.answer("Ошибка: заказ не найден")
            await state.clear()
            return
            
        # Check if order is already cancelled
        if order.get('status') == 'cancelled':
            await message.answer("Заказ уже отменен")
            await state.clear()
            return
            
        logger.info(f"Processing order cancellation: {order}")
        
        # Return all items to inventory using common function
        success = await return_items_to_inventory(order.get('items', []))
        if not success:
            await message.answer("Ошибка при возврате товара на склад")
            await state.clear()
            return
        
        # Update order status and save cancellation reason
        await db.update_order(order_id, {
            'status': 'cancelled',
            'cancellation_reason': message.text
        })
        
        # Notify user about cancellation
        user_notification = (
            "❌ К сожалению, ваш заказ был отменен.\n\n"
            f"Причина: {message.text}\n\n"
            "Если у вас есть вопросы, пожалуйста, свяжитесь с нами."
        )
        
        try:
            await message.bot.send_message(
                chat_id=order['user_id'],
                text=user_notification
            )
        except Exception as e:
            logger.error(f"Failed to notify user about order cancellation: {e}")
        
        # Delete the original order message
        try:
            await safe_delete_message(message.bot, chat_id, original_message_id)
        except Exception as e:
            logger.error(f"Failed to delete original message: {e}")
        
        # Confirm to admin
        await message.answer(f"❌ Заказ #{order_id} отменен. Клиент уведомлен о причине отмены.")
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error in admin_finish_cancel_order: {str(e)}", exc_info=True)
        await message.answer("Произошла ошибка при отмене заказа")
        await state.clear()

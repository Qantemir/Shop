from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import ADMIN_ID
from database.mongodb import db
from keyboards.admin_kb import (
    admin_main_menu,
    product_management_kb,
    categories_kb,
    order_management_kb,
    confirm_action_kb
)
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
async def admin_logout(message: Message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        security_manager.remove_admin_session(user_id)
        await message.answer("Вы вышли из панели администратора.")

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
        await state.set_state(AdminStates.adding_product)
        print(f"[DEBUG] State set to: {AdminStates.adding_product}")
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
        text += f"📦 {product['name']} - {product['price']} RUB\n"
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
        text += f"📦 {product['name']} - {product['price']} RUB\n"
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
    product_id = callback.data.replace("edit_product_", "")
    product = await db.get_product(product_id)
    if not product:
        await callback.message.edit_text("Товар не найден")
        await callback.answer()
        return
    
    await state.update_data(editing_product_id=product_id)
    keyboard = [
        [InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"edit_name_{product_id}")],
        [InlineKeyboardButton(text="💰 Изменить цену", callback_data=f"edit_price_{product_id}")],
        [InlineKeyboardButton(text="📝 Изменить описание", callback_data=f"edit_description_{product_id}")],
        [InlineKeyboardButton(text="🖼 Изменить фото", callback_data=f"edit_photo_{product_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_product_management")]
    ]
    
    text = f"Редактирование товара:\n\n"
    text += f"📦 Название: {product['name']}\n"
    text += f"💰 Цена: {product['price']} RUB\n"
    text += f"📝 Описание: {product['description']}\n"
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

@router.callback_query(F.data.startswith("edit_name_"))
@check_admin_session
async def edit_product_name(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.editing_product)
    await callback.message.edit_text("Введите новое название товара:")
    await callback.answer()

@router.callback_query(F.data.startswith("edit_price_"))
@check_admin_session
async def edit_product_price(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.setting_price)
    await callback.message.edit_text("Введите новую цену товара (только число):")
    await callback.answer()

@router.callback_query(F.data.startswith("edit_description_"))
@check_admin_session
async def edit_product_description(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.setting_description)
    await callback.message.edit_text("Введите новое описание товара:")
    await callback.answer()

@router.callback_query(F.data.startswith("edit_photo_"))
@check_admin_session
async def edit_product_photo(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.setting_image)
    await callback.message.edit_text("Отправьте новую фотографию товара:")
    await callback.answer()

@router.message(AdminStates.editing_product)
@check_admin_session
async def process_new_name(message: Message, state: FSMContext):
    data = await state.get_data()
    product_id = data.get('editing_product_id')
    
    await db.update_product(product_id, {'name': message.text})
    await message.answer("Название товара успешно обновлено!", reply_markup=product_management_kb())
    await state.clear()

@router.message(F.text == "📊 Заказы")
async def show_orders(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    orders = await db.get_all_orders()
    if not orders:
        await message.answer("Заказы отсутствуют")
        return
    
    for order in orders:
        text = f"Заказ #{order['_id']}\n"
        text += f"От: {order['user_id']}\n"
        text += f"Статус: {order['status']}\n"
        text += "Товары:\n"
        
        total = 0
        for item in order['items']:
            text += f"- {item['name']} x{item['quantity']} = {item['price'] * item['quantity']} RUB\n"
            total += item['price'] * item['quantity']
        
        text += f"\nИтого: {total} RUB"
        await message.answer(text, reply_markup=order_management_kb(str(order['_id'])))

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
        
        users = await db.get_all_users()
        sent_count = 0
        
        for user in users:
            try:
                await message.bot.send_message(user['user_id'], broadcast_text)
                sent_count += 1
            except Exception as e:
                continue
        
        await message.answer(
            f"Рассылка завершена!\nСообщение получили {sent_count} пользователей.",
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
        current_state = await state.get_state()
        print(f"[DEBUG] Current state: {current_state}")
        
        if current_state != AdminStates.adding_product:
            print("[DEBUG] Invalid state transition")
            await callback.message.edit_text(
                "Ошибка состояния. Начните сначала.",
                reply_markup=product_management_kb()
            )
            await callback.answer()
            return

        category = callback.data.replace("add_to_", "")
        print(f"[DEBUG] Selected category: {category}")
        
        # Сохраняем категорию и переходим к вводу названия
        await state.update_data(category=category)
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

@router.message(AdminStates.setting_name)
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

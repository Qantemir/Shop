from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from database.mongodb import db
from keyboards.user_kb import (
    main_menu,
    catalog_menu,
    product_actions_kb,
    cart_actions_kb,
    cart_item_kb,
    confirm_order_kb,
    help_menu
)

router = Router()

class OrderStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_address = State()

@router.message(Command("start"))
async def cmd_start(message: Message):
    try:
        # Check if user already exists
        existing_user = await db.get_user(message.from_user.id)
        
        if not existing_user:
            user_data = {
                "user_id": message.from_user.id,
                "username": message.from_user.username,
                "first_name": message.from_user.first_name,
                "last_name": message.from_user.last_name,
                "cart": []
            }
            await db.create_user(user_data)
            print(f"[DEBUG] Created new user: {message.from_user.id}")
        
        await message.answer(
            "Добро пожаловать в наш магазин!",
            reply_markup=main_menu()
        )
    except Exception as e:
        print(f"[ERROR] Error in start command: {str(e)}")
        await message.answer("Произошла ошибка при запуске бота. Пожалуйста, попробуйте позже.")

@router.message(F.text == "🛍 Каталог")
async def show_catalog(message: Message):
    await message.answer(
        "Выберите категорию:",
        reply_markup=catalog_menu()
    )

@router.callback_query(F.data.startswith("category_"))
async def show_category(callback: CallbackQuery):
    category = callback.data.replace("category_", "")
    products = await db.get_products_by_category(category)
    
    if not products:
        await callback.message.answer("В данной категории нет товаров")
        return
    
    for product in products:
        caption = f"📦 {product['name']}\n"
        caption += f"💰 {product['price']} RUB\n"
        caption += f"📝 {product['description']}"
        
        await callback.message.answer_photo(
            photo=product['photo'],
            caption=caption,
            reply_markup=product_actions_kb(str(product['_id']))
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("add_to_cart_"))
async def add_to_cart(callback: CallbackQuery):
    print("[DEBUG] Starting add_to_cart handler")
    try:
        product_id = callback.data.replace("add_to_cart_", "")
        print(f"[DEBUG] Product ID: {product_id}")
        
        # First, ensure user exists in database
        user = await db.get_user(callback.from_user.id)
        if not user:
            print("[DEBUG] User not found, creating new user")
            user_data = {
                "user_id": callback.from_user.id,
                "username": callback.from_user.username,
                "first_name": callback.from_user.first_name,
                "last_name": callback.from_user.last_name,
                "cart": []
            }
            await db.create_user(user_data)
            user = await db.get_user(callback.from_user.id)  # Get fresh user data
            
            if not user:
                print("[ERROR] Failed to create/retrieve user")
                await callback.answer("Произошла ошибка. Пожалуйста, попробуйте /start")
                return
        
        product = await db.get_product(product_id)
        print(f"[DEBUG] Found product: {product}")
        
        if not product:
            print("[DEBUG] Product not found")
            await callback.answer("Товар не найден")
            return
        
        # Initialize cart if it doesn't exist
        cart = user.get('cart', [])
        if cart is None:
            cart = []
        print(f"[DEBUG] Current cart: {cart}")
        
        # Create new cart item
        cart_item = {
            'product_id': str(product_id),
            'name': product['name'],
            'price': product['price'],
            'quantity': 1
        }
        
        # Check if product already in cart
        found = False
        for item in cart:
            if item.get('product_id') == str(product_id):
                item['quantity'] += 1
                found = True
                print(f"[DEBUG] Increased quantity for existing item: {item}")
                break
        
        if not found:
            cart.append(cart_item)
            print(f"[DEBUG] Added new item to cart: {cart_item}")
        
        print(f"[DEBUG] Updated cart: {cart}")
        
        # Update user's cart
        update_result = await db.update_user(callback.from_user.id, {'cart': cart})
        print(f"[DEBUG] Update result: {update_result}")
        
        await callback.answer("Товар добавлен в корзину!")
        print("[DEBUG] Successfully added to cart")
        
    except Exception as e:
        print(f"[ERROR] Error in add_to_cart: {str(e)}")
        await callback.answer("Произошла ошибка при добавлении товара. Попробуйте /start")

@router.message(F.text == "🛒 Корзина")
async def show_cart(message: Message):
    print("[DEBUG] Starting show_cart handler")
    try:
        # Check if user exists and create if not
        user = await db.get_user(message.from_user.id)
        if not user:
            print("[DEBUG] User not found in show_cart, creating new user")
            user_data = {
                "user_id": message.from_user.id,
                "username": message.from_user.username,
                "first_name": message.from_user.first_name,
                "last_name": message.from_user.last_name,
                "cart": []
            }
            await db.create_user(user_data)
            user = await db.get_user(message.from_user.id)
            
            if not user:
                print("[ERROR] Failed to create/retrieve user in show_cart")
                await message.answer("Пожалуйста, используйте команду /start для начала работы с ботом")
                return
        
        cart = user.get('cart', [])
        if cart is None:
            cart = []
        print(f"[DEBUG] Cart data: {cart}")
        
        if not cart:
            await message.answer("Ваша корзина пуста", reply_markup=main_menu())
            return
        
        total = 0
        text = "🛒 Ваша корзина:\n\n"
        
        for item in cart:
            subtotal = item['price'] * item['quantity']
            total += subtotal
            text += f"📦 {item['name']}\n"
            text += f"💰 {item['price']} Tg x {item['quantity']} = {subtotal} Tg\n"
            text += "➖➖➖➖➖➖➖➖\n"
        
        text += f"\n💵 Итого: {total} Tg"
        await message.answer(text, reply_markup=cart_actions_kb())
        print("[DEBUG] Cart displayed successfully")
        
    except Exception as e:
        print(f"[ERROR] Error in show_cart: {str(e)}")
        await message.answer("Произошла ошибка. Пожалуйста, попробуйте использовать команду /start")

@router.callback_query(F.data == "checkout")
async def start_checkout(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Пожалуйста, введите ваш номер телефона:")
    await state.set_state(OrderStates.waiting_for_phone)
    await callback.answer()

@router.message(OrderStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("Теперь введите адрес доставки:")
    await state.set_state(OrderStates.waiting_for_address)

@router.message(OrderStates.waiting_for_address)
async def process_address(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    cart = user.get('cart', [])
    
    if not cart:
        await message.answer("Ваша корзина пуста")
        await state.clear()
        return
    
    data = await state.get_data()
    
    order_data = {
        'user_id': message.from_user.id,
        'phone': data['phone'],
        'address': message.text,
        'items': cart,
        'status': 'pending',
        'total': sum(item['price'] * item['quantity'] for item in cart)
    }
    
    await db.create_order(order_data)
    await db.update_user(message.from_user.id, {'cart': []})
    
    await message.answer(
        "Спасибо за заказ! Мы свяжемся с вами в ближайшее время.",
        reply_markup=main_menu()
    )
    await state.clear()

@router.message(F.text == "📱 Мои заказы")
async def show_user_orders(message: Message):
    orders = await db.get_user_orders(message.from_user.id)
    
    if not orders:
        await message.answer("У вас пока нет заказов")
        return
    
    for order in orders:
        text = f"Заказ #{order['_id']}\n"
        text += f"Статус: {order['status']}\n"
        text += "Товары:\n"
        
        for item in order['items']:
            text += f"- {item['name']} x{item['quantity']} = {item['price'] * item['quantity']} RUB\n"
        
        text += f"\nИтого: {order['total']} RUB"
        await message.answer(text)

@router.callback_query(F.data == "clear_cart")
async def clear_cart(callback: CallbackQuery):
    await db.update_user(callback.from_user.id, {'cart': []})
    await callback.message.edit_text("Корзина очищена!")
    await callback.answer()

@router.message(F.text == "ℹ️ Помощь")
async def show_help_menu(message: Message):
    await message.answer(
        "Выберите раздел помощи:",
        reply_markup=help_menu()
    )

@router.callback_query(F.data == "help_contacts")
async def show_contacts(callback: CallbackQuery):
    text = """📞 Наши контакты:

☎️ Телефон: +7 (XXX) XXX-XX-XX
📱 WhatsApp: +7 (XXX) XXX-XX-XX
📧 Email: example@email.com
📍 Адрес: г. Город, ул. Улица, д. XX

Время работы:
Пн-Пт: 10:00 - 20:00
Сб-Вс: 11:00 - 18:00"""
    
    await callback.message.edit_text(text, reply_markup=help_menu())
    await callback.answer()

@router.callback_query(F.data == "help_how_to_order")
async def show_how_to_order(callback: CallbackQuery):
    text = """❓ Как сделать заказ:

1️⃣ Выберите товары в каталоге
2️⃣ Добавьте их в корзину
3️⃣ Перейдите в корзину
4️⃣ Нажмите "Оформить заказ"
5️⃣ Укажите контактные данные
6️⃣ Подтвердите заказ

После оформления заказа наш менеджер свяжется с вами для подтверждения."""
    
    await callback.message.edit_text(text, reply_markup=help_menu())
    await callback.answer()

@router.callback_query(F.data == "help_payment")
async def show_payment_info(callback: CallbackQuery):
    text = """💳 Способы оплаты:

1️⃣ Наличными при получении
2️⃣ Картой при получении
3️⃣ Онлайн-оплата (по согласованию)

Оплата производится только после подтверждения заказа менеджером."""
    
    await callback.message.edit_text(text, reply_markup=help_menu())
    await callback.answer()

@router.callback_query(F.data == "help_delivery")
async def show_delivery_info(callback: CallbackQuery):
    text = """🚚 Информация о доставке:

📦 Способы доставки:
- Самовывоз (бесплатно)
- Доставка курьером по городу
- Доставка в регионы

⏱ Сроки доставки:
- По городу: 1-2 дня
- В регионы: 3-7 дней

💰 Стоимость доставки:
- По городу: от XXX Tg
- В регионы: рассчитывается индивидуально

Точную стоимость и сроки доставки уточняйте у менеджера при оформлении заказа."""
    
    await callback.message.edit_text(text, reply_markup=help_menu())
    await callback.answer()

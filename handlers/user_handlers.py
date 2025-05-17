from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

from database.mongodb import db
from keyboards.user_kb import (
    main_menu,
    catalog_menu,
    product_actions_kb,
    cart_actions_kb,
    cart_item_kb,
    confirm_order_kb,
    help_menu,
    confirm_clear_cart_kb
)
from keyboards.admin_kb import order_management_kb
from config import ADMIN_ID, ADMIN_CARD

router = Router()

class OrderStates(StatesGroup):
    waiting_phone = State()
    waiting_address = State()
    waiting_payment = State()
    selecting_flavor = State()

class CancellationStates(StatesGroup):
    waiting_for_reason = State()

# Helper function to format price with decimal points
def format_price(price):
    return f"{float(price):.2f}"

@router.message(Command("start"))
async def cmd_start(message: Message):
    # Проверяем режим сна
    sleep_data = await db.get_sleep_mode()
    if sleep_data["enabled"]:
        end_time = sleep_data.get("end_time", "Не указано")
        # Create help button
        help_button = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="show_help")]
        ])
        await message.answer(
            f"😴 Магазин временно не работает.\n"
            f"Работа возобновится в {end_time}.\n"
            f"Пожалуйста, используйте /start когда время придет.",
            reply_markup=help_button
        )
        return
        
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
        
        # Create inline keyboard with help button
        help_button = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="ℹ️ Открыть раздел помощи", callback_data="show_help")]
        ])
        
        await message.answer(
            "Добро пожаловать в наш магазин! \n"
            "Наш магазин работает с 10:00 до 02:00\n"
            "(перед заказом внимательно прочитайте раздел помощь)",
            reply_markup=help_button
        )
        
        # Send main menu separately
        await message.answer("Выберите действие:", reply_markup=main_menu())
        
    except Exception as e:
        print(f"[ERROR] Error in start command: {str(e)}")
        await message.answer("Произошла ошибка при запуске бота. Пожалуйста, попробуйте позже.")

@router.message(F.text == "🛍 Каталог")
async def show_catalog(message: Message):
    # Проверяем режим сна
    sleep_data = await db.get_sleep_mode()
    if sleep_data["enabled"]:
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
        return

    await message.answer(
        "Выберите категорию:",
        reply_markup=catalog_menu()
    )

@router.callback_query(F.data.startswith("category_"))
async def show_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.replace("category_", "")
    products = await db.get_products_by_category(category)
    
    if not products:
        await callback.message.answer("В данной категории нет товаров")
        return
    
    for product in products:
        caption = f"📦 {product['name']}\n"
        caption += f"💰 {format_price(product['price'])} Tg\n"
        caption += f"📝 {product['description']}"
        
        product_id = str(product['_id'])
        print(f"[DEBUG] Showing product with ID: {product_id}")
        
        keyboard = product_actions_kb(product_id, False, product.get('flavors', []))
        
        try:
            await callback.message.answer_photo(
                photo=product['photo'],
                caption=caption,
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"[ERROR] Error showing product {product_id}: {str(e)}")
            await callback.message.answer(
                f"Ошибка при отображении товара {product['name']}"
            )
    
    await callback.answer()

@router.message(OrderStates.selecting_flavor)
async def handle_flavor_number(message: Message, state: FSMContext):
    try:
        # Get the number from message
        if not message.text.isdigit():
            await message.answer("Пожалуйста, отправьте только номер вкуса")
            return
            
        number = int(message.text)
        
        # Get product data from state
        data = await state.get_data()
        product_id = data.get('current_product_id')
        flavors = data.get('current_product_flavors', [])
        
        if not product_id or not flavors:
            await message.answer("Ошибка: информация о товаре не найдена")
            await state.clear()
            return
            
        # Check if number is valid
        if number < 1 or number > len(flavors):
            await message.answer(f"Пожалуйста, выберите номер от 1 до {len(flavors)}")
            return
            
        # Get the selected flavor
        selected_flavor = flavors[number - 1]
        
        # Get product
        product = await db.get_product(product_id)
        if not product:
            await message.answer("Товар не найден")
            await state.clear()
            return
            
        # Get or create user
        user = await db.get_user(message.from_user.id)
        if not user:
            user_data = {
                "user_id": message.from_user.id,
                "username": message.from_user.username,
                "first_name": message.from_user.first_name,
                "last_name": message.from_user.last_name,
                "cart": []
            }
            user = await db.create_user(user_data)
        
        # Initialize cart if needed
        cart = user.get('cart', [])
        if cart is None:
            cart = []
        
        # Check if product with same flavor already in cart
        found = False
        for item in cart:
            if item.get('product_id') == product_id and item.get('flavor') == selected_flavor:
                item['quantity'] += 1
                found = True
                break
        
        # Add new item if not found
        if not found:
            cart.append({
                'product_id': product_id,
                'name': product['name'],
                'price': product['price'],
                'quantity': 1,
                'flavor': selected_flavor
            })
        
        # Update cart
        await db.update_user(message.from_user.id, {'cart': cart})
        await message.answer(f"Товар ({selected_flavor}) добавлен в корзину!")
        await state.clear()
        
    except Exception as e:
        print(f"[ERROR] Error in handle_flavor_number: {str(e)}")
        await message.answer("Произошла ошибка при выборе вкуса")
        await state.clear()

@router.callback_query(F.data.startswith("select_flavor_"))
async def select_flavor(callback: CallbackQuery, state: FSMContext):
    print("[DEBUG] Starting select_flavor handler")
    try:
        # Get the full callback data
        full_data = callback.data
        print(f"[DEBUG] Full callback data: {full_data}")
        
        # Extract product_id and flavor correctly
        # Format is: select_flavor_PRODUCTID_FLAVOR
        # Remove 'select_flavor_' prefix first
        data_without_prefix = full_data.replace("select_flavor_", "")
        # Find the first underscore after product ID
        underscore_index = data_without_prefix.find("_")
        if underscore_index == -1:
            print("[DEBUG] Invalid callback data format")
            await callback.answer("Ошибка формата данных", show_alert=True)
            return
            
        product_id = data_without_prefix[:underscore_index]
        flavor = data_without_prefix[underscore_index + 1:]
        
        print(f"[DEBUG] Parsed product_id: {product_id}, flavor: {flavor}")
        
        # Get product first to validate it exists
        product = await db.get_product(product_id)
        print(f"[DEBUG] Retrieved product from DB: {product}")
        
        if not product:
            print(f"[DEBUG] Product not found in database: {product_id}")
            await callback.answer("Товар не найден или недоступен", show_alert=True)
            return
            
        # Get or create user
        user = await db.get_user(callback.from_user.id)
        if not user:
            user_data = {
                "user_id": callback.from_user.id,
                "username": callback.from_user.username,
                "first_name": callback.from_user.first_name,
                "last_name": callback.from_user.last_name,
                "cart": []
            }
            user = await db.create_user(user_data)
            print(f"[DEBUG] Created new user: {user}")
        
        # Initialize cart if needed
        cart = user.get('cart', [])
        if cart is None:
            cart = []
        
        print(f"[DEBUG] Current cart before update: {cart}")
        
        # Check if product with same flavor already in cart
        found = False
        for item in cart:
            if str(item.get('product_id')) == str(product_id) and item.get('flavor') == flavor:
                item['quantity'] += 1
                found = True
                print(f"[DEBUG] Increased quantity for existing item: {item}")
                break
        
        # Add new item if not found
        if not found:
            new_item = {
                'product_id': str(product_id),
                'name': product['name'],
                'price': int(product['price']),
                'quantity': 1,
                'flavor': flavor
            }
            cart.append(new_item)
            print(f"[DEBUG] Added new item to cart: {new_item}")
        
        print(f"[DEBUG] Cart after update: {cart}")
        
        # Update user's cart in database
        result = await db.update_user(callback.from_user.id, {'cart': cart})
        print(f"[DEBUG] Database update result: {result}")
        
        if result:
            await callback.answer(f"Товар ({flavor}) добавлен в корзину!", show_alert=True)
            # Show updated cart
            await show_cart_message(callback.message, user)
        else:
            await callback.answer("Ошибка при добавлении товара в корзину", show_alert=True)
        
    except Exception as e:
        print(f"[ERROR] Error in select_flavor: {str(e)}")
        await callback.answer("Произошла ошибка при добавлении товара в корзину", show_alert=True)

@router.callback_query(F.data.startswith("add_to_cart_"))
async def add_to_cart(callback: CallbackQuery):
    print("[DEBUG] Starting add_to_cart handler")
    try:
        product_id = callback.data.replace("add_to_cart_", "")
        print(f"[DEBUG] Attempting to add product with ID: {product_id}")
        
        # Get product first to validate it exists
        product = await db.get_product(product_id)
        print(f"[DEBUG] Retrieved product from DB: {product}")
        
        if not product:
            print(f"[DEBUG] Product not found in database: {product_id}")
            await callback.answer("Товар не найден или недоступен", show_alert=True)
            return
            
        # If product has flavors, show flavor selection keyboard
        if 'flavors' in product and product['flavors']:
            keyboard = []
            for flavor in product['flavors']:
                keyboard.append([
                    InlineKeyboardButton(
                        text=f"🌈 {flavor}",
                        callback_data=f"select_flavor_{product_id}_{flavor}"
                    )
                ])
            keyboard.append([
                InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_catalog")
            ])
            
            await callback.message.edit_caption(
                caption=f"📦 {product['name']}\n"
                f"💰 {format_price(product['price'])} Tg\n"
                f"📝 {product['description']}\n\n"
                "Выберите вкус:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
            )
            await callback.answer()
            return
            
        # Get or create user
        user = await db.get_user(callback.from_user.id)
        if not user:
            user_data = {
                "user_id": callback.from_user.id,
                "username": callback.from_user.username,
                "first_name": callback.from_user.first_name,
                "last_name": callback.from_user.last_name,
                "cart": []
            }
            user = await db.create_user(user_data)
            print(f"[DEBUG] Created new user: {user}")
        
        # Initialize cart if needed
        cart = user.get('cart', [])
        if cart is None:
            cart = []
        
        print(f"[DEBUG] Current cart before update: {cart}")
        
        # Check if product already in cart
        found = False
        for item in cart:
            if str(item.get('product_id')) == str(product_id):
                item['quantity'] += 1
                found = True
                print(f"[DEBUG] Increased quantity for existing item: {item}")
                break
        
        # Add new item if not found
        if not found:
            new_item = {
                'product_id': str(product_id),
                'name': product['name'],
                'price': int(product['price']),
                'quantity': 1
            }
            cart.append(new_item)
            print(f"[DEBUG] Added new item to cart: {new_item}")
        
        print(f"[DEBUG] Cart after update: {cart}")
        
        # Update user's cart in database
        result = await db.update_user(callback.from_user.id, {'cart': cart})
        print(f"[DEBUG] Database update result: {result}")
        
        if result:
            await callback.answer("Товар добавлен в корзину!", show_alert=True)
            # Show updated cart
            await show_cart_message(callback.message, user)
        else:
            await callback.answer("Ошибка при добавлении товара в корзину", show_alert=True)
        
    except Exception as e:
        print(f"[ERROR] Error in add_to_cart: {str(e)}")
        await callback.answer("Произошла ошибка при добавлении товара в корзину", show_alert=True)

async def show_cart_message(message, user):
    """Helper function to show cart contents"""
    if not user or not user.get('cart'):
        await message.answer("Ваша корзина пуста")
        return
    
    cart = user['cart']
    text = "🛒 Ваша корзина:\n\n"
    total = 0
    
    for item in cart:
        subtotal = item['price'] * item['quantity']
        text += f"📦 {item['name']}"
        if 'flavor' in item:
            text += f" (🌈 {item['flavor']})"
        text += f"\n💰 {format_price(item['price'])} Tg x {item['quantity']} = {format_price(subtotal)} Tg\n"
        text += "➖➖➖➖➖➖➖➖\n"
        total += subtotal
    
    text += f"\n💎 Итого: {format_price(total)} Tg"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear_cart")],
        [InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout")]
    ])
    
    await message.answer(text, reply_markup=keyboard)

@router.message(F.text == "🛒 Корзина")
async def show_cart(message: Message):
    # Проверяем режим сна
    sleep_data = await db.get_sleep_mode()
    if sleep_data["enabled"]:
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
        return

    user = await db.get_user(message.from_user.id)
    await show_cart_message(message, user)

@router.callback_query(F.data.startswith("increase_"))
async def increase_item(callback: CallbackQuery):
    try:
        product_id = callback.data.replace("increase_", "")
        print(f"[DEBUG] Increasing quantity for product: {product_id}")
        
        user = await db.get_user(callback.from_user.id)
        if not user or not user.get('cart'):
            await callback.answer("Корзина пуста")
            return
            
        cart = user['cart']
        item = next((item for item in cart if item['product_id'] == product_id), None)
        
        if item:
            item['quantity'] += 1
            await db.update_user(callback.from_user.id, {'cart': cart})
            
            subtotal = item['price'] * item['quantity']
            await callback.message.edit_text(
                f"📦 {item['name']}\n"
                f"💰 {item['price']} Tg x {item['quantity']} = {format_price(subtotal)} Tg",
                reply_markup=cart_item_kb(product_id)
            )
            await callback.answer("Количество увеличено")
        else:
            print(f"[DEBUG] Item not found in cart: {product_id}")
            await callback.answer("Товар не найден в корзине")
            
    except Exception as e:
        print(f"[ERROR] Error in increase_item: {str(e)}")
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data.startswith("decrease_"))
async def decrease_item(callback: CallbackQuery):
    try:
        product_id = callback.data.replace("decrease_", "")
        print(f"[DEBUG] Decreasing quantity for product: {product_id}")
        
        user = await db.get_user(callback.from_user.id)
        if not user or not user.get('cart'):
            await callback.answer("Корзина пуста")
            return
            
        cart = user['cart']
        item = next((item for item in cart if item['product_id'] == product_id), None)
        
        if item:
            if item['quantity'] > 1:
                item['quantity'] -= 1
                await db.update_user(callback.from_user.id, {'cart': cart})
                
                subtotal = item['price'] * item['quantity']
                await callback.message.edit_text(
                    f"📦 {item['name']}\n"
                    f"💰 {item['price']} Tg x {item['quantity']} = {format_price(subtotal)} Tg",
                    reply_markup=cart_item_kb(product_id)
                )
                await callback.answer("Количество уменьшено")
            else:
                await callback.answer("Используйте ❌ для удаления товара")
        else:
            print(f"[DEBUG] Item not found in cart: {product_id}")
            await callback.answer("Товар не найден в корзине")
            
    except Exception as e:
        print(f"[ERROR] Error in decrease_item: {str(e)}")
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data.startswith("remove_"))
async def remove_item(callback: CallbackQuery):
    try:
        product_id = callback.data.replace("remove_", "")
        print(f"[DEBUG] Removing product from cart: {product_id}")
        
        user = await db.get_user(callback.from_user.id)
        if not user or not user.get('cart'):
            await callback.answer("Корзина пуста")
            return
            
        cart = user['cart']
        # Remove item with matching product_id
        cart = [item for item in cart if item['product_id'] != product_id]
        await db.update_user(callback.from_user.id, {'cart': cart})
        
        await callback.message.delete()
        await callback.answer("Товар удален из корзины")
        
        if not cart:
            await callback.message.answer("Ваша корзина пуста", reply_markup=main_menu())
            
    except Exception as e:
        print(f"[ERROR] Error in remove_item: {str(e)}")
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data == "back_to_catalog")
async def back_to_catalog_handler(callback: CallbackQuery):
    try:
        # Delete the previous message with cart
        await callback.message.delete()
        
        # Show catalog menu
        await callback.message.answer(
            "Выберите категорию:",
            reply_markup=catalog_menu()
        )
        await callback.answer()
    except Exception as e:
        print(f"[ERROR] Error in back_to_catalog: {str(e)}")
        await callback.answer("Произошла ошибка при возврате к каталогу")

@router.callback_query(F.data == "confirm_clear_cart")
async def confirm_clear_cart(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            "Вы уверены, что хотите очистить корзину?",
            reply_markup=confirm_clear_cart_kb()
        )
        await callback.answer()
    except Exception as e:
        print(f"[ERROR] Error in confirm_clear_cart: {str(e)}")
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data == "clear_cart")
async def clear_cart(callback: CallbackQuery):
    try:
        # Clear user's cart in database
        await db.update_user(callback.from_user.id, {'cart': []})
        
        # Delete all previous cart item messages
        message_id = callback.message.message_id
        chat_id = callback.message.chat.id
        
        # Try to delete recent messages that might be cart items
        for i in range(message_id - 10, message_id + 1):
            try:
                await callback.bot.delete_message(chat_id, i)
            except:
                continue
        
        # Show empty cart message
        await callback.message.answer(
            "Корзина очищена! Вы можете продолжить покупки.",
            reply_markup=main_menu()
        )
        await callback.answer("Корзина успешно очищена")
        
    except Exception as e:
        print(f"[ERROR] Error in clear_cart: {str(e)}")
        await callback.answer("Произошла ошибка при очистке корзины")

@router.callback_query(F.data == "cancel_clear_cart")
async def cancel_clear_cart(callback: CallbackQuery):
    try:
        user = await db.get_user(callback.from_user.id)
        cart = user.get('cart', [])
        
        if not cart:
            await callback.message.edit_text(
                "Ваша корзина пуста",
                reply_markup=main_menu()
            )
        else:
            total = sum(item['price'] * item['quantity'] for item in cart)
            await callback.message.edit_text(
                f"💵 Итого: {format_price(total)} Tg",
                reply_markup=cart_actions_kb()
            )
        await callback.answer("Очистка корзины отменена")
        
    except Exception as e:
        print(f"[ERROR] Error in cancel_clear_cart: {str(e)}")
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data == "checkout")
async def start_checkout(callback: CallbackQuery, state: FSMContext):
    # Проверяем режим сна
    sleep_data = await db.get_sleep_mode()
    if sleep_data["enabled"]:
        end_time = sleep_data.get("end_time", "Не указано")
        await callback.message.answer(
            f"😴 Магазин временно не работает.\n"
            f"Работа возобновится в {end_time}.\n"
            f"Пожалуйста, используйте /start когда время придет."
        )
        await callback.answer()
        return
    
    user = await db.get_user(callback.from_user.id)
    if not user or not user.get('cart'):
        await callback.message.answer("Ваша корзина пуста")
        await callback.answer()
        return
    
    # Calculate total and prepare order items
    cart = user['cart']
    total = 0
    order_items = []
    
    for item in cart:
        subtotal = item['price'] * item['quantity']
        total += subtotal
        order_item = {
            'product_id': item['product_id'],
            'name': item['name'],
            'price': item['price'],
            'quantity': item['quantity']
        }
        if 'flavor' in item:
            order_item['flavor'] = item['flavor']
        order_items.append(order_item)
    
    # Save order details in state
    await state.update_data(
        order_items=order_items,
        total_amount=total
    )
    
    # Ask for phone number
    await callback.message.answer(
        "Для оформления заказа, пожалуйста, отправьте ваш номер телефона в формате +7XXXXXXXXXX"
    )
    await state.set_state(OrderStates.waiting_phone)
    await callback.answer()

@router.message(OrderStates.waiting_phone)
async def process_phone(message: Message, state: FSMContext):
    # Validate phone number format
    phone = message.text.strip()
    if not phone.startswith('+') or not phone[1:].isdigit() or len(phone) < 10:
        await message.answer("Пожалуйста, введите корректный номер телефона в формате +7XXXXXXXXXX")
        return
    
    # Save phone and ask for address
    await state.update_data(phone=phone)
    await message.answer(
        "Теперь отправьте ваш адрес доставки.\n"
        "Пожалуйста, укажите адрес доставки."
    )
    await state.set_state(OrderStates.waiting_address)

@router.message(OrderStates.waiting_address)
async def process_address(message: Message, state: FSMContext):
    # Get all order data
    data = await state.get_data()
    user = await db.get_user(message.from_user.id)
    
    # Save address and ask for payment
    await state.update_data(address=message.text)
    
    cart = user['cart']
    total = sum(item['price'] * item['quantity'] for item in cart)
    
    # Get admin card from config
    admin_card = ADMIN_CARD
    
    payment_text = (
        f"💳 Для оплаты заказа переведите {format_price(total)} Tg на карту:\n\n"
        f"<span class=\"tg-spoiler\"><code>{admin_card}</code></span>\n\n"
        "👆 Нажмите на номер карты, чтобы скопировать\n\n"
        "После оплаты отправьте скриншот чека."
    )
    
    await message.answer(payment_text, parse_mode="HTML")
    await state.set_state(OrderStates.waiting_payment)

@router.message(OrderStates.waiting_payment, F.photo)
async def process_payment(message: Message, state: FSMContext):
    try:
        # Get all order data
        data = await state.get_data()
        user = await db.get_user(message.from_user.id)
        cart = user['cart']
        total = sum(item['price'] * item['quantity'] for item in cart)
        
        # Create order data
        order_data = {
            'user_id': message.from_user.id,
            'username': message.from_user.username,
            'phone': data['phone'],
            'address': data['address'],
            'items': cart,
            'total_amount': total,
            'status': 'pending',
            'created_at': datetime.now(),
            'payment_photo': message.photo[-1].file_id
        }
        
        # Create order in database
        order_result = await db.create_order(order_data)
        order_id = str(order_result.inserted_id)
        
        # Clear user's cart
        await db.update_user(message.from_user.id, {'cart': []})
        
        # Send confirmation to user
        await message.answer(
            "✅ Спасибо! Ваш заказ принят и ожидает подтверждения оплаты.\n"
            "Мы уведомим вас, когда заказ будет подтвержден.",
            reply_markup=main_menu()
        )
        
        # Prepare admin notification
        admin_text = (
            f"🆕 Новый заказ #{order_id}\n\n"
            f"👤 От: {message.from_user.full_name} (@{message.from_user.username})\n"
            f"📱 Телефон: {data['phone']}\n"
            f"📍 Адрес: {data['address']}\n\n"
            f"🛍 Товары:\n"
        )
        
        for item in cart:
            subtotal = item['price'] * item['quantity']
            admin_text += f"- {item['name']}"
            if 'flavor' in item:
                admin_text += f" (🌈 {item['flavor']})"
            admin_text += f" x{item['quantity']} = {format_price(subtotal)} Tg\n"
        
        admin_text += f"\n💰 Итого: {format_price(total)} Tg"
        
        # Send notification and payment photo to admin
        try:
            # First send the order details
            await message.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                parse_mode="HTML"
            )
            
            # Then send the payment screenshot
            await message.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=message.photo[-1].file_id,
                caption=f"💳 Скриншот оплаты для заказа #{order_id}",
                reply_markup=order_management_kb(order_id)
            )
            
            print(f"[DEBUG] Successfully notified admin about order {order_id}")
        except Exception as e:
            print(f"[ERROR] Failed to notify admin about order {order_id}: {str(e)}")
        
        await state.clear()
        
    except Exception as e:
        print(f"[ERROR] Error in process_payment: {str(e)}")
        await message.answer(
            "Произошла ошибка при обработке оплаты. Пожалуйста, попробуйте позже.",
            reply_markup=main_menu()
        )
        await state.clear()

@router.message(OrderStates.waiting_payment)
async def wrong_payment_proof(message: Message):
    await message.answer(
        "Пожалуйста, отправьте скриншот чека об оплате в виде фотографии."
    )

@router.message(F.text == "ℹ️ Помощь")
async def show_help_menu(message: Message):
    await message.answer(
        "Выберите раздел помощи:",
        reply_markup=help_menu()
    )

@router.callback_query(F.data == "help_contacts")
async def show_contacts(callback: CallbackQuery):
    text = """📞 Наши контакты:

Telegram: @Dimka_44"""
    
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

После оформления заказа ожидайте потверждения менеджера"""
    
    await callback.message.edit_text(text, reply_markup=help_menu())
    await callback.answer()

@router.callback_query(F.data == "help_payment")
async def show_payment_info(callback: CallbackQuery):
    text = """💳 Способы оплаты:

Онлайн-оплата"""
    
    await callback.message.edit_text(text, reply_markup=help_menu())
    await callback.answer()

@router.callback_query(F.data == "help_delivery")
async def show_delivery_info(callback: CallbackQuery):
    text = """🚚 Информация о доставке:

📦 Способы доставки:
- Доставка курьером по городу

⏱ Сроки доставки:
- По городу: В течении дня

💰 Стоимость доставки:
- По городу: Яндекс.Курьером(Стоимость рассчитывается индивидуально)"""
    
    await callback.message.edit_text(text, reply_markup=help_menu())
    await callback.answer()

# Add handler for order status updates (notifications to users)
@router.callback_query(F.data.startswith("order_status_"))
async def handle_order_status_update(callback: CallbackQuery):
    try:
        _, order_id, new_status = callback.data.split("_")
        order = await db.get_order(order_id)
        
        if not order:
            await callback.answer("Заказ не найден")
            return
            
        # Update order status
        await db.update_order_status(order_id, new_status)
        
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
        status_text = ORDER_STATUSES.get(new_status, "Статус неизвестен")
        await callback.message.edit_text(
            f"{callback.message.text.split('Статус:')[0]}\nСтатус: {status_text}",
            reply_markup=order_management_kb(order_id)
        )
        await callback.answer(f"Статус заказа обновлен: {status_text}")
        
    except Exception as e:
        print(f"[ERROR] Error in handle_order_status_update: {str(e)}")
        await callback.answer("Произошла ошибка при обновлении статуса")

@router.callback_query(F.data.startswith("admin_confirm_"))
async def admin_confirm_order(callback: CallbackQuery):
    try:
        order_id = callback.data.replace("admin_confirm_", "")
        order = await db.get_order(order_id)
        
        if not order:
            await callback.answer("Заказ не найден")
            return
            
        # Update order status
        await db.update_order_status(order_id, "confirmed")
        
        # Notify user about confirmation
        user_notification = (
            "✅ Ваш заказ подтвержден!\n\n"
            "🚚 Доставка будет осуществляться Яндекс.Доставкой в течение часа.(Доставка на месте)\n"
            "📱 Курьер свяжется с вами перед доставкой.\n\n"
            "Спасибо за ваш заказ! 🙏"
        )
        
        try:
            await callback.bot.send_message(
                chat_id=order['user_id'],
                text=user_notification
            )
        except Exception as e:
            print(f"[ERROR] Failed to notify user about order confirmation: {str(e)}")
        
        # Delete the original message
        await callback.message.delete()
        
        # Send confirmation to admin
        await callback.message.answer(
            f"✅ Заказ #{order_id} подтвержден и передан в доставку"
        )
        
        await callback.answer("Заказ подтвержден и передан в доставку")
        
    except Exception as e:
        print(f"[ERROR] Error in admin_confirm_order: {str(e)}")
        await callback.answer("Произошла ошибка при подтверждении заказа")

@router.callback_query(F.data.startswith("admin_cancel_"))
async def admin_start_cancel_order(callback: CallbackQuery, state: FSMContext):
    try:
        order_id = callback.data.replace("admin_cancel_", "")
        
        # Store message_id and order_id in state
        await state.update_data(
            order_id=order_id,
            message_id=callback.message.message_id,
            chat_id=callback.message.chat.id
        )
        
        await callback.message.reply(
            "Пожалуйста, укажите причину отмены заказа:\n"
            "Это сообщение будет отправлено клиенту."
        )
        await state.set_state(CancellationStates.waiting_for_reason)
        await callback.answer()
        
    except Exception as e:
        print(f"[ERROR] Error in admin_start_cancel_order: {str(e)}")
        await callback.answer("Произошла ошибка при отмене заказа")

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
            print(f"[ERROR] Failed to notify user about order cancellation: {str(e)}")
        
        # Delete the original order message
        try:
            await message.bot.delete_message(chat_id, original_message_id)
        except Exception as e:
            print(f"[ERROR] Failed to delete original message: {str(e)}")
        
        # Confirm to admin
        await message.answer(f"❌ Заказ #{order_id} отменен. Клиент уведомлен о причине отмены.")
        await state.clear()
        
    except Exception as e:
        print(f"[ERROR] Error in admin_finish_cancel_order: {str(e)}")
        await message.answer("Произошла ошибка при отмене заказа")
        await state.clear()

@router.callback_query(F.data.startswith("show_cart"))
async def show_cart(callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        cart = await db.get_cart(user_id)
        
        if not cart or not cart.get('items', []):
            await callback.message.answer("Ваша корзина пуста")
            await callback.answer()
            return
        
        total = 0
        text = "🛒 Ваша корзина:\n\n"
        
        for item in cart['items']:
            price = item['price']
            quantity = item['quantity']
            subtotal = price * quantity
            total += subtotal
            
            text += f"📦 {item['name']}"
            if item.get('flavor'):
                text += f" (🌈 {item['flavor']})"
            text += f"\n💰 {format_price(price)} x {quantity} = {format_price(subtotal)} Tg\n"
            text += "➖➖➖➖➖➖➖➖\n"
        
        text += f"\n💵 Итого: {format_price(total)} Tg"
        
        keyboard = cart_actions_kb()
        await callback.message.answer(text, reply_markup=keyboard)
        await callback.answer()
        
    except Exception as e:
        print(f"[ERROR] Error in show_cart: {str(e)}")
        await callback.message.answer("Произошла ошибка при отображении корзины")
        await callback.answer()

@router.callback_query(F.data == "show_help")
async def show_help_from_button(callback: CallbackQuery):
    await callback.message.answer(
        "Выберите раздел помощи:",
        reply_markup=help_menu()
    )
    await callback.answer()

@router.callback_query(F.data == "create_order")
async def start_order(callback: CallbackQuery, state: FSMContext):
    # Проверяем режим сна
    sleep_data = await db.get_sleep_mode()
    if sleep_data["enabled"]:
        end_time = sleep_data.get("end_time", "Не указано")
        await callback.message.answer(
            f"😴 Магазин временно не работает.\n"
            f"Работа возобновится в {end_time}.\n"
            f"Пожалуйста, используйте /start когда время придет."
        )
        await callback.answer()
        return
        
    # ... остальной код функции ...

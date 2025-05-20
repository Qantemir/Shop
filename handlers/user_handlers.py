from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
import logging

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
from handlers.admin_handlers import format_order_notification

# Configure logging
logger = logging.getLogger(__name__)

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
    try:
        # Проверяем режим сна
        sleep_data = await db.get_sleep_mode()
        if sleep_data is None:
            # Если не удалось получить статус режима сна, продолжаем работу
            await message.answer(
                "Добро пожаловать в магазин!\n\n"
                "Наш магазин работает до 01:00\n\n"
                "👇Нажмите на ℹ️ Помощь, чтобы узнать подробнее👇",
                reply_markup=main_menu()
            )
            return
            
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
            
        await message.answer(
                "Добро пожаловать в магазин!\n\n"
                "Наш магазин работает до 01:00\n\n"
                "👇Нажмите на ℹ️ Помощь, чтобы узнать подробнее👇",
            reply_markup=main_menu()
        )
    except Exception as e:
        logger.error(f"Error in cmd_start: {str(e)}")
        await message.answer(
                "Добро пожаловать в магазин!\n\n"
                "Наш магазин работает до 01:00\n\n"
                "👇Нажмите на ℹ️ Помощь, чтобы узнать подробнее👇",
            reply_markup=main_menu()
        )

@router.message(F.text == "🛍 Каталог")
async def show_catalog(message: Message):
    try:
        # Проверяем режим сна
        sleep_data = await db.get_sleep_mode()
        if sleep_data is None:
            # Если не удалось получить статус режима сна, продолжаем работу
            await message.answer(
                "Выберите категорию:",
                reply_markup=catalog_menu()
            )
            return
            
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
    except Exception as e:
        logger.error(f"Error in show_catalog: {str(e)}")
        await message.answer(
            "Выберите категорию:",
            reply_markup=catalog_menu()
        )

@router.callback_query(F.data.startswith("category_"))
async def show_category(callback: CallbackQuery, state: FSMContext):
    try:
        category = callback.data.replace("category_", "")
        products = await db.get_products_by_category(category)
        
        if not products:
            await callback.message.answer("В данной категории нет товаров")
            return
        
        for product in products:
            try:
                caption = f"📦 {product['name']}\n"
                caption += f"💰 {format_price(product['price'])} Tg\n"
                caption += f"📝 {product['description']}\n\n"
                
                # Add flavors to caption if they exist
                flavors = product.get('flavors', [])
                if flavors:
                    caption += "🌈 Доступные вкусы:\n"
                    for flavor in flavors:
                        flavor_name = flavor.get('name', '') if isinstance(flavor, dict) else flavor
                        flavor_quantity = flavor.get('quantity', 0) if isinstance(flavor, dict) else 0
                        if flavor_quantity > 0:
                            caption += f"• {flavor_name} ({flavor_quantity} шт.)\n"
                
                product_id = str(product['_id'])
                print(f"[DEBUG] Showing product with ID: {product_id}")
                
                # Get flavors for the product
                flavors = product.get('flavors', [])
                if isinstance(flavors, list):
                    # If flavors is a list of strings, convert to list of dicts
                    if flavors and isinstance(flavors[0], str):
                        flavors = [{'name': flavor, 'quantity': 0} for flavor in flavors]
                
                keyboard = product_actions_kb(product_id, False, flavors)
                
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
            except Exception as e:
                print(f"[ERROR] Error processing product: {str(e)}")
                continue
        
        await callback.answer()
    except Exception as e:
        print(f"[ERROR] Error in show_category: {str(e)}")
        await callback.answer("Произошла ошибка при отображении категории")

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

@router.callback_query(F.data.startswith("sf_"))
async def select_flavor(callback: CallbackQuery, state: FSMContext):
    logger.info("Starting select_flavor handler")
    try:
        # Get the full callback data
        full_data = callback.data
        logger.debug(f"Full callback data: {full_data}")
        
        # Extract product_id and flavor index
        _, product_id, flavor_index = full_data.split("_")
        flavor_index = int(flavor_index) - 1  # Convert to 0-based index
        
        logger.debug(f"Parsed product_id: {product_id}, flavor_index: {flavor_index}")
        
        # Get product first to validate it exists
        product = await db.get_product(product_id)
        if not product:
            logger.warning(f"Product not found in database: {product_id}")
            await callback.answer("Товар не найден или недоступен", show_alert=True)
            return
            
        # Check if flavor exists and has enough quantity
        flavors = product.get('flavors', [])
        if flavor_index < 0 or flavor_index >= len(flavors):
            await callback.answer("Выбранный вкус недоступен", show_alert=True)
            return
            
        flavor = flavors[flavor_index]
        flavor_name = flavor.get('name', '')
        
        if flavor.get('quantity', 0) <= 0:
            await callback.answer("К сожалению, этот вкус закончился", show_alert=True)
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
            logger.info(f"Created new user: {callback.from_user.id}")
        
        # Initialize cart if needed
        cart = user.get('cart', [])
        if cart is None:
            cart = []
        
        # Check if product with same flavor already in cart
        found = False
        for item in cart:
            if str(item.get('product_id')) == str(product_id) and item.get('flavor') == flavor_name:
                # Check if we can add more
                if item['quantity'] >= flavor.get('quantity', 0):
                    await callback.answer("К сожалению, больше нет в наличии", show_alert=True)
                    return
                item['quantity'] += 1
                found = True
                break
        
        # Add new item if not found
        if not found:
            new_item = {
                'product_id': str(product_id),
                'name': product['name'],
                'price': int(product['price']),
                'quantity': 1,
                'flavor': flavor_name
            }
            cart.append(new_item)
        
        # Update user's cart in database
        result = await db.update_user(callback.from_user.id, {'cart': cart})
        
        if result:
            await callback.answer(f"Товар ({flavor_name}) добавлен в корзину!", show_alert=True)
            await show_cart_message(callback.message, user)
        else:
            await callback.answer("Ошибка при добавлении товара в корзину", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error in select_flavor: {str(e)}")
        await callback.answer("Произошла ошибка при выборе вкуса", show_alert=True)

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
                flavor_name = flavor.get('name', '')
                flavor_quantity = flavor.get('quantity', 0)
                if flavor_quantity > 0:  # Only show flavors that are in stock
                    keyboard.append([
                        InlineKeyboardButton(
                            text=f"🌈 {flavor_name} ({flavor_quantity} шт.)",
                            callback_data=f"select_flavor_{product_id}_{flavor_name}"
                        )
                    ])
            keyboard.append([
                InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_catalog")
            ])
            
            if not keyboard:  # If no flavors are in stock
                await callback.answer("К сожалению, все вкусы закончились", show_alert=True)
                return
            
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
    
    # Create keyboard with +/- buttons for each item
    keyboard = []
    for item in cart:
        item_id = item['product_id']
        keyboard.append([
            InlineKeyboardButton(text=f"➖ {item['name']}", callback_data=f"decrease_{item_id}"),
            InlineKeyboardButton(text=f"➕ {item['name']}", callback_data=f"increase_{item_id}")
        ])
    
    # Add action buttons at the bottom
    keyboard.append([
        InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear_cart"),
        InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout")
    ])
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.message(F.text == "🛒 Корзина")
async def show_cart(message: Message):
    try:
        # Проверяем режим сна
        sleep_data = await db.get_sleep_mode()
        if sleep_data is None:
            # Если не удалось получить статус режима сна, продолжаем работу
            user = await db.get_user(message.from_user.id)
            await show_cart_message(message, user)
            return
            
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
    except Exception as e:
        logger.error(f"Error in show_cart: {str(e)}")
        await message.answer("❌ Произошла ошибка при отображении корзины")

@router.callback_query(F.data.startswith("increase_"))
async def increase_cart_item(callback: CallbackQuery):
    try:
        product_id = callback.data.replace("increase_", "")
        user = await db.get_user(callback.from_user.id)
        
        if not user or not user.get('cart'):
            await callback.answer("Корзина пуста")
            return
            
        cart = user['cart']
        item = next((item for item in cart if str(item['product_id']) == str(product_id)), None)
        
        if not item:
            await callback.answer("Товар не найден в корзине")
            return
            
        # Check if product still exists and has enough quantity
        product = await db.get_product(product_id)
        if not product:
            await callback.answer("Товар больше не доступен")
            return
            
        if 'flavor' in item:
            flavors = product.get('flavors', [])
            flavor = next((f for f in flavors if f.get('name') == item['flavor']), None)
            if not flavor or flavor.get('quantity', 0) <= item['quantity']:
                await callback.answer("К сожалению, больше нет в наличии")
                return
        
        # Increase quantity
        item['quantity'] += 1
        await db.update_user(callback.from_user.id, {'cart': cart})
        
        # Show updated cart
        await show_cart_message(callback.message, user)
        await callback.answer("Количество увеличено")
        
    except Exception as e:
        print(f"[ERROR] Error in increase_cart_item: {str(e)}")
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data.startswith("decrease_"))
async def decrease_cart_item(callback: CallbackQuery):
    try:
        product_id = callback.data.replace("decrease_", "")
        user = await db.get_user(callback.from_user.id)
        
        if not user or not user.get('cart'):
            await callback.answer("Корзина пуста")
            return
            
        cart = user['cart']
        item = next((item for item in cart if str(item['product_id']) == str(product_id)), None)
        
        if not item:
            await callback.answer("Товар не найден в корзине")
            return
            
        if item['quantity'] > 1:
            # Decrease quantity
            item['quantity'] -= 1
            await db.update_user(callback.from_user.id, {'cart': cart})
            
            # Show updated cart
            await show_cart_message(callback.message, user)
            await callback.answer("Количество уменьшено")
        else:
            # Remove item if quantity is 1
            cart = [i for i in cart if str(i['product_id']) != str(product_id)]
            await db.update_user(callback.from_user.id, {'cart': cart})
            
            if not cart:
                await callback.message.edit_text("Ваша корзина пуста")
            else:
                await show_cart_message(callback.message, user)
            await callback.answer("Товар удален из корзины")
        
    except Exception as e:
        print(f"[ERROR] Error in decrease_cart_item: {str(e)}")
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
    
    # Check if all items are still available
    for item in cart:
        product = await db.get_product(item['product_id'])
        if not product:
            await callback.message.answer(f"Товар {item['name']} больше не доступен")
            await callback.answer()
            return
            
        if 'flavor' in item:
            flavors = product.get('flavors', [])
            flavor = next((f for f in flavors if f.get('name') == item['flavor']), None)
            if not flavor or flavor.get('quantity', 0) < item['quantity']:
                await callback.message.answer(
                    f"К сожалению, вкус {item['flavor']} для товара {item['name']} "
                    f"больше не доступен в нужном количестве"
                )
                await callback.answer()
                return
    
    # If all items are available, proceed with checkout
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
        "Для оформления заказа, пожалуйста, отправьте ваш номер телефона в формате 8XXXXXXXXXX"
    )
    await state.set_state(OrderStates.waiting_phone)
    await callback.answer()

@router.message(OrderStates.waiting_phone)
async def process_phone(message: Message, state: FSMContext):
    # Validate phone number format
    phone = message.text.strip()
    if not  phone.startswith('8') or not phone[1:].isdigit() or len(phone) != 11:
        await message.answer("Пожалуйста, введите корректный номер телефона в формате 8XXXXXXXXXX")
        return
    
    # Save phone and ask for address
    await state.update_data(phone=phone)
    await message.answer(
        "Теперь отправьте ваш адрес доставки.\n"
        "Пожалуйста, укажите улицу и дом (например: ул. Ленина 123)"
    )
    await state.set_state(OrderStates.waiting_address)

@router.message(OrderStates.waiting_address)
async def process_address(message: Message, state: FSMContext):
    # Get all order data
    data = await state.get_data()
    user = await db.get_user(message.from_user.id)
    
    # Создание ссылки на 2GIS
    address = message.text.strip()
    address_for_link = address.replace(' ', '%20').replace('/', '%2F') # Замена пробелов и слэшей на ЮТФ симолов для коректного отоброжения
    gis_link = f"https://2gis.kz/pavlodarr/search/{address_for_link}"
    
    # Save both original address and 2GIS link
    await state.update_data(
        address=address,
        gis_link=gis_link
    )
    
    cart = user['cart']
    total = sum(item['price'] * item['quantity'] for item in cart)
    
    # Get admin card from config
    admin_card = ADMIN_CARD
    
    payment_text = (
        f"💳 Для оплаты заказа переведите {format_price(total)} Tg на карту:\n\n"
        f"<span class=\"tg-spoiler\"><code>{admin_card}</code></span>\n\n"
        "KaspiBank(Дарья.К)\n\n"
        "👆 Нажмите на номер карты, чтобы скопировать\n\n"
        "После оплаты отправьте скриншот чека."
    )
    
    await message.answer(payment_text, parse_mode="HTML")
    await state.set_state(OrderStates.waiting_payment)

@router.message(OrderStates.waiting_payment)
async def handle_payment_proof(message: Message, state: FSMContext):
    print(f"[DEBUG] Received payment proof. Content type: {message.content_type}")
    
    try:
        if message.photo:
            print("[DEBUG] Processing photo")
            file_id = message.photo[-1].file_id
            file_type = 'photo'
        elif message.document:
            print(f"[DEBUG] Processing document - MIME: {message.document.mime_type}, Name: {message.document.file_name}")
            file_id = message.document.file_id
            file_type = 'document'
        else:
            print("[DEBUG] Invalid payment proof type")
            await message.answer(
                "Пожалуйста, отправьте скриншот чека об оплате в виде фотографии или файла."
            )
            return

        # Get all order data
        data = await state.get_data()
        print(f"[DEBUG] State data: {data}")
        
        if not data:
            print("[ERROR] No state data found")
            await message.answer(
                "Произошла ошибка при обработке заказа. Пожалуйста, начните оформление заказа заново.",
                reply_markup=main_menu()
            )
            await state.clear()
            return

        user = await db.get_user(message.from_user.id)
        print(f"[DEBUG] User data: {user}")
        
        if not user or not user.get('cart'):
            print("[ERROR] No user or cart data found")
            await message.answer(
                "Произошла ошибка при обработке заказа. Пожалуйста, начните оформление заказа заново.",
                reply_markup=main_menu()
            )
            await state.clear()
            return

        cart = user['cart']
        total = sum(item['price'] * item['quantity'] for item in cart)
        
        # Create order data
        order_data = {
            'user_id': message.from_user.id,
            'username': message.from_user.username,
            'phone': data['phone'],
            'address': data['address'],
            'gis_link': data['gis_link'],
            'items': cart,
            'total_amount': total,
            'status': 'pending',
            'created_at': datetime.now(),
            'payment_file_id': file_id,
            'payment_file_type': file_type
        }
        
        print(f"[DEBUG] Order data prepared: {order_data}")
        
        # Create order in database
        order_result = await db.create_order(order_data)
        order_id = str(order_result.inserted_id)
        print(f"[DEBUG] Order created with ID: {order_id}")
        
        # Clear user's cart
        await db.update_user(message.from_user.id, {'cart': []})
        
        # Send confirmation to user
        await message.answer(
            "✅ Спасибо! Ваш заказ принят и ожидает подтверждения оплаты.\n"
            "Мы уведомим вас, когда заказ будет подтвержден.",
            reply_markup=main_menu()
        )
        
        # Prepare user data for notification
        user_data = {
            'full_name': message.from_user.full_name,
            'username': message.from_user.username
        }
        
        # Format and send admin notification
        admin_text = await format_order_notification(
            order_id=order_id,
            user_data=user_data,
            order_data=data,
            cart=cart,
            total=total
        )
        
        try:
            # First send the order details
            await message.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text
            )
            
            # Then send the payment proof (photo or document)
            if file_type == 'photo':
                await message.bot.send_photo(
                    chat_id=ADMIN_ID,
                    photo=file_id,
                    caption=f"💳 Скриншот оплаты для заказа #{order_id}",
                    reply_markup=order_management_kb(order_id)
                )
            else:  # Any document
                await message.bot.send_document(
                    chat_id=ADMIN_ID,
                    document=file_id,
                    caption=f"💳 Чек оплаты для заказа #{order_id}",
                    reply_markup=order_management_kb(order_id)
                )
            
            print(f"[DEBUG] Successfully notified admin about order {order_id}")
        except Exception as e:
            print(f"[ERROR] Failed to notify admin about order {order_id}: {str(e)}")
        
        await state.clear()
        
    except Exception as e:
        print(f"[ERROR] Error in handle_payment_proof: {str(e)}")
        await message.answer(
            "Произошла ошибка при обработке оплаты. Пожалуйста, попробуйте позже.",
            reply_markup=main_menu()
        )
        await state.clear()

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
6️⃣ Произведите оплату

После оформления заказа ожидайте потверждения менеджера"""
    
    await callback.message.edit_text(text, reply_markup=help_menu())
    await callback.answer()

@router.callback_query(F.data == "help_payment")
async def show_payment_info(callback: CallbackQuery):
    text = """💳 Способы оплаты:

-Онлайн-оплата(переводом на карту)"""
    
    await callback.message.edit_text(text, reply_markup=help_menu())
    await callback.answer()

@router.callback_query(F.data == "help_delivery")
async def show_delivery_info(callback: CallbackQuery):
    text = """🚚 Информация о доставке:

📦 О доставки:
- Доставка курьером по городу(Только в черте города Павлодар)

⏱ Сроки доставки:
-В течении дня

💰 Стоимость доставки:
-Яндекс.Курьером(Стоимость рассчитывается индивидуально)"""
    
    await callback.message.edit_text(text, reply_markup=help_menu())
    await callback.answer()

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
    try:
        # Проверяем режим сна
        sleep_data = await db.get_sleep_mode()
        if sleep_data is None:
            # Если не удалось получить статус режима сна, продолжаем работу
            # ... остальной код функции ...
            return
            
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
    except Exception as e:
        logger.error(f"Error in start_order: {str(e)}")
        await callback.answer("❌ Произошла ошибка при создании заказа")

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
import logging

from database import db
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
from handlers.sleep_mode import check_sleep_mode, check_sleep_mode_callback
from utils import format_price
from utils.message_manager import store_message_id
from utils.cart_expiration import check_cart_expiration

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
        # Check sleep mode first
        sleep_data = await db.get_sleep_mode()
        if sleep_data and sleep_data.get("enabled", False):
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
        if await check_sleep_mode(message):
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
async def show_category(callback: CallbackQuery):
    try:
        if await check_sleep_mode_callback(callback):
            return
            
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
                    caption += "🌈 Доступно:\n"
                    for flavor in flavors:
                        flavor_name = flavor.get('name', '') if isinstance(flavor, dict) else flavor
                        flavor_quantity = flavor.get('quantity', 0) if isinstance(flavor, dict) else 0
                        if flavor_quantity > 0:
                            caption += f"• {flavor_name} ({flavor_quantity} шт.)\n"
                
                product_id = str(product['_id'])
                keyboard = product_actions_kb(product_id, False, flavors)
                
                try:
                    await callback.message.answer_photo(
                        photo=product['photo'],
                        caption=caption,
                        reply_markup=keyboard
                    )
                except Exception as e:
                    logger.error(f"Error showing product {product_id}: {str(e)}")
                    await callback.message.answer(
                        f"Ошибка при отображении товара {product['name']}"
                    )
            except Exception as e:
                logger.error(f"Error processing product: {str(e)}")
                continue
        
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in show_category: {str(e)}")
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
async def select_flavor(callback: CallbackQuery):
    try:
        logger.info(f"Starting select_flavor handler with callback data: {callback.data}")
        
        # Check if shop is in sleep mode
        sleep_mode = await db.get_sleep_mode()
        if sleep_mode.get('enabled', False):
            logger.info("Shop is in sleep mode")
            await callback.answer("Магазин сейчас закрыт. Попробуйте позже.", show_alert=True)
            return
            
        # Parse callback data
        data = callback.data.split("_")
        logger.info(f"Parsed callback data: {data}")
        
        if len(data) != 3:
            logger.error(f"Invalid callback data format: {callback.data}")
            await callback.answer("Ошибка в формате данных")
            return
            
        product_id = data[1]
        try:
            flavor_index = int(data[2]) - 1  # Convert to 0-based index
        except ValueError:
            logger.error(f"Invalid flavor index: {data[2]}")
            await callback.answer("Ошибка в индексе вкуса")
            return
            
        logger.info(f"Product ID: {product_id}, Flavor Index: {flavor_index}")
        
        # Get product and check if it exists
        product = await db.get_product(product_id)
        if not product:
            logger.error(f"Product not found: {product_id}")
            await callback.answer("Товар не найден")
            return
            
        logger.info(f"Found product: {product.get('name')}")
        
        # Get flavor and check if it exists and has quantity
        flavors = product.get('flavors', [])
        logger.info(f"Product flavors: {flavors}")
        
        if flavor_index >= len(flavors):
            logger.error(f"Flavor index out of range: {flavor_index} >= {len(flavors)}")
            await callback.answer("Вкус не найден")
            return
            
        flavor = flavors[flavor_index]
        logger.info(f"Selected flavor: {flavor}")
        
        if not flavor.get('quantity', 0):
            logger.info(f"Flavor out of stock: {flavor.get('name')}")
            await callback.answer("К сожалению, этот вкус закончился")
            return
            
        # Get or create user
        user = await db.get_user(callback.from_user.id)
        if not user:
            logger.info(f"Creating new user: {callback.from_user.id}")
            user = {
                'user_id': callback.from_user.id,
                'username': callback.from_user.username,
                'cart': [],
                'cart_expires_at': None
            }
            await db.create_user(user)
            
        logger.info(f"User data: {user}")
        
        # Initialize cart if not exists
        if 'cart' not in user:
            logger.info("Initializing empty cart")
            user['cart'] = []
            
        # Check if cart has expired
        if await check_cart_expiration(callback.from_user.id):
            logger.info("Cart has expired")
            await callback.answer("Ваша корзина была очищена из-за неактивности", show_alert=True)
            return
            
        # Check if flavor is already in cart
        cart_item = next((item for item in user['cart'] 
                         if str(item['product_id']) == str(product_id) 
                         and item.get('flavor') == flavor['name']), None)
                         
        if cart_item:
            logger.info("Flavor already in cart")
            await callback.answer("Этот вкус уже в вашей корзине")
            return
            
        # Deduct flavor quantity using atomic operation
        logger.info(f"Attempting to deduct flavor quantity: {flavor['name']}")
        success = await db.update_product_flavor_quantity(product_id, flavor['name'], -1)
        if not success:
            logger.error("Failed to update flavor quantity")
            await callback.answer("К сожалению, этот вкус закончился", show_alert=True)
            return
            
        # Add to cart
        cart_item = {
            'product_id': product_id,
            'name': product['name'],
            'price': product['price'],
            'flavor': flavor['name'],
            'quantity': 1
        }
        logger.info(f"Adding to cart: {cart_item}")
        user['cart'].append(cart_item)
        
        # Set cart expiration time (10 minutes from now)
        user['cart_expires_at'] = (datetime.now() + timedelta(minutes=10)).isoformat()
        
        # Update user
        logger.info("Updating user data")
        await db.update_user(callback.from_user.id, {
            'cart': user['cart'],
            'cart_expires_at': user['cart_expires_at']
        })
        
        await callback.answer("Товар добавлен в корзину")
        logger.info("Successfully added item to cart")
        
    except Exception as e:
        logger.error(f"Error in select_flavor: {str(e)}", exc_info=True)
        await callback.answer("Произошла ошибка при добавлении товара в корзину")

@router.callback_query(F.data.startswith("add_to_cart_"))
async def add_to_cart(callback: CallbackQuery):
    try:
        if await check_sleep_mode_callback(callback):
            return
            
        product_id = callback.data.replace("add_to_cart_", "")
        product = await db.get_product(product_id)
        
        if not product:
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
        else:
            # If product has no flavors, show message that it's not available
            await callback.answer("Данный товар отсутствует", show_alert=True)
            return
            
    except Exception as e:
        logger.error(f"Error in add_to_cart: {str(e)}")
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
        if await check_sleep_mode(message):
            return

        user = await db.get_user(message.from_user.id)
        await show_cart_message(message, user)
    except Exception as e:
        logger.error(f"Error in show_cart: {str(e)}")
        await message.answer("❌ Произошла ошибка при отображении корзины")

@router.callback_query(F.data.startswith("increase_"))
async def increase_cart_item(callback: CallbackQuery):
    try:
        # Check if cart has expired
        if await check_cart_expiration(callback.from_user.id):
            await callback.answer("Ваша корзина была очищена из-за неактивности", show_alert=True)
            return
            
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
                
            # Deduct flavor quantity using atomic operation
            success = await db.update_product_flavor_quantity(product_id, item['flavor'], -1)
            if not success:
                await callback.answer("Ошибка при обновлении количества товара", show_alert=True)
                return
        
        # Increase quantity
        item['quantity'] += 1
        
        # Update cart expiration time
        user['cart_expires_at'] = (datetime.now() + timedelta(minutes=10)).isoformat()
        
        await db.update_user(callback.from_user.id, {
            'cart': cart,
            'cart_expires_at': user['cart_expires_at']
        })
        
        # Show updated cart
        await show_cart_message(callback.message, user)
        await callback.answer("Количество увеличено")
        
    except Exception as e:
        logger.error(f"Error in increase_cart_item: {str(e)}")
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data.startswith("decrease_"))
async def decrease_cart_item(callback: CallbackQuery):
    try:
        # Check if cart has expired
        if await check_cart_expiration(callback.from_user.id):
            await callback.answer("Ваша корзина была очищена из-за неактивности", show_alert=True)
            return
            
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
            
        # Return flavor to inventory using atomic operation
        if 'flavor' in item:
            success = await db.update_product_flavor_quantity(product_id, item['flavor'], 1)
            if not success:
                await callback.answer("Ошибка при обновлении количества товара", show_alert=True)
                return
        
        # Decrease quantity or remove item
        if item['quantity'] > 1:
            item['quantity'] -= 1
        else:
            cart.remove(item)
            
        # Update cart expiration time if cart is not empty
        if cart:
            user['cart_expires_at'] = (datetime.now() + timedelta(minutes=10)).isoformat()
        else:
            user['cart_expires_at'] = None
            
        # Update user's cart
        await db.update_user(callback.from_user.id, {
            'cart': cart,
            'cart_expires_at': user['cart_expires_at']
        })
        
        # Show updated cart
        await show_cart_message(callback.message, user)
        await callback.answer("Количество уменьшено")
        
    except Exception as e:
        logger.error(f"Error in decrease_cart_item: {str(e)}")
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data == "clear_cart")
async def clear_cart(callback: CallbackQuery):
    try:
        user = await db.get_user(callback.from_user.id)
        if not user or not user.get('cart'):
            await callback.answer("Корзина уже пуста")
            return
            
        # Return all flavors to inventory using atomic operations
        for item in user['cart']:
            if 'flavor' in item:
                await db.update_product_flavor_quantity(
                    item['product_id'],
                    item['flavor'],
                    item['quantity']
                )
        
        # Clear cart and expiration time
        await db.update_user(callback.from_user.id, {
            'cart': [],
            'cart_expires_at': None
        })
        
        await callback.message.answer("Корзина очищена")
        await callback.answer("Корзина очищена")
        
    except Exception as e:
        logger.error(f"Error in clear_cart: {str(e)}")
        await callback.answer("Произошла ошибка при очистке корзины")

@router.callback_query(F.data.startswith("remove_"))
async def remove_item(callback: CallbackQuery):
    try:
        # Check if cart has expired
        if await check_cart_expiration(callback.from_user.id):
            await callback.answer("Ваша корзина была очищена из-за неактивности", show_alert=True)
            return
            
        product_id = callback.data.replace("remove_", "")
        user = await db.get_user(callback.from_user.id)
        
        if not user or not user.get('cart'):
            await callback.answer("Корзина пуста")
            return
            
        cart = user['cart']
        item = next((item for item in cart if str(item['product_id']) == str(product_id)), None)
        
        if not item:
            await callback.answer("Товар не найден в корзине")
            return
            
        # Return all quantity of the flavor to inventory
        if 'flavor' in item:
            success = await db.update_product_flavor_quantity(
                product_id,
                item['flavor'],
                item['quantity']
            )
            if not success:
                await callback.answer("Ошибка при обновлении количества товара", show_alert=True)
                return
        
        # Remove item from cart
        cart.remove(item)
        
        # Update cart expiration time if cart is not empty
        if cart:
            user['cart_expires_at'] = (datetime.now() + timedelta(minutes=10)).isoformat()
        else:
            user['cart_expires_at'] = None
            
        # Update user's cart
        await db.update_user(callback.from_user.id, {
            'cart': cart,
            'cart_expires_at': user['cart_expires_at']
        })
        
        # Show updated cart
        await show_cart_message(callback.message, user)
        await callback.answer("Товар удален из корзины")
        
    except Exception as e:
        logger.error(f"Error in remove_item: {str(e)}")
        await callback.answer("Произошла ошибка при удалении товара")

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
    try:
        if await check_sleep_mode_callback(callback):
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
    except Exception as e:
        logger.error(f"Error in start_checkout: {str(e)}")
        await callback.answer("Произошла ошибка при оформлении заказа")

@router.message(OrderStates.waiting_phone)
async def process_phone(message: Message, state: FSMContext):
    try:
        if await check_sleep_mode(message):
            return
            
        # Validate phone number format
        phone = message.text.strip()
        if not phone.startswith('8') or not phone[1:].isdigit() or len(phone) != 11:
            await message.answer("Пожалуйста, введите корректный номер телефона в формате 8XXXXXXXXXX")
            return
        
        # Save phone and ask for address
        await state.update_data(phone=phone)
        await message.answer(
            "Теперь отправьте ваш адрес доставки.\n"
            "Пожалуйста, укажите улицу и дом (например: ул. Ленина 123)"
        )
        await state.set_state(OrderStates.waiting_address)
    except Exception as e:
        logger.error(f"Error in process_phone: {str(e)}")
        await message.answer("Произошла ошибка при обработке номера телефона")

@router.message(OrderStates.waiting_address)
async def process_address(message: Message, state: FSMContext):
    try:
        if await check_sleep_mode(message):
            return
            
        # Get all order data
        data = await state.get_data()
        user = await db.get_user(message.from_user.id)
        
        # Создание ссылки на 2GIS
        address = message.text.strip()
        address_for_link = address.replace(' ', '%20').replace('/', '%2F')
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
            "KaspiBank(Александра А.)\n\n"
            "👆 Нажмите на номер карты, чтобы скопировать\n\n"
            "После оплаты отправьте скриншот чека."
        )
        
        await message.answer(payment_text, parse_mode="HTML")
        await state.set_state(OrderStates.waiting_payment)
    except Exception as e:
        logger.error(f"Error in process_address: {str(e)}")
        await message.answer("Произошла ошибка при обработке адреса")

@router.message(OrderStates.waiting_payment)
async def handle_payment_proof(message: Message, state: FSMContext):
    try:
        if await check_sleep_mode(message):
            return
            
        if message.photo:
            file_id = message.photo[-1].file_id
            file_type = 'photo'
        elif message.document:
            file_id = message.document.file_id
            file_type = 'document'
        else:
            await message.answer(
                "Пожалуйста, отправьте скриншот чека об оплате в виде фотографии или файла."
            )
            return

        # Get all order data
        data = await state.get_data()
        if not data:
            await message.answer(
                "Произошла ошибка при обработке заказа. Пожалуйста, начните оформление заказа заново.",
                reply_markup=main_menu()
            )
            await state.clear()
            return

        user = await db.get_user(message.from_user.id)
        if not user or not user.get('cart'):
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
            
            # Then send the payment proof
            if file_type == 'photo':
                await message.bot.send_photo(
                    chat_id=ADMIN_ID,
                    photo=file_id,
                    caption=f"💳 Скриншот оплаты для заказа #{order_id}",
                    reply_markup=order_management_kb(order_id)
                )
            else:
                await message.bot.send_document(
                    chat_id=ADMIN_ID,
                    document=file_id,
                    caption=f"💳 Чек оплаты для заказа #{order_id}",
                    reply_markup=order_management_kb(order_id)
                )
        except Exception as e:
            logger.error(f"Failed to notify admin about order {order_id}: {str(e)}")
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error in handle_payment_proof: {str(e)}")
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
    await callback.message.edit_text(
        "🚚 Информация о доставке:\n\n"
        "• Доставка осуществляется в течение 1-2 часов\n"
        "• Курьер свяжется с вами перед доставкой\n"
        "• Пожалуйста, подготовьте документ, удостоверяющий личность\n\n"
        "По всем вопросам обращайтесь к администратору.",
        reply_markup=help_menu()
    )

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
            
        # Check if order is already cancelled
        if order.get('status') == 'cancelled':
            await message.answer("Заказ уже отменен")
            await state.clear()
            return
            
        logger.info(f"Processing order cancellation: {order}")
        logger.info(f"Order items: {order.get('items', [])}")
        
        # Return all items to inventory
        for item in order.get('items', []):
            logger.info(f"Processing item: {item}")
            if 'flavor' in item:
                logger.info(f"Found flavor in item: {item['flavor']}")
                logger.info(f"Product ID: {item['product_id']}, Quantity: {item['quantity']}")
                
                # Get current product state
                product = await db.get_product(item['product_id'])
                logger.info(f"Current product state: {product}")
                
                if product:
                    current_flavor = next((f for f in product.get('flavors', []) if f['name'] == item['flavor']), None)
                    if current_flavor:
                        logger.info(f"Current flavor quantity: {current_flavor.get('quantity', 0)}")
                
                success = await db.update_product_flavor_quantity(
                    item['product_id'],
                    item['flavor'],
                    item['quantity']  # Return the full quantity
                )
                
                if not success:
                    logger.error(f"Failed to restore flavor quantity: product_id={item['product_id']}, flavor={item['flavor']}")
                    await message.answer("Ошибка при возврате товара на склад")
                    await state.clear()
                    return
                else:
                    logger.info(f"Successfully restored flavor quantity for {item['flavor']}")
                    
                    # Verify the update
                    updated_product = await db.get_product(item['product_id'])
                    if updated_product:
                        updated_flavor = next((f for f in updated_product.get('flavors', []) if f['name'] == item['flavor']), None)
                        if updated_flavor:
                            logger.info(f"Updated flavor quantity: {updated_flavor.get('quantity', 0)}")
        
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
            await message.bot.delete_message(chat_id, original_message_id)
        except Exception as e:
            logger.error(f"Failed to delete original message: {e}")
        
        # Confirm to admin
        await message.answer(f"❌ Заказ #{order_id} отменен. Клиент уведомлен о причине отмены.")
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error in admin_finish_cancel_order: {str(e)}", exc_info=True)
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

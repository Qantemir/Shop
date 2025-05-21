from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import db
from utils import format_price
from handlers.sleep_mode import check_sleep_mode_callback
import logging

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data.startswith("select_flavor_"))
async def select_flavor(callback: CallbackQuery):
    logger.info("Starting select_flavor handler")
    try:
        if await check_sleep_mode_callback(callback):
            return
            
        # Get the full callback data
        full_data = callback.data
        logger.debug(f"Full callback data: {full_data}")
        
        # Extract product_id and flavor name
        _, product_id, flavor_name = full_data.split("_")
        
        logger.debug(f"Parsed product_id: {product_id}, flavor_name: {flavor_name}")
        
        # Get product first to validate it exists
        product = await db.get_product(product_id)
        if not product:
            logger.warning(f"Product not found in database: {product_id}")
            await callback.answer("Товар не найден или недоступен", show_alert=True)
            return
            
        # Check if flavor exists and has enough quantity
        flavors = product.get('flavors', [])
        flavor = next((f for f in flavors if f.get('name') == flavor_name), None)
        
        if not flavor:
            await callback.answer("Выбранный вкус недоступен", show_alert=True)
            return
            
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
            # Show updated cart
            await show_cart_message(callback.message, user)
        else:
            await callback.answer("Ошибка при добавлении товара в корзину", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error in select_flavor: {str(e)}")
        await callback.answer("Произошла ошибка при выборе вкуса", show_alert=True)

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
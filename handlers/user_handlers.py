from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
import logging
import asyncio
from collections import defaultdict

from database import db
from keyboards.user_kb import (
    main_menu,
    catalog_menu,
    product_actions_kb,
    cart_actions_kb,
    help_menu,
    cart_full_kb,
    help_button_kb
)
from keyboards.admin_kb import order_management_kb
from config import ADMIN_ID, ADMIN_CARD,ADMIN_SWITCHING, CATEGORIES, ADMIN_CARD_NAME
from handlers.admin_handlers import format_order_notification
from utils.sleep_mode import check_sleep_mode
from utils.message_utils import safe_delete_message

user_log = logging.getLogger(__name__)#Инициализация логера

# Система защиты от спама
user_last_click = defaultdict(dict)  # {user_id: {callback_data: timestamp}}
RATE_LIMIT_SECONDS = 1  # Минимальный интервал между нажатиями (в секундах)

async def check_rate_limit(user_id: int, callback_data: str) -> bool:
    """Проверяет, не слишком ли часто пользователь нажимает кнопки"""
    current_time = datetime.now()
    
    # Получаем время последнего нажатия для этого пользователя и кнопки
    user_clicks = user_last_click.get(user_id, {})
    last_click_time = user_clicks.get(callback_data)
    
    if last_click_time:
        time_diff = (current_time - last_click_time).total_seconds()
        if time_diff < RATE_LIMIT_SECONDS:
            return False  # Слишком часто
    
    # Обновляем время последнего нажатия
    user_last_click[user_id][callback_data] = current_time
    return True  # Можно нажимать

async def cleanup_old_rate_limits():#авототчистка старых записаей антиспама
    current_time = datetime.now()
    cleanup_threshold = 3600  # 1 час
    
    for user_id in list(user_last_click.keys()):
        user_clicks = user_last_click[user_id]
        for callback_data in list(user_clicks.keys()):
            last_click_time = user_clicks[callback_data]
            if (current_time - last_click_time).total_seconds() > cleanup_threshold:
                del user_clicks[callback_data]
        
        if not user_clicks:
            del user_last_click[user_id]

async def start_rate_limit_cleanup():# Запускаем периодическую очистку каждые 30 минут
    while True:
        await asyncio.sleep(1800)  # 30 минут
        await cleanup_old_rate_limits()

def rate_limit_protected(func):#Декоратор для автоматической защиты от спама
    async def wrapper(callback: CallbackQuery, *args, **kwargs):
        if not await check_rate_limit(callback.from_user.id, callback.data):
            await callback.answer("⚠️ Подождите немного перед следующим нажатием", show_alert=True)
            return
        return await func(callback, *args, **kwargs)
    return wrapper

async def init_rate_limit_cleanup(bot=None):#Инициализирует периодическую очистку rate limiting и корзин
    asyncio.create_task(start_rate_limit_cleanup())
    asyncio.create_task(start_cart_cleanup(bot))
    user_log.info("Rate limit and cart cleanup tasks started")

router = Router()

class OrderStates(StatesGroup):#состояния при создании заказа
    waiting_phone = State()
    waiting_address = State()
    waiting_payment = State()
    selecting_flavor = State()

class CancellationStates(StatesGroup):#для ожидания причины отмены
    waiting_for_reason = State()

class WelcomeMessageState(StatesGroup):#для хранения ID приветственного сообщения
    message_id = State()

def format_price(price):#Маска для суммы
    return f"{float(price):.2f}"

@router.message(Command("start"))#Обработчик /start
async def cmd_start(message: Message, state: FSMContext):
    try:
        if await check_sleep_mode(message):
            return
    except Exception as e:
        user_log.error(f"Ошибка при проверке режима сна: {e}")

    help_button = help_button_kb()
    welcome_msg = await message.answer(
        "Добро пожаловать в магазин!\n\n"
        "👇Нажмите на ℹ️ Помощь, чтобы узнать подробнее👇",
          reply_markup=main_menu()
    )
    # Сохраняем ID сообщения в состоянии
    await state.update_data(welcome_message_id=welcome_msg.message_id)

@router.message(F.text == "🛍 Каталог")#Обработка для клавиатурной кнопки каталог
async def show_catalog(message: Message, state: FSMContext):
    try:
        await safe_delete_message(message.bot, message.chat.id, message.message_id)

        if await check_sleep_mode(message):
            return
    except Exception as e:
        user_log.error(f"Ошибка в show_catalog: {e}")

    try:
        data = await state.get_data()
        
        # Удаляем предыдущее сообщение каталога
        catalog_message_id = data.get('catalog_message_id')
        if catalog_message_id:
            await safe_delete_message(message.bot, message.chat.id, catalog_message_id)
        
        # Удаляем карточки товаров
        product_message_ids = data.get('product_message_ids', [])
        if product_message_ids:
            for message_id in product_message_ids:
                await safe_delete_message(message.bot, message.chat.id, message_id)
            
            # Очищаем список ID карточек товаров
            await state.update_data(product_message_ids=[])
        
        # Удаляем сообщения корзины
        cart_message_id = data.get('cart_message_id')
        if cart_message_id:
            await safe_delete_message(message.bot, message.chat.id, cart_message_id)
        
        # Удаляем сообщения помощи
        help_message_id = data.get('help_message_id')
        if help_message_id:
            await safe_delete_message(message.bot, message.chat.id, help_message_id)
    except Exception as e:
        user_log.error(f"Ошибка при удалении предыдущих сообщений: {e}")

    catalog_msg = await message.answer(
        "Выберите категорию:",
        reply_markup=catalog_menu()
    )
    await state.update_data(catalog_message_id=catalog_msg.message_id)

@router.callback_query(F.data.startswith("category_"))#создание категорий
async def show_category(callback: CallbackQuery, state: FSMContext):
    try:
        if await check_sleep_mode(callback):
            return
            
        category = callback.data.replace("category_", "")
        products = await db.get_products_by_category(category)
        
        if not products:
            await callback.answer(
                text="❗️В данной категории нет товаров",
                show_alert=True 
            )
            return
        
        await delete_previous_callback_messages(callback, state, "catalog")
        
        product_message_ids = []
        
        for product in products:
            product_id = str(product['_id'])
            try:
                caption = build_product_caption(product)
                keyboard = product_actions_kb(product_id, False, product.get('flavors', []))
                
                product_msg = await callback.message.answer_photo(
                    photo=product['photo'],
                    caption=caption,
                    reply_markup=keyboard
                )
                product_message_ids.append(product_msg.message_id)
            except Exception as e:
                user_log.error(f"Ошибка отображения товара {product_id}: {e}")
                await callback.message.answer(f"Ошибка при отображении товара {product.get('name', 'Неизвестно')}")

        await state.update_data(product_message_ids=product_message_ids)
        await callback.answer()

    except Exception as e:
        user_log.error(f"Ошибка в show_category: {e}")
        await callback.answer("Произошла ошибка при отображении категории")

def build_product_caption(product: dict) -> str:#вывод карточки товара
    caption = f"📦 {product['name']}\n"
    caption += f"💰 {format_price(product['price'])} ₸\n"
    caption += f"📝 {product['description']}\n\n"

    flavors = product.get('flavors', [])
    available_flavors = []

    for flavor in flavors:
        if isinstance(flavor, dict):
            name = flavor.get('name', 'Неизвестно')
            quantity = flavor.get('quantity', 0)
            if quantity > 0:
                available_flavors.append(f"• {name} ({quantity} шт.)")

    if available_flavors:
        caption += "👇Чтобы добавить в корзину нажмите нужный вкус ниже👇"
    else:
        caption += "🚫 Нет в наличии\n"

    return caption

@router.callback_query(F.data.startswith("sf_"))#создание и обработка кнопок выбора вкуса
@rate_limit_protected
async def select_flavor(callback: CallbackQuery, *args, **kwargs):
    try:
        # Check sleep mode
        if await check_sleep_mode(callback):
            return
        
        parts = callback.data.split("_")
        if len(parts) != 3:
            await callback.answer("Ошибка в формате данных")
            return

        product_id, flavor_index = parts[1], parts[2]
        try:
            flavor_index = int(flavor_index) - 1
        except ValueError:
            await callback.answer("Ошибка в индексе вкуса")
            return

        product = await db.get_product(product_id)
        if not product:
            await callback.answer("Товар не найден")
            return

        flavors = product.get("flavors", [])
        if flavor_index >= len(flavors):
            await callback.answer("Вкус не найден")
            return

        flavor = flavors[flavor_index]
        if not flavor.get("quantity", 0):
            await callback.answer("К сожалению, этот вкус закончился")
            return

        user = await db.get_user(callback.from_user.id)
        if not user:
            user = {'user_id': callback.from_user.id, 'username': callback.from_user.username, 'cart': []}
            await db.create_user(user)

        cart = user.get("cart", [])
        if any(item['product_id'] == product_id and item['flavor'] == flavor['name'] for item in cart):
            await callback.answer("🔄 Товар уже в вашей корзине (чтобы изменить количество, перейдите в корзину)", show_alert=True)
            return

        # Atomic deduction
        success = await db.update_product_flavor_quantity(product_id, flavor['name'], -1)
        if not success:
            await callback.answer("К сожалению, этот вкус закончился", show_alert=True)
            return

        cart.append({
            'product_id': product_id,
            'name': product['name'],
            'price': product['price'],
            'flavor': flavor['name'],
            'quantity': 1
        })

        await db.update_user(callback.from_user.id, {
            'cart': cart,
            'cart_expires_at': (datetime.now() + timedelta(minutes=5)).isoformat()
        })

        await callback.answer("✅ Товар добавлен в корзину", show_alert=True)

    except Exception as e:
        user_log.error(f"Ошибка в select_flavor: {e}", exc_info=True)
        await callback.answer("Произошла ошибка при добавлении товара в корзину")

@router.callback_query(F.data == "back_to_catalog")#оброботка кнопки назад в каталог
async def back_to_catalog_handler(callback: CallbackQuery, state: FSMContext):
    try:    
        from config import CATEGORIES
        if not CATEGORIES:
            await callback.answer("Категории не найдены", show_alert=True)
            return

        await delete_product_cards(callback, state)
        await delete_previous_callback_messages(callback, state, "cart")

        await safe_delete_message(callback.message)

        keyboard = catalog_menu()
        if not keyboard.inline_keyboard:
            user_log.error("⚠️ Клавиатура каталога пуста!")
            await callback.answer("Ошибка: каталог пуст", show_alert=True)
            return

        msg = await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text="Выберите категорию:",
            reply_markup=keyboard
        )

        await state.update_data(catalog_message_id=msg.message_id)
        await callback.answer()

    except Exception as e:
        user_log.error(f"Ошибка в back_to_catalog_handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

@router.message(F.text == "🛒 Корзина")#обработка клавиатурной кнопки корзина
async def show_cart(message: Message, state: FSMContext):
    try:
        # Удаляем приветственное сообщение
        await safe_delete_message(message.bot, message.chat.id, message.message_id)

        if await check_sleep_mode(message):
            return

        # Удаляем сообщения каталога и карточки товаров
        try:
            data = await state.get_data()
            
            # Удаляем сообщение каталога
            catalog_message_id = data.get('catalog_message_id')
            if catalog_message_id:
                await safe_delete_message(message.bot, message.chat.id, catalog_message_id)
            
            # Удаляем карточки товаров
            product_message_ids = data.get('product_message_ids', [])
            if product_message_ids:
                for message_id in product_message_ids:
                    await safe_delete_message(message.bot, message.chat.id, message_id)
            
            # Удаляем сообщения помощи
            help_message_id = data.get('help_message_id')
            if help_message_id:
                await safe_delete_message(message.bot, message.chat.id, help_message_id)
        except Exception as e:
            user_log.error(f"Ошибка при удалении предыдущих сообщений: {e}")

        user = await db.get_user(message.from_user.id)
        await show_cart_message(message, user, state)
    except Exception as e:
        user_log.error(f"Error in show_cart: {str(e)}")
        await message.answer("❌ Произошла ошибка при отображении корзины", reply_markup=main_menu())


async def show_cart_message(message: Message, user: dict, state: FSMContext = None):
    # Проверяем истечение корзины
    if await check_cart_expiration(user):
        await clear_expired_cart(user['user_id'])
        cart_msg = await message.answer(
            "🛒 Ваша корзина была очищена из-за истечения времени (5 минут)",
            reply_markup=main_menu()
        )
        if state:
            await state.update_data(cart_message_id=cart_msg.message_id)
        return

    if not user or not user.get('cart'):
        cart_msg = await message.answer(
            "🛒 Ваша корзина пуста",
            reply_markup=main_menu()
        )
        if state:
            await state.update_data(cart_message_id=cart_msg.message_id)
        return

    cart = user['cart']
    text = "🛒 Ваша корзина:\n\n"
    total = 0

    for item in cart:
        name = item.get('name', 'Без названия')
        flavor = item.get('flavor')
        price = item.get('price', 0)
        quantity = item.get('quantity', 0)
        subtotal = price * quantity

        text += f"📦 {name}"
        if flavor:
            text += f" (🌈 {flavor})"
        text += f"\n💰 {format_price(price)} ₸ x {quantity} = {format_price(subtotal)} ₸\n"
        text += "➖➖➖➖➖➖➖➖\n\n"

        total += subtotal

    text += f"💎 <b>Итого:</b> {format_price(total)} ₸"

    keyboard = cart_full_kb(cart)
    cart_msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    if state:
        await state.update_data(cart_message_id=cart_msg.message_id)


async def get_cart_item(user_id: int, product_id: str):#вспомогательная функция для изменеиния количества в корзине
    user = await db.get_user(user_id)
    if not user or not user.get('cart'):
        return None, None
    cart = user['cart']
    item = next((i for i in cart if str(i['product_id']) == str(product_id)), None)
    return user, item


@router.callback_query(F.data.startswith("increase_"))#увелечения количества вкусов в корзине
async def increase_cart_item(callback: CallbackQuery, state: FSMContext):
    try:
        # Проверка rate limit
        if not await check_rate_limit(callback.from_user.id, callback.data):
            await callback.answer("⚠️ Подождите немного перед следующим нажатием", show_alert=True)
            return
            
        await delete_previous_callback_messages(callback, state, "cart")
        product_id = callback.data.replace("increase_", "")
        user, item = await get_cart_item(callback.from_user.id, product_id)

        # Проверяем истечение корзины
        if await check_cart_expiration(user):
            await clear_expired_cart(callback.from_user.id)
            await callback.answer("🛒 Ваша корзина была очищена из-за истечения времени", show_alert=True)
            return

        if not user or not item:
            await callback.answer("Товар не найден в корзине")
            return

        product = await db.get_product(product_id)
        if not product:
            await callback.answer("Товар больше не доступен")
            return

        if 'flavor' in item:
            flavor = next((f for f in product.get('flavors', []) if f.get('name') == item['flavor']), None)
            if not flavor or flavor.get('quantity', 0) <= 0:
                await callback.answer("Нет в наличии")
                return
            if not await db.update_product_flavor_quantity(product_id, item['flavor'], -1):
                await callback.answer("Ошибка при обновлении", show_alert=True)
                return

        item['quantity'] += 1
        user['cart_expires_at'] = (datetime.now() + timedelta(minutes=10)).isoformat()

        await db.update_user(callback.from_user.id, {
            'cart': user['cart'],
            'cart_expires_at': user['cart_expires_at']
        })

        await show_cart_message(callback.message, user, state)
        await callback.answer("✅ Количество увеличено")
    except Exception as e:
        user_log.error(f"Error in increase_cart_item: {e}")
        await callback.answer("Произошла ошибка")


@router.callback_query(F.data.startswith("decrease_"))#уменьшения количества вкусов в корзине
async def decrease_cart_item(callback: CallbackQuery, state: FSMContext):
    try:
        # Проверка rate limit
        if not await check_rate_limit(callback.from_user.id, callback.data):
            await callback.answer("⚠️ Подождите немного перед следующим нажатием", show_alert=True)
            return
            
        await delete_previous_callback_messages(callback, state, "cart")
        product_id = callback.data.replace("decrease_", "")
        user, item = await get_cart_item(callback.from_user.id, product_id)

        # Проверяем истечение корзины
        if await check_cart_expiration(user):
            await clear_expired_cart(callback.from_user.id)
            await callback.answer("🛒 Ваша корзина была очищена из-за истечения времени", show_alert=True)
            return

        if not user or not item:
            await callback.answer("Товар не найден в корзине")
            return

        if 'flavor' in item:
            if not await db.update_product_flavor_quantity(product_id, item['flavor'], 1):
                await callback.answer("Ошибка при обновлении", show_alert=True)
                return

        if item['quantity'] > 1:
            item['quantity'] -= 1
        else:
            user['cart'].remove(item)

        user['cart_expires_at'] = (
            (datetime.now() + timedelta(minutes=10)).isoformat() if user['cart'] else None
        )

        await db.update_user(callback.from_user.id, {
            'cart': user['cart'],
            'cart_expires_at': user['cart_expires_at']
        })

        await show_cart_message(callback.message, user, state)
        await callback.answer("✅ Количество уменьшено")
    except Exception as e:
        user_log.error(f"Error in decrease_cart_item: {e}")
        await callback.answer("Произошла ошибка")


@router.callback_query(F.data == "clear_cart")
async def clear_cart(callback: CallbackQuery, state: FSMContext):
    try:
        # Проверка rate limit
        if not await check_rate_limit(callback.from_user.id, callback.data):
            await callback.answer("⚠️ Подождите немного перед следующим нажатием", show_alert=True)
            return
            
        # Удаляем предыдущие сообщения корзины
        await delete_previous_callback_messages(callback, state, "cart")
        
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
        
        await callback.message.answer("Корзина очищена", reply_markup=main_menu())
        await callback.answer("Корзина очищена")
        
    except Exception as e:
        user_log.error(f"Error in clear_cart: {str(e)}")
        await callback.answer("Произошла ошибка при очистке корзины")

@router.callback_query(F.data.startswith("remove_"))
async def remove_item(callback: CallbackQuery, state: FSMContext):
    try:
        # Удаляем предыдущие сообщения корзины
        await delete_previous_callback_messages(callback, state, "cart")

        product_id = callback.data.replace("remove_", "")
        user, item = await get_cart_item(callback.from_user.id, product_id)
        
        if not user or not item:
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
        user['cart'].remove(item)
        
        # Update cart expiration time if cart is not empty
        if user['cart']:
            user['cart_expires_at'] = (datetime.now() + timedelta(minutes=10)).isoformat()
        else:
            user['cart_expires_at'] = None
            
        # Update user's cart
        await db.update_user(callback.from_user.id, {
            'cart': user['cart'],
            'cart_expires_at': user['cart_expires_at']
        })
        
        # Show updated cart
        await show_cart_message(callback.message, user, state)
        await callback.answer("Товар удален из корзины")
        
    except Exception as e:
        user_log.error(f"Error in remove_item: {str(e)}")
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data == "checkout")
async def start_checkout(callback: CallbackQuery, state: FSMContext):
    try:
        # Проверка rate limit
        if not await check_rate_limit(callback.from_user.id, callback.data):
            await callback.answer("⚠️ Подождите немного перед следующим нажатием", show_alert=True)
            return
            
        # Удаляем предыдущие сообщения корзины
        await delete_previous_callback_messages(callback, state, "cart")
        
        if await check_sleep_mode(callback):
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
        
        # Check minimum quantities for Snus and E-liquid categories
        snus_total = 0
        liquid_total = 0
        
        # Count category totals
        for item in cart:
            product = await db.get_product(item['product_id'])
            if not product:
                await callback.message.answer(f"Товар {item['name']} больше не доступен")
                await callback.answer()
                return
                
            # Count category totals
            if product.get('category') == 'Снюс':
                snus_total += item['quantity']
            elif product.get('category') == 'Жидкости':
                liquid_total += item['quantity']
        
        # Check minimum quantities
        if snus_total > 0 and snus_total < 1:
            await callback.message.answer(
                "❌ Минимальный заказ для категории Снюс - 1 штук.\n"
                f"Текущее количество: {snus_total} шт."
            )
            await callback.answer()
            return
            
        if liquid_total > 0 and liquid_total < 3:
            await callback.message.answer(
                "❌ Минимальный заказ для категории Жидкости - 1 штук.\n"
                f"Текущее количество: {liquid_total} шт."
            )
            await callback.answer()
            return
        
        # Prepare order items
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
        user_log.error(f"Error in start_checkout: {str(e)}")
        await callback.answer("Произошла ошибка при оформлении заказа", show_alert=True)
        await callback.message.answer("Произошла ошибка. Попробуйте позже.", reply_markup=main_menu())

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
        user_log.error(f"Error in process_phone: {str(e)}")
        await message.answer("Произошла ошибка при обработке номера телефона", reply_markup=main_menu())
        await state.clear()

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
        admin_card_name = ADMIN_CARD_NAME
        
        payment_text = (
            f"💳 Для оплаты заказа переведите {format_price(total)} ₸ на карту:\n\n"
           f'<a href="{admin_card}">Перейти к оплате</a>\n\n'
            f"{admin_card_name}\n"
           "👆 Нажмите, чтобы оплатить заказ\n\n"
            "⚠️ ВАЖНО:\n"
            "• Стоимость доставки: до 1000 ₸ (оплачивается курьеру при получении)\n"
            "• После оплаты отправьте скриншот чека\n"
            "• Убедитесь, что вы будете находиться по указанному адресу в течение 2-3 часов\n"
            "• Встречайте курьера лично - возврат средств за неполученный заказ не производится\n"
            "• После отправки заказа вы получите номер для отслеживания в Яндекс.Go\n"
            "• Заказы отправляются пачками для оптимизации доставки"
        )
        
        await message.answer(payment_text, parse_mode="HTML")
        await state.set_state(OrderStates.waiting_payment)
    except Exception as e:
        user_log.error(f"Error in process_address: {str(e)}")
        await message.answer("Произошла ошибка при обработке адреса", reply_markup=main_menu())
        await state.clear()

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
        if not order_result:
            await message.answer(
                "Произошла ошибка при создании заказа. Пожалуйста, попробуйте позже.",
                reply_markup=main_menu()
            )
            await state.clear()
            return
            
        order_id = order_result  # create_order возвращает строку с ID
        
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
        admin_text = format_order_notification(
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
            user_log.error(f"Failed to notify admin about order {order_id}: {str(e)}")
        
        await state.clear()
        
    except Exception as e:
        user_log.error(f"Error in handle_payment_proof: {str(e)}")
        await message.answer(
            "Произошла ошибка при обработке оплаты. Пожалуйста, попробуйте позже.",
            reply_markup=main_menu()
        )
        await state.clear()

@router.callback_query(F.data == "create_order")
async def start_order(callback: CallbackQuery, state: FSMContext):
    try:
        # Проверяем режим сна
        if await check_sleep_mode(callback):
            return
            
        # ... остальной код функции ...
    except Exception as e:
        user_log.error(f"Error in start_order: {str(e)}")
        await callback.answer("❌ Произошла ошибка при создании заказа", show_alert=True)
        await callback.message.answer("Произошла ошибка. Попробуйте позже.", reply_markup=main_menu())

@router.message(F.text == "ℹ️ Помощь") #Обработчик калвиатурной кнопки кнопки Помошь
async def show_help_menu(message: Message, state: FSMContext):
    # Удаляем приветственное сообщение
    await safe_delete_message(message.bot, message.chat.id, message.message_id)
    
    # Удаляем другие сообщения
    try:
        data = await state.get_data()
        
        # Удаляем сообщение каталога
        catalog_message_id = data.get('catalog_message_id')
        if catalog_message_id:
            await safe_delete_message(message.bot, message.chat.id, catalog_message_id)
        
        # Удаляем карточки товаров
        product_message_ids = data.get('product_message_ids', [])
        if product_message_ids:
            for message_id in product_message_ids:
                await safe_delete_message(message.bot, message.chat.id, message_id)
            
            # Очищаем список ID карточек товаров
            await state.update_data(product_message_ids=[])
        
        # Удаляем сообщения корзины
        cart_message_id = data.get('cart_message_id')
        if cart_message_id:
            await safe_delete_message(message.bot, message.chat.id, cart_message_id)
    except Exception as e:
        user_log.error(f"Ошибка при удалении предыдущих сообщений: {e}")
    
    await send_help_menu(message, state)

@router.callback_query(F.data == "show_help")  #Обработчик inline кнопки Помошь
async def show_help_from_button(callback: CallbackQuery, state: FSMContext):
    try:
        # Удаляем приветственное сообщение
        await safe_delete_message(callback.message.bot, callback.message.chat.id, callback.message.message_id)
        await safe_delete_message(callback.message)
    except Exception:
        pass

    await send_help_menu(callback.message, state)
    await callback.answer()
    
async def send_help_menu(target_message: Message, state: FSMContext = None):#Вызов меню помощи
    """Общая функция для отправки меню помощи"""
    help_msg = await target_message.answer(
        "Выберите раздел помощи:",
        reply_markup=help_menu()
    )
    if state:
        await state.update_data(help_message_id=help_msg.message_id)

@router.callback_query(F.data == "help_how_to_order")#Раздел помоши (Заказ)
async def show_how_to_order(callback: CallbackQuery, state: FSMContext):
    try:
        # Удаляем предыдущие сообщения помощи
        await delete_previous_callback_messages(callback, state, "help")
    except Exception as e:
        user_log.error(f"Ошибка при удалении предыдущих сообщений помощи: {e}")
    
    text = """❓ Как сделать заказ:

    1️⃣ Выберите товары в каталоге
    2️⃣ Добавьте их в корзину
    3️⃣ Перейдите в корзину
    4️⃣ Нажмите "Оформить заказ"
    5️⃣ Укажите контактные данные
    6️⃣ Произведите оплату

    ⚠️ ВАЖНО:
    • Указывайте адрес, на котором вы будете находиться в течение 2-3 часов
    • После отправки заказа вы получите номер для отслеживания в Яндекс.Go
    • Встречайте курьера лично - возврат средств невозможен
    • Заказы отправляются пачками для оптимизации доставки
    • Магазин автоматически уходит в сон при достижении 25 заказов

    После оформления заказа ожидайте подтверждения менеджера"""
    
    await safe_delete_message(callback.message)
    help_msg = await callback.message.answer(text, reply_markup=help_menu())
    await state.update_data(help_message_id=help_msg.message_id)
    await callback.answer()

@router.callback_query(F.data == "help_payment")#Раздел помоши (Оплата)
async def show_payment_info(callback: CallbackQuery, state: FSMContext):
    try:
        # Удаляем предыдущие сообщения помощи
        await delete_previous_callback_messages(callback, state, "help")
    except Exception as e:
        user_log.error(f"Ошибка при удалении предыдущих сообщений помощи: {e}")
    
    text = """💳 Способы оплаты:

    • Онлайн-оплата (переводом на карту)
    • Стоимость доставки: до 1000 ₸ (оплачивается курьеру при получении)

    ⚠️ ВАЖНО:
    • После оплаты отправьте скриншот чека
    • Убедитесь, что вы будете находиться по указанному адресу в течение 2-3 часов
    • Встречайте курьера лично - возврат средств за неполученный заказ не производится"""
    
    await safe_delete_message(callback.message)
    help_msg = await callback.message.answer(text, reply_markup=help_menu())
    await state.update_data(help_message_id=help_msg.message_id)
    await callback.answer()

@router.callback_query(F.data == "help_delivery")#Раздел помоши (Доставка)
async def show_delivery_info(callback: CallbackQuery, state: FSMContext):
    try:
        # Удаляем предыдущие сообщения помощи
        await delete_previous_callback_messages(callback, state, "help")
    except Exception as e:
        user_log.error(f"Ошибка при удалении предыдущих сообщений помощи: {e}")
    
    text="""🚚 Информация о доставке:
    • Доставка осуществляется в течение 2-3 часов
    • Стоимость доставки: до 1000 ₸ (оплачивается курьеру при получении)
    • Курьер свяжется с вами перед доставкой
    • После отправки заказа вы получите номер для отслеживания в Яндекс.Go
    • Заказы отправляются пачками для оптимизации доставки

    ⚠️ ВАЖНО:
    • Указывайте адрес, на котором вы будете находиться в течение 2-3 часов
    • Встречайте курьера лично - возврат средств за неполученный заказ не производится
    • Магазин автоматически уходит в сон при достижении 25 заказов

    Просим отнестись с пониманием в это непростое время."""

    await safe_delete_message(callback.message)
    help_msg = await callback.message.answer(text, reply_markup=help_menu())
    await state.update_data(help_message_id=help_msg.message_id)
    await callback.answer()

@router.callback_query(F.data == "help_contact")
async def show_contact_help(callback: CallbackQuery, state: FSMContext):
    try:
        await delete_previous_callback_messages(callback, state, "help")
    except Exception as e:
        user_log.error(f"Произошла ошибка при удалении придыдуших сообшений: {e}")
    
    text="""
    🤙Возникли проблемы?
⬇️Telegram для связи⬇️
            @tikto7182
    """
    await safe_delete_message(callback.message)
    help_msg = await callback.message.answer(text, reply_markup=help_menu())
    await state.update_data(help_message_id=help_msg.message_id)
    await callback.answer()



async def delete_welcome_message(message: Message, state: FSMContext):
    """Удаляет приветственное сообщение пользователя"""
    try:
        data = await state.get_data()
        welcome_message_id = data.get('welcome_message_id')
        
        if welcome_message_id:
            await safe_delete_message(message.bot, message.chat.id, welcome_message_id)
    except Exception as e:
        user_log.error(f"Ошибка в delete_welcome_message: {e}")

async def delete_previous_messages(message: Message, state: FSMContext, message_type: str = "catalog"):
    """Удаляет предыдущие сообщения определенного типа"""
    try:
        data = await state.get_data()
        previous_message_id = data.get(f'{message_type}_message_id')
        
        if previous_message_id:
            await safe_delete_message(message.bot, message.chat.id, previous_message_id)
    except Exception as e:
        user_log.error(f"Ошибка в delete_previous_messages: {e}")

async def delete_previous_callback_messages(callback: CallbackQuery, state: FSMContext, message_type: str = "catalog"):
    """Удаляет предыдущие сообщения для callback запросов"""
    try:
        data = await state.get_data()
        previous_message_id = data.get(f'{message_type}_message_id')
        
        if previous_message_id:
            await safe_delete_message(callback.message.bot, callback.message.chat.id, previous_message_id)
    except Exception as e:
        user_log.error(f"Ошибка в delete_previous_callback_messages: {e}")

async def delete_product_cards(callback: CallbackQuery, state: FSMContext):
    """Удаляет карточки товаров при возврате к каталогу"""
    try:
        data = await state.get_data()
        product_message_ids = data.get('product_message_ids', [])
        
        if product_message_ids:
            for message_id in product_message_ids:
                await safe_delete_message(callback.message.bot, callback.message.chat.id, message_id)
            
            # Очищаем список ID карточек товаров
            await state.update_data(product_message_ids=[])
    except Exception as e:
        user_log.error(f"Ошибка в delete_product_cards: {e}")

@router.callback_query(F.data == "cancel_clear_cart")
async def cancel_clear_cart(callback: CallbackQuery, state: FSMContext):
    try:
        # Удаляем предыдущие сообщения корзины
        await delete_previous_callback_messages(callback, state, "cart")
        
        user = await db.get_user(callback.from_user.id)
        if not user or not user.get('cart'):
            await callback.message.edit_text(
                "Ваша корзина пуста",
                reply_markup=main_menu()
            )
        else:
            total = sum(item['price'] * item['quantity'] for item in user['cart'])
            await callback.message.edit_text(
                f"💵 Итого: {format_price(total)} ₸",
                reply_markup=cart_actions_kb()
            )
        await callback.answer("Очистка корзины отменена")
        
    except Exception as e:
        user_log.error(f"Error in cancel_clear_cart: {str(e)}")
        await callback.answer("Произошла ошибка")

async def check_cart_expiration(user: dict) -> bool:
    """Проверяет, истекла ли корзина пользователя"""
    if not user or not user.get('cart') or not user.get('cart_expires_at'):
        return False
    
    try:
        expires_at = datetime.fromisoformat(user['cart_expires_at'])
        return datetime.now() > expires_at
    except (ValueError, TypeError):
        return False

async def clear_expired_cart(user_id: int) -> bool:
    """Очищает истекшую корзину пользователя и возвращает товары в наличие"""
    try:
        user = await db.get_user(user_id)
        if not user or not user.get('cart'):
            return False
            
        if await check_cart_expiration(user):
            # Возвращаем товары в наличие
            for item in user['cart']:
                if 'flavor' in item:
                    await db.update_product_flavor_quantity(
                        item['product_id'],
                        item['flavor'],
                        item['quantity']
                    )
            
            # Очищаем корзину
            await db.update_user(user_id, {
                'cart': [],
                'cart_expires_at': None
            })
            
            user_log.info(f"Expired cart cleared for user {user_id}")
            return True
        return False
    except Exception as e:
        user_log.error(f"Error clearing expired cart for user {user_id}: {e}")
        return False

async def notify_cart_expiration(bot, user_id: int):
    """Уведомляет пользователя об истечении корзины"""
    try:
        await bot.send_message(
            chat_id=user_id,
            text="⏰ Ваша корзина была автоматически очищена из-за истечения времени (5 минут).\n"
                 "Товары возвращены в наличие. Вы можете добавить их заново."
        )
    except Exception as e:
        user_log.error(f"Error notifying user {user_id} about cart expiration: {e}")

async def cleanup_expired_carts(bot=None):
    """Очищает все истекшие корзины"""
    try:
        # Получаем всех пользователей с корзинами
        users = await db.get_users_with_cart()
        
        cleared_count = 0
        for user in users:
            if await clear_expired_cart(user['user_id']):
                cleared_count += 1
                # Уведомляем пользователя если bot доступен
                if bot:
                    await notify_cart_expiration(bot, user['user_id'])
        
        if cleared_count > 0:
            user_log.info(f"Cleared {cleared_count} expired carts")
            
    except Exception as e:
        user_log.error(f"Error in cleanup_expired_carts: {e}")

async def start_cart_cleanup(bot=None):
    """Запускает периодическую очистку истекших корзин"""
    while True:
        await asyncio.sleep(60)  # Проверяем каждую минуту
        await cleanup_expired_carts(bot)

@router.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery, state: FSMContext):
    try:
        # Удаляем предыдущие сообщения
        await delete_previous_callback_messages(callback, state, "cart")
        await delete_previous_callback_messages(callback, state, "catalog")
        await delete_previous_callback_messages(callback, state, "help")
        
        # Удаляем карточки товаров
        await delete_product_cards(callback, state)
        
        await safe_delete_message(callback.message)
        
        # Отправляем приветственное сообщение с основными кнопками
        welcome_msg = await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text="Добро пожаловать в магазин!\n\n"
                 "Выберите нужный раздел:",
            reply_markup=main_menu()
        )
        
        await state.update_data(welcome_message_id=welcome_msg.message_id)
        await callback.answer("Переход в главное меню")
        
    except Exception as e:
        user_log.error(f"Ошибка в show_main_menu: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")

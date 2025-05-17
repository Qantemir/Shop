from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
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
    waiting_for_phone = State()
    waiting_for_address = State()
    waiting_for_payment = State()

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
        print(f"[DEBUG] Processing product_id: {product_id}")
        
        # Get product first to validate it exists
        product = await db.get_product(product_id)
        if not product:
            print(f"[DEBUG] Product not found: {product_id}")
            await callback.answer("Товар не найден или недоступен")
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
        
        # Initialize cart if needed
        cart = user.get('cart', [])
        if cart is None:
            cart = []
        
        # Check if product already in cart
        found = False
        for item in cart:
            if item.get('product_id') == product_id:  # Using string comparison
                item['quantity'] += 1
                found = True
                break
        
        # Add new item if not found
        if not found:
            cart.append({
                'product_id': product_id,  # Store as string
                'name': product['name'],
                'price': product['price'],
                'quantity': 1
            })
        
        # Update cart
        await db.update_user(callback.from_user.id, {'cart': cart})
        await callback.answer("Товар добавлен в корзину!")
        print(f"[DEBUG] Successfully added product {product_id} to cart")
        
    except Exception as e:
        print(f"[ERROR] Error in add_to_cart: {str(e)}")
        await callback.answer("Произошла ошибка при добавлении товара")

@router.message(F.text == "🛒 Корзина")
async def show_cart(message: Message):
    print("[DEBUG] Starting show_cart handler")
    try:
        user = await db.get_user(message.from_user.id)
        
        # If no user or no cart, just show empty cart message
        if not user or not user.get('cart'):
            await message.answer("Ваша корзина пуста", reply_markup=main_menu())
            return
        
        cart = user['cart']
        total = 0
        
        # Show each item in cart
        for item in cart:
            subtotal = item['price'] * item['quantity']
            total += subtotal
            await message.answer(
                f"📦 {item['name']}\n"
                f"💰 {item['price']} Tg x {item['quantity']} = {subtotal} Tg",
                reply_markup=cart_item_kb(str(item['product_id']))
            )
        
        # Show total
        await message.answer(
            f"💵 Итого: {total} Tg",
            reply_markup=cart_actions_kb()
        )
        print("[DEBUG] Cart displayed successfully")
        
    except Exception as e:
        print(f"[ERROR] Error in show_cart: {str(e)}")
        await message.answer("Произошла ошибка при отображении корзины")

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
                f"💰 {item['price']} Tg x {item['quantity']} = {subtotal} Tg",
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
                    f"💰 {item['price']} Tg x {item['quantity']} = {subtotal} Tg",
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

@router.callback_query(F.data == "confirm_clear_cart")
async def confirm_clear_cart(callback: CallbackQuery):
    await callback.message.edit_text(
        "Вы уверены, что хотите очистить корзину?",
        reply_markup=confirm_clear_cart_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "clear_cart")
async def clear_cart(callback: CallbackQuery):
    try:
        await db.update_user(callback.from_user.id, {'cart': []})
        await callback.message.edit_text(
            "Корзина очищена!",
            reply_markup=main_menu()
        )
        await callback.answer()
    except Exception as e:
        print(f"[ERROR] Error in clear_cart: {str(e)}")
        await callback.answer("Произошла ошибка при очистке корзины")

@router.callback_query(F.data == "cancel_clear_cart")
async def cancel_clear_cart(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    cart = user.get('cart', [])
    
    if not cart:
        await callback.message.edit_text("Ваша корзина пуста", reply_markup=main_menu())
    else:
        total = sum(item['price'] * item['quantity'] for item in cart)
        await callback.message.edit_text(
            f"💵 Итого: {total} Tg",
            reply_markup=cart_actions_kb()
        )
    await callback.answer("Операция отменена")

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
    try:
        user = await db.get_user(message.from_user.id)
        cart = user.get('cart', [])
        
        if not cart:
            await message.answer("Ваша корзина пуста")
            await state.clear()
            return
        
        data = await state.get_data()
        total = sum(item['price'] * item['quantity'] for item in cart)
        
        # Save address and create order
        await state.update_data(address=message.text, total=total)
        
        # Send payment instructions
        payment_msg = (
            f"💳 Для оплаты заказа переведите {total} Tg на карту:\n\n"
            f"<code>{ADMIN_CARD}</code>\n\n"
            "После оплаты отправьте скриншот чека или фото подтверждения оплаты."
        )
        await message.answer(payment_msg, parse_mode="HTML")
        await state.set_state(OrderStates.waiting_for_payment)
        
    except Exception as e:
        print(f"[ERROR] Error in process_address: {str(e)}")
        await message.answer(
            "Произошла ошибка. Пожалуйста, попробуйте позже.",
            reply_markup=main_menu()
        )
        await state.clear()

@router.message(OrderStates.waiting_for_payment, F.photo)
async def process_payment(message: Message, state: FSMContext):
    try:
        user = await db.get_user(message.from_user.id)
        cart = user.get('cart', [])
        data = await state.get_data()
        
        # Create order data
        order_data = {
            'user_id': message.from_user.id,
            'username': message.from_user.username,
            'phone': data['phone'],
            'address': data['address'],
            'items': cart,
            'status': 'pending',
            'total': data['total'],
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
            "Спасибо! Ваш заказ принят и ожидает подтверждения оплаты. "
            "Мы уведомим вас, когда заказ будет подтвержден.",
            reply_markup=main_menu()
        )
        
        # Notify admin about new order
        admin_notification = (
            f"📦 Новый заказ #{order_id}\n"
            f"👤 От: {message.from_user.full_name} (@{message.from_user.username})\n"
            f"📱 Телефон: {data['phone']}\n"
            f"📍 Адрес: {data['address']}\n\n"
            f"🛍 Товары:\n"
        )
        
        for item in cart:
            subtotal = item['price'] * item['quantity']
            admin_notification += f"- {item['name']} x{item['quantity']} = {subtotal} Tg\n"
        
        admin_notification += f"\n💰 Итого: {data['total']} Tg"
        
        # Send notification and payment photo to admin
        try:
            await message.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=message.photo[-1].file_id,
                caption=admin_notification,
                reply_markup=order_management_kb(order_id)
            )
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
            "confirmed": "✅ Ваш заказ подтвержден и готовится к отправке!",
            "cancelled": "❌ Ваш заказ был отменен. Свяжитесь с администратором для уточнения деталей.",
            "completed": "🎉 Ваш заказ выполнен! Спасибо за покупку!",
            "paid": "💰 Оплата подтверждена! Ваш заказ готовится к отправке."
        }
        
        if new_status in status_messages:
            try:
                await callback.bot.send_message(
                    chat_id=order['user_id'],
                    text=f"📦 Обновление статуса заказа #{order_id}:\n\n{status_messages[new_status]}"
                )
            except Exception as e:
                print(f"[ERROR] Failed to notify user about order status: {str(e)}")
        
        await callback.message.edit_text(
            f"{callback.message.text}\n\nСтатус обновлен: {ORDER_STATUSES[new_status]}",
            reply_markup=order_management_kb(order_id)
        )
        await callback.answer("Статус заказа обновлен")
        
    except Exception as e:
        print(f"[ERROR] Error in handle_order_status_update: {str(e)}")
        await callback.answer("Произошла ошибка при обновлении статуса")

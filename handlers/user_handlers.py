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
    confirm_order_kb
)

router = Router()

class OrderStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_address = State()

@router.message(Command("start"))
async def cmd_start(message: Message):
    # Временно выводим ID пользователя
    await message.answer(f"Ваш ID: {message.from_user.id}")
    
    user_data = {
        "user_id": message.from_user.id,
        "username": message.from_user.username,
        "first_name": message.from_user.first_name,
        "last_name": message.from_user.last_name,
        "cart": []
    }
    await db.create_user(user_data)
    
    await message.answer(
        "Добро пожаловать в наш магазин!",
        reply_markup=main_menu()
    )

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
    product_id = callback.data.replace("add_to_cart_", "")
    product = await db.get_product(product_id)
    
    if not product:
        await callback.answer("Товар не найден")
        return
    
    user = await db.get_user(callback.from_user.id)
    cart = user.get('cart', [])
    
    # Check if product already in cart
    for item in cart:
        if item['product_id'] == product_id:
            item['quantity'] += 1
            break
    else:
        cart.append({
            'product_id': product_id,
            'name': product['name'],
            'price': product['price'],
            'quantity': 1
        })
    
    await db.update_user(callback.from_user.id, {'cart': cart})
    await callback.answer("Товар добавлен в корзину!")

@router.message(F.text == "🛒 Корзина")
async def show_cart(message: Message):
    user = await db.get_user(message.from_user.id)
    cart = user.get('cart', [])
    
    if not cart:
        await message.answer("Ваша корзина пуста")
        return
    
    total = 0
    text = "🛒 Ваша корзина:\n\n"
    
    for item in cart:
        subtotal = item['price'] * item['quantity']
        total += subtotal
        text += f"📦 {item['name']}\n"
        text += f"💰 {item['price']} RUB x {item['quantity']} = {subtotal} RUB\n"
        text += "➖➖➖➖➖➖➖➖\n"
    
    text += f"\n💵 Итого: {total} RUB"
    await message.answer(text, reply_markup=cart_actions_kb())

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

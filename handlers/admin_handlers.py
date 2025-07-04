from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime, timedelta
import asyncio
import logging

from config import ADMIN_ID, ADMIN_SWITCHING, ORDER_STATUSES
from database.mongodb import db
from keyboards.admin_kb import (
    admin_main_menu,
    product_management_kb,
    categories_kb,
    order_management_kb,
    sleep_mode_kb,
    product_edit_kb,  # добавлен импорт
    build_flavor_editor  # импорт функции для управления вкусами
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

@router.message(F.text == "📦 Управление товарами")#Обработка клавиатурной кнопки управление товароми
@check_admin_session
async def product_management(message: Message):
    try:
        await message.answer(
            "Выберите действие для управления товарами:",
            reply_markup=product_management_kb()
        )
    except Exception as e:
        logger.error(f"Ошибка в product_management: {e}")

@router.callback_query(F.data == "back_to_product_management")#Обработка кнопки назад в управление товарами
@check_admin_session
async def back_to_product_management(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выберите действие для управления товарами:",
        reply_markup=product_management_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "list_products")#Обработка кнопки список товаров
@check_admin_session
async def list_products(callback: CallbackQuery):
    products = await db.get_all_products()

    if not products:
        await callback.message.edit_text(
            "📭 Товары отсутствуют.",
            reply_markup=product_management_kb()
        )
        await callback.answer()
        return

    lines = [
        f"📦 {p['name']}\n💰 {p['price']} ₸\n📝 {p['description']}"
        for p in products
    ]
    text = "📋 Список товаров:\n\n" + "\n\n".join(lines)

    await callback.message.edit_text(
        text,
        reply_markup=product_management_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "add_product")#Обработка кнопки добавить продукт
@check_admin_session
async def add_product_start(callback: CallbackQuery, state: FSMContext):
    try:
        await state.clear()
        await callback.message.edit_text(
            "Выберите категорию товара:",
            reply_markup=categories_kb()
        )
        await state.set_state(AdminStates.setting_name)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в add_product_start: {e}")
        await callback.message.edit_text(
            "Произошла ошибка. Попробуйте снова.",
            reply_markup=product_management_kb()
        )

@router.callback_query(F.data == "edit_products")#Обработка кнопки редактировать
@check_admin_session
async def edit_products_list(callback: CallbackQuery):
    products = await db.get_all_products()

    if not products:
        await callback.message.edit_text(
            "📭 Товары отсутствуют.",
            reply_markup=product_management_kb()
        )
        await callback.answer()
        return

    text_lines = ["🛠 Выберите товар для редактирования:\n"]
    keyboard = []

    for product in products:
        name = product.get("name", "Без названия")
        price = product.get("price", "—")
        product_id = str(product.get("_id"))

        text_lines.append(f"📦 {name} — {price} ₸")
        keyboard.append([
            InlineKeyboardButton(
                text=f"✏️ {name}",
                callback_data=f"edit_product_{product_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_product_management")
    ])

    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()

@router.callback_query(F.data == "delete_product")#Потверждения продукта
@check_admin_session
async def delete_product_list(callback: CallbackQuery):
    products = await db.get_all_products()

    if not products:
        await callback.message.edit_text(
            "📭 Товары отсутствуют.",
            reply_markup=product_management_kb()
        )
        await callback.answer()
        return

    keyboard = [
        [InlineKeyboardButton(
            text=f"❌ {product.get('name', 'Без названия')}",
            callback_data=f"confirm_delete_{str(product.get('_id'))}"
        )]
        for product in products
    ]

    keyboard.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_product_management")
    ])

    text = "\n".join([
        "🗑 Выберите товар для удаления:",
        *(f"📦 {p.get('name', 'Без названия')} — {p.get('price', '—')} ₸" for p in products)
    ])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete_"))#Потвержденик удоления
@check_admin_session
async def confirm_delete_product(callback: CallbackQuery):
    product_id = callback.data.removeprefix("confirm_delete_")

    try:
        result = await db.delete_product(product_id)
        if result:
            text = "✅ Товар успешно удалён!"
        else:
            text = "⚠️ Не удалось удалить товар. Возможно, он уже удалён."
    except Exception as e:
        logger.error(f"Ошибка при удалении товара {product_id}: {e}")
        text = "❌ Произошла ошибка при удалении товара."

    await callback.message.edit_text(
        text,
        reply_markup=product_management_kb()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("edit_product_"))#Обработка кнопки редактировать 
async def edit_product_menu(callback: CallbackQuery, state: FSMContext):
    try:
        product_id = callback.data.removeprefix("edit_product_")
        product = await db.get_product(product_id)

        if not product:
            await callback.answer("⚠️ Товар не найден.")
            return

        await state.update_data(editing_product_id=product_id)

        name = product.get("name", "Без названия")
        price = format_price(product.get("price", 0))
        description = product.get("description", "—")

        text = f"""🛠 <b>Редактирование товара</b>:

    📦 Название: {name}
    💰 Цена: {price} ₸
    📝 Описание: {description}
    """
        # Добавление вкусов, если есть
        flavors = product.get("flavors", [])
        if flavors:
            text += "\n🌈 Доступно:\n"
            for flavor in flavors:
                flavor_name = flavor.get('name', '—')
                quantity = flavor.get('quantity', 0)
                text += f"• {flavor_name} — {quantity} шт.\n"

        await callback.message.edit_text(
            text,
            reply_markup=product_edit_kb(product_id),
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка в edit_product_menu: {e}")
        await callback.answer("❌ Произошла ошибка при загрузке товара.")

@router.message(AdminStates.setting_name)#Обработка ввода названия товара
@check_admin_session
async def process_edit_name(message: Message, state: FSMContext):
    try:
        data = await state.get_data()

        # Добавление нового товара
        if data.get('is_adding_product'):
            await state.update_data(name=message.text)
            await message.answer("Введите цену товара (только число):")
            await state.set_state(AdminStates.setting_price)
            return

        # Редактирование существующего товара
        product_id = data.get('editing_product_id')
        if not product_id:
            await message.answer("❌ Ошибка: товар не найден.")
            await state.clear()
            return

        await db.update_product(product_id, {'name': message.text})
        product = await db.get_product(product_id)

        if not product:
            await message.answer("❌ Ошибка: товар не найден.")
            await state.clear()
            return

        name = product.get("name", "Без названия")
        price = product.get("price", "—")
        description = product.get("description", "—")
        flavors = product.get("flavors", [])

        text = f"""✅ Название успешно изменено!

    📦 Название: {name}
    💰 Цена: {price} ₸
    📝 Описание: {description}
    """

        if flavors:
            text += "\n🌈 Доступно:\n"
            for flavor in flavors:
                flavor_name = flavor.get('name', '')
                quantity = flavor.get('quantity', 0)
                text += f"• {flavor_name} — {quantity} шт.\n"

        await message.answer(text, reply_markup=product_edit_kb(product_id))
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка в process_edit_name: {e}")
        await message.answer("❌ Произошла ошибка при обновлении названия.")
        await state.clear()

@router.message(AdminStates.setting_price)#Обработка ввода цены товара
@check_admin_session
async def handle_setting_price(message: Message, state: FSMContext):
    try:
        if not message.text or not message.text.isdigit():
            await message.answer("❗ Пожалуйста, введите только число для цены:")
            return

        price = int(message.text)
        data = await state.get_data()

        # Добавление нового товара
        if data.get('is_adding_product') or ('name' in data and 'category' in data and 'price' not in data):
            await state.update_data(price=price)
            await message.answer("Введите описание товара:")
            await state.set_state(AdminStates.setting_description)
            return

        # Редактирование существующего товара
        product_id = data.get('editing_product_id')
        if not product_id:
            await message.answer("❌ Ошибка: товар не найден.")
            await state.clear()
            return

        await db.update_product(product_id, {'price': price})
        product = await db.get_product(product_id)

        if not product:
            await message.answer("❌ Ошибка: товар не найден.")
            await state.clear()
            return

        name = product.get("name", "Без названия")
        price = format_price(product.get("price", 0))
        description = product.get("description", "—")
        flavors = product.get("flavors", [])

        text = f"""✅ Цена успешно изменена!

    📦 Название: {name}
    💰 Цена: {price} ₸
    📝 Описание: {description}
    """

        if flavors:
            text += "\n🌈 Доступно:\n"
            for flavor in flavors:
                flavor_name = flavor.get("name", "—")
                quantity = flavor.get("quantity", 0)
                text += f"• {flavor_name} — {quantity} шт.\n"

        await message.answer(
            text,
            reply_markup=product_edit_kb(product_id),
            parse_mode="HTML"
        )
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка в handle_setting_price: {e}")
        await message.answer("❌ Произошла ошибка при обновлении цены.")
        await state.clear()

@router.message(AdminStates.setting_description)#Обработка ввода описания товара
@check_admin_session
async def handle_setting_description(message: Message, state: FSMContext):
    try:
        data = await state.get_data()

        # Добавление нового товара
        if data.get('is_adding_product') or (
            'name' in data and 'category' in data and 'price' in data and 'description' not in data
        ):
            await state.update_data(description=message.text)
            await message.answer("📸 Отправьте фотографию товара:")
            await state.set_state(AdminStates.setting_image)
            return

        # Редактирование существующего товара
        product_id = data.get('editing_product_id')
        if not product_id:
            await message.answer("❌ Ошибка: товар не найден.")
            await state.clear()
            return

        await db.update_product(product_id, {'description': message.text})
        product = await db.get_product(product_id)

        if not product:
            await message.answer("❌ Ошибка: товар не найден.")
            await state.clear()
            return

        name = product.get("name", "Без названия")
        price = format_price(product.get("price", 0))
        description = product.get("description", "—")
        flavors = product.get("flavors", [])

        text = f"""✅ Описание успешно изменено!

    📦 Название: {name}
    💰 Цена: {price} ₸
    📝 Описание: {description}
    """

        if flavors:
            text += "\n🌈 Доступно:\n"
            for flavor in flavors:
                flavor_name = flavor.get("name", "—")
                quantity = flavor.get("quantity", 0)
                text += f"• {flavor_name} — {quantity} шт.\n"

        await message.answer(
            text,
            reply_markup=product_edit_kb(product_id),
            parse_mode="HTML"
        )
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка в handle_setting_description: {e}")
        await message.answer("❌ Произошла ошибка при обновлении описания.")
        await state.clear()

@router.message(AdminStates.setting_image, F.photo)#Обработка ввода фото товара
@check_admin_session
async def process_edit_photo(message: Message, state: FSMContext):
    try:
        if not message.photo or not message.photo[-1]:
            await message.answer("❗ Пожалуйста, отправьте корректное фото.")
            return

        photo_id = message.photo[-1].file_id
        data = await state.get_data()

        # Добавление нового товара
        if data.get('is_adding_product') or (
            'name' in data and 'category' in data and 'price' in data and 'description' in data and 'photo' not in data
        ):
            product_data = {
                "name": data["name"],
                "category": data["category"],
                "price": data["price"],
                "description": data["description"],
                "photo": photo_id,
                "available": True
            }

            await db.add_product(product_data)
            await message.answer("✅ Товар успешно добавлен!", reply_markup=product_management_kb())
            await state.clear()
            return

        # Редактирование фото товара
        product_id = data.get('editing_product_id')
        if not product_id:
            await message.answer("❌ Ошибка: товар не найден.")
            await state.clear()
            return

        await db.update_product(product_id, {'photo': photo_id})
        product = await db.get_product(product_id)

        if not product:
            await message.answer("❌ Ошибка: товар не найден.")
            await state.clear()
            return

        name = product.get("name", "Без названия")
        price = format_price(product.get("price", 0))
        description = product.get("description", "—")
        flavors = product.get("flavors", [])

        text = f"""✅ Фото успешно изменено!

    📦 Название: {name}
    💰 Цена: {price} ₸
    📝 Описание: {description}
    """

        if flavors:
            text += "\n🌈 Доступно:\n"
            for flavor in flavors:
                flavor_name = flavor.get('name', '—')
                quantity = flavor.get('quantity', 0)
                text += f"• {flavor_name} — {quantity} шт.\n"

        await message.answer_photo(
            photo=photo_id,
            caption=text,
            reply_markup=product_edit_kb(product_id),
            parse_mode="HTML"
        )
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка в process_edit_photo: {e}")
        await message.answer("❌ Произошла ошибка при обновлении фото.")
        await state.clear()

@router.message(F.text == "📊 Заказы")#Обработка кнопки заказы
@check_admin_session
async def show_orders(message: Message, state: FSMContext):
    try:
        await db.ensure_connected()
        orders = await db.get_all_orders()

        if not orders:
            await message.answer("📭 Нет активных заказов.")
            return

        # Подсчёт активных заказов
        active_orders = [o for o in orders if o.get("status") in ["pending", "confirmed"]]
        active_count = len(active_orders)

        # Клавиатура управления
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Очистить заказы", callback_data="delete_all_orders")]
        ])

        sent_message_ids = []
        # Отображение каждого заказа
        for order in orders:
            order_id = str(order.get("_id", ""))
            user_data = {
                "full_name": order.get("username", "Не указано"),
                "username": order.get("username", "Не указано"),
            }

            order_text = format_order_notification(
                order_id,
                user_data,
                order,
                order.get("items", []),
                order.get("total_amount", 0)
            )

            status = order.get("status", "pending")
            status_text = ORDER_STATUSES.get(status, "Статус неизвестен")

            order_text += f"\n\nСтатус: {status_text}"

            msg = await message.answer(
                order_text,
                parse_mode="HTML",
                reply_markup=order_management_kb(order_id, status)
            )
            sent_message_ids.append(msg.message_id)

        # После всех заказов — статистика и кнопки
        stat_msg = await message.answer(
            f"📊 Статистика заказов:\n"
            f"📦 Заказов: {active_count}/{ADMIN_SWITCHING}\n"
            f"⚠️ Магазин уйдёт в режим сна при достижении {ADMIN_SWITCHING} активных заказов\n",
            reply_markup=keyboard
        )
        sent_message_ids.append(stat_msg.message_id)

        # Сохраняем id сообщений в state
        await state.update_data(order_message_ids=sent_message_ids)

        # Автопереход в спящий режим
        if active_count >= ADMIN_SWITCHING:
            end_time = (datetime.now() + timedelta(hours=2)).strftime("%H:%M")
            await db.set_sleep_mode(True, end_time)
            await message.answer(
                f"⚠️ Достигнут лимит заказов ({active_count}). "
                f"Магазин переведён в режим сна до {end_time}."
            )

    except Exception as e:
        logger.error(f"Ошибка при отображении заказов: {e}")
        await message.answer("❌ Произошла ошибка при получении заказов.")

@router.callback_query(F.data == "delete_all_orders")#Обработка кнопки удалить все заказы
@check_admin_session
async def delete_all_orders(callback: CallbackQuery, state: FSMContext):
    try:
        orders = await db.get_all_orders()

        if not orders:
            await callback.answer("❗ Нет заказов для удаления.")
            return

        for order in orders:
            order_id = str(order.get("_id"))
            status = order.get("status")
            items = order.get("items", [])

            if status == "pending":
                for item in items:
                    product_id = item.get("product_id")
                    flavor = item.get("flavor")
                    quantity = item.get("quantity", 0)

                    if product_id and flavor:
                        try:
                            await db.update_product_flavor_quantity(product_id, flavor, quantity)
                        except Exception as e:
                            logger.exception(f"Ошибка при возврате на склад: {e}")

            try:
                await db.delete_order(order_id)
            except Exception as e:
                logger.exception(f"Ошибка при удалении заказа {order_id}: {e}")

        # Удаляем все сообщения с заказами и статистикой
        data = await state.get_data()
        order_message_ids = data.get("order_message_ids", [])
        for msg_id in order_message_ids:
            try:
                await callback.bot.delete_message(callback.message.chat.id, msg_id)
            except Exception as e:
                logger.exception(f"Ошибка при удалении сообщения заказа: {e}")

        # Ответ админу (короткое подтверждение)
        await callback.message.answer("✅ Все заказы и сообщения удалены.")
        await state.clear()
        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка при массовом удалении заказов: {e}")
        await callback.answer("❌ Произошла ошибка при удалении заказов.")

@router.message(F.text == "📢 Рассылка")#Обработка кнопки рассылка
@check_admin_session
async def broadcast_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📢 Введите текст рассылки или отправьте /cancel для отмены:"
    )
    await state.set_state(AdminStates.broadcasting)
    logger.info(f"Админ {message.from_user.id} начал рассылку")

@router.message(Command("cancel"))#Обработка команды отмена
@check_admin_session
async def cancel_any_state(message: Message, state: FSMContext):
    current_state = await state.get_state()

    if current_state:
        await state.clear()
        await message.answer(
            "❌ Действие отменено.",
            reply_markup=admin_main_menu()
        )
        logger.info(f"Админ {message.from_user.id} отменил состояние {current_state}")
    else:
        await message.answer(
            "Нет активного действия для отмены.",
            reply_markup=admin_main_menu()
        )

@router.message(AdminStates.broadcasting)#Обработка ввода текста рассылки
@check_admin_session
async def prepare_broadcast(message: Message, state: FSMContext):
    text = message.text.strip()

    if not text:
        await message.answer("⚠️ Сообщение не может быть пустым. Попробуйте снова.")
        return

    # Сохраняем текст в состояние
    await state.update_data(broadcast_text=text)

    # Кнопки подтверждения
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправить", callback_data="confirm_broadcast"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_broadcast")
        ]
    ])

    await message.answer(
        f"📢 Подтвердите отправку сообщения:\n\n{text}",
        reply_markup=keyboard
    )

    await state.set_state(AdminStates.confirm_broadcast)

SEND_DELAY = 0.05

@router.callback_query(F.data == "confirm_broadcast")
@check_admin_session
async def handle_confirm_broadcast(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    broadcast_text = data.get("broadcast_text")

    if not broadcast_text:
        await callback.answer("❌ Ошибка: текст не найден")
        await state.clear()
        return

    users = await db.get_all_users()
    if not users:
        await callback.message.edit_text("⚠️ Пользователи не найдены.")
        await state.clear()
        return

    sent_count = 0
    failed_count = 0
    users_to_delete = []

    for user in users:
        try:
            await callback.bot.send_message(
                chat_id=user['user_id'],
                text=broadcast_text
            )
            sent_count += 1
            await asyncio.sleep(SEND_DELAY)
        except Exception as e:
            error_text = str(e).lower()
            logger.error(f"Не удалось отправить сообщение пользователю {user['user_id']}: {e}")
            failed_count += 1
            if 'chat not found' in error_text or 'bot was blocked by the user' in error_text:
                try:
                    user_data = await db.get_user(user['user_id'])
                    cart = user_data.get('cart', []) if user_data else []
                    if not cart:
                        users_to_delete.append(user['user_id'])
                    else:
                        logger.info(f"Пользователь {user['user_id']} не удалён: корзина не пуста.")
                except Exception as del_e:
                    logger.error(f"Ошибка при проверке пользователя {user['user_id']}: {del_e}")
            continue

    # Массовое удаление пользователей после рассылки
    if users_to_delete:
        try:
            deleted_count = await db.delete_users_bulk(users_to_delete)
            logger.info(f"Массово удалено пользователей: {deleted_count}")
        except Exception as e:
            logger.error(f"Ошибка при массовом удалении пользователей: {e}")

    summary = (
        f"✅ Рассылка завершена!\n\n"
        f"📨 Отправлено: {sent_count}\n"
        f"{'❌ Не доставлено: ' + str(failed_count) if failed_count else ''}"
    )

    await callback.message.edit_text(summary)
    await callback.message.answer("Главное меню", reply_markup=admin_main_menu())
    await callback.answer()

    logger.info(f"Рассылка завершена: отправлено {sent_count}, не доставлено {failed_count}")


@router.callback_query(F.data == "cancel_broadcast")#Обработка кнопки отмены рассылки
@check_admin_session
async def handle_cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🚫 Рассылка отменена.")
    await callback.message.answer("Главное меню", reply_markup=admin_main_menu())
    await callback.answer()

@router.callback_query(F.data.startswith("add_to_"))#Обработка кнопки добавить категорию товара
@check_admin_session
async def add_product_category(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()  # Отвечаем как можно раньше
        await state.clear()

        category = callback.data.replace("add_to_", "")
        await state.update_data(category=category, is_adding_product=True)

        await callback.message.edit_text("Введите название товара:")
        await state.set_state(AdminStates.setting_name)

    except Exception as e:
        logger.error(f"Ошибка в add_product_category: {e}")
        await callback.message.edit_text(
            "Произошла ошибка. Попробуйте снова.",
            reply_markup=product_management_kb()
        )

@router.callback_query(F.data.startswith("edit_name_"))#Обработка кнопки редактирования названия товара
@check_admin_session
async def start_edit_name(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()  # Быстрое закрытие "часиков"
        
        product_id = callback.data.replace("edit_name_", "")
        product = await db.get_product(product_id)
        
        if not product:
            await callback.message.answer("❌ Товар не найден.")
            return

        await state.update_data(editing_product_id=product_id)

        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"edit_product_{product_id}")
        ]])

        await callback.message.edit_text(
            f"Текущее название: <b>{product['name']}</b>\n\n"
            "Введите новое название товара:",
            reply_markup=cancel_kb,
            parse_mode="HTML"
        )

        await state.set_state(AdminStates.setting_name)

    except Exception as e:
        logger.error(f"Ошибка в start_edit_name: {e}")
        await callback.message.answer("⚠️ Произошла ошибка. Попробуйте позже.")

@router.callback_query(F.data.startswith("edit_price_"))#Обработка кнопки редактирования цены товара
@check_admin_session
async def start_edit_price(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()  # Закрываем "часики"

        product_id = callback.data.replace("edit_price_", "")
        product = await db.get_product(product_id)
        
        if not product:
            await callback.message.answer("❌ Товар не найден.")
            return

        await state.update_data(editing_product_id=product_id)

        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"edit_product_{product_id}")
        ]])

        await callback.message.edit_text(
            f"Текущая цена: <b>{format_price(product['price'])} ₸</b>\n\n"
            "Введите новую цену товара (только число):",
            reply_markup=cancel_kb,
            parse_mode="HTML"
        )

        await state.set_state(AdminStates.setting_price)

    except Exception as e:
        logger.error(f"Ошибка в start_edit_price: {e}")
        await callback.message.answer("⚠️ Произошла ошибка. Попробуйте позже.")

@router.callback_query(F.data.startswith("edit_description_"))#Обработка кнопки редактирования описания товара
@check_admin_session
async def start_edit_description(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()  # Гасим "часики" сразу

        product_id = callback.data.replace("edit_description_", "")
        product = await db.get_product(product_id)

        if not product:
            await callback.message.answer("❌ Товар не найден.")
            return

        await state.update_data(editing_product_id=product_id)

        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"edit_product_{product_id}")
        ]])

        await callback.message.edit_text(
            f"Текущее описание:\n<blockquote>{product['description']}</blockquote>\n"
            "Введите новое описание товара:",
            reply_markup=cancel_kb,
            parse_mode="HTML"
        )

        await state.set_state(AdminStates.setting_description)

    except Exception as e:
        logger.error(f"Ошибка в start_edit_description: {e}")
        await callback.message.answer("⚠️ Произошла ошибка. Попробуйте позже.")

@router.callback_query(F.data.startswith("edit_photo_"))#Обработка кнопки редактирования фото товара
@check_admin_session
async def start_edit_photo(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()  # Закрываем "часики"

        product_id = callback.data.replace("edit_photo_", "")
        product = await db.get_product(product_id)

        if not product:
            await callback.message.answer("❌ Товар не найден.")
            return

        await state.update_data(editing_product_id=product_id)

        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"edit_product_{product_id}")
        ]])

        await callback.message.edit_text(
            "📸 Отправьте новое фото товара одним сообщением:",
            reply_markup=cancel_kb
        )

        await state.set_state(AdminStates.setting_image)

    except Exception as e:
        logger.error(f"Ошибка в start_edit_photo: {e}")
        await callback.message.answer("⚠️ Произошла ошибка. Попробуйте позже.")

@router.callback_query(F.data.startswith("manage_flavors_"))#Обработка кнопки управления вкусами
@check_admin_session
async def manage_flavors(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()  # Сразу убираем "часики"

        product_id = callback.data.replace("manage_flavors_", "")
        product = await db.get_product(product_id)

        if not product:
            await callback.message.answer("❌ Товар не найден.")
            return

        await state.update_data(editing_product_id=product_id)

        flavors = product.get('flavors', [])
        text, markup = build_flavor_editor(product_id, flavors)
        await callback.message.edit_text(text, reply_markup=markup)

    except Exception as e:
        logger.exception("Ошибка в manage_flavors")
        await callback.answer("Произошла ошибка при управлении вкусами")

@router.callback_query(F.data.startswith("delete_flavor_"))#Обработка кнопки удаления вкуса
@check_admin_session
async def delete_flavor(callback: CallbackQuery):
    try:
        _, product_id, index = callback.data.rsplit("_", 2)
        index = int(index)

        product = await db.get_product(product_id)
        if not product:
            return await callback.answer("Товар не найден")

        flavors = product.get('flavors', [])
        if not (0 <= index < len(flavors)):
            return await callback.answer("Вкус не найден")

        removed_flavor = flavors[index].get('name', '')
        flavors.pop(index)
        await db.update_product(product_id, {'flavors': flavors})

        text, markup = build_flavor_editor(product_id, flavors)

        await callback.message.edit_text(text, reply_markup=markup)
        await callback.answer(f"Вкус {removed_flavor} удалён")

    except Exception as e:
        logger.exception("Ошибка при удалении вкуса")  # Используй loguru
        await callback.answer("Произошла ошибка при удалении вкуса")

@router.callback_query(F.data.startswith("add_flavor_quantity_"))#Обработка кнопки добавления количества вкуса
@check_admin_session
async def start_add_flavor_quantity(callback: CallbackQuery, state: FSMContext):
    try:
        _, product_id, index = callback.data.rsplit("_", 2)
        index = int(index)

        product = await db.get_product(product_id)
        if not product:
            return await callback.answer("Товар не найден")

        flavors = product.get('flavors', [])
        if not (0 <= index < len(flavors)):
            return await callback.answer("Вкус не найден")

        flavor = flavors[index]
        await state.update_data({
            'editing_product_id': product_id,
            'editing_flavor_index': index
        })

        flavor_name = flavor.get('name', 'неизвестно')
        quantity = flavor.get('quantity', 0)

        text = (
            f"Текущее количество для вкуса «{flavor_name}»: {quantity} шт.\n\n"
            "Введите новое количество (только число):"
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data=f"manage_flavors_{product_id}")]])

        await callback.message.edit_text(text, reply_markup=markup)
        await state.set_state(AdminStates.setting_flavor_quantity)
        await callback.answer()

    except Exception:
        logger.exception("Ошибка в start_add_flavor_quantity")
        await callback.answer("Произошла ошибка")

@router.message(AdminStates.adding_flavor)#Обработка ввода названия нового вкуса
@check_admin_session
async def process_add_flavor(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        product_id = data.get('editing_product_id')

        if not product_id:
            await message.answer("Ошибка: товар не найден")
            return await state.clear()

        product = await db.get_product(product_id)
        if not product:
            await message.answer("Товар не найден")
            return await state.clear()

        flavors = product.get('flavors', [])
        new_flavor = message.text.strip()

        if any(flavor.get('name') == new_flavor for flavor in flavors):
            markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton("🔙 Отмена", callback_data=f"manage_flavors_{product_id}")
            ]])
            await message.answer(
                "Такой вкус уже существует!\n"
                "Введите другой вкус или нажмите Отмена для возврата.",
                reply_markup=markup
            )
            return

        flavors.append({'name': new_flavor, 'quantity': 0})
        await db.update_product(product_id, {'flavors': flavors})

        text, markup = build_flavor_editor(product_id, flavors)
        await message.answer(text, reply_markup=markup)
        await state.clear()

    except Exception:
        logger.exception("Ошибка в process_add_flavor")
        await message.answer("Произошла ошибка при добавлении вкуса")
        await state.clear()

@router.message(AdminStates.setting_flavor_quantity)#Обработка ввода количества вкуса
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
            text, markup = build_flavor_editor(product_id, flavors)
            await message.answer(text, reply_markup=markup)
        else:
            await message.answer("Вкус не найден")
            
        await state.clear()
        
    except Exception as e:
        logger.exception("Ошибка в process_flavor_quantity")
        await message.answer("Произошла ошибка при обновлении количества")
        await state.clear()

@router.callback_query(F.data.startswith("add_flavor_"))#Обработка кнопки добавления вкуса
@check_admin_session
async def start_add_flavor(callback: CallbackQuery, state: FSMContext):
    try:
        product_id = callback.data.replace("add_flavor_", "")
        product = await db.get_product(product_id)

        if not product:
            return await callback.answer("Товар не найден")

        await state.update_data(editing_product_id=product_id)

        text = "Введите название нового вкуса:"
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"manage_flavors_{product_id}")
        ]])

        await callback.message.edit_text(text, reply_markup=markup)
        await state.set_state(AdminStates.adding_flavor)
        await callback.answer()

    except Exception:
        logger.exception("Ошибка в start_add_flavor")
        await callback.answer("Произошла ошибка")

@router.callback_query(F.data == "manage_flavors")#Обработка кнопки управления вкусами
@check_admin_session
async def show_products_for_flavors(callback: CallbackQuery):
    try:
        products = await db.get_all_products()

        if not products:
            return await callback.answer("Нет доступных товаров")

        keyboard = [
            [InlineKeyboardButton(
                text=f"{product['name']} ({len(product.get('flavors', []))} вкусов)",
                callback_data=f"manage_flavors_{product['_id']}"
            )] for product in products
        ]

        keyboard.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_product_management")
        ])

        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

        await callback.message.edit_text(
            "Выберите товар для управления вкусами:",
            reply_markup=markup
        )
        await callback.answer()

    except Exception:
        logger.exception("Ошибка в show_products_for_flavors")
        await callback.answer("Произошла ошибка при загрузке списка товаров")

@router.message(F.text == "❓ Помощь")#Обработка кнопки помощи
@check_admin_session
async def show_admin_help(message: Message):
    help_text = """
    <b>🔰 АДМИН-ПАНЕЛЬ: КРАТКОЕ РУКОВОДСТВО</b>

    <b>🔑 ОСНОВНОЕ УПРАВЛЕНИЕ</b>
    • /admin - Вход в панель администратора
    • /logout - Выход из панели

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
    • Цены указываются в ₸
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

@router.message(F.text == "😴 Режим сна")#Обработка кнопки режима сна
@check_admin_session
async def sleep_mode_menu(message: Message):
    try:
        sleep_data = await db.get_sleep_mode()
        if not sleep_data:
            return await message.answer("❌ Ошибка при получении статуса режима сна")

        is_enabled = sleep_data.get("enabled", False)
        end_time = sleep_data.get("end_time")

        lines = [
            "🌙 Режим сна магазина",
            "",
            f"Текущий статус: {'✅ Включен' if is_enabled else '❌ Выключен'}"
        ]
        if is_enabled and end_time:
            lines.append(f"Время работы возобновится: {end_time}")

        lines.append("\nВ режиме сна пользователи не смогут делать заказы.")

        await message.answer(
            "\n".join(lines),
            reply_markup=sleep_mode_kb(is_enabled)
        )

    except Exception:
        logger.exception("Ошибка в sleep_mode_menu")
        await message.answer("❌ Произошла ошибка при получении статуса режима сна")

@router.callback_query(F.data == "toggle_sleep_mode")#Обработка кнопки переключения режима сна
@check_admin_session
async def toggle_sleep_mode(callback: CallbackQuery, state: FSMContext):
    try:
        sleep_data = await db.get_sleep_mode()
        if not sleep_data:
            await callback.message.edit_text("❌ Ошибка при получении статуса режима сна")
            return await callback.answer()

        is_enabled = sleep_data.get("enabled", False)

        if not is_enabled:
            text = (
                "🕒 Введите время, до которого магазин будет закрыт\n"
                "❗❗МАГАЗИН НЕ ВЫХОДИТ ИЗ РЕЖИМА СНА АВТОМАТИЧЕСКИ❗❗\n"
                "Формат: ЧЧ:ММ (например, 10:00)"
            )
            markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_admin_menu")]])
            await callback.message.edit_text(text, reply_markup=markup)
            await state.set_state(AdminStates.setting_sleep_time)

        else:
            await db.set_sleep_mode(False, None)
            await callback.message.edit_text(
                "🌙 Режим сна магазина\n\n"
                "Текущий статус: ❌ Выключен\n\n"
                "В режиме сна пользователи не смогут делать заказы.",
                reply_markup=sleep_mode_kb(False)
            )

        await callback.answer()

    except Exception:
        logger.exception("Ошибка при переключении режима сна")
        await callback.answer("❌ Произошла ошибка при изменении режима сна")

@router.message(AdminStates.setting_sleep_time)#Обработка ввода времени режима сна
@check_admin_session
async def process_sleep_time(message: Message, state: FSMContext):
    try:
        time_text = message.text.strip()

        # Валидация формата ЧЧ:ММ
        try:
            hours, minutes = map(int, time_text.split(":"))
        except Exception:
            return await message.answer(
                "❌ Неверный формат времени. Используйте формат ЧЧ:ММ (например, 10:00)"
            )

        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            return await message.answer(
                "❌ Неверное время. Часы должны быть от 0 до 23, минуты от 0 до 59"
            )

        # Запись режима сна
        await db.set_sleep_mode(True, time_text)
        await message.answer(
            f"🌙 Режим сна включён!\n\n"
            f"Магазин будет закрыт до {time_text}\n"
            f"Текущий статус: ✅ Включен",
            reply_markup=sleep_mode_kb(True)
        )
        await state.clear()

    except Exception:
        logger.exception("Ошибка при установке времени режима сна")
        await message.answer("❌ Произошла ошибка при установке времени")
        await state.clear()

def format_order_notification(order_id: str, user_data: dict, order_data: dict, cart: list, total: float) -> str:
    """Формирует уведомление о заказе для администратора"""
    full_name = user_data.get('full_name', 'Не указано')
    username = user_data.get('username', 'Не указано')

    lines = [
        f"🆕 Новый заказ #{order_id}\n",
        f"👤 От: {full_name} (@{username})",
        f"📱 Телефон: {order_data.get('phone', 'Не указано')}",
        f"📍 Адрес: {order_data.get('address', 'Не указано')}",
        f"🗺 2GIS: {order_data.get('gis_link', 'Не указано')}",
        "",
        "🛍 Товары:"
    ]

    for item in cart:
        name = item.get('name', 'Неизвестный товар')
        quantity = item.get('quantity', 1)
        price = item.get('price', 0)
        subtotal = price * quantity

        item_line = f"- {name}"
        flavor = item.get('flavor')
        if flavor:
            item_line += f" (🌈 {flavor})"
        item_line += f" x{quantity} = {format_price(subtotal)} ₸"
        lines.append(item_line)

    lines.append(f"\n💰 Итого: {format_price(total)} ₸")
    return "\n".join(lines)

@router.callback_query(F.data.startswith("admin_confirm_"))#обработка кнопки потвержждения
@check_admin_session
async def admin_confirm_order(callback: CallbackQuery):
    order_id = callback.data.replace("admin_confirm_", "")

    try:
        order = await db.get_order(order_id)
        if not order:
            return await callback.answer("Заказ не найден")

        if order.get('status') == 'cancelled':
            return await callback.answer("Нельзя подтвердить отмененный заказ", show_alert=True)

        products_to_check = set()

        for item in order['items']:
            try:
                product = await db.get_product(item['product_id'])
                if not product:
                    continue

                flavors = product.get('flavors', [])
                flavor = next((f for f in flavors if f.get('name') == item.get('flavor')), None)
                if not flavor:
                    continue

                flavor['quantity'] -= item['quantity']
                await db.update_product(item['product_id'], {'flavors': flavors})
                products_to_check.add(item['product_id'])
            except Exception as e:
                logger.error(f"Ошибка при обновлении количества вкуса: {e}")
                return await callback.answer("Ошибка при обновлении количества товара", show_alert=True)

        for product_id in products_to_check:
            try:
                product = await db.get_product(product_id)
                if product:
                    flavors = product.get('flavors', [])
                    if all(f.get('quantity', 0) == 0 for f in flavors):
                        await db.delete_product(product_id)
            except Exception as e:
                logger.error(f"Ошибка при удалении товара без остатков: {e}")

        try:
            await db.update_order(order_id, {'status': 'confirmed'})

            user_notification = (
                "✅ Ваш заказ подтверждён и будет отправлен в течение часа!\n\n"
                "❗❗❗ Стоимость доставки: до 1000 (оплачивается курьеру при получении)\n"
                "🔍 Отслеживание доступно в приложении Яндекс по номеру телефона\n"
                "⚠️ ВАЖНО: Встречайте курьера лично - возврат средств не производится\n"
                "Спасибо за ваш заказ! ❤️"
            )

            try:
                await callback.bot.send_message(chat_id=order['user_id'], text=user_notification)
            except Exception as e:
                logger.warning(f"Не удалось уведомить пользователя: {e}")

            await safe_delete_message(callback.message)

            await callback.message.answer(f"✅ Заказ #{order_id} подтвержден, передайте заказ курьеру в течение часа")
            await callback.answer("Заказ подтвержден")
        except Exception as e:
            logger.error(f"Ошибка при подтверждении заказа: {e}")
            return await callback.answer("Ошибка при подтверждении заказа", show_alert=True)

    except Exception as e:
        logger.critical(f"Фатальная ошибка в admin_confirm_order: {e}")
        await callback.answer("Произошла ошибка при подтверждении заказа", show_alert=True)

@router.callback_query(F.data.startswith("delete_order_"))#обработка кнопки удалить заказ
@check_admin_session
async def delete_order(callback: CallbackQuery):
    try:
        order_id = callback.data.replace("delete_order_", "")
        order = await db.get_order(order_id)

        if not order:
            logger.warning(f"Попытка удалить несуществующий заказ: {order_id}")
            return await callback.answer("Заказ не найден")

        success = await return_items_to_inventory(order.get('items', []))
        if not success:
            return await callback.answer("Ошибка при возврате товара на склад", show_alert=True)

        delete_result = await db.delete_order(order_id)
        if not delete_result:
            logger.error(f"Не удалось удалить заказ {order_id}")
            return await callback.answer("Ошибка при удалении заказа")

        try:
            await callback.bot.send_message(
                chat_id=order['user_id'],
                text="❌ Ваш заказ был отменен администратором."
            )
        except Exception as e:
            logger.warning(f"Ошибка при уведомлении пользователя {order['user_id']}: {e}")

        await callback.message.edit_text(
            "✅ Заказ успешно отменен\nВсе товары возвращены на склад",
            reply_markup=order_management_kb()
        )
        await callback.answer("Заказ отменен")

        logger.info(f"Заказ {order_id} успешно отменен и товары возвращены на склад")

    except Exception as e:
        logger.exception(f"Ошибка в delete_order: {e}")
        await callback.answer("Произошла ошибка при отмене заказа")

@router.callback_query(F.data.startswith("admin_cancel_"))#Обработка кнопки отменить
@check_admin_session
async def admin_cancel_order(callback: CallbackQuery, state: FSMContext):
    try:
        order_id = callback.data.replace("admin_cancel_", "")
        order = await db.get_order(order_id)

        if not order:
            return await callback.answer("Заказ не найден")

        if order.get('status') == 'cancelled':
            return await callback.answer("Заказ уже отменен", show_alert=True)

        await state.update_data({
            'order_id': order_id,
            'message_id': callback.message.message_id,
            'chat_id': callback.message.chat.id
        })

        await callback.message.edit_text(
            f"❌ *Отмена заказа #{order_id}*\n\n"
            "Пожалуйста, укажите причину отмены заказа:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"back_to_order_{order_id}")]
            ]),
            parse_mode="Markdown"
        )

        await state.set_state(CancellationStates.waiting_for_reason)
        await callback.answer()

    except Exception:
        logger.exception("Ошибка в admin_cancel_order")
        await callback.answer("Произошла ошибка при отмене заказа", show_alert=True)

@router.callback_query(F.data.startswith("back_to_order_"))#обработка формирования заказа
@check_admin_session
async def back_to_order_from_cancel(callback: CallbackQuery, state: FSMContext):
    try:
        order_id = callback.data.replace("back_to_order_", "")
        order = await db.get_order(order_id)

        if not order:
            return await callback.answer("Заказ не найден")

        user_data = {
            'full_name': order.get('full_name') or order.get('username', 'Не указано'),
            'username': order.get('username', 'Не указано')
        }

        order_text = format_order_notification(
            str(order["_id"]),
            user_data,
            order,
            order.get("items", []),
            order.get("total_amount", 0)
        )

        order_text += f"\n\nСтатус: {ORDER_STATUSES.get(order.get('status', 'pending'), 'Статус неизвестен')}"

        await callback.message.edit_text(
            order_text,
            parse_mode="HTML",
            reply_markup=order_management_kb(str(order["_id"]), order.get('status', 'pending'))
        )

        await state.clear()
        await callback.answer("Отмена отмены заказа")

    except Exception:
        logger.exception("Ошибка в back_to_order_from_cancel")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.message(CancellationStates.waiting_for_reason)#ожидание причины отмены
async def admin_finish_cancel_order(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        order_id = data.get('order_id')
        original_message_id = data.get('message_id')
        chat_id = data.get('chat_id')

        if not order_id:
            await message.answer("Ошибка: не найден ID заказа")
            return await state.clear()

        order = await db.get_order(order_id)
        if not order:
            await message.answer("Ошибка: заказ не найден")
            return await state.clear()

        if order.get('status') == 'cancelled':
            await message.answer("Заказ уже отменен")
            return await state.clear()

        logger.info(f"Отмена заказа #{order_id}")

        success = await return_items_to_inventory(order.get('items', []))
        if not success:
            await message.answer("Ошибка при возврате товара на склад")
            return await state.clear()

        await db.update_order(order_id, {
            'status': 'cancelled',
            'cancellation_reason': message.text
        })

        user_notification = (
            "❌ *Ваш заказ был отменен.*\n\n"
            f"📄 Причина: _{message.text}_\n\n"
        )

        try:
            await message.bot.send_message(
                chat_id=order['user_id'],
                text=user_notification,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Не удалось уведомить пользователя {order['user_id']}: {e}")

        try:
            await safe_delete_message(message.bot, chat_id, original_message_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить оригинальное сообщение: {e}")

        await message.answer(f"❌ Заказ #{order_id} отменен. Клиент уведомлен о причине отмены.")

    except Exception:
        logger.exception("Ошибка в admin_finish_cancel_order")
        await message.answer("Произошла ошибка при отмене заказа")

    finally:
        await state.clear()
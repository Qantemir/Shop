from aiogram import types, Dispatcher
from keyboards.admin_kb import admin_menu
from utils.database import get_all_categories, update_product_quantity

async def admin_panel(message: types.Message):
    """Отправляет администратору меню управления магазином."""
    if message.from_user.id != ADMIN_ID:  # Проверяем, является ли пользователь админом
        await message.answer("У вас нет доступа к админ-панели.")
        return

    await message.answer("Добро пожаловать в админ-панель!", reply_markup=admin_menu)

async def view_database(message: types.Message):
    """Отображает список всех категорий и товаров."""
    if message.from_user.id != ADMIN_ID:
        return

    categories = get_all_categories()
    response = "📂 База данных:\n\n"
    for category, products in categories.items():
        response += f"🔹 {category}\n"
        for product in products:
            response += f"  - {product['name']} ({product['quantity']})\n"
    await message.answer(response)

async def confirm_order(callback_query: types.CallbackQuery):
    """Подтверждает заказ и списывает товар из базы."""
    if callback_query.from_user.id != ADMIN_ID:
        return

    order_id = callback_query.data.split("_")[1]
    success = update_product_quantity(order_id)
    
    if success:
        await callback_query.message.edit_text("✅ Заказ подтвержден!")
    else:
        await callback_query.message.answer("Ошибка при подтверждении заказа.")

def register_handlers(dp: Dispatcher):
    """Регистрирует обработчики команд администратора."""
    dp.register_message_handler(admin_panel, commands=["admin"])
    dp.register_message_handler(view_database, commands=["view_db"])
    dp.register_callback_query_handler(confirm_order, lambda c: c.data.startswith("confirm_"))

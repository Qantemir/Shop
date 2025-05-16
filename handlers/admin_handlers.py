from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from keyboards.admin_kb import admin_menu
from utils.database import get_all_categories, update_product_quantity

ADMIN_ID = 123456789  # Не забудь заменить на своего администратора

admin_router = Router()

@admin_router.message(F.from_user.id == ADMIN_ID, F.text == "/admin")
async def admin_panel(message: Message):
    """Отправляет администратору меню управления магазином."""
    await message.answer("Добро пожаловать в админ-панель!", reply_markup=admin_menu)

@admin_router.message(F.from_user.id == ADMIN_ID, F.text == "/view_db")
async def view_database(message: Message):
    """Отображает список всех категорий и товаров."""
    categories = get_all_categories()
    response = "📂 База данных:\n\n"
    for category, products in categories.items():
        response += f"🔹 {category}\n"
        for product in products:
            response += f"  - {product['name']} ({product['quantity']})\n"
    await message.answer(response)

@admin_router.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("confirm_"))
async def confirm_order(callback: CallbackQuery):
    """Подтверждает заказ и списывает товар из базы."""
    order_id = callback.data.split("_")[1]
    success = update_product_quantity(order_id)

    if success:
        await callback.message.edit_text("✅ Заказ подтвержден!")
    else:
        await callback.message.answer("Ошибка при подтверждении заказа.")

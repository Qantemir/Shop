from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from config import CATEGORIES, ORDER_STATUSES

def admin_main_menu() -> ReplyKeyboardMarkup:
    """Главное меню администратора"""
    keyboard = [
        [
            KeyboardButton(text="📦 Управление товарами"),
            KeyboardButton(text="📊 Заказы")
        ],
        [
            KeyboardButton(text="📢 Рассылка"),
            KeyboardButton(text="😴 Режим сна")
        ],
        [KeyboardButton(text="❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def product_management_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить товар", callback_data="add_product"),
            InlineKeyboardButton(text="❌ Удалить товар", callback_data="delete_product"),
        ],
        [
            InlineKeyboardButton(text="📝 Редактировать", callback_data="edit_products"),
            InlineKeyboardButton(text="📋 Список товаров", callback_data="list_products")
        ]
    ])

def categories_kb(for_adding: bool = True) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=category,
            callback_data=f"add_to_{category}" if for_adding else f"view_{category}"
        )]
        for category in CATEGORIES
    ]
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_product_management")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def order_management_kb(order_id: str, status: str = "pending") -> InlineKeyboardMarkup:
    keyboard = []
    
    if status == "pending":
        keyboard.append([
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_confirm_{order_id}"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"admin_cancel_{order_id}")
        ])
    elif status == "confirmed":
        keyboard.append([
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"admin_cancel_{order_id}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_order_{order_id}")
        ])
    else:
        # For completed or cancelled orders
        keyboard.append([
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_order_{order_id}")
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def confirm_action_kb(action: str, item_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}_{item_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"cancel_{action}")
        ]
    ])

def sleep_mode_kb(is_enabled: bool) -> InlineKeyboardMarkup:
    """Клавиатура управления режимом сна"""
    button_text = "❌ Выключить режим сна" if is_enabled else "✅ Включить режим сна"
    
    keyboard = [
        [InlineKeyboardButton(text=button_text, callback_data="toggle_sleep_mode")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def product_edit_kb(product_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"edit_name_{product_id}")],
        [InlineKeyboardButton(text="💰 Изменить цену", callback_data=f"edit_price_{product_id}")],
        [InlineKeyboardButton(text="📝 Изменить описание", callback_data=f"edit_description_{product_id}")],
        [InlineKeyboardButton(text="🖼 Изменить фото", callback_data=f"edit_photo_{product_id}")],
        [InlineKeyboardButton(text="🌈 Управление вкусами", callback_data=f"manage_flavors_{product_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_product_management")]
    ])

def build_flavor_editor(product_id: str, flavors: list) -> tuple[str, InlineKeyboardMarkup]:
    keyboard = []
    text = "🌈 Управление вкусами\n\n"

    if flavors:
        text += "Текущие вкусы:\n"
        for i, flavor in enumerate(flavors, 1):
            name = flavor.get('name', '')
            qty = flavor.get('quantity', 0)
            text += f"{i}. {name} - {qty} шт.\n"
            keyboard.extend([
                [
                    InlineKeyboardButton(text=f"❌ {name} ({qty} шт.)", callback_data=f"delete_flavor_{product_id}_{i-1}"),
                ],
                [
                    InlineKeyboardButton(text=f"➕ Изменить количество- {name}", callback_data=f"add_flavor_quantity_{product_id}_{i-1}")
                ]
            ])
    else:
        text += "У товара пока нет вкусов\n"

    text += "\nНажмите на вкус, чтобы удалить его, или добавьте новый"
    keyboard.extend([
        [InlineKeyboardButton(text="➕ Добавить вкус", callback_data=f"add_flavor_{product_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"edit_product_{product_id}")]
    ])

    return text, InlineKeyboardMarkup(inline_keyboard=keyboard)

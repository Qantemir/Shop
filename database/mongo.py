import sqlite3

DB_PATH = "data/database.db"

def get_all_categories():
    """Получает список всех категорий и товаров из базы данных."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT category, name, quantity FROM products")
    rows = cursor.fetchall()
    
    categories = {}
    for category, name, quantity in rows:
        if category not in categories:
            categories[category] = []
        categories[category].append({"name": name, "quantity": quantity})

    conn.close()
    return categories

def update_product_quantity(product_id):
    """Уменьшает количество товара после подтверждения заказа."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("UPDATE products SET quantity = quantity - 1 WHERE id = ?", (product_id,))
    conn.commit()
    success = cursor.rowcount > 0  # Проверяем, изменилось ли что-то
    conn.close()
    return success

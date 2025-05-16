import sqlite3

DB_PATH = "data/database.db"

def get_all_categories():
    """Получает список всех категорий и товаров из базы данных."""
    categories = {}
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT category, name, quantity FROM products")
        rows = cursor.fetchall()
        for category, name, quantity in rows:
            categories.setdefault(category, []).append({
                "name": name,
                "quantity": quantity
            })
    return categories

def update_product_quantity(product_id):
    """Уменьшает количество товара после подтверждения заказа."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET quantity = quantity - 1 WHERE id = ?", (product_id,))
        conn.commit()
        return cursor.rowcount > 0

from datetime import datetime, timedelta
import asyncio
from aiogram import Router
from database import db

async def cleanup_old_orders():
    """
    Удаляет заказы, которые были выполнены или отменены более 24 часов назад
    """
    try:
        # Получаем текущее время
        now = datetime.now()
        # Вычисляем время 24 часа назад
        day_ago = now - timedelta(days=1)
        
        # Находим и удаляем старые заказы
        result = await db.orders.delete_many({
            "status": {"$in": ["confirmed", "cancelled"]},
            "created_at": {"$lt": day_ago}
        })
        
        print(f"[DEBUG] Cleaned up {result.deleted_count} old orders")
        
    except Exception as e:
        print(f"[ERROR] Error in cleanup_old_orders: {str(e)}")

async def start_cleanup_scheduler():
    """
    Запускает периодическую очистку старых заказов
    """
    while True:
        try:
            await cleanup_old_orders()
            # Ждем 1 час перед следующей проверкой
            await asyncio.sleep(3600)
        except Exception as e:
            print(f"[ERROR] Error in cleanup scheduler: {str(e)}")
            # В случае ошибки ждем 5 минут перед повторной попыткой
            await asyncio.sleep(300) 
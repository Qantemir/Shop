from datetime import datetime, timedelta
from typing import Dict, Set
import hashlib
import os
from dotenv import load_dotenv
from functools import wraps
from aiogram.types import CallbackQuery, Message
import logging
from database import db

load_dotenv()

security_log = logging.getLogger(__name__)

def check_admin_session(func):
    """Decorator to check if user has valid admin session"""
    @wraps(func)
    async def wrapper(event: CallbackQuery | Message, *args, **kwargs):
        from_user = getattr(event, "from_user", None)

        if from_user is None:
            logging.warning("from_user is None. Возможно, событие не поддерживает пользователя.")
            if isinstance(event, CallbackQuery):
                await event.answer("❌ Невозможно определить пользователя", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("❌ Невозможно определить пользователя")
            return

        user_id = from_user.id

        if not security_manager.is_admin_session_valid(user_id):
            if isinstance(event, CallbackQuery):
                await event.answer("Требуется авторизация администратора", show_alert=True)
            else:
                await event.answer("Требуется авторизация администратора")
            return

        return await func(event, *args, **kwargs)
    return wrapper

class SecurityManager:
    def __init__(self):
        self._admin_sessions: Set[int] = set()
        self._failed_attempts: Dict[int, int] = {}
        self._blocked_until: Dict[int, datetime] = {}
        self._admin_password = os.getenv("ADMIN_PASSWORD", "your_default_password_here")
        self.max_attempts = 3
        self.block_time = timedelta(minutes=30)

    def verify_password(self, password: str) -> bool:
        """Проверяет пароль администратора"""
        hashed_input = hashlib.sha256(password.encode()).hexdigest()
        stored_hash = hashlib.sha256(self._admin_password.encode()).hexdigest()
        return hashed_input == stored_hash

    def check_failed_attempts(self, user_id: int) -> bool:
        """Проверяет, не превышено ли количество попыток входа"""
        if user_id in self._blocked_until:
            if datetime.now() < self._blocked_until[user_id]:
                return False
            else:
                del self._blocked_until[user_id]
                self._failed_attempts[user_id] = 0
        return True

    def add_failed_attempt(self, user_id: int):
        """Добавляет неудачную попытку входа"""
        self._failed_attempts[user_id] = self._failed_attempts.get(user_id, 0) + 1
        if self._failed_attempts[user_id] >= self.max_attempts:
            self._blocked_until[user_id] = datetime.now() + self.block_time

    def reset_attempts(self, user_id: int):
        """Сбрасывает счетчик неудачных попыток"""
        if user_id in self._failed_attempts:
            del self._failed_attempts[user_id]
        if user_id in self._blocked_until:
            del self._blocked_until[user_id]

    def create_admin_session(self, user_id: int):
        """Создает сессию администратора"""
        self._admin_sessions.add(user_id)

    def remove_admin_session(self, user_id: int):
        """Удаляет сессию администратора"""
        self._admin_sessions.discard(user_id)

    def is_admin_session_valid(self, user_id: int) -> bool:
        """Проверяет, активна ли сессия администратора"""
        return user_id in self._admin_sessions

    def get_block_time_remaining(self, user_id: int) -> timedelta:
        """Возвращает оставшееся время блокировки"""
        if user_id in self._blocked_until:
            return self._blocked_until[user_id] - datetime.now()
        return timedelta(0)

    def try_admin_login(self, user_id: int, password: str):
        """
        Пытается выполнить вход администратора. Возвращает dict с результатом:
        {
            'success': bool,  # Вход выполнен
            'blocked': bool,  # Пользователь заблокирован
            'block_time': int,  # Минут до разблокировки
            'attempts_left': int  # Осталось попыток
        }
        """
        # Проверка блокировки
        if user_id in self._blocked_until:
            remaining = self._blocked_until[user_id] - datetime.now()
            if remaining.total_seconds() > 0:
                return {
                    'success': False,
                    'blocked': True,
                    'block_time': max(1, int(remaining.total_seconds() // 60)),
                    'attempts_left': 0
                }
            else:
                del self._blocked_until[user_id]
                self._failed_attempts[user_id] = 0
        
        # Проверка пароля
        if self.verify_password(password):
            self.create_admin_session(user_id)
            self.reset_attempts(user_id)
            return {
                'success': True,
                'blocked': False,
                'block_time': 0,
                'attempts_left': self.max_attempts
            }
        else:
            self.add_failed_attempt(user_id)
            attempts_left = self.max_attempts - self._failed_attempts.get(user_id, 0)
            if attempts_left <= 0:
                block_time = self.block_time.seconds // 60
                return {
                    'success': False,
                    'blocked': True,
                    'block_time': block_time,
                    'attempts_left': 0
                }
            else:
                return {
                    'success': False,
                    'blocked': False,
                    'block_time': 0,
                    'attempts_left': attempts_left
                }

# Создаем глобальный экземпляр менеджера безопасности
security_manager = SecurityManager()

async def return_items_to_inventory(order_items):
    """
    Общая функция для возврата товаров на склад
    Returns True if successful, False if any item failed
    """
    try:
        for item in order_items:
            if 'flavor' in item:
                security_log.info(f"Returning item to inventory: product_id={item['product_id']}, flavor={item['flavor']}, quantity={item['quantity']}")
                
                success = await db.update_product_flavor_quantity(
                    item['product_id'],
                    item['flavor'],
                    item['quantity']  # Return the full quantity
                )
                
                if not success:
                    security_log.error(f"Failed to restore flavor quantity: product_id={item['product_id']}, flavor={item['flavor']}")
                    return False
                else:
                    security_log.info(f"Successfully restored flavor quantity for {item['flavor']}")
        
        return True
    except Exception as e:
        security_log.error(f"Error returning items to inventory: {str(e)}")
        return False 
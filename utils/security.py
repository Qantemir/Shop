from datetime import datetime, timedelta
from typing import Dict, Set
import hashlib
import os
from dotenv import load_dotenv

load_dotenv()

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

# Создаем глобальный экземпляр менеджера безопасности
security_manager = SecurityManager() 
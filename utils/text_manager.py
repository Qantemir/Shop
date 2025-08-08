import hashlib
import logging
from typing import Dict, Optional
from database.mongodb import db

logger = logging.getLogger(__name__)

# Кэш для текстов
TEXT_CACHE: Dict[str, Dict[str, str]] = {}

# Список ключей текстов, которые можно редактировать
EDITABLE_TEXT_KEYS = [
    "WELCOME_MESSAGE",
    "CHECKOUT_PAYMENT_REQUEST", 
    "HELP_HOW_TO_ORDER",
    "HELP_PAYMENT",
    "HELP_DELIVERY",
    "HELP_CONTACT"
]

async def load_texts() -> bool:
    """Загружает все тексты из MongoDB в кэш"""
    try:
        await db.ensure_connected()
        
        # Получаем все тексты из коллекции texts
        cursor = db.db.texts.find()
        texts = await cursor.to_list(length=None)
        
        # Очищаем кэш
        TEXT_CACHE.clear()
        
        # Загружаем тексты в кэш
        for text_doc in texts:
            key = text_doc.get('key')
            value = text_doc.get('value', '')
            hash_value = text_doc.get('hash', '')
            
            if key:
                TEXT_CACHE[key] = {
                    'value': value,
                    'hash': hash_value
                }
        
        logger.info(f"✅ Загружено {len(TEXT_CACHE)} текстов в кэш")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке текстов: {e}")
        return False

def get_text(key: str, default: str = "") -> str:
    """Получает текст по ключу из кэша"""
    if key in TEXT_CACHE:
        return TEXT_CACHE[key]['value']
    return default

def get_text_sync(key: str, default: str = "") -> str:
    """Синхронная версия get_text для использования в обычных функциях"""
    if key in TEXT_CACHE:
        return TEXT_CACHE[key]['value']
    return default

async def update_text(key: str, new_value: str) -> bool:
    """Обновляет текст в MongoDB и кэше"""
    try:
        await db.ensure_connected()
        
        # Генерируем новый хеш
        new_hash = hashlib.sha256(new_value.encode('utf-8')).hexdigest()
        
        # Обновляем в MongoDB
        result = await db.db.texts.update_one(
            {'key': key},
            {
                '$set': {
                    'value': new_value,
                    'hash': new_hash
                }
            },
            upsert=True
        )
        
        # Обновляем кэш
        TEXT_CACHE[key] = {
            'value': new_value,
            'hash': new_hash
        }
        
        logger.info(f"✅ Текст '{key}' обновлен")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении текста '{key}': {e}")
        return False

def get_all_texts() -> Dict[str, Dict[str, str]]:
    """Получает все тексты из кэша"""
    return TEXT_CACHE.copy()

def is_cache_empty() -> bool:
    """Проверяет, пуст ли кэш текстов"""
    return len(TEXT_CACHE) == 0

def is_cache_loaded() -> bool:
    """Проверяет, загружен ли кэш текстов"""
    return len(TEXT_CACHE) > 0

def get_text_info(key: str) -> Optional[Dict[str, str]]:
    """Получает информацию о тексте (значение и хеш)"""
    return TEXT_CACHE.get(key)

async def initialize_texts() -> bool:
    """Инициализирует тексты в MongoDB из texts.py если коллекция пуста"""
    try:
        await db.ensure_connected()
        
        # Проверяем, есть ли уже тексты в базе
        count = await db.db.texts.count_documents({})
        if count > 0:
            logger.info("Тексты уже инициализированы в базе")
            return True
        
        # Импортируем тексты из texts.py
        from texts import (
            WELCOME_MESSAGE,
            CHECKOUT_PAYMENT_REQUEST,
            HELP_HOW_TO_ORDER,
            HELP_PAYMENT,
            HELP_DELIVERY,
            HELP_CONTACT
        )
        
        # Создаем документы для каждого текста
        texts_to_insert = [
            ('WELCOME_MESSAGE', WELCOME_MESSAGE),
            ('CHECKOUT_PAYMENT_REQUEST', CHECKOUT_PAYMENT_REQUEST),
            ('HELP_HOW_TO_ORDER', HELP_HOW_TO_ORDER),
            ('HELP_PAYMENT', HELP_PAYMENT),
            ('HELP_DELIVERY', HELP_DELIVERY),
            ('HELP_CONTACT', HELP_CONTACT)
        ]
        
        # Вставляем тексты в базу
        for key, value in texts_to_insert:
            hash_value = hashlib.sha256(value.encode('utf-8')).hexdigest()
            await db.db.texts.insert_one({
                'key': key,
                'value': value,
                'hash': hash_value
            })
        
        logger.info(f"✅ Инициализировано {len(texts_to_insert)} текстов в базе")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации текстов: {e}")
        return False 
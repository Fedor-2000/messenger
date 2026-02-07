# Caching Configuration
# File: caching/cache_config.py

import asyncio
import json
import logging
import os
from typing import Any, Optional

import aioredis
import asyncpg
from aioredis import Redis

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
class CacheConfig:
    REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379')
    MEMCACHED_URL = os.getenv('MEMCACHED_URL', 'memcached:11211')
    CDN_BASE_URL = os.getenv('CDN_BASE_URL', 'https://cdn.messenger.example.com')

config = CacheConfig()

class MultiLevelCache:
    """
    Реализация многоуровневого кэширования:
    - L1: In-memory cache (Python dict)
    - L2: Redis cache
    - L3: Memcached (для больших объектов)
    - CDN: для статических файлов и медиа
    """
    
    def __init__(self):
        self.l1_cache = {}  # In-memory cache
        self.l1_max_size = 1000  # Максимальный размер L1 кэша
        self.redis_client = None
        self.memcached_client = None
        self.cdn_base_url = config.CDN_BASE_URL
        
    async def initialize(self):
        """Инициализация внешних кэшей"""
        # Инициализация Redis
        try:
            self.redis_client = aioredis.from_url(config.REDIS_URL, decode_responses=True)
            await self.redis_client.ping()
            logger.info("Redis cache initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
        
        # Инициализация Memcached
        try:
            # В реальном приложении использовалась бы библиотека pymemcache
            # Для упрощения в этом примере мы не будем подключаться к Memcached
            logger.info("Memcached interface initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Memcached: {e}")
    
    def _get_l1_key(self, key: str) -> str:
        """Получение ключа для L1 кэша"""
        return f"L1:{key}"
    
    def _get_l2_key(self, key: str) -> str:
        """Получение ключа для L2 кэша (Redis)"""
        return f"L2:{key}"
    
    def _get_l3_key(self, key: str) -> str:
        """Получение ключа для L3 кэша (Memcached)"""
        return f"L3:{key}"
    
    async def get(self, key: str, use_l1: bool = True, use_l2: bool = True, use_l3: bool = True) -> Optional[Any]:
        """
        Получение значения из кэша с проверкой по уровням
        """
        # Проверяем L1 кэш
        if use_l1 and self._get_l1_key(key) in self.l1_cache:
            logger.debug(f"Cache hit L1 for key: {key}")
            return self.l1_cache[self._get_l1_key(key)]
        
        # Проверяем L2 кэш (Redis)
        if use_l2 and self.redis_client:
            try:
                value = await self.redis_client.get(self._get_l2_key(key))
                if value is not None:
                    logger.debug(f"Cache hit L2 for key: {key}")
                    # Сохраняем в L1 для быстрого доступа
                    if use_l1:
                        self._put_l1(self._get_l1_key(key), value)
                    return json.loads(value) if isinstance(value, str) else value
            except Exception as e:
                logger.error(f"Error getting from Redis cache: {e}")
        
        # Проверяем L3 кэш (Memcached)
        if use_l3:
            try:
                # В реальном приложении здесь был бы вызов memcached
                # Для упрощения возвращаем None
                # Здесь должна быть реализация для получения из Memcached
                # result = await memcached_client.get(key)
                # if result is not None:
                #     return result
                # В реальной системе здесь будет вызов memcached
                result = None  # Заглушка для реального вызова memcached
            except Exception as e:
                logger.error(f"Error getting from Memcached: {e}")
        
        logger.debug(f"Cache miss for key: {key}")
        return None
    
    async def set(self, key: str, value: Any, ttl: int = 3600, 
                  to_l1: bool = True, to_l2: bool = True, to_l3: bool = False) -> bool:
        """
        Установка значения в кэш на указанные уровни
        """
        success = True
        
        # Устанавливаем в L1
        if to_l1:
            self._put_l1(self._get_l1_key(key), value)
        
        # Устанавливаем в L2 (Redis)
        if to_l2 and self.redis_client:
            try:
                await self.redis_client.setex(self._get_l2_key(key), ttl, json.dumps(value))
            except Exception as e:
                logger.error(f"Error setting to Redis cache: {e}")
                success = False
        
        # Устанавливаем в L3 (Memcached)
        if to_l3:
            try:
                # В реальном приложении здесь был бы вызов memcached
                # Для упрощения просто логируем
                logger.debug(f"Would set to Memcached: {key}")
            except Exception as e:
                logger.error(f"Error setting to Memcached: {e}")
                success = False
        
        return success
    
    def _put_l1(self, key: str, value: Any):
        """Установка значения в L1 кэш с контролем размера"""
        # Если кэш переполнен, удаляем случайный элемент
        if len(self.l1_cache) >= self.l1_max_size:
            # Удаляем случайный ключ
            import random
            random_key = random.choice(list(self.l1_cache.keys()))
            del self.l1_cache[random_key]
        
        self.l1_cache[key] = value
    
    async def delete(self, key: str, from_l1: bool = True, from_l2: bool = True, from_l3: bool = True) -> bool:
        """Удаление значения из кэша"""
        success = True
        
        # Удаляем из L1
        if from_l1 and self._get_l1_key(key) in self.l1_cache:
            del self.l1_cache[self._get_l1_key(key)]
        
        # Удаляем из L2 (Redis)
        if from_l2 and self.redis_client:
            try:
                await self.redis_client.delete(self._get_l2_key(key))
            except Exception as e:
                logger.error(f"Error deleting from Redis cache: {e}")
                success = False
        
        # Удаляем из L3 (Memcached)
        if from_l3:
            try:
                # В реальном приложении здесь был бы вызов memcached
                logger.debug(f"Would delete from Memcached: {key}")
            except Exception as e:
                logger.error(f"Error deleting from Memcached: {e}")
                success = False
        
        return success
    
    async def invalidate_pattern(self, pattern: str):
        """Инвалидация по паттерну"""
        # Инвалидация в Redis
        if self.redis_client:
            try:
                keys = await self.redis_client.keys(pattern)
                if keys:
                    await self.redis_client.delete(*keys)
                    logger.info(f"Invalidated {len(keys)} keys matching pattern: {pattern}")
            except Exception as e:
                logger.error(f"Error invalidating Redis keys: {e}")
    
    def get_cdn_url(self, resource_path: str) -> str:
        """Получение URL ресурса через CDN"""
        return f"{self.cdn_base_url}/{resource_path}"
    
    async def warm_up_cache(self, db_pool: asyncpg.Pool):
        """Разогрев кэша часто используемыми данными"""
        logger.info("Starting cache warm-up...")
        
        try:
            # Кэшируем информацию о пользователях
            async with db_pool.acquire() as conn:
                users = await conn.fetch("SELECT id, username, avatar FROM users LIMIT 100")
                
                for user in users:
                    user_data = {
                        'id': user['id'],
                        'username': user['username'],
                        'avatar': user['avatar']
                    }
                    await self.set(f"user:{user['id']}", user_data, ttl=7200)  # 2 часа
            
            # Кэшируем популярные чаты
            async with db_pool.acquire() as conn:
                popular_chats = await conn.fetch(
                    """
                    SELECT id, type, name, creator_id, participants, last_activity
                    FROM chats 
                    ORDER BY last_activity DESC 
                    LIMIT 50
                    """
                )
                
                for chat in popular_chats:
                    chat_data = {
                        'id': chat['id'],
                        'type': chat['type'],
                        'name': chat['name'],
                        'creator_id': chat['creator_id'],
                        'participants': chat['participants'],
                        'last_activity': chat['last_activity'].isoformat() if chat['last_activity'] else None
                    }
                    await self.set(f"chat:{chat['id']}", chat_data, ttl=3600)  # 1 час
            
            # Кэшируем последние сообщения в популярных чатах
            for chat in popular_chats:
                async with db_pool.acquire() as conn:
                    recent_messages = await conn.fetch(
                        """
                        SELECT m.sender_id, u.username, m.content, m.timestamp
                        FROM messages m
                        JOIN users u ON m.sender_id = u.id
                        WHERE m.chat_id = $1
                        ORDER BY m.timestamp DESC
                        LIMIT 20
                        """,
                        chat['id']
                    )
                    
                    messages = []
                    for msg in recent_messages:
                        messages.append({
                            'sender_id': msg['sender_id'],
                            'username': msg['username'],
                            'content': msg['content'],
                            'timestamp': msg['timestamp'].isoformat()
                        })
                    
                    await self.set(f"chat:{chat['id']}:recent_messages", messages, ttl=600)  # 10 минут
            
            logger.info("Cache warm-up completed")
        except Exception as e:
            logger.error(f"Error during cache warm-up: {e}")

# Глобальный экземпляр кэша
cache = MultiLevelCache()

# Функции для удобного доступа к кэшу

async def get_user_from_cache(user_id: int):
    """Получение пользователя из кэша"""
    return await cache.get(f"user:{user_id}")

async def set_user_in_cache(user_id: int, user_data: dict, ttl: int = 7200):
    """Сохранение пользователя в кэш"""
    return await cache.set(f"user:{user_id}", user_data, ttl)

async def get_chat_from_cache(chat_id: str):
    """Получение чата из кэша"""
    return await cache.get(f"chat:{chat_id}")

async def set_chat_in_cache(chat_id: str, chat_data: dict, ttl: int = 3600):
    """Сохранение чата в кэш"""
    return await cache.set(f"chat:{chat_id}", chat_data, ttl)

async def get_chat_recent_messages(chat_id: str):
    """Получение последних сообщений чата из кэша"""
    return await cache.get(f"chat:{chat_id}:recent_messages")

async def set_chat_recent_messages(chat_id: str, messages: list, ttl: int = 600):
    """Сохранение последних сообщений чата в кэш"""
    return await cache.set(f"chat:{chat_id}:recent_messages", messages, ttl)

async def invalidate_user_cache(user_id: int):
    """Инвалидация кэша пользователя"""
    return await cache.delete(f"user:{user_id}")

async def invalidate_chat_cache(chat_id: str):
    """Инвалидация кэша чата"""
    return await cache.delete(f"chat:{chat_id}")

async def invalidate_chat_messages_cache(chat_id: str):
    """Инвалидация кэша сообщений чата"""
    return await cache.delete(f"chat:{chat_id}:recent_messages")

# CDN функции

def get_avatar_cdn_url(avatar_filename: str) -> str:
    """Получение URL аватара через CDN"""
    return cache.get_cdn_url(f"avatars/{avatar_filename}")

def get_file_cdn_url(file_stored_name: str) -> str:
    """Получение URL файла через CDN"""
    return cache.get_cdn_url(f"files/{file_stored_name}")

def get_image_cdn_url(image_filename: str, width: int = None, height: int = None) -> str:
    """Получение URL изображения через CDN с возможностью изменения размера"""
    if width and height:
        return cache.get_cdn_url(f"images/{image_filename}?width={width}&height={height}")
    elif width:
        return cache.get_cdn_url(f"images/{image_filename}?width={width}")
    elif height:
        return cache.get_cdn_url(f"images/{image_filename}?height={height}")
    else:
        return cache.get_cdn_url(f"images/{image_filename}")
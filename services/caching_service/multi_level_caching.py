# Multi-Level Caching System
# File: services/caching_service/multi_level_caching.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from enum import Enum
import uuid
import hashlib
import pickle
from functools import wraps

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel
import aiocache
from aiocache import Cache, caches
from aiocache.serializers import PickleSerializer, StringSerializer
import aiomcache

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class CacheLevel(Enum):
    L1_MEMORY = "l1_memory"      # In-memory cache (fastest)
    L2_REDIS = "l2_redis"        # Redis cache (fast)
    L3_MEMCACHED = "l3_memcached" # Memcached (for large objects)
    L4_DATABASE = "l4_database"   # Database cache (persistent)

class CacheStrategy(Enum):
    LRU = "lru"           # Least Recently Used
    LFU = "lfu"           # Least Frequently Used
    TTL = "ttl"           # Time To Live
    SLIDING_WINDOW = "sliding_window"
    WRITE_THROUGH = "write_through"
    WRITE_BACK = "write_back"
    READ_THROUGH = "read_through"

class CacheOperation(Enum):
    GET = "get"
    SET = "set"
    DELETE = "delete"
    INVALIDATE = "invalidate"
    STATS = "stats"

class CacheConfig(BaseModel):
    level: CacheLevel
    ttl: int = 300  # 5 minutes default
    max_size: Optional[int] = None
    strategy: CacheStrategy = CacheStrategy.TTL
    namespace: str = "messenger"
    serializer: str = "pickle"  # 'pickle', 'json', 'string'

class CacheMetrics(BaseModel):
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    evictions: int = 0
    total_size_bytes: int = 0
    timestamp: datetime = None

class MultiLevelCacheService:
    def __init__(self):
        self.levels = {}
        self.metrics = {}
        self.cache_configs = {}
        self.initialized = False
        
        # Настройки кэширования по умолчанию
        self.default_configs = {
            CacheLevel.L1_MEMORY: CacheConfig(
                level=CacheLevel.L1_MEMORY,
                ttl=60,  # 1 minute
                max_size=1000,
                strategy=CacheStrategy.LRU,
                namespace="l1_cache"
            ),
            CacheLevel.L2_REDIS: CacheConfig(
                level=CacheLevel.L2_REDIS,
                ttl=300,  # 5 minutes
                strategy=CacheStrategy.TTL,
                namespace="l2_cache"
            ),
            CacheLevel.L3_MEMCACHED: CacheConfig(
                level=CacheLevel.L3_MEMCACHED,
                ttl=600,  # 10 minutes
                strategy=CacheStrategy.TTL,
                namespace="l3_cache"
            ),
            CacheLevel.L4_DATABASE: CacheConfig(
                level=CacheLevel.L4_DATABASE,
                ttl=3600,  # 1 hour
                strategy=CacheStrategy.TTL,
                namespace="l4_cache"
            )
        }

    async def initialize(self):
        """Инициализация многоуровневого кэширования"""
        if self.initialized:
            return

        # Инициализация L1 (in-memory) кэша
        self.levels[CacheLevel.L1_MEMORY] = Cache(
            Cache.MEMORY,
            ttl=self.default_configs[CacheLevel.L1_MEMORY].ttl,
            limit=self.default_configs[CacheLevel.L1_MEMORY].max_size
        )

        # Инициализация L2 (Redis) кэша
        self.levels[CacheLevel.L2_REDIS] = Cache(
            Cache.REDIS,
            endpoint="redis",
            port=6379,
            ttl=self.default_configs[CacheLevel.L2_REDIS].ttl
        )

        # Инициализация L3 (Memcached) кэша
        # self.levels[CacheLevel.L3_MEMCACHED] = Cache(
        #     Cache.MEMCACHED,
        #     endpoint="memcached",
        #     port=11211,
        #     ttl=self.default_configs[CacheLevel.L3_MEMCACHED].ttl
        # )

        # Инициализация метрик
        for level in CacheLevel:
            self.metrics[level] = CacheMetrics(timestamp=datetime.utcnow())

        self.initialized = True
        logger.info("Multi-level caching system initialized")

    def _generate_cache_key(self, namespace: str, key: str) -> str:
        """Генерация ключа кэша с пространством имен"""
        return f"{namespace}:{key}"

    def _get_serialized_value(self, value: Any, serializer: str) -> bytes:
        """Сериализация значения"""
        if serializer == 'json':
            return json.dumps(value).encode()
        elif serializer == 'pickle':
            return pickle.dumps(value)
        elif serializer == 'string':
            return str(value).encode()
        else:
            return str(value).encode()

    def _deserialize_value(self, value: bytes, serializer: str) -> Any:
        """Десериализация значения"""
        if serializer == 'json':
            return json.loads(value.decode())
        elif serializer == 'pickle':
            return pickle.loads(value)
        elif serializer == 'string':
            return value.decode()
        else:
            return value.decode()

    async def get(self, key: str, default: Any = None, 
                 cache_levels: Optional[List[CacheLevel]] = None) -> Optional[Any]:
        """Получение значения из кэша"""
        if not self.initialized:
            await self.initialize()

        cache_levels = cache_levels or [CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS, CacheLevel.L4_DATABASE]

        # Проверяем каждый уровень кэша
        for level in cache_levels:
            cache = self.levels.get(level)
            if not cache:
                continue

            try:
                cache_key = self._generate_cache_key(self.default_configs[level].namespace, key)
                value = await cache.get(cache_key)
                
                if value is not None:
                    # Обновляем метрики
                    self.metrics[level].hits += 1
                    logger.debug(f"Cache hit at level {level.value} for key {key}")
                    return value
                else:
                    self.metrics[level].misses += 1
            except Exception as e:
                logger.error(f"Error getting from {level.value} cache: {e}")
                self.metrics[level].misses += 1

        logger.debug(f"All cache levels missed for key {key}")
        return default

    async def set(self, key: str, value: Any, ttl: Optional[int] = None,
                 cache_levels: Optional[List[CacheLevel]] = None,
                 strategy: Optional[CacheStrategy] = None):
        """Установка значения в кэш"""
        if not self.initialized:
            await self.initialize()

        cache_levels = cache_levels or [CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS]

        for level in cache_levels:
            cache = self.levels.get(level)
            if not cache:
                continue

            try:
                cache_key = self._generate_cache_key(self.default_configs[level].namespace, key)
                actual_ttl = ttl or self.default_configs[level].ttl
                
                await cache.set(cache_key, value, ttl=actual_ttl)
                self.metrics[level].sets += 1
                
                logger.debug(f"Set value in {level.value} cache for key {key}")
            except Exception as e:
                logger.error(f"Error setting to {level.value} cache: {e}")

    async def delete(self, key: str, cache_levels: Optional[List[CacheLevel]] = None):
        """Удаление значения из кэша"""
        if not self.initialized:
            await self.initialize()

        cache_levels = cache_levels or [CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS]

        for level in cache_levels:
            cache = self.levels.get(level)
            if not cache:
                continue

            try:
                cache_key = self._generate_cache_key(self.default_configs[level].namespace, key)
                await cache.delete(cache_key)
                self.metrics[level].deletes += 1
                
                logger.debug(f"Deleted from {level.value} cache for key {key}")
            except Exception as e:
                logger.error(f"Error deleting from {level.value} cache: {e}")

    async def invalidate_pattern(self, pattern: str, cache_levels: Optional[List[CacheLevel]] = None):
        """Инвалидация по паттерну"""
        if not self.initialized:
            await self.initialize()

        cache_levels = cache_levels or [CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS]

        for level in cache_levels:
            if level == CacheLevel.L2_REDIS:
                # Для Redis используем паттерн
                try:
                    full_pattern = self._generate_cache_key(self.default_configs[level].namespace, pattern)
                    keys = await redis_client.keys(full_pattern)
                    if keys:
                        await redis_client.delete(*keys)
                        self.metrics[level].deletes += len(keys)
                        logger.debug(f"Invalidated {len(keys)} keys in {level.value} cache with pattern {pattern}")
                except Exception as e:
                    logger.error(f"Error invalidating pattern in {level.value} cache: {e}")
            elif level == CacheLevel.L1_MEMORY:
                # Для in-memory кэша инвалидация по паттерну не поддерживается напрямую
                # Вместо этого можно использовать тегирование
                logger.debug(f"Pattern invalidation not supported for {level.value} cache")

    async def get_multi(self, keys: List[str], cache_levels: Optional[List[CacheLevel]] = None) -> Dict[str, Any]:
        """Получение нескольких значений из кэша"""
        if not self.initialized:
            await self.initialize()

        results = {}
        for key in keys:
            value = await self.get(key, cache_levels=cache_levels)
            results[key] = value

        return results

    async def set_multi(self, data: Dict[str, Any], ttl: Optional[int] = None,
                       cache_levels: Optional[List[CacheLevel]] = None):
        """Установка нескольких значений в кэш"""
        if not self.initialized:
            await self.initialize()

        for key, value in data.items():
            await self.set(key, value, ttl=ttl, cache_levels=cache_levels)

    async def clear_level(self, level: CacheLevel):
        """Очистка уровня кэша"""
        if not self.initialized:
            await self.initialize()

        cache = self.levels.get(level)
        if not cache:
            return

        try:
            if level == CacheLevel.L2_REDIS:
                # Для Redis очищаем все ключи с префиксом
                namespace = self.default_configs[level].namespace
                keys = await redis_client.keys(f"{namespace}:*")
                if keys:
                    await redis_client.delete(*keys)
            elif level == CacheLevel.L1_MEMORY:
                # Для in-memory кэша используем метод очистки
                await cache.clear()
            
            logger.info(f"Cleared {level.value} cache")
        except Exception as e:
            logger.error(f"Error clearing {level.value} cache: {e}")

    async def get_cache_stats(self) -> Dict[CacheLevel, CacheMetrics]:
        """Получение статистики по кэшу"""
        stats = {}
        
        for level in CacheLevel:
            metrics = self.metrics[level]
            if metrics.hits + metrics.misses > 0:
                hit_rate = metrics.hits / (metrics.hits + metrics.misses)
            else:
                hit_rate = 0.0
            
            stats[level] = {
                'hits': metrics.hits,
                'misses': metrics.misses,
                'sets': metrics.sets,
                'deletes': metrics.deletes,
                'hit_rate': hit_rate,
                'timestamp': metrics.timestamp.isoformat()
            }
        
        return stats

    def cache_with_fallback(self, ttl: int = 300, 
                           cache_levels: Optional[List[CacheLevel]] = None,
                           fallback_func: Optional[Callable] = None):
        """Декоратор для кэширования с fallback"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Генерируем ключ кэша на основе аргументов
                cache_key = f"{func.__name__}:{hash(str(args) + str(kwargs))}"
                
                # Пытаемся получить из кэша
                cached_result = await self.get(cache_key, cache_levels=cache_levels)
                if cached_result is not None:
                    logger.debug(f"Cache hit for {cache_key}")
                    return cached_result
                
                # Выполняем функцию
                try:
                    result = await func(*args, **kwargs)
                    
                    # Сохраняем в кэш
                    await self.set(cache_key, result, ttl=ttl, cache_levels=cache_levels)
                    
                    logger.debug(f"Cache miss, cached result for {cache_key}")
                    return result
                except Exception as e:
                    logger.error(f"Error in {func.__name__}: {e}")
                    
                    # Если есть fallback функция, используем её
                    if fallback_func:
                        fallback_result = await fallback_func(*args, **kwargs)
                        return fallback_result
                    else:
                        raise
            
            return wrapper
        return decorator

    async def smart_cache_set(self, key: str, value: Any, 
                            content_type: str = "general",
                            priority: int = 1) -> bool:
        """Умная установка значения в кэш с учетом типа контента и приоритета"""
        if not self.initialized:
            await self.initialize()

        # Определяем оптимальный уровень кэша на основе типа контента
        cache_level = self._determine_optimal_cache_level(content_type, priority)
        
        try:
            await self.set(key, value, cache_levels=[cache_level])
            return True
        except Exception as e:
            logger.error(f"Error in smart cache set: {e}")
            return False

    def _determine_optimal_cache_level(self, content_type: str, priority: int) -> CacheLevel:
        """Определение оптимального уровня кэша"""
        # Для высокоприоритетных данных используем быстрые уровни
        if priority >= 3:
            if content_type in ["user_session", "auth_token", "realtime_data"]:
                return CacheLevel.L1_MEMORY
            else:
                return CacheLevel.L2_REDIS
        # Для больших объектов используем Memcached
        elif content_type in ["large_file", "media_content", "binary_data"]:
            return CacheLevel.L3_MEMCACHED
        # Для данных, которые нужно сохранить надолго
        elif content_type in ["configuration", "static_content", "reference_data"]:
            return CacheLevel.L4_DATABASE
        # Для остальных используем Redis
        else:
            return CacheLevel.L2_REDIS

    async def cache_user_data(self, user_id: int, data: Dict[str, Any], 
                            ttl: int = 900) -> bool:  # 15 минут
        """Кэширование пользовательских данных"""
        try:
            cache_key = f"user_data:{user_id}"
            await self.set(cache_key, data, ttl=ttl, 
                          cache_levels=[CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS])
            return True
        except Exception as e:
            logger.error(f"Error caching user data: {e}")
            return False

    async def get_user_data(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение пользовательских данных из кэша"""
        cache_key = f"user_data:{user_id}"
        return await self.get(cache_key, 
                             cache_levels=[CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS])

    async def cache_chat_data(self, chat_id: str, data: Dict[str, Any], 
                            ttl: int = 600) -> bool:  # 10 минут
        """Кэширование данных чата"""
        try:
            cache_key = f"chat_data:{chat_id}"
            await self.set(cache_key, data, ttl=ttl,
                          cache_levels=[CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS])
            return True
        except Exception as e:
            logger.error(f"Error caching chat data: {e}")
            return False

    async def get_chat_data(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Получение данных чата из кэша"""
        cache_key = f"chat_data:{chat_id}"
        return await self.get(cache_key,
                             cache_levels=[CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS])

    async def cache_message_history(self, chat_id: str, messages: List[Dict[str, Any]], 
                                   ttl: int = 1800) -> bool:  # 30 минут
        """Кэширование истории сообщений"""
        try:
            cache_key = f"message_history:{chat_id}"
            await self.set(cache_key, messages, ttl=ttl,
                          cache_levels=[CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS])
            return True
        except Exception as e:
            logger.error(f"Error caching message history: {e}")
            return False

    async def get_message_history(self, chat_id: str) -> Optional[List[Dict[str, Any]]]:
        """Получение истории сообщений из кэша"""
        cache_key = f"message_history:{chat_id}"
        return await self.get(cache_key,
                             cache_levels=[CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS])

    async def cache_file_metadata(self, file_id: str, metadata: Dict[str, Any], 
                                 ttl: int = 3600) -> bool:  # 1 час
        """Кэширование метаданных файла"""
        try:
            cache_key = f"file_metadata:{file_id}"
            await self.set(cache_key, metadata, ttl=ttl,
                          cache_levels=[CacheLevel.L2_REDIS])
            return True
        except Exception as e:
            logger.error(f"Error caching file metadata: {e}")
            return False

    async def get_file_metadata(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Получение метаданных файла из кэша"""
        cache_key = f"file_metadata:{file_id}"
        return await self.get(cache_key,
                             cache_levels=[CacheLevel.L2_REDIS])

    async def cache_system_config(self, config_name: str, config_data: Dict[str, Any], 
                                 ttl: int = 7200) -> bool:  # 2 часа
        """Кэширование системной конфигурации"""
        try:
            cache_key = f"system_config:{config_name}"
            await self.set(cache_key, config_data, ttl=ttl,
                          cache_levels=[CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS])
            return True
        except Exception as e:
            logger.error(f"Error caching system config: {e}")
            return False

    async def get_system_config(self, config_name: str) -> Optional[Dict[str, Any]]:
        """Получение системной конфигурации из кэша"""
        cache_key = f"system_config:{config_name}"
        return await self.get(cache_key,
                             cache_levels=[CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS])

    async def cache_api_response(self, endpoint: str, params: Dict[str, Any], 
                               response: Any, ttl: int = 300) -> bool:  # 5 минут
        """Кэширование ответа API"""
        try:
            # Создаем уникальный ключ на основе эндпоинта и параметров
            params_str = json.dumps(params, sort_keys=True)
            cache_key = f"api_response:{endpoint}:{hashlib.md5(params_str.encode()).hexdigest()}"
            
            await self.set(cache_key, response, ttl=ttl,
                          cache_levels=[CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS])
            return True
        except Exception as e:
            logger.error(f"Error caching API response: {e}")
            return False

    async def get_api_response(self, endpoint: str, params: Dict[str, Any]) -> Optional[Any]:
        """Получение ответа API из кэша"""
        params_str = json.dumps(params, sort_keys=True)
        cache_key = f"api_response:{endpoint}:{hashlib.md5(params_str.encode()).hexdigest()}"
        return await self.get(cache_key,
                             cache_levels=[CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS])

    async def cache_computation_result(self, computation_name: str, 
                                     inputs: Dict[str, Any], result: Any,
                                     ttl: int = 1800) -> bool:  # 30 минут
        """Кэширование результата вычислений"""
        try:
            # Создаем уникальный ключ на основе имени вычисления и входных данных
            inputs_str = json.dumps(inputs, sort_keys=True)
            cache_key = f"computation_result:{computation_name}:{hashlib.md5(inputs_str.encode()).hexdigest()}"
            
            await self.set(cache_key, result, ttl=ttl,
                          cache_levels=[CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS])
            return True
        except Exception as e:
            logger.error(f"Error caching computation result: {e}")
            return False

    async def get_computation_result(self, computation_name: str, 
                                   inputs: Dict[str, Any]) -> Optional[Any]:
        """Получение результата вычислений из кэша"""
        inputs_str = json.dumps(inputs, sort_keys=True)
        cache_key = f"computation_result:{computation_name}:{hashlib.md5(inputs_str.encode()).hexdigest()}"
        return await self.get(cache_key,
                             cache_levels=[CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS])

    async def cache_user_preferences(self, user_id: int, preferences: Dict[str, Any], 
                                   ttl: int = 86400) -> bool:  # 24 часа
        """Кэширование пользовательских предпочтений"""
        try:
            cache_key = f"user_preferences:{user_id}"
            await self.set(cache_key, preferences, ttl=ttl,
                          cache_levels=[CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS])
            return True
        except Exception as e:
            logger.error(f"Error caching user preferences: {e}")
            return False

    async def get_user_preferences(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение пользовательских предпочтений из кэша"""
        cache_key = f"user_preferences:{user_id}"
        return await self.get(cache_key,
                             cache_levels=[CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS])

    async def cache_content_analysis(self, content_id: str, analysis: Dict[str, Any], 
                                   ttl: int = 3600) -> bool:  # 1 час
        """Кэширование анализа контента"""
        try:
            cache_key = f"content_analysis:{content_id}"
            await self.set(cache_key, analysis, ttl=ttl,
                          cache_levels=[CacheLevel.L2_REDIS])
            return True
        except Exception as e:
            logger.error(f"Error caching content analysis: {e}")
            return False

    async def get_content_analysis(self, content_id: str) -> Optional[Dict[str, Any]]:
        """Получение анализа контента из кэша"""
        cache_key = f"content_analysis:{content_id}"
        return await self.get(cache_key,
                             cache_levels=[CacheLevel.L2_REDIS])

    async def requires_moderation(self, content_type: ContentType) -> bool:
        """Проверка, требует ли контент модерации"""
        # В реальной системе здесь будет более сложная логика
        # в зависимости от типа контента, пользователя и т.д.
        return content_type in [ContentType.IMAGE, ContentType.VIDEO, ContentType.LINK]

    async def _submit_for_moderation(self, content: Content):
        """Отправка контента на модерацию"""
        moderation_record = ContentModeration(
            id=str(uuid.uuid4()),
            content_id=content.id,
            moderator_id=None,  # Будет назначен системой
            status=ContentModerationStatus.PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем в базу данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO content_moderation (
                    id, content_id, moderator_id, status, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                moderation_record.id, moderation_record.content_id,
                moderation_record.moderator_id, moderation_record.status.value,
                moderation_record.created_at, moderation_record.updated_at
            )

    async def _schedule_content_publish(self, content: Content):
        """Планирование публикации контента"""
        if not content.scheduled_publish:
            return

        # Добавляем в очередь планировщика
        await redis_client.zadd(
            "scheduled_content_queue",
            {content.id: content.scheduled_publish.timestamp()}
        )

    async def _are_friends(self, user1_id: int, user2_id: int) -> bool:
        """Проверка, являются ли пользователи друзьями"""
        # В реальной системе здесь будет проверка в таблице друзей
        return False

    async def _is_group_member(self, user_id: int, group_id: str) -> bool:
        """Проверка, является ли пользователь членом группы"""
        # В реальной системе здесь будет проверка в таблице участников группы
        return False

    async def _is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        # В реальной системе здесь будет проверка прав пользователя
        return False

# Глобальный экземпляр для использования в приложении
multi_level_cache_service = MultiLevelCacheService()
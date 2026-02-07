# server/app/performance_optimizer.py
import asyncio
import aioredis
import asyncpg
from typing import Dict, List, Any, Optional, Callable
from functools import wraps
import time
import logging
from collections import OrderedDict
import pickle
import hashlib
from concurrent.futures import ThreadPoolExecutor
import aiocache
from aiocache import cached, Cache
from aiocache.serializers import PickleSerializer

logger = logging.getLogger(__name__)

class ConnectionPoolManager:
    """Менеджер пула соединений для оптимизации производительности"""
    
    def __init__(self):
        self.pools = {}
    
    async def get_pool(self, dsn: str, min_size: int = 5, max_size: int = 20):
        """Получение пула соединений"""
        if dsn not in self.pools:
            pool = await asyncpg.create_pool(
                dsn,
                min_size=min_size,
                max_size=max_size,
                command_timeout=60,
                statement_cache_size=0  # Отключаем кэш для высоконагруженных сценариев
            )
            self.pools[dsn] = pool
        return self.pools[dsn]
    
    async def close_all(self):
        """Закрытие всех пулов"""
        for pool in self.pools.values():
            await pool.close()

class QueryOptimizer:
    """Оптимизатор запросов"""
    
    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.prepared_statements = {}
        self.query_cache = {}
    
    async def prepare_statement(self, name: str, query: str):
        """Подготовка часто используемых запросов"""
        if name not in self.prepared_statements:
            pool = await self.db_pool
            self.prepared_statements[name] = await pool.prepare(query)
        return self.prepared_statements[name]
    
    async def execute_prepared(self, name: str, *args):
        """Выполнение подготовленного запроса"""
        stmt = await self.prepare_statement(name, self.prepared_statements.get(name))
        return await stmt.fetch(*args)
    
    async def batch_insert(self, table: str, records: List[Dict], batch_size: int = 1000):
        """Массовая вставка записей"""
        async with self.db_pool.acquire() as conn:
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                if batch:
                    columns = list(batch[0].keys())
                    values = [tuple(record[col] for col in columns) for record in batch]
                    
                    placeholders = ', '.join([f'${i}' for i in range(1, len(columns) + 1)])
                    query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
                    
                    await conn.executemany(query, values)

class CacheManager:
    """Менеджер кэширования"""
    
    def __init__(self, redis_url: str):
        self.redis = aioredis.from_url(redis_url, decode_responses=True)
        self.memory_cache = OrderedDict()  # LRU кэш в памяти
        self.max_memory_items = 1000
    
    async def get(self, key: str) -> Optional[Any]:
        """Получение значения из кэша"""
        # Сначала проверяем память
        if key in self.memory_cache:
            return self.memory_cache[key]
        
        # Потом Redis
        value = await self.redis.get(key)
        if value:
            try:
                deserialized = pickle.loads(value.encode())
                # Добавляем в память
                self._add_to_memory_cache(key, deserialized)
                return deserialized
            except:
                return value
        
        return None
    
    async def set(self, key: str, value: Any, ttl: int = 300):
        """Установка значения в кэш"""
        # Сериализуем значение
        try:
            serialized = pickle.dumps(value)
            await self.redis.setex(key, ttl, serialized.decode())
        except:
            # Если не удается сериализовать, сохраняем как строку
            await self.redis.setex(key, ttl, str(value))
        
        # Добавляем в память
        self._add_to_memory_cache(key, value)
    
    def _add_to_memory_cache(self, key: str, value: Any):
        """Добавление в кэш памяти с LRU политикой"""
        if key in self.memory_cache:
            del self.memory_cache[key]
        elif len(self.memory_cache) >= self.max_memory_items:
            # Удаляем самый старый элемент
            self.memory_cache.popitem(last=False)
        
        self.memory_cache[key] = value
    
    async def delete(self, key: str):
        """Удаление из кэша"""
        if key in self.memory_cache:
            del self.memory_cache[key]
        await self.redis.delete(key)
    
    async def invalidate_pattern(self, pattern: str):
        """Инвалидация по паттерну"""
        # Удаление из Redis
        keys = await self.redis.keys(pattern)
        if keys:
            await self.redis.delete(*keys)
        
        # Удаление из памяти
        for key in list(self.memory_cache.keys()):
            if self._match_pattern(key, pattern):
                del self.memory_cache[key]
    
    def _match_pattern(self, key: str, pattern: str) -> bool:
        """Проверка соответствия ключа паттерну"""
        # Простая реализация для *
        if '*' in pattern:
            import fnmatch
            return fnmatch.fnmatch(key, pattern)
        return key == pattern

class PerformanceMonitor:
    """Мониторинг производительности"""
    
    def __init__(self):
        self.metrics = {}
        self.start_times = {}
    
    def start_timer(self, operation: str):
        """Начало отсчета времени операции"""
        self.start_times[operation] = time.time()
    
    def stop_timer(self, operation: str) -> float:
        """Окончание отсчета времени операции"""
        if operation in self.start_times:
            duration = time.time() - self.start_times[operation]
            del self.start_times[operation]
            
            # Сохраняем метрики
            if operation not in self.metrics:
                self.metrics[operation] = []
            self.metrics[operation].append(duration)
            
            return duration
        return 0.0
    
    def get_avg_duration(self, operation: str) -> float:
        """Получение средней длительности операции"""
        if operation in self.metrics and self.metrics[operation]:
            return sum(self.metrics[operation]) / len(self.metrics[operation])
        return 0.0
    
    def log_slow_queries(self, threshold: float = 1.0):
        """Логирование медленных запросов"""
        for operation, durations in self.metrics.items():
            avg_duration = self.get_avg_duration(operation)
            if avg_duration > threshold:
                logger.warning(f"Slow operation detected: {operation}, avg duration: {avg_duration:.2f}s")

def performance_monitor(func):
    """Декоратор для мониторинга производительности"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        monitor = getattr(args[0] if args else None, 'monitor', PerformanceMonitor())
        op_name = f"{func.__module__}.{func.__name__}"
        
        monitor.start_timer(op_name)
        try:
            result = await func(*args, **kwargs)
            duration = monitor.stop_timer(op_name)
            logger.debug(f"{op_name} took {duration:.4f}s")
            return result
        except Exception as e:
            duration = monitor.stop_timer(op_name)
            logger.error(f"{op_name} failed after {duration:.4f}s: {str(e)}")
            raise
    return wrapper

class BatchProcessor:
    """Пакетная обработка сообщений для улучшения производительности"""
    
    def __init__(self, batch_size: int = 100, flush_interval: float = 1.0):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.batches = {}
        self.timers = {}
        self.callbacks = {}
    
    def add_to_batch(self, queue_name: str, item: Any, callback: Callable = None):
        """Добавление элемента в очередь пакетной обработки"""
        if queue_name not in self.batches:
            self.batches[queue_name] = []
            self.callbacks[queue_name] = callback
        
        self.batches[queue_name].append(item)
        
        # Запускаем таймер, если первый элемент
        if len(self.batches[queue_name]) == 1:
            self.timers[queue_name] = asyncio.create_task(self._schedule_flush(queue_name))
        
        # Если достигли размера пакета, сразу обрабатываем
        if len(self.batches[queue_name]) >= self.batch_size:
            self._flush_batch(queue_name)
    
    async def _schedule_flush(self, queue_name: str):
        """Планирование сброса пакета по таймеру"""
        await asyncio.sleep(self.flush_interval)
        self._flush_batch(queue_name)
    
    def _flush_batch(self, queue_name: str):
        """Сброс пакета для обработки"""
        if queue_name in self.batches and self.batches[queue_name]:
            items = self.batches[queue_name]
            self.batches[queue_name] = []
            
            # Отменяем таймер
            if queue_name in self.timers:
                self.timers[queue_name].cancel()
                del self.timers[queue_name]
            
            # Вызываем коллбэк для обработки пакета
            if queue_name in self.callbacks and self.callbacks[queue_name]:
                asyncio.create_task(self.callbacks[queue_name](items))

class MessageQueue:
    """Оптимизированная очередь сообщений"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.batch_processor = BatchProcessor()
    
    async def publish_message(self, channel: str, message: Dict[str, Any]):
        """Публикация сообщения в канал"""
        # Используем пакетную обработку для высокой производительности
        self.batch_processor.add_to_batch(
            f"channel:{channel}",
            message,
            self._process_batch
        )
    
    async def _process_batch(self, messages: List[Dict[str, Any]]):
        """Обработка пакета сообщений"""
        # Оптимизированная публикация нескольких сообщений
        pipe = self.redis.pipeline()
        for msg in messages:
            pipe.publish(f"chat:{msg.get('room', 'general')}", str(msg))
        await pipe.execute()

class PaginationHelper:
    """Помощник для эффективной пагинации"""
    
    @staticmethod
    async def get_paginated_results(
        db_pool,
        query: str,
        params: tuple,
        page: int = 1,
        page_size: int = 50,
        count_query: Optional[str] = None
    ) -> Dict[str, Any]:
        """Получение пагинированных результатов"""
        offset = (page - 1) * page_size
        
        async with db_pool.acquire() as conn:
            # Получаем данные
            data = await conn.fetch(f"{query} LIMIT $1 OFFSET $2", page_size, offset)
            
            # Получаем общее количество
            if count_query:
                count_result = await conn.fetchval(count_query, *params)
            else:
                # Если нет отдельного запроса для подсчета, используем тот же запрос
                count_query = f"SELECT COUNT(*) FROM ({query}) AS subquery"
                count_params = params
                count_result = await conn.fetchval(count_query, *count_params)
        
        return {
            'data': [dict(row) for row in data],
            'total': count_result,
            'page': page,
            'page_size': page_size,
            'pages': (count_result + page_size - 1) // page_size
        }

# Глобальный экземпляр для использования в приложении
connection_pool_manager = ConnectionPoolManager()
"""
Performance optimization module for the hybrid messenger application.

This module contains performance optimizations including:
- Connection pooling improvements
- Caching strategies
- Database query optimizations
- Memory management
- Async optimizations
- WebSocket optimizations
"""

import asyncio
import time
import functools
from typing import Dict, List, Optional, Any, Callable, Awaitable
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
import aioredis
import asyncpg
from functools import lru_cache
import weakref
import gc
from concurrent.futures import ThreadPoolExecutor
import psutil
import logging

logger = logging.getLogger(__name__)


class LRUCache:
    """
    Least Recently Used (LRU) Cache implementation for high-performance caching.
    """
    
    def __init__(self, max_size: int = 1000, ttl: int = 300):  # 5 minutes default TTL
        self.max_size = max_size
        self.ttl = ttl
        self.cache: OrderedDict[str, tuple] = OrderedDict()  # (value, expiration_time)
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if key in self.cache:
            value, expiry = self.cache[key]
            if time.time() < expiry:
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                return value
            else:
                # Expired, remove from cache
                del self.cache[key]
        return None
    
    def set(self, key: str, value: Any):
        """Set value in cache."""
        # Remove oldest items if cache is full
        while len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)
        
        expiry = time.time() + self.ttl
        self.cache[key] = (value, expiry)
        # Move to end (most recently used)
        self.cache.move_to_end(key)
    
    def delete(self, key: str):
        """Delete key from cache."""
        if key in self.cache:
            del self.cache[key]
    
    def clear(self):
        """Clear all cache."""
        self.cache.clear()
    
    def size(self) -> int:
        """Get current cache size."""
        return len(self.cache)


class ConnectionPoolManager:
    """
    Enhanced connection pool manager with performance optimizations.
    """
    
    def __init__(self, db_config: Dict[str, Any]):
        self.db_config = db_config
        self.pools: Dict[str, asyncpg.Pool] = {}
        self.redis_pools: Dict[str, aioredis.ConnectionPool] = {}
    
    async def get_db_pool(self, name: str = "default") -> asyncpg.Pool:
        """Get or create a database connection pool."""
        if name not in self.pools:
            pool = await asyncpg.create_pool(
                **self.db_config,
                min_size=10,      # Increased for better performance
                max_size=50,      # Increased for better performance
                max_queries=50000, # Increased to reduce connection overhead
                max_inactive_connection_lifetime=300.0,  # 5 minutes
                command_timeout=30,  # 30 seconds timeout
                init=self._init_connection
            )
            self.pools[name] = pool
        return self.pools[name]
    
    async def _init_connection(self, conn):
        """Initialize connection with performance settings."""
        # Set connection settings for better performance
        await conn.set_type_codec(
            'json',
            encoder=lambda x: json.dumps(x),
            decoder=json.loads,
            schema='pg_catalog'
        )
    
    async def get_redis_pool(self, name: str = "default") -> aioredis.ConnectionPool:
        """Get or create a Redis connection pool."""
        if name not in self.redis_pools:
            pool = aioredis.ConnectionPool.from_url(
                self.db_config['redis_url'],
                max_connections=50,  # Increased for better performance
                decode_responses=True,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30
            )
            self.redis_pools[name] = pool
        return self.redis_pools[name]
    
    async def close_all(self):
        """Close all pools."""
        for pool in self.pools.values():
            await pool.close()
        for pool in self.redis_pools.values():
            await pool.disconnect()


class QueryOptimizer:
    """
    Database query optimizer with prepared statements and batching.
    """
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.prepared_statements: Dict[str, asyncpg.PreparedStatement] = {}
        self.statement_cache_size = 100
    
    async def prepare_statement(self, name: str, query: str) -> asyncpg.PreparedStatement:
        """Prepare a statement for reuse."""
        if name in self.prepared_statements:
            return self.prepared_statements[name]
        
        # Limit cache size
        if len(self.prepared_statements) >= self.statement_cache_size:
            # Remove oldest statement (least recently used)
            oldest_key = next(iter(self.prepared_statements))
            del self.prepared_statements[oldest_key]
        
        conn = await self.db_pool.acquire()
        try:
            stmt = await conn.prepare(query)
            self.prepared_statements[name] = stmt
            return stmt
        finally:
            await self.db_pool.release(conn)
    
    async def execute_batch(self, query: str, args_list: List[tuple]) -> List[Any]:
        """Execute a batch of queries efficiently."""
        conn = await self.db_pool.acquire()
        try:
            return await conn.executemany(query, args_list)
        finally:
            await self.db_pool.release(conn)
    
    async def fetch_many(self, query: str, *args, batch_size: int = 1000) -> List[Dict[str, Any]]:
        """Fetch many records with pagination to avoid memory issues."""
        all_records = []
        offset = 0
        
        while True:
            batch_query = f"{query} LIMIT {batch_size} OFFSET {offset}"
            batch = await self.fetch(query, *args)
            
            if not batch:
                break
            
            all_records.extend(batch)
            offset += batch_size
            
            # Yield control to event loop periodically
            if len(all_records) % (batch_size * 10) == 0:
                await asyncio.sleep(0)
        
        return all_records


class MessageBatchProcessor:
    """
    Batch processor for messages to improve throughput.
    """
    
    def __init__(self, process_callback: Callable[[List[Dict[str, Any]]], Awaitable[None]], 
                 batch_size: int = 100, flush_interval: float = 1.0):
        self.process_callback = process_callback
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.message_buffer: List[Dict[str, Any]] = []
        self.flush_timer: Optional[asyncio.TimerHandle] = None
        self.lock = asyncio.Lock()
    
    async def add_message(self, message: Dict[str, Any]):
        """Add a message to the batch."""
        async with self.lock:
            self.message_buffer.append(message)
            
            if len(self.message_buffer) >= self.batch_size:
                await self._flush_batch()
            elif self.flush_timer is None:
                self.flush_timer = asyncio.get_event_loop().call_later(
                    self.flush_interval, 
                    lambda: asyncio.create_task(self._flush_batch())
                )
    
    async def _flush_batch(self):
        """Flush the current batch."""
        async with self.lock:
            if self.flush_timer:
                self.flush_timer.cancel()
                self.flush_timer = None
            
            if self.message_buffer:
                batch = self.message_buffer[:]
                self.message_buffer.clear()
                
                try:
                    await self.process_callback(batch)
                except Exception as e:
                    logger.error(f"Error processing message batch: {e}")
                    # Put messages back in buffer for retry
                    self.message_buffer.extend(batch)


class WebSocketOptimizations:
    """
    WebSocket optimizations for better performance.
    """
    
    def __init__(self):
        self.connection_registry = weakref.WeakSet()
        self.message_compressors = {}  # Per-connection compressors
        self.heartbeat_intervals = {}  # Per-connection heartbeat intervals
        self.message_aggregators = {}  # Per-connection message aggregators
    
    def register_connection(self, ws_connection):
        """Register a WebSocket connection for optimizations."""
        self.connection_registry.add(ws_connection)
        
        # Initialize per-connection optimizations
        self.message_compressors[id(ws_connection)] = self._create_compressor()
        self.heartbeat_intervals[id(ws_connection)] = 30  # 30 seconds
        self.message_aggregators[id(ws_connection)] = deque(maxlen=10)  # Last 10 messages
    
    def unregister_connection(self, ws_connection):
        """Unregister a WebSocket connection."""
        # Clean up per-connection resources
        conn_id = id(ws_connection)
        if conn_id in self.message_compressors:
            del self.message_compressors[conn_id]
        if conn_id in self.heartbeat_intervals:
            del self.heartbeat_intervals[conn_id]
        if conn_id in self.message_aggregators:
            del self.message_aggregators[conn_id]
    
    def _create_compressor(self):
        """Create a message compressor for a connection."""
        import zlib
        return zlib.compressobj(wbits=12)  # Smaller window size for faster compression
    
    async def compress_message(self, ws_connection, message: str) -> bytes:
        """Compress a message for a specific connection."""
        conn_id = id(ws_connection)
        if conn_id in self.message_compressors:
            compressor = self.message_compressors[conn_id]
            compressed = compressor.compress(message.encode('utf-8'))
            # Flush compressor periodically to ensure data is compressed
            if len(compressed) < len(message.encode('utf-8')) * 0.1:  # If compression ratio is poor
                compressed += compressor.flush(zlib.Z_SYNC_FLUSH)
            return compressed
        return message.encode('utf-8')
    
    def aggregate_messages(self, ws_connection, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Aggregate similar messages to reduce network traffic."""
        conn_id = id(ws_connection)
        if conn_id not in self.message_aggregators:
            return message
        
        aggregator = self.message_aggregators[conn_id]
        
        # Aggregation logic for typing indicators
        if message.get('type') == 'typing_indicator' and aggregator:
            # If last message was also a typing indicator from same user, aggregate them
            last_msg = aggregator[-1]
            if (last_msg.get('type') == 'typing_indicator' and 
                last_msg.get('user_id') == message.get('user_id')):
                # Skip duplicate typing indicators
                return None
        
        aggregator.append(message)
        return message


class MemoryOptimizer:
    """
    Memory optimization utilities.
    """
    
    def __init__(self):
        self.object_sizes: Dict[str, int] = {}
        self.object_counts: Dict[str, int] = {}
        self.large_objects: List[Any] = []
    
    def track_object_size(self, obj: Any, name: str):
        """Track the size of an object."""
        import sys
        size = sys.getsizeof(obj)
        self.object_sizes[name] = size
        
        if size > 1024 * 1024:  # Larger than 1MB
            self.large_objects.append(obj)
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """Get current memory usage statistics."""
        process = psutil.Process()
        memory_info = process.memory_info()
        
        return {
            'rss': memory_info.rss,  # Resident Set Size
            'vms': memory_info.vms,  # Virtual Memory Size
            'percent': process.memory_percent(),
            'large_objects_count': len(self.large_objects),
            'tracked_objects': dict(self.object_sizes)
        }
    
    def cleanup_large_objects(self):
        """Clean up large objects that are no longer needed."""
        # Force garbage collection
        collected = gc.collect()
        logger.info(f"Garbage collected {collected} objects")
        
        # Clear references to large objects
        self.large_objects.clear()


class AsyncOptimizer:
    """
    Async performance optimizations.
    """
    
    def __init__(self, max_workers: int = 4):
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        self.coroutines_in_flight = 0
        self.max_concurrent_coroutines = 1000
    
    def async_semaphore(self, max_concurrent: int = None):
        """Create an async semaphore for limiting concurrent operations."""
        limit = max_concurrent or self.max_concurrent_coroutines
        return asyncio.Semaphore(limit)
    
    async def run_in_thread(self, func: Callable, *args, **kwargs) -> Any:
        """Run a synchronous function in a thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.thread_pool, func, *args)
    
    def timed_cache(self, ttl: int = 300):
        """Decorator for creating timed cache for coroutines."""
        def decorator(func: Callable[..., Awaitable[Any]]):
            cache: Dict[tuple, tuple] = {}  # (result, expiry_time)
            
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                key = str(args) + str(sorted(kwargs.items()))
                current_time = time.time()
                
                if key in cache:
                    result, expiry = cache[key]
                    if current_time < expiry:
                        return result
                    else:
                        del cache[key]
                
                result = await func(*args, **kwargs)
                cache[key] = (result, current_time + ttl)
                return result
            
            return wrapper
        return decorator
    
    def rate_limit(self, max_calls: int, time_window: int):
        """Decorator for rate limiting coroutines."""
        calls: Dict[str, deque] = {}
        
        def decorator(func: Callable[..., Awaitable[Any]]):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                # Use function name as identifier (in real app, use user/session ID)
                identifier = f"{func.__module__}.{func.__name__}"
                
                if identifier not in calls:
                    calls[identifier] = deque()
                
                now = time.time()
                
                # Remove calls outside the time window
                while calls[identifier] and now - calls[identifier][0] > time_window:
                    calls[identifier].popleft()
                
                if len(calls[identifier]) >= max_calls:
                    raise Exception(f"Rate limit exceeded: {max_calls} calls per {time_window} seconds")
                
                calls[identifier].append(now)
                return await func(*args, **kwargs)
            
            return wrapper
        return decorator


# Global performance optimizers
lru_cache = LRUCache(max_size=5000, ttl=600)  # 10 minute TTL, 5000 item limit
connection_pool_manager = ConnectionPoolManager({})
query_optimizer = None  # Will be initialized with pool
message_batch_processor = MessageBatchProcessor(None)  # Will be initialized with callback
websocket_optimizations = WebSocketOptimizations()
memory_optimizer = MemoryOptimizer()
async_optimizer = AsyncOptimizer(max_workers=8)


def performance_monitor(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Decorator to monitor performance of async functions."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        start_memory = memory_optimizer.get_memory_usage()['rss']
        
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            end_time = time.time()
            end_memory = memory_optimizer.get_memory_usage()['rss']
            
            duration = end_time - start_time
            memory_change = end_memory - start_memory
            
            if duration > 1.0:  # Log slow functions (> 1 second)
                logger.warning(
                    f"Slow function {func.__name__}: {duration:.2f}s, "
                    f"memory change: {memory_change:,} bytes"
                )
            elif memory_change > 1024 * 1024:  # Log high memory usage (> 1MB)
                logger.info(
                    f"High memory function {func.__name__}: "
                    f"memory change: {memory_change:,} bytes"
                )
    
    return wrapper


def async_cache(ttl: int = 300):
    """Async cache decorator with TTL."""
    def decorator(func: Callable[..., Awaitable[Any]]):
        cache: Dict[tuple, tuple] = {}  # (result, expiry_time)
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            key = str(args) + str(sorted(kwargs.items()))
            current_time = time.time()
            
            if key in cache:
                result, expiry = cache[key]
                if current_time < expiry:
                    return result
                else:
                    del cache[key]
            
            result = await func(*args, **kwargs)
            cache[key] = (result, current_time + ttl)
            return result
        
        return wrapper
    return decorator


# Initialize optimizers with actual pools when available
async def initialize_performance_optimizers(db_pool: asyncpg.Pool, redis_client: aioredis.Redis):
    """Initialize performance optimizers with actual connections."""
    global query_optimizer
    query_optimizer = QueryOptimizer(db_pool)
    
    # Initialize batch processor with actual callback
    async def process_message_batch(messages: List[Dict[str, Any]]):
        # Process batch of messages with optimization
        import logging
        for msg in messages:
            # Process individual message
            # Handle the actual message processing
            logging.debug(f"Processing message: {msg.get('id', 'unknown')}")

            # Process the actual message
            await process_individual_message(msg)

    async def process_individual_message(msg: Dict[str, Any]):
        """Process individual message in batch"""
        # This is where the actual message processing would happen
        # For example: save to database, send to recipients, etc.
        import logging
        message_id = msg.get('id', 'unknown')
        message_type = msg.get('type', 'text')
        sender_id = msg.get('sender_id')
        chat_id = msg.get('chat_id')

        logging.info(f"Processing individual message {message_id} of type {message_type} from {sender_id} in chat {chat_id}")

        # В реальной системе здесь будет:
        # 1. Валидация сообщения
        # 2. Сохранение в базу данных
        # 3. Шифрование при необходимости
        # 4. Отправка получателям
        # 5. Обновление статистики

        # Для упрощения возвращаем True
        return True
    
    message_batch_processor.process_callback = process_message_batch
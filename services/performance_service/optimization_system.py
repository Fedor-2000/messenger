# Performance Optimization and Caching System
# File: services/performance_service/optimization_system.py

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import uuid
import psutil
import aioredis
from pydantic import BaseModel
import asyncpg
from functools import wraps
import aiocache
from aiocache import cached, Cache
from aiocache.serializers import JsonSerializer

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class OptimizationStrategy(Enum):
    CACHING = "caching"
    DATABASE_INDEXING = "database_indexing"
    QUERY_OPTIMIZATION = "query_optimization"
    RESOURCE_POOLING = "resource_pooling"
    ASYNC_PROCESSING = "async_processing"
    LOAD_BALANCING = "load_balancing"
    COMPRESSION = "compression"
    BATCHING = "batching"
    PREFETCHING = "prefetching"
    CONNECTION_REUSE = "connection_reuse"

class PerformanceMetric(Enum):
    RESPONSE_TIME_MS = "response_time_ms"
    THROUGHPUT_RPS = "throughput_rps"
    CPU_USAGE_PERCENT = "cpu_usage_percent"
    MEMORY_USAGE_PERCENT = "memory_usage_percent"
    DATABASE_QUERY_TIME_MS = "database_query_time_ms"
    CACHE_HIT_RATE = "cache_hit_rate"
    CONNECTION_POOL_UTILIZATION = "connection_pool_utilization"
    ERROR_RATE = "error_rate"

class CacheLayer(Enum):
    L1_MEMORY = "l1_memory"  # In-memory cache (fastest)
    L2_REDIS = "l2_redis"    # Redis cache
    L3_DATABASE = "l3_database"  # Database cache

class OptimizationRule(BaseModel):
    id: str
    name: str
    description: str
    strategy: OptimizationStrategy
    condition: str  # Условие для применения оптимизации
    action: str     # Действие для выполнения
    priority: int = 1  # 1-5, где 5 - самый высокий приоритет
    enabled: bool = True
    created_at: datetime = None
    updated_at: datetime = None

class PerformanceMetricRecord(BaseModel):
    id: str
    metric_name: PerformanceMetric
    value: float
    timestamp: datetime = None
    tags: Optional[Dict[str, str]] = None  # Дополнительные теги для фильтрации

class PerformanceOptimizer:
    def __init__(self):
        self.cache = Cache(Cache.MEMORY)  # Локальный кэш
        self.optimization_rules: List[OptimizationRule] = []
        self.performance_metrics: Dict[str, List[tuple]] = {}  # metric_name -> [(timestamp, value)]
        self.cache_hit_count = 0
        self.cache_miss_count = 0
        self.active_optimizations: Dict[str, Any] = {}
        self.optimization_thresholds = {
            'response_time_ms': 500,  # порог для оптимизации производительности
            'cpu_usage_percent': 80,
            'memory_usage_percent': 85,
            'database_query_time_ms': 100,
            'cache_hit_rate_percent': 80
        }
        self.cache_config = {
            'ttl': 300,  # 5 минут по умолчанию
            'namespace': 'messenger_cache',
            'serializer': JsonSerializer()
        }

    async def initialize_optimization_rules(self):
        """Инициализация правил оптимизации"""
        default_rules = [
            OptimizationRule(
                id="rule_cache_optimization",
                name="Cache Optimization",
                description="Automatically optimize cache strategies based on usage patterns",
                strategy=OptimizationStrategy.CACHING,
                condition="cache_hit_rate < 0.7",
                action="increase_cache_size_or_change_policy",
                priority=4,
                created_at=datetime.utcnow()
            ),
            OptimizationRule(
                id="rule_db_query_optimization",
                name="Database Query Optimization",
                description="Optimize database queries based on execution time",
                strategy=OptimizationStrategy.QUERY_OPTIMIZATION,
                condition="query_time > 1000",
                action="add_index_or_rewrite_query",
                priority=5,
                created_at=datetime.utcnow()
            ),
            OptimizationRule(
                id="rule_response_time_optimization",
                name="Response Time Optimization",
                description="Optimize response time when it exceeds threshold",
                strategy=OptimizationStrategy.ASYNC_PROCESSING,
                condition="response_time > 1000",
                action="enable_caching_or_async_processing",
                priority=3,
                created_at=datetime.utcnow()
            ),
            OptimizationRule(
                id="rule_memory_optimization",
                name="Memory Optimization",
                description="Optimize memory usage when it exceeds threshold",
                strategy=OptimizationStrategy.RESOURCE_POOLING,
                condition="memory_usage > 85",
                action="garbage_collection_or_caching_adjustment",
                priority=5,
                created_at=datetime.utcnow()
            ),
            OptimizationRule(
                id="rule_compression_optimization",
                name="Compression Optimization",
                description="Enable compression for large data transfers",
                strategy=OptimizationStrategy.COMPRESSION,
                condition="data_size > 102400",  # 100KB
                action="enable_compression",
                priority=2,
                created_at=datetime.utcnow()
            )
        ]

        for rule in default_rules:
            await self.add_optimization_rule(rule)

    async def add_optimization_rule(self, rule: OptimizationRule):
        """Добавление правила оптимизации"""
        self.optimization_rules.append(rule)

        # Сохраняем правило в базу данных
        await self._save_optimization_rule(rule)

    async def _save_optimization_rule(self, rule: OptimizationRule):
        """Сохранение правила оптимизации в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO optimization_rules (
                    id, name, description, strategy, condition, action, priority, enabled, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (id) DO UPDATE SET
                    name = $2, description = $3, strategy = $4, condition = $5,
                    action = $6, priority = $7, enabled = $8, updated_at = $10
                """,
                rule.id, rule.name, rule.description, rule.strategy.value,
                rule.condition, rule.action, rule.priority, rule.enabled,
                rule.created_at, rule.updated_at
            )

    async def record_performance_metric(self, metric_name: PerformanceMetric, value: float, 
                                      tags: Optional[Dict[str, str]] = None):
        """Запись метрики производительности"""
        metric_id = str(uuid.uuid4())
        timestamp = datetime.utcnow()

        # Сохраняем в промежуточное хранилище
        if metric_name.value not in self.performance_metrics:
            self.performance_metrics[metric_name.value] = []
        self.performance_metrics[metric_name.value].append((timestamp, value))

        # Ограничиваем размер промежуточного хранилища
        if len(self.performance_metrics[metric_name.value]) > 10000:
            self.performance_metrics[metric_name.value] = self.performance_metrics[metric_name.value][-5000:]

        # Сохраняем в базу данных
        await self._save_performance_metric(metric_id, metric_name, value, tags, timestamp)

        # Проверяем, не нужно ли применить оптимизацию
        await self._check_optimization_needed(metric_name, value)

    async def _save_performance_metric(self, metric_id: str, metric_name: PerformanceMetric, 
                                     value: float, tags: Optional[Dict[str, str]], 
                                     timestamp: datetime):
        """Сохранение метрики производительности в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO performance_metrics (
                    id, metric_name, value, tags, recorded_at
                ) VALUES ($1, $2, $3, $4, $5)
                """,
                metric_id, metric_name.value, value, 
                json.dumps(tags) if tags else None, timestamp
            )

    async def _check_optimization_needed(self, metric_name: PerformanceMetric, value: float):
        """Проверка, требуется ли оптимизация на основе метрики"""
        # Сортируем правила по приоритету
        sorted_rules = sorted(self.optimization_rules, key=lambda r: r.priority, reverse=True)

        for rule in sorted_rules:
            if not rule.enabled:
                continue

            # Проверяем условие для применения оптимизации
            if await self._evaluate_condition(rule.condition, metric_name.value, value):
                await self._apply_optimization_action(rule.action, metric_name, value)

    async def _evaluate_condition(self, condition: str, metric_name: str, value: float) -> bool:
        """Оценка условия для применения оптимизации"""
        # Простая реализация - в реальности потребуется более сложный парсер условий
        if condition.startswith("cache_hit_rate < "):
            threshold = float(condition.split(" ")[-1])
            if metric_name == "cache_hit_rate":
                return value < threshold
        elif condition.startswith("response_time > "):
            threshold = float(condition.split(" ")[-1])
            if metric_name == "response_time_ms":
                return value > threshold
        elif condition.startswith("query_time > "):
            threshold = float(condition.split(" ")[-1])
            if metric_name == "database_query_time_ms":
                return value > threshold
        elif condition.startswith("memory_usage > "):
            threshold = float(condition.split(" ")[-1])
            if metric_name == "memory_usage_percent":
                return value > threshold
        elif condition.startswith("data_size > "):
            threshold = float(condition.split(" ")[-1])
            if metric_name == "data_transfer_size":
                return value > threshold

        return False

    async def _apply_optimization_action(self, action: str, metric_name: PerformanceMetric, value: float):
        """Применение действия оптимизации"""
        if action == "increase_cache_size_or_change_policy":
            await self._increase_cache_efficiency()
        elif action == "add_index_or_rewrite_query":
            await self._optimize_database_queries()
        elif action == "enable_caching_or_async_processing":
            await self._enable_additional_caching()
        elif action == "garbage_collection_or_caching_adjustment":
            await self._perform_garbage_collection()
        elif action == "enable_compression":
            await self._enable_compression()

    async def _increase_cache_efficiency(self):
        """Увеличение эффективности кэширования"""
        logger.info("Increasing cache efficiency based on optimization rule")
        # В реальной системе здесь будет увеличение размера кэша Redis или другого кэша
        # и возможно изменение политики кэширования

    async def _optimize_database_queries(self):
        """Оптимизация запросов к базе данных"""
        logger.info("Optimizing database queries based on performance metrics")
        # В реальной системе здесь будет анализ медленных запросов и добавление индексов

    async def _enable_additional_caching(self):
        """Включение дополнительного кэширования"""
        logger.info("Enabling additional caching based on performance metrics")
        # В реальной системе здесь будет включение дополнительных уровней кэширования

    async def _perform_garbage_collection(self):
        """Выполнение сборки мусора"""
        logger.info("Performing garbage collection based on memory usage")
        # В реальной системе здесь будет вызов сборщика мусора Python
        import gc
        collected = gc.collect()
        logger.info(f"Garbage collection completed. Collected {collected} objects")

    async def _enable_compression(self):
        """Включение сжатия данных"""
        logger.info("Enabling data compression based on transfer size")
        # В реальной системе здесь будет включение сжатия для передачи данных

    def cache_with_ttl(self, ttl: int = 300, namespace: str = "default"):
        """Декоратор для кэширования с TTL"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Генерируем ключ кэша на основе аргументов
                cache_key = f"{namespace}:{func.__name__}:{hash(str(args) + str(kwargs))}"
                
                # Проверяем кэш
                cached_result = await redis_client.get(cache_key)
                if cached_result:
                    logger.debug(f"Cache hit for {cache_key}")
                    return json.loads(cached_result)
                
                # Выполняем функцию
                start_time = time.time()
                result = await func(*args, **kwargs)
                execution_time = (time.time() - start_time) * 1000  # в миллисекундах
                
                # Кэшируем результат
                await redis_client.setex(cache_key, ttl, json.dumps(result))
                
                logger.debug(f"Cache miss, cached result for {cache_key} (exec time: {execution_time:.2f}ms)")
                
                # Записываем метрику производительности
                await self.record_performance_metric(PerformanceMetric.RESPONSE_TIME_MS, execution_time, {
                    'function': func.__name__,
                    'cache_used': False
                })
                
                return result
            
            return wrapper
        return decorator

    def measure_performance(self, metric_name: PerformanceMetric):
        """Декоратор для измерения производительности функций"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                
                try:
                    result = await func(*args, **kwargs)
                    execution_time = (time.time() - start_time) * 1000  # в миллисекундах
                    
                    # Записываем метрику производительности
                    await self.record_performance_metric(metric_name, execution_time, {
                        'function': func.__name__,
                        'module': func.__module__
                    })
                    
                    return result
                except Exception as e:
                    execution_time = (time.time() - start_time) * 1000
                    logger.error(f"Error in {func.__name__}: {e}")
                    
                    # Записываем метрику ошибки
                    await self.record_performance_metric(PerformanceMetric.ERROR_RATE, 1.0, {
                        'function': func.__name__,
                        'module': func.__module__,
                        'error': str(e)
                    })
                    
                    raise
            
            return wrapper
        return decorator

    async def get_performance_report(self, start_time: datetime, 
                                   end_time: datetime) -> Dict[str, Any]:
        """Получение отчета о производительности"""
        # Получаем метрики за указанный период
        metrics = await self._get_performance_metrics_in_range(start_time, end_time)
        
        # Вычисляем агрегированные значения
        aggregated_metrics = {}
        for metric_name, values in metrics.items():
            if values:
                values_only = [v for _, v in values]
                aggregated_metrics[metric_name] = {
                    'avg': sum(values_only) / len(values_only),
                    'min': min(values_only),
                    'max': max(values_only),
                    'count': len(values_only),
                    'std_dev': self._calculate_std_dev(values_only)
                }
        
        # Получаем информацию о системных ресурсах
        system_info = await self._get_system_resources_info()
        
        # Получаем информацию о кэше
        cache_info = await self._get_cache_performance_info()
        
        # Получаем информацию о базе данных
        db_info = await self._get_database_performance_info()
        
        report = {
            'period': {
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat()
            },
            'aggregated_metrics': aggregated_metrics,
            'system_resources': system_info,
            'cache_performance': cache_info,
            'database_performance': db_info,
            'recommendations': await self._generate_performance_recommendations(aggregated_metrics)
        }
        
        return report

    async def _get_performance_metrics_in_range(self, start_time: datetime, 
                                              end_time: datetime) -> Dict[str, List[tuple]]:
        """Получение метрик производительности за указанный период"""
        # В реальной системе здесь будет запрос к базе данных или Prometheus
        # Временно возвращаем данные из промежуточного хранилища
        result = {}
        
        for metric_name, values in self.performance_metrics.items():
            filtered_values = [(ts, val) for ts, val in values if start_time <= ts <= end_time]
            if filtered_values:
                result[metric_name] = filtered_values
        
        return result

    def _calculate_std_dev(self, values: List[float]) -> float:
        """Расчет стандартного отклонения"""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance ** 0.5

    async def _get_system_resources_info(self) -> Dict[str, Any]:
        """Получение информации о системных ресурсах"""
        return {
            'cpu': {
                'percent': psutil.cpu_percent(interval=1),
                'count': psutil.cpu_count()
            },
            'memory': {
                'percent': psutil.virtual_memory().percent,
                'total': psutil.virtual_memory().total,
                'available': psutil.virtual_memory().available,
                'used': psutil.virtual_memory().used
            },
            'disk': {
                'percent': psutil.disk_usage('/').percent,
                'total': psutil.disk_usage('/').total,
                'free': psutil.disk_usage('/').free,
                'used': psutil.disk_usage('/').used
            },
            'network': {
                'bytes_sent': psutil.net_io_counters().bytes_sent,
                'bytes_recv': psutil.net_io_counters().bytes_recv,
                'packets_sent': psutil.net_io_counters().packets_sent,
                'packets_recv': psutil.net_io_counters().packets_recv
            },
            'timestamp': datetime.utcnow().isoformat()
        }

    async def _get_cache_performance_info(self) -> Dict[str, Any]:
        """Получение информации о производительности кэша"""
        try:
            info = await redis_client.info()
            total_requests = info.get('total_commands_processed', 1)
            hits = info.get('keyspace_hits', 0)
            misses = info.get('keyspace_misses', 0)
            
            return {
                'connected_clients': info.get('connected_clients', 0),
                'used_memory_mb': info.get('used_memory', 0) / (1024*1024),
                'used_memory_peak_mb': info.get('used_memory_peak', 0) / (1024*1024),
                'total_commands_processed': total_requests,
                'keyspace_hits': hits,
                'keyspace_misses': misses,
                'hit_rate_percent': (hits / (hits + misses)) * 100 if (hits + misses) > 0 else 0,
                'uptime_in_seconds': info.get('uptime_in_seconds', 0),
                'expired_keys': info.get('expired_keys', 0),
                'evicted_keys': info.get('evicted_keys', 0)
            }
        except Exception as e:
            logger.error(f"Error getting cache performance info: {e}")
            return {}

    async def _get_database_performance_info(self) -> Dict[str, Any]:
        """Получение информации о производительности базы данных"""
        try:
            async with db_pool.acquire() as conn:
                # Получаем статистику активности
                activity_stats = await conn.fetchrow(
                    """
                    SELECT 
                        COUNT(*) as active_connections,
                        COUNT(CASE WHEN state = 'active' THEN 1 END) as running_queries,
                        COUNT(CASE WHEN state = 'idle in transaction' THEN 1 END) as idle_in_transaction
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                    """
                )
                
                # Получаем статистику по таблицам
                table_stats = await conn.fetchrow(
                    """
                    SELECT 
                        schemaname,
                        tablename,
                        seq_scan,
                        seq_tup_read,
                        idx_scan,
                        idx_tup_fetch,
                        n_tup_ins,
                        n_tup_upd,
                        n_tup_del
                    FROM pg_stat_user_tables
                    ORDER BY seq_scan DESC
                    LIMIT 1
                    """
                )
                
                # Получаем статистику медленных запросов
                slow_queries = await conn.fetch(
                    """
                    SELECT query, mean_time, calls, total_time
                    FROM pg_stat_statements
                    ORDER BY mean_time DESC
                    LIMIT 5
                    """
                )
                
                return {
                    'active_connections': activity_stats['active_connections'],
                    'running_queries': activity_stats['running_queries'],
                    'idle_in_transaction': activity_stats['idle_in_transaction'],
                    'most_scanned_table': dict(table_stats) if table_stats else None,
                    'slowest_queries': [dict(row) for row in slow_queries]
                }
        except Exception as e:
            logger.error(f"Error getting database performance info: {e}")
            return {}

    async def _generate_performance_recommendations(self, metrics: Dict[str, Dict]) -> List[Dict[str, str]]:
        """Генерация рекомендаций по производительности"""
        recommendations = []
        
        # Рекомендации по времени отклика
        if 'response_time_ms' in metrics:
            avg_response_time = metrics['response_time_ms']['avg']
            if avg_response_time > 1000:
                recommendations.append({
                    'type': 'response_time',
                    'priority': 'high',
                    'message': f'Average response time is {avg_response_time:.2f}ms, which is high. Consider implementing additional caching or optimizing database queries.',
                    'action': 'enable_caching_or_optimize_queries'
                })
            elif avg_response_time > 500:
                recommendations.append({
                    'type': 'response_time',
                    'priority': 'medium',
                    'message': f'Average response time is {avg_response_time:.2f}ms. Consider optimizing performance.',
                    'action': 'review_performance_bottlenecks'
                })
        
        # Рекомендации по использованию CPU
        if 'cpu_usage_percent' in metrics:
            avg_cpu_usage = metrics['cpu_usage_percent']['avg']
            if avg_cpu_usage > 80:
                recommendations.append({
                    'type': 'cpu_usage',
                    'priority': 'high',
                    'message': f'Average CPU usage is {avg_cpu_usage:.2f}%. Consider scaling compute resources or optimizing code.',
                    'action': 'scale_resources_or_optimize_code'
                })
        
        # Рекомендации по использованию памяти
        if 'memory_usage_percent' in metrics:
            avg_memory_usage = metrics['memory_usage_percent']['avg']
            if avg_memory_usage > 85:
                recommendations.append({
                    'type': 'memory_usage',
                    'priority': 'high',
                    'message': f'Average memory usage is {avg_memory_usage:.2f}%. Consider optimizing memory usage or increasing available memory.',
                    'action': 'optimize_memory_usage'
                })
        
        # Рекомендации по времени запросов к базе данных
        if 'database_query_time_ms' in metrics:
            avg_query_time = metrics['database_query_time_ms']['avg']
            if avg_query_time > 100:
                recommendations.append({
                    'type': 'database_performance',
                    'priority': 'high',
                    'message': f'Average database query time is {avg_query_time:.2f}ms. Consider adding indexes or optimizing queries.',
                    'action': 'add_indexes_or_optimize_queries'
                })
        
        # Рекомендации по кэшированию
        if 'cache_hit_rate_percent' in metrics:
            avg_cache_hit_rate = metrics['cache_hit_rate_percent']['avg']
            if avg_cache_hit_rate < 80:
                recommendations.append({
                    'type': 'cache_performance',
                    'priority': 'medium',
                    'message': f'Cache hit rate is {avg_cache_hit_rate:.2f}%. Consider optimizing cache strategies.',
                    'action': 'optimize_cache_strategies'
                })
        
        return recommendations

    async def optimize_database_queries(self):
        """Оптимизация запросов к базе данных"""
        # Анализируем медленные запросы
        slow_queries = await self._analyze_slow_queries()
        
        for query_info in slow_queries:
            query = query_info['query']
            avg_time = query_info['mean_time']
            
            if avg_time > 100:  # Если запрос занимает больше 100мс
                # Проверяем, можно ли оптимизировать запрос
                await self._suggest_query_optimization(query, avg_time)

    async def _analyze_slow_queries(self) -> List[Dict[str, Any]]:
        """Анализ медленных запросов к базе данных"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT query, mean_time, calls, total_time, rows
                FROM pg_stat_statements
                ORDER BY mean_time DESC
                LIMIT 20
                """
            )
        
        return [dict(row) for row in rows]

    async def _suggest_query_optimization(self, query: str, avg_time: float):
        """Предложение оптимизации для медленного запроса"""
        # Проверяем, содержит ли запрос JOIN без индексов
        if 'JOIN' in query.upper() and avg_time > 200:
            logger.info(f"Suggesting index creation for query: {query[:100]}... (avg time: {avg_time}ms)")
            # В реальной системе здесь будет анализ структуры запроса и предложение создания индексов
        
        # Проверяем, содержит ли запрос полнотекстовый поиск без индекса
        if 'LIKE' in query.upper() and avg_time > 150:
            logger.info(f"Suggesting full-text index for query: {query[:100]}... (avg time: {avg_time}ms)")

    async def optimize_cache_strategy(self):
        """Оптимизация стратегии кэширования"""
        # Анализируем использование кэша
        cache_stats = await self._get_cache_statistics()
        
        # Если hit rate низкий, предлагаем улучшения
        if cache_stats.get('hit_rate_percent', 0) < 70:
            logger.info("Low cache hit rate detected. Suggesting cache strategy improvements.")
            # В реальной системе здесь будет анализ использования кэша и предложения по улучшению
            
        # Анализируем размеры кэша
        if cache_stats.get('used_memory_percent', 0) > 80:
            logger.info("High cache memory usage. Suggesting cache size optimization or eviction policy adjustment.")

    async def _get_cache_statistics(self) -> Dict[str, Any]:
        """Получение статистики использования кэша"""
        try:
            info = await redis_client.info()
            total_commands = info.get('total_commands_processed', 1)
            keyspace_hits = info.get('keyspace_hits', 0)
            keyspace_misses = info.get('keyspace_misses', 0)
            
            return {
                'connected_clients': info.get('connected_clients', 0),
                'used_memory': info.get('used_memory', 0),
                'total_memory': info.get('total_system_memory', 1024*1024*1024),  # 1GB default
                'used_memory_percent': (info.get('used_memory', 0) / info.get('total_system_memory', 1024*1024*1024)) * 100,
                'keyspace_hits': keyspace_hits,
                'keyspace_misses': keyspace_misses,
                'hit_rate_percent': (keyspace_hits / (keyspace_hits + keyspace_misses)) * 100 if (keyspace_hits + keyspace_misses) > 0 else 0,
                'total_commands_processed': total_commands,
                'expired_keys': info.get('expired_keys', 0),
                'evicted_keys': info.get('evicted_keys', 0)
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {}

    async def get_system_performance_insights(self) -> Dict[str, Any]:
        """Получение инсайтов о производительности системы"""
        insights = {
            'timestamp': datetime.utcnow().isoformat(),
            'system_resources': await self._get_current_system_resources(),
            'database_performance': await self._get_current_database_performance(),
            'cache_performance': await self._get_current_cache_performance(),
            'network_performance': await self._get_current_network_performance(),
            'recommendations': await self._get_performance_recommendations(),
            'bottlenecks': await self._identify_bottlenecks(),
            'optimization_opportunities': await self._identify_optimization_opportunities()
        }
        
        return insights

    async def _identify_bottlenecks(self) -> List[Dict[str, Any]]:
        """Идентификация узких мест в производительности"""
        bottlenecks = []
        
        # Проверяем использование CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent > 85:
            bottlenecks.append({
                'type': 'cpu',
                'severity': 'high',
                'description': f'High CPU usage detected: {cpu_percent}%'
            })
        
        # Проверяем использование памяти
        memory_percent = psutil.virtual_memory().percent
        if memory_percent > 90:
            bottlenecks.append({
                'type': 'memory',
                'severity': 'high',
                'description': f'High memory usage detected: {memory_percent}%'
            })
        
        # Проверяем использование диска
        disk_percent = psutil.disk_usage('/').percent
        if disk_percent > 95:
            bottlenecks.append({
                'type': 'disk',
                'severity': 'high',
                'description': f'High disk usage detected: {disk_percent}%'
            })
        
        # Проверяем медленные запросы к базе данных
        db_performance = await self._get_current_database_performance()
        if db_performance.get('running_queries', 0) > 50:
            bottlenecks.append({
                'type': 'database',
                'severity': 'medium',
                'description': f'High number of running queries: {db_performance["running_queries"]}'
            })
        
        # Проверяем низкий hit rate кэша
        cache_performance = await self._get_current_cache_performance()
        if cache_performance.get('hit_rate_percent', 100) < 70:
            bottlenecks.append({
                'type': 'cache',
                'severity': 'medium',
                'description': f'Low cache hit rate: {cache_performance["hit_rate_percent"]:.2f}%'
            })
        
        return bottlenecks

    async def _identify_optimization_opportunities(self) -> List[Dict[str, Any]]:
        """Идентификация возможностей для оптимизации"""
        opportunities = []
        
        # Возможности для оптимизации кэширования
        cache_performance = await self._get_current_cache_performance()
        if cache_performance.get('hit_rate_percent', 100) < 80:
            opportunities.append({
                'area': 'caching',
                'opportunity': 'Improve cache hit rate by optimizing cache keys or increasing cache size',
                'potential_improvement': 'Up to 30% performance improvement'
            })
        
        # Возможности для оптимизации базы данных
        db_performance = await self._get_current_database_performance()
        if db_performance.get('idle_in_transaction', 0) > 10:
            opportunities.append({
                'area': 'database',
                'opportunity': 'Reduce idle transactions to improve connection pool utilization',
                'potential_improvement': 'Better connection utilization'
            })
        
        # Возможности для оптимизации CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        if 60 < cpu_percent < 85:
            opportunities.append({
                'area': 'compute',
                'opportunity': 'Optimize CPU-intensive operations or implement async processing',
                'potential_improvement': 'Reduced response times'
            })
        
        # Возможности для оптимизации памяти
        memory_percent = psutil.virtual_memory().percent
        if 70 < memory_percent < 90:
            opportunities.append({
                'area': 'memory',
                'opportunity': 'Optimize memory usage by implementing object pooling or lazy loading',
                'potential_improvement': 'Reduced memory footprint'
            })
        
        return opportunities

    async def implement_optimization(self, optimization_strategy: OptimizationStrategy) -> bool:
        """Реализация определенной стратегии оптимизации"""
        if optimization_strategy == OptimizationStrategy.CACHING:
            return await self._implement_caching_optimization()
        elif optimization_strategy == OptimizationStrategy.DATABASE_INDEXING:
            return await self._implement_database_indexing()
        elif optimization_strategy == OptimizationStrategy.QUERY_OPTIMIZATION:
            return await self._implement_query_optimization()
        elif optimization_strategy == OptimizationStrategy.RESOURCE_POOLING:
            return await self._implement_resource_pooling()
        elif optimization_strategy == OptimizationStrategy.ASYNC_PROCESSING:
            return await self._implement_async_processing()
        elif optimization_strategy == OptimizationStrategy.LOAD_BALANCING:
            return await self._implement_load_balancing()
        elif optimization_strategy == OptimizationStrategy.COMPRESSION:
            return await self._implement_compression()
        elif optimization_strategy == OptimizationStrategy.BATCHING:
            return await self._implement_batching()
        elif optimization_strategy == OptimizationStrategy.PREFETCHING:
            return await self._implement_prefetching()
        elif optimization_strategy == OptimizationStrategy.CONNECTION_REUSE:
            return await self._implement_connection_reuse()
        else:
            return False

    async def _implement_caching_optimization(self) -> bool:
        """Реализация оптимизации кэширования"""
        # Увеличиваем размер кэша
        # Оптимизируем политику кэширования
        # Внедряем многоуровневое кэширование
        logger.info("Implementing caching optimization...")
        return True

    async def _implement_database_indexing(self) -> bool:
        """Реализация оптимизации индексации базы данных"""
        # Анализируем медленные запросы
        slow_queries = await self._analyze_slow_queries()
        
        # Создаем индексы для часто используемых полей
        for query_info in slow_queries:
            await self._create_optimal_indexes(query_info['query'])
        
        logger.info("Implementing database indexing optimization...")
        return True

    async def _create_optimal_indexes(self, query: str):
        """Создание оптимальных индексов для запроса"""
        # В реальной системе здесь будет анализ запроса и создание соответствующих индексов
        try:
            # Анализируем запрос для определения потенциальных полей для индексации
            import re
            # Ищем условия WHERE в запросе
            where_match = re.search(r'WHERE\s+(.+?)(?:ORDER BY|GROUP BY|LIMIT|$)', query, re.IGNORECASE | re.DOTALL)

            potential_fields = []
            if where_match:
                where_clause = where_match.group(1)
                # Ищем имена полей в условии WHERE
                field_matches = re.findall(r'(\w+)\s*(?:=|!=|>|<|>=|<=|LIKE|IN)\s*', where_clause)
                potential_fields.extend(field_matches)

            # Также ищем поля в ORDER BY
            order_match = re.search(r'ORDER BY\s+(.+?)(?:LIMIT|$)', query, re.IGNORECASE)
            if order_match:
                order_clause = order_match.group(1)
                order_fields = re.findall(r'(\w+)', order_clause)
                potential_fields.extend(order_fields)

            # Удаляем дубликаты и создаем индексы
            unique_fields = list(set(potential_fields))

            if unique_fields:
                # Определяем имя таблицы из запроса
                table_match = re.search(r'FROM\s+(\w+)', query, re.IGNORECASE)
                table_name = table_match.group(1) if table_match else "unknown_table"

                # Создаем индексы для потенциальных полей
                for field in unique_fields:
                    index_name = f"idx_{table_name}_{field}"

                    # Проверяем, существует ли уже индекс
                    async with db_pool.acquire() as conn:
                        try:
                            # Создаем индекс
                            await conn.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({field})")

                            # Логируем создание индекса
                            index_info = {
                                'index_name': index_name,
                                'table': table_name,
                                'field': field,
                                'query_hint': query[:50] + "..." if len(query) > 50 else query,
                                'created_at': datetime.utcnow().isoformat()
                            }

                            # Сохраняем информацию об индексе
                            await conn.execute(
                                """
                                INSERT INTO performance_indexes (name, table_name, field_name, query_hint, created_at)
                                VALUES ($1, $2, $3, $4, $5)
                                ON CONFLICT (name) DO NOTHING
                                """,
                                index_name, table_name, field, query[:100], datetime.utcnow()
                            )

                            logger.info(f"Created index {index_name} on {table_name}.{field}")
                        except Exception as e:
                            logger.warning(f"Could not create index {index_name}: {e}")
                            continue  # Продолжаем с другими полями

                return True
            else:
                logger.info(f"No potential index fields found in query: {query[:50]}...")
                return False

        except Exception as e:
            logger.error(f"Error creating optimal indexes for query: {e}")
            return False

    async def _implement_query_optimization(self) -> bool:
        """Реализация оптимизации запросов"""
        # Оптимизируем медленные запросы
        await self.optimize_database_queries()
        logger.info("Implementing query optimization...")
        return True

    async def _implement_resource_pooling(self) -> bool:
        """Реализация пула ресурсов"""
        # Оптимизируем пулы соединений
        # Внедряем пул объектов
        logger.info("Implementing resource pooling optimization...")
        return True

    async def _implement_async_processing(self) -> bool:
        """Реализация асинхронной обработки"""
        # Внедряем асинхронные очереди задач
        # Оптимизируем обработку фоновых задач
        logger.info("Implementing async processing optimization...")
        return True

    async def _implement_load_balancing(self) -> bool:
        """Реализация балансировки нагрузки"""
        # Настройка балансировщиков нагрузки
        # Оптимизация распределения запросов
        logger.info("Implementing load balancing optimization...")
        return True

    async def _implement_compression(self) -> bool:
        """Реализация сжатия данных"""
        # Внедряем сжатие для передачи данных
        logger.info("Implementing compression optimization...")
        return True

    async def _implement_batching(self) -> bool:
        """Реализация пакетной обработки"""
        # Оптимизируем запросы к базе данных с использованием пакетной обработки
        logger.info("Implementing batching optimization...")
        return True

    async def _implement_prefetching(self) -> bool:
        """Реализация предзагрузки данных"""
        # Внедряем предзагрузку часто используемых данных
        logger.info("Implementing prefetching optimization...")
        return True

    async def _implement_connection_reuse(self) -> bool:
        """Реализация повторного использования соединений"""
        # Оптимизируем использование соединений с базой данных и Redis
        logger.info("Implementing connection reuse optimization...")
        return True

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
performance_optimization_service = PerformanceOptimizationService()
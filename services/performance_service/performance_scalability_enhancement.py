# Performance and Scalability Enhancement System
# File: services/performance_service/performance_scalability_enhancement.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
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
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt
import seaborn as sns
from io import BytesIO
import base64

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class PerformanceMetric(Enum):
    RESPONSE_TIME_MS = "response_time_ms"
    THROUGHPUT_RPS = "throughput_rps"
    CPU_USAGE_PERCENT = "cpu_usage_percent"
    MEMORY_USAGE_PERCENT = "memory_usage_percent"
    DATABASE_QUERY_TIME_MS = "database_query_time_ms"
    CACHE_HIT_RATE = "cache_hit_rate"
    CONNECTION_POOL_UTILIZATION = "connection_pool_utilization"
    ERROR_RATE = "error_rate"
    LATENCY_MS = "latency_ms"
    THROUGHPUT_MBPS = "throughput_mbps"

class ScalabilityStrategy(Enum):
    HORIZONTAL_SCALING = "horizontal_scaling"
    VERTICAL_SCALING = "vertical_scaling"
    LOAD_BALANCING = "load_balancing"
    CACHING_STRATEGY = "caching_strategy"
    DATABASE_SHARDING = "database_sharding"
    MICROSERVICES_DEPLOYMENT = "microservices_deployment"
    CDN_IMPLEMENTATION = "cdn_implementation"
    ASYNC_PROCESSING = "async_processing"

class PerformanceOptimization(BaseModel):
    id: str
    name: str
    description: str
    strategy: ScalabilityStrategy
    impact: str  # 'low', 'medium', 'high', 'critical'
    implementation_complexity: str  # 'simple', 'moderate', 'complex'
    estimated_performance_gain: float  # Ожидаемое улучшение производительности в %
    is_implemented: bool = False
    implemented_at: Optional[datetime] = None
    created_at: datetime = None
    updated_at: datetime = None

class PerformanceMetricRecord(BaseModel):
    id: str
    metric_name: PerformanceMetric
    value: float
    timestamp: datetime = None
    tags: Optional[Dict[str, str]] = None  # Дополнительные теги для фильтрации

class PerformanceScalabilityService:
    def __init__(self):
        self.performance_metrics: Dict[str, List[tuple]] = {}  # metric_name -> [(timestamp, value)]
        self.scalability_strategies: List[PerformanceOptimization] = []
        self.optimization_thresholds = {
            'response_time_ms': 500,  # порог для оптимизации производительности
            'cpu_usage_percent': 80,
            'memory_usage_percent': 85,
            'database_query_time_ms': 100,
            'cache_hit_rate_percent': 80
        }
        self.scalability_thresholds = {
            'concurrent_users': 1000,
            'requests_per_second': 100,
            'memory_usage_percent': 85,
            'cpu_usage_percent': 80
        }
        self.ml_models = {}  # Модели машинного обучения для предсказания производительности

    async def initialize_scalability_strategies(self):
        """Инициализация стратегий масштабируемости"""
        default_strategies = [
            PerformanceOptimization(
                id="strategy_horizontal_scaling",
                name="Horizontal Scaling",
                description="Scale application horizontally by adding more instances",
                strategy=ScalabilityStrategy.HORIZONTAL_SCALING,
                impact="high",
                implementation_complexity="complex",
                estimated_performance_gain=200.0,  # 200% улучшение
                created_at=datetime.utcnow()
            ),
            PerformanceOptimization(
                id="strategy_load_balancing",
                name="Load Balancing",
                description="Implement load balancing to distribute traffic",
                strategy=ScalabilityStrategy.LOAD_BALANCING,
                impact="high",
                implementation_complexity="moderate",
                estimated_performance_gain=150.0,
                created_at=datetime.utcnow()
            ),
            PerformanceOptimization(
                id="strategy_caching_strategy",
                name="Caching Strategy",
                description="Implement multi-level caching to reduce database load",
                strategy=ScalabilityStrategy.CACHING_STRATEGY,
                impact="high",
                implementation_complexity="moderate",
                estimated_performance_gain=100.0,
                created_at=datetime.utcnow()
            ),
            PerformanceOptimization(
                id="strategy_database_sharding",
                name="Database Sharding",
                description="Shard database to improve query performance",
                strategy=ScalabilityStrategy.DATABASE_SHARDING,
                impact="critical",
                implementation_complexity="complex",
                estimated_performance_gain=300.0,
                created_at=datetime.utcnow()
            ),
            PerformanceOptimization(
                id="strategy_async_processing",
                name="Async Processing",
                description="Implement async processing for non-critical operations",
                strategy=ScalabilityStrategy.ASYNC_PROCESSING,
                impact="medium",
                implementation_complexity="moderate",
                estimated_performance_gain=75.0,
                created_at=datetime.utcnow()
            )
        ]

        for strategy in default_strategies:
            await self.add_scalability_strategy(strategy)

    async def add_scalability_strategy(self, strategy: PerformanceOptimization):
        """Добавление стратегии масштабируемости"""
        self.scalability_strategies.append(strategy)

        # Сохраняем стратегию в базу данных
        await self._save_scalability_strategy(strategy)

    async def _save_scalability_strategy(self, strategy: PerformanceOptimization):
        """Сохранение стратегии масштабируемости в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO scalability_strategies (
                    id, name, description, strategy, impact, implementation_complexity,
                    estimated_performance_gain, is_implemented, implemented_at, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                strategy.id, strategy.name, strategy.description, strategy.strategy.value,
                strategy.impact, strategy.implementation_complexity,
                strategy.estimated_performance_gain, strategy.is_implemented,
                strategy.implemented_at, strategy.created_at, strategy.updated_at
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

        # Проверяем, не нужно ли масштабировать систему
        await self._check_scalability_needed(metric_name, value)

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
        # Проверяем, превышает ли значение порог для оптимизации
        if metric_name == PerformanceMetric.RESPONSE_TIME_MS:
            if value > self.optimization_thresholds['response_time_ms']:
                await self._suggest_response_time_optimization()
        elif metric_name == PerformanceMetric.CPU_USAGE_PERCENT:
            if value > self.optimization_thresholds['cpu_usage_percent']:
                await self._suggest_cpu_optimization()
        elif metric_name == PerformanceMetric.MEMORY_USAGE_PERCENT:
            if value > self.optimization_thresholds['memory_usage_percent']:
                await self._suggest_memory_optimization()
        elif metric_name == PerformanceMetric.DATABASE_QUERY_TIME_MS:
            if value > self.optimization_thresholds['database_query_time_ms']:
                await self._suggest_database_optimization()
        elif metric_name == PerformanceMetric.CACHE_HIT_RATE:
            if value < self.optimization_thresholds['cache_hit_rate_percent']:
                await self._suggest_caching_optimization()

    async def _check_scalability_needed(self, metric_name: PerformanceMetric, value: float):
        """Проверка, требуется ли масштабирование на основе метрики"""
        # Проверяем, превышает ли значение порог для масштабирования
        if metric_name == PerformanceMetric.CONNECTION_POOL_UTILIZATION:
            if value > self.scalability_thresholds['connection_pool_utilization']:
                await self._suggest_horizontal_scaling()
        elif metric_name == PerformanceMetric.CPU_USAGE_PERCENT:
            if value > self.scalability_thresholds['cpu_usage_percent']:
                await self._suggest_vertical_scaling()
        elif metric_name == PerformanceMetric.MEMORY_USAGE_PERCENT:
            if value > self.scalability_thresholds['memory_usage_percent']:
                await self._suggest_memory_scaling()

    async def _suggest_response_time_optimization(self):
        """Предложение оптимизации времени отклика"""
        logger.info("Response time optimization suggested")
        # В реальной системе здесь будет более сложная логика
        # для определения причин медленного отклика и предложений по улучшению

    async def _suggest_cpu_optimization(self):
        """Предложение оптимизации использования CPU"""
        logger.info("CPU usage optimization suggested")
        # В реальной системе здесь будет анализ нагрузки на CPU
        # и предложения по оптимизации вычислительных операций

    async def _suggest_memory_optimization(self):
        """Предложение оптимизации использования памяти"""
        logger.info("Memory usage optimization suggested")
        # В реальной системе здесь будет анализ использования памяти
        # и предложения по оптимизации

    async def _suggest_database_optimization(self):
        """Предложение оптимизации базы данных"""
        logger.info("Database query optimization suggested")
        # В реальной системе здесь будет анализ медленных запросов
        # и предложения по оптимизации

    async def _suggest_caching_optimization(self):
        """Предложение оптимизации кэширования"""
        logger.info("Caching optimization suggested")
        # В реальной системе здесь будет анализ эффективности кэширования
        # и предложения по улучшению

    async def _suggest_horizontal_scaling(self):
        """Предложение горизонтального масштабирования"""
        logger.info("Horizontal scaling suggested")
        # В реальной системе здесь будет автоматическое масштабирование
        # через Kubernetes или другие средства оркестрации

    async def _suggest_vertical_scaling(self):
        """Предложение вертикального масштабирования"""
        logger.info("Vertical scaling suggested")
        # В реальной системе здесь будет увеличение ресурсов
        # для текущих инстансов

    async def _suggest_memory_scaling(self):
        """Предложение масштабирования памяти"""
        logger.info("Memory scaling suggested")
        # В реальной системе здесь будет увеличение доступной памяти

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
        
        # Рассчитываем агрегированные значения
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
            'recommendations': await self._generate_performance_recommendations(aggregated_metrics),
            'scalability_assessment': await self._assess_scalability_needs(aggregated_metrics)
        }
        
        return report

    async def _get_performance_metrics_in_range(self, start_time: datetime, 
                                              end_time: datetime) -> Dict[str, List[tuple]]:
        """Получение метрик производительности в диапазоне"""
        # В реальной системе это запросило бы базу данных или Prometheus
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
            total_commands = info.get('total_commands_processed', 1)
            keyspace_hits = info.get('keyspace_hits', 0)
            keyspace_misses = info.get('keyspace_misses', 0)
            
            return {
                'connected_clients': info.get('connected_clients', 0),
                'used_memory_mb': info.get('used_memory', 0) / (1024*1024),
                'used_memory_peak_mb': info.get('used_memory_peak', 0) / (1024*1024),
                'total_commands_processed': total_commands,
                'keyspace_hits': keyspace_hits,
                'keyspace_misses': keyspace_misses,
                'hit_rate_percent': (keyspace_hits / (keyspace_hits + keyspace_misses)) * 100 if (keyspace_hits + keyspace_misses) > 0 else 0,
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
                
                # Получаем статистику таблиц
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
                
                # Получаем медленные запросы
                slow_queries = await conn.fetch(
                    """
                    SELECT query, mean_time, calls, total_time
                    FROM pg_stat_statements
                    ORDER BY mean_time DESC
                    LIMIT 10
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
        
        # Рекомендации для времени отклика
        if 'response_time_ms' in metrics:
            avg_response_time = metrics['response_time_ms']['avg']
            if avg_response_time > 1000:
                recommendations.append({
                    'type': 'response_time',
                    'priority': 'high',
                    'message': f'Average response time is {avg_response_time:.2f}ms, which is high. Consider implementing additional caching or optimizing database queries.'
                })
            elif avg_response_time > 500:
                recommendations.append({
                    'type': 'response_time',
                    'priority': 'medium',
                    'message': f'Average response time is {avg_response_time:.2f}ms. Consider optimizing performance.'
                })
        
        # Рекомендации для использования CPU
        if 'cpu_usage_percent' in metrics:
            avg_cpu_usage = metrics['cpu_usage_percent']['avg']
            if avg_cpu_usage > 80:
                recommendations.append({
                    'type': 'cpu_usage',
                    'priority': 'high',
                    'message': f'Average CPU usage is {avg_cpu_usage:.2f}%. Consider scaling compute resources or optimizing code.'
                })
        
        # Рекомендации для использования памяти
        if 'memory_usage_percent' in metrics:
            avg_memory_usage = metrics['memory_usage_percent']['avg']
            if avg_memory_usage > 85:
                recommendations.append({
                    'type': 'memory_usage',
                    'priority': 'high',
                    'message': f'Average memory usage is {avg_memory_usage:.2f}%. Consider optimizing memory usage or increasing available memory.'
                })
        
        # Рекомендации для времени запросов к базе данных
        if 'database_query_time_ms' in metrics:
            avg_query_time = metrics['database_query_time_ms']['avg']
            if avg_query_time > 100:
                recommendations.append({
                    'type': 'database_performance',
                    'priority': 'high',
                    'message': f'Average database query time is {avg_query_time:.2f}ms. Consider adding indexes or optimizing queries.'
                })
        
        # Рекомендации для кэширования
        if 'cache_hit_rate_percent' in metrics:
            avg_cache_hit_rate = metrics['cache_hit_rate_percent']['avg']
            if avg_cache_hit_rate < 80:
                recommendations.append({
                    'type': 'cache_performance',
                    'priority': 'medium',
                    'message': f'Cache hit rate is {avg_cache_hit_rate:.2f}%. Consider optimizing cache strategies.'
                })
        
        return recommendations

    async def _assess_scalability_needs(self, metrics: Dict[str, Dict]) -> Dict[str, Any]:
        """Оценка потребностей в масштабировании"""
        assessment = {
            'current_load': {},
            'scalability_recommendations': [],
            'capacity_planning': {}
        }

        # Оценка текущей нагрузки
        if 'throughput_rps' in metrics:
            avg_throughput = metrics['throughput_rps']['avg']
            assessment['current_load']['requests_per_second'] = avg_throughput
            
            if avg_throughput > 100:
                assessment['scalability_recommendations'].append({
                    'strategy': 'horizontal_scaling',
                    'urgency': 'high',
                    'reason': f'Current throughput ({avg_throughput} RPS) approaching capacity limits'
                })
            elif avg_throughput > 50:
                assessment['scalability_recommendations'].append({
                    'strategy': 'load_balancing',
                    'urgency': 'medium',
                    'reason': f'Moderate throughput ({avg_throughput} RPS) - consider load distribution'
                })

        # Оценка использования памяти
        if 'memory_usage_percent' in metrics:
            avg_memory_usage = metrics['memory_usage_percent']['avg']
            assessment['current_load']['memory_usage_percent'] = avg_memory_usage
            
            if avg_memory_usage > 85:
                assessment['scalability_recommendations'].append({
                    'strategy': 'vertical_scaling',
                    'urgency': 'high',
                    'reason': f'High memory usage ({avg_memory_usage}%) - consider increasing memory allocation'
                })

        # Оценка использования CPU
        if 'cpu_usage_percent' in metrics:
            avg_cpu_usage = metrics['cpu_usage_percent']['avg']
            assessment['current_load']['cpu_usage_percent'] = avg_cpu_usage
            
            if avg_cpu_usage > 80:
                assessment['scalability_recommendations'].append({
                    'strategy': 'horizontal_scaling',
                    'urgency': 'high',
                    'reason': f'High CPU usage ({avg_cpu_usage}%) - consider distributing load across multiple instances'
                })

        # Планирование емкости
        current_time = datetime.utcnow()
        projected_growth = self._calculate_growth_projection(metrics)
        
        assessment['capacity_planning'] = {
            'current_capacity_utilization': self._calculate_current_utilization(metrics),
            'projected_growth_rate': projected_growth,
            'estimated_capacity_needs': self._estimate_future_capacity(metrics, projected_growth),
            'recommended_scaling_timeline': self._recommend_scaling_timeline(metrics)
        }

        return assessment

    def _calculate_growth_projection(self, metrics: Dict[str, Dict]) -> float:
        """Расчет прогноза роста"""
        # Простая реализация - в реальности потребуется более сложный анализ
        return 0.1  # 10% роста в месяц

    def _calculate_current_utilization(self, metrics: Dict[str, Dict]) -> Dict[str, float]:
        """Расчет текущей загрузки системы"""
        utilization = {}
        
        if 'cpu_usage_percent' in metrics:
            utilization['cpu'] = metrics['cpu_usage_percent']['avg'] / 100
        if 'memory_usage_percent' in metrics:
            utilization['memory'] = metrics['memory_usage_percent']['avg'] / 100
        if 'connection_pool_utilization' in metrics:
            utilization['connections'] = metrics['connection_pool_utilization']['avg'] / 100
        if 'throughput_rps' in metrics:
            # Предполагаем максимальную пропускную способность 1000 RPS
            utilization['throughput'] = min(metrics['throughput_rps']['avg'] / 1000, 1.0)
        
        return utilization

    def _estimate_future_capacity(self, metrics: Dict[str, Dict], growth_rate: float) -> Dict[str, float]:
        """Оценка будущих потребностей в мощности"""
        current_utilization = self._calculate_current_utilization(metrics)
        future_utilization = {}
        
        for resource, current_usage in current_utilization.items():
            future_usage = current_usage * (1 + growth_rate)
            future_utilization[resource] = min(future_usage, 1.0)  # Ограничиваем 100%
        
        return future_utilization

    def _recommend_scaling_timeline(self, metrics: Dict[str, Dict]) -> Dict[str, str]:
        """Рекомендация сроков масштабирования"""
        timeline = {}
        
        current_utilization = self._calculate_current_utilization(metrics)
        
        for resource, usage in current_utilization.items():
            if usage > 0.8:  # > 80%
                timeline[resource] = "immediate"  # Нужно масштабировать немедленно
            elif usage > 0.6:  # > 60%
                timeline[resource] = "short_term"  # Нужно масштабировать в ближайшие 2-4 недели
            elif usage > 0.4:  # > 40%
                timeline[resource] = "medium_term"  # Нужно масштабировать в течение 1-3 месяцев
            else:
                timeline[resource] = "long_term"  # Масштабирование не требуется в ближайшее время
        
        return timeline

    async def optimize_database_performance(self):
        """Оптимизация производительности базы данных"""
        # Анализируем медленные запросы
        slow_queries = await self._analyze_slow_queries()
        
        for query_info in slow_queries:
            query = query_info['query']
            avg_time = query_info['mean_time']
            
            if avg_time > 100:  # Если запрос занимает более 100мс
                # Проверяем, можно ли оптимизировать запрос
                await self._suggest_query_optimization(query, avg_time)

        # Оптимизируем индексы
        await self._optimize_database_indexes()

        # Проверяем использование соединений
        await self._analyze_connection_pool_usage()

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
            # В реальной системе это проанализировало бы структуру запроса и предложило создание индексов
        
        # Проверяем, содержит ли запрос полнотекстовый поиск без индекса
        if 'LIKE' in query.upper() and avg_time > 150:
            logger.info(f"Suggesting full-text index for query: {query[:100]}... (avg time: {avg_time}ms)")

    async def _optimize_database_indexes(self):
        """Оптимизация индексов базы данных"""
        # Анализируем использование индексов
        async with db_pool.acquire() as conn:
            index_stats = await conn.fetch(
                """
                SELECT schemaname, tablename, indexname, 
                       idx_scan, idx_tup_read, idx_tup_fetch
                FROM pg_stat_user_indexes
                ORDER BY idx_scan ASC  -- Мало используемые индексы
                LIMIT 10
                """
            )
        
        unused_indexes = []
        for row in index_stats:
            if row['idx_scan'] < 100:  # Если индекс используется менее 100 раз
                unused_indexes.append({
                    'schema': row['schemaname'],
                    'table': row['tablename'],
                    'index': row['indexname'],
                    'scans': row['idx_scan']
                })
        
        if unused_indexes:
            logger.info(f"Found {len(unused_indexes)} potentially unused indexes that could be removed")
            # В реальной системе здесь будет анализ необходимости этих индексов и возможное удаление

        # Также анализируем таблицы с высоким количеством seq scans
        table_stats = await self._analyze_table_statistics()
        for table_stat in table_stats:
            if table_stat['seq_scan'] > 1000 and table_stat['idx_scan'] < table_stat['seq_scan'] * 0.1:
                # Если последовательных сканирований намного больше, чем сканирований индексов
                logger.info(f"Suggesting new indexes for table {table_stat['tablename']}")

    async def _analyze_table_statistics(self) -> List[Dict[str, Any]]:
        """Анализ статистики таблиц базы данных"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT schemaname, tablename, 
                       seq_scan, seq_tup_read, 
                       idx_scan, idx_tup_fetch,
                       n_tup_ins, n_tup_upd, n_tup_del
                FROM pg_stat_user_tables
                ORDER BY seq_scan DESC
                LIMIT 20
                """
            )
        
        return [dict(row) for row in rows]

    async def _analyze_connection_pool_usage(self):
        """Анализ использования пула соединений"""
        async with db_pool.acquire() as conn:
            # Получаем статистику активности
            activity_stats = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total_connections,
                    COUNT(CASE WHEN state = 'active' THEN 1 END) as active_connections,
                    COUNT(CASE WHEN state = 'idle' THEN 1 END) as idle_connections,
                    COUNT(CASE WHEN state = 'idle in transaction' THEN 1 END) as idle_in_transaction
                FROM pg_stat_activity
                WHERE datname = current_database()
                """
            )
        
        total_connections = activity_stats['total_connections']
        active_connections = activity_stats['active_connections']
        utilization_rate = active_connections / total_connections if total_connections > 0 else 0
        
        if utilization_rate > 0.8:
            logger.info(f"High connection pool utilization: {utilization_rate:.2%}")
            # Рекомендуем увеличить размер пула
        elif utilization_rate < 0.2:
            logger.info(f"Low connection pool utilization: {utilization_rate:.2%}")
            # Рекомендуем уменьшить размер пула для экономии ресурсов

    async def implement_scalability_strategy(self, strategy_id: str) -> bool:
        """Реализация стратегии масштабируемости"""
        # Получаем стратегию из базы данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM scalability_strategies WHERE id = $1",
                strategy_id
            )

        if not row:
            return False

        strategy = PerformanceOptimization(
            id=row['id'],
            name=row['name'],
            description=row['description'],
            strategy=ScalabilityStrategy(row['strategy']),
            impact=row['impact'],
            implementation_complexity=row['implementation_complexity'],
            estimated_performance_gain=row['estimated_performance_gain'],
            is_implemented=row['is_implemented'],
            implemented_at=row['implemented_at'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

        # Проверяем, не реализована ли уже стратегия
        if strategy.is_implemented:
            return True

        success = False

        # Выполняем стратегию в зависимости от типа
        if strategy.strategy == ScalabilityStrategy.HORIZONTAL_SCALING:
            success = await self._implement_horizontal_scaling(strategy)
        elif strategy.strategy == ScalabilityStrategy.VERTICAL_SCALING:
            success = await self._implement_vertical_scaling(strategy)
        elif strategy.strategy == ScalabilityStrategy.LOAD_BALANCING:
            success = await self._implement_load_balancing(strategy)
        elif strategy.strategy == ScalabilityStrategy.CACHING_STRATEGY:
            success = await self._implement_caching_strategy(strategy)
        elif strategy.strategy == ScalabilityStrategy.DATABASE_SHARDING:
            success = await self._implement_database_sharding(strategy)
        elif strategy.strategy == ScalabilityStrategy.MICROSERVICES_DEPLOYMENT:
            success = await self._implement_microservices_deployment(strategy)
        elif strategy.strategy == ScalabilityStrategy.CDN_IMPLEMENTATION:
            success = await self._implement_cdn_strategy(strategy)
        elif strategy.strategy == ScalabilityStrategy.ASYNC_PROCESSING:
            success = await self._implement_async_processing_strategy(strategy)

        if success:
            # Обновляем статус стратегии
            strategy.is_implemented = True
            strategy.implemented_at = datetime.utcnow()
            strategy.updated_at = datetime.utcnow()

            await self._update_scalability_strategy(strategy)

        return success

    async def _implement_horizontal_scaling(self, strategy: PerformanceOptimization) -> bool:
        """Реализация горизонтального масштабирования"""
        logger.info("Implementing horizontal scaling strategy...")
        # В реальной системе это привело бы к запуску дополнительных инстансов
        # через Kubernetes или другие средства оркестрации
        return True

    async def _implement_vertical_scaling(self, strategy: PerformanceOptimization) -> bool:
        """Реализация вертикального масштабирования"""
        logger.info("Implementing vertical scaling strategy...")
        # В реальной системе это привело бы к увеличению ресурсов для текущих инстансов
        return True

    async def _implement_load_balancing(self, strategy: PerformanceOptimization) -> bool:
        """Реализация балансировки нагрузки"""
        logger.info("Implementing load balancing strategy...")
        # В реальной системе это привело бы к настройке балансировщика нагрузки
        return True

    async def _implement_caching_strategy(self, strategy: PerformanceOptimization) -> bool:
        """Реализация стратегии кэширования"""
        logger.info("Implementing caching strategy...")
        # В реальной системе это привело бы к настройке многоуровневого кэширования
        return True

    async def _implement_database_sharding(self, strategy: PerformanceOptimization) -> bool:
        """Реализация шардинга базы данных"""
        logger.info("Implementing database sharding strategy...")
        # В реальной системе это привело бы к разделению базы данных на шарды
        return True

    async def _implement_microservices_deployment(self, strategy: PerformanceOptimization) -> bool:
        """Реализация развертывания микросервисов"""
        logger.info("Implementing microservices deployment strategy...")
        # В реальной системе это привело бы к разбиению монолита на микросервисы
        return True

    async def _implement_cdn_strategy(self, strategy: PerformanceOptimization) -> bool:
        """Реализация CDN стратегии"""
        logger.info("Implementing CDN strategy...")
        # В реальной системе это привело бы к настройке CDN для статических ресурсов
        return True

    async def _implement_async_processing_strategy(self, strategy: PerformanceOptimization) -> bool:
        """Реализация асинхронной обработки"""
        logger.info("Implementing async processing strategy...")
        # В реальной системе это привело бы к внедрению очередей задач
        return True

    async def _update_scalability_strategy(self, strategy: PerformanceOptimization):
        """Обновление стратегии масштабируемости в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE scalability_strategies SET
                    is_implemented = $2, implemented_at = $3, updated_at = $4
                WHERE id = $1
                """,
                strategy.id, strategy.is_implemented, strategy.implemented_at, strategy.updated_at
            )

    async def get_scalability_recommendations(self) -> List[Dict[str, Any]]:
        """Получение рекомендаций по масштабируемости"""
        # Получаем текущие метрики производительности
        current_time = datetime.utcnow()
        week_ago = current_time - timedelta(days=7)
        
        metrics = await self._get_performance_metrics_in_range(week_ago, current_time)
        aggregated_metrics = {}
        
        for metric_name, values in metrics.items():
            if values:
                values_only = [v for _, v in values]
                aggregated_metrics[metric_name] = {
                    'avg': sum(values_only) / len(values_only),
                    'min': min(values_only),
                    'max': max(values_only),
                    'count': len(values_only)
                }

        # Оцениваем потребности в масштабировании
        assessment = await self._assess_scalability_needs(aggregated_metrics)

        recommendations = []
        
        # Добавляем рекомендации из оценки
        for rec in assessment['scalability_recommendations']:
            recommendations.append({
                'strategy': rec['strategy'],
                'urgency': rec['urgency'],
                'reason': rec['reason'],
                'estimated_benefit': self._get_estimated_benefit(rec['strategy'])
            })

        # Добавляем рекомендации на основе текущих показателей
        current_cpu_avg = aggregated_metrics.get('cpu_usage_percent', {}).get('avg', 0)
        if current_cpu_avg > 75:
            recommendations.append({
                'strategy': 'horizontal_scaling',
                'urgency': 'high',
                'reason': 'High average CPU usage detected',
                'estimated_benefit': 150
            })

        current_memory_avg = aggregated_metrics.get('memory_usage_percent', {}).get('avg', 0)
        if current_memory_avg > 80:
            recommendations.append({
                'strategy': 'vertical_scaling',
                'urgency': 'high',
                'reason': 'High average memory usage detected',
                'estimated_benefit': 100
            })

        return recommendations

    def _get_estimated_benefit(self, strategy: str) -> float:
        """Получение оценки выгоды от стратегии"""
        benefits = {
            'horizontal_scaling': 200,
            'vertical_scaling': 100,
            'load_balancing': 150,
            'caching_strategy': 100,
            'database_sharding': 300,
            'microservices_deployment': 250,
            'cdn_implementation': 120,
            'async_processing': 75
        }
        return benefits.get(strategy, 50)

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
performance_scalability_service = PerformanceScalabilityService()
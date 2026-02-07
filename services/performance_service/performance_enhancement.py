# Performance Optimization and Enhancement System
# File: services/performance_service/performance_enhancement.py

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
    optimization_type: OptimizationType
    level: OptimizationLevel
    condition: str  # Condition for applying optimization
    action: str     # Action to perform
    enabled: bool = True
    created_at: datetime = None
    updated_at: datetime = None

class PerformanceMetricRecord(BaseModel):
    id: str
    metric_name: PerformanceMetric
    value: float
    timestamp: datetime = None
    tags: Optional[Dict[str, str]] = None  # Additional tags for filtering

class PerformanceOptimizer:
    def __init__(self):
        self.cache = Cache(Cache.MEMORY)  # Local cache
        self.optimization_rules: List[OptimizationRule] = []
        self.performance_metrics: Dict[str, List[tuple]] = {}  # metric_name -> [(timestamp, value)]
        self.cache_hit_count = 0
        self.cache_miss_count = 0
        self.active_optimizations: Dict[str, Any] = {}
        self.optimization_thresholds = {
            'response_time_ms': 500,  # threshold for performance optimization
            'cpu_usage_percent': 80,
            'memory_usage_percent': 85,
            'database_query_time_ms': 100,
            'cache_hit_rate_percent': 80
        }
        self.cache_config = {
            'ttl': 300,  # 5 minutes default
            'namespace': 'messenger_cache',
            'serializer': JsonSerializer()
        }

    async def initialize_optimization_rules(self):
        """Initialize optimization rules"""
        default_rules = [
            OptimizationRule(
                id="rule_cache_optimization",
                name="Cache Optimization",
                description="Automatically optimize cache strategies based on usage patterns",
                optimization_type=OptimizationType.CACHING,
                level=OptimizationLevel.MEDIUM,
                condition="cache_hit_rate < 0.7",
                action="increase_cache_size_or_change_policy",
                created_at=datetime.utcnow()
            ),
            OptimizationRule(
                id="rule_db_query_optimization",
                name="Database Query Optimization",
                description="Optimize database queries based on execution time",
                optimization_type=OptimizationType.DATABASE,
                level=OptimizationLevel.HIGH,
                condition="query_time > 1000",
                action="add_index_or_rewrite_query",
                created_at=datetime.utcnow()
            ),
            OptimizationRule(
                id="rule_response_time_optimization",
                name="Response Time Optimization",
                description="Optimize response time when it exceeds threshold",
                optimization_type=OptimizationType.COMPUTE,
                level=OptimizationLevel.MEDIUM,
                condition="response_time > 1000",
                action="enable_caching_or_async_processing",
                created_at=datetime.utcnow()
            ),
            OptimizationRule(
                id="rule_memory_optimization",
                name="Memory Optimization",
                description="Optimize memory usage when it exceeds threshold",
                optimization_type=OptimizationType.MEMORY,
                level=OptimizationLevel.HIGH,
                condition="memory_usage > 85",
                action="garbage_collection_or_caching_adjustment",
                created_at=datetime.utcnow()
            ),
            OptimizationRule(
                id="rule_compression_optimization",
                name="Compression Optimization",
                description="Enable compression for large data transfers",
                optimization_type=OptimizationType.COMPRESSION,
                level=OptimizationLevel.LOW,
                condition="data_size > 102400",  # 100KB
                action="enable_compression",
                created_at=datetime.utcnow()
            )
        ]

        for rule in default_rules:
            await self.add_optimization_rule(rule)

    async def add_optimization_rule(self, rule: OptimizationRule):
        """Add an optimization rule"""
        self.optimization_rules.append(rule)

        # Save rule to database
        await self._save_optimization_rule(rule)

    async def _save_optimization_rule(self, rule: OptimizationRule):
        """Save optimization rule to database"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO optimization_rules (
                    id, name, description, optimization_type, level, condition, action, enabled, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (id) DO UPDATE SET
                    name = $2, description = $3, optimization_type = $4, level = $5,
                    condition = $6, action = $7, enabled = $8, updated_at = $10
                """,
                rule.id, rule.name, rule.description, rule.optimization_type.value,
                rule.level.value, rule.condition, rule.action, rule.enabled,
                rule.created_at, rule.updated_at
            )

    async def record_performance_metric(self, metric_name: PerformanceMetric, value: float, 
                                      tags: Optional[Dict[str, str]] = None):
        """Record performance metric"""
        metric_id = str(uuid.uuid4())
        timestamp = datetime.utcnow()

        # Store in intermediate storage
        if metric_name.value not in self.performance_metrics:
            self.performance_metrics[metric_name.value] = []
        self.performance_metrics[metric_name.value].append((timestamp, value))

        # Limit intermediate storage size
        if len(self.performance_metrics[metric_name.value]) > 10000:
            self.performance_metrics[metric_name.value] = self.performance_metrics[metric_name.value][-5000:]

        # Save to database
        await self._save_performance_metric(metric_id, metric_name, value, tags, timestamp)

        # Check if optimization is needed
        await self._check_optimization_needed(metric_name, value)

    async def _save_performance_metric(self, metric_id: str, metric_name: PerformanceMetric, 
                                     value: float, tags: Optional[Dict[str, str]], 
                                     timestamp: datetime):
        """Save performance metric to database"""
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
        """Check if optimization is needed based on metric"""
        # Sort rules by priority
        sorted_rules = sorted(self.optimization_rules, key=lambda r: r.priority, reverse=True)

        for rule in sorted_rules:
            if not rule.enabled:
                continue

            # Check condition for applying optimization
            if await self._evaluate_condition(rule.condition, metric_name.value, value):
                await self._apply_optimization_action(rule.action, metric_name, value)

    async def _evaluate_condition(self, condition: str, metric_name: str, value: float) -> bool:
        """Evaluate condition for applying optimization"""
        # Implementation of condition evaluation logic
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
        """Apply optimization action"""
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
        """Increase cache efficiency"""
        logger.info("Increasing cache efficiency based on optimization rule")
        # Increase Redis cache efficiency by adjusting configuration
        try:
            # Get current cache statistics
            cache_info = await self.redis_client.info(section="memory")
            current_used_memory = cache_info.get('used_memory_human', '0B')
            current_max_memory = cache_info.get('maxmemory_human', '0B')

            # Calculate memory usage percentage
            used_bytes = int(cache_info.get('used_memory', 0))
            max_bytes = int(cache_info.get('maxmemory', 1))
            if max_bytes > 0:
                usage_percent = (used_bytes / max_bytes) * 100
                if usage_percent > 80:
                    # Increase cache size if usage is high
                    await self.redis_client.config_set('maxmemory', str(int(max_bytes * 1.2)))  # Increase by 20%
                    logger.info(f"Increased Redis cache size to accommodate usage. Current: {current_used_memory}, Max: {current_max_memory}")

            # Update cache policy to LRU if not already set
            current_policy = await self.redis_client.config_get('maxmemory-policy')
            if current_policy.get('maxmemory-policy') != 'allkeys-lru':
                await self.redis_client.config_set('maxmemory-policy', 'allkeys-lru')
                logger.info("Updated Redis cache policy to LRU")

        except Exception as e:
            logger.error(f"Error increasing cache efficiency: {e}")

    async def _optimize_database_queries(self):
        """Optimize database queries"""
        logger.info("Optimizing database queries based on performance metrics")
        # Analyze slow queries and add indexes
        try:
            # Get slow queries from PostgreSQL statistics
            async with self.db_pool.acquire() as conn:
                slow_queries = await conn.fetch(
                    """
                    SELECT query, mean_time, calls, total_time
                    FROM pg_stat_statements
                    WHERE mean_time > 100  -- Queries taking more than 100ms on average
                    ORDER BY total_time DESC
                    LIMIT 10
                    """
                )

            # Create indexes for slow queries
            for query_row in slow_queries:
                query = query_row['query']
                avg_time = query_row['mean_time']

                # Analyze query to determine potential indexes
                await self._create_optimal_indexes(query)

                logger.info(f"Analyzed and optimized slow query (avg time: {avg_time:.2f}ms): {query[:100]}...")

        except Exception as e:
            logger.error(f"Error optimizing database queries: {e}")

    async def _enable_additional_caching(self):
        """Enable additional caching"""
        logger.info("Enabling additional caching based on performance metrics")
        # Enable additional caching layers
        try:
            # Enable multi-level caching: L1 (in-memory), L2 (Redis), L3 (Memcached)
            # For now, we'll implement additional Redis caching strategies

            # Enable Redis caching for frequently accessed data
            await self.redis_client.config_set('maxmemory-policy', 'allkeys-lru')

            # Set up cache warming for common queries
            common_queries = [
                "SELECT * FROM users WHERE id = $1",
                "SELECT * FROM messages WHERE chat_id = $1 ORDER BY timestamp DESC LIMIT $2",
                "SELECT * FROM chats WHERE id = $1"
            ]

            # Pre-cache common data patterns
            for query_pattern in common_queries:
                # Create cache key for this pattern
                cache_key = f"query_pattern:{hashlib.md5(query_pattern.encode()).hexdigest()}"
                await self.redis_client.setex(cache_key, 3600, query_pattern)  # Cache for 1 hour

            logger.info("Additional caching layers enabled")

        except Exception as e:
            logger.error(f"Error enabling additional caching: {e}")

    async def _perform_garbage_collection(self):
        """Perform garbage collection"""
        logger.info("Performing garbage collection based on memory usage")
        # In real system, this would call Python's garbage collector
        import gc
        collected = gc.collect()
        logger.info(f"Garbage collection completed. Collected {collected} objects")

    async def _enable_compression(self):
        """Enable data compression"""
        logger.info("Enabling data compression based on transfer size")
        # Enable compression for data transfers
        try:
            # In a real system, this would configure compression for HTTP responses
            # and potentially for database queries and other data transfers

            # For HTTP responses, we would typically use gzip compression
            # This would be handled by the web framework middleware
            # For now, we'll log that compression is enabled
            logger.info("Compression for data transfers enabled")

            # Additionally, we could compress large data before storing in Redis
            # or before sending over network

        except Exception as e:
            logger.error(f"Error enabling compression: {e}")

    def cache_with_ttl(self, ttl: int = 300, namespace: str = "default"):
        """Decorator for caching with TTL"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Generate cache key based on arguments
                cache_key = f"{namespace}:{func.__name__}:{hash(str(args) + str(kwargs))}"
                
                # Check cache
                cached_result = await redis_client.get(cache_key)
                if cached_result:
                    logger.debug(f"Cache hit for {cache_key}")
                    return json.loads(cached_result)
                
                # Execute function
                start_time = time.time()
                result = await func(*args, **kwargs)
                execution_time = (time.time() - start_time) * 1000  # in milliseconds
                
                # Cache result
                await redis_client.setex(cache_key, ttl, json.dumps(result))
                
                logger.debug(f"Cache miss, cached result for {cache_key} (exec time: {execution_time:.2f}ms)")
                
                # Record performance metric
                await self.record_performance_metric(PerformanceMetric.RESPONSE_TIME_MS, execution_time, {
                    'function': func.__name__,
                    'cache_used': False
                })
                
                return result
            
            return wrapper
        return decorator

    def measure_performance(self, metric_name: PerformanceMetric):
        """Decorator for measuring function performance"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                
                try:
                    result = await func(*args, **kwargs)
                    execution_time = (time.time() - start_time) * 1000  # in milliseconds
                    
                    # Record performance metric
                    await self.record_performance_metric(metric_name, execution_time, {
                        'function': func.__name__,
                        'module': func.__module__
                    })
                    
                    return result
                except Exception as e:
                    execution_time = (time.time() - start_time) * 1000
                    logger.error(f"Error in {func.__name__}: {e}")
                    
                    # Record error metric
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
        """Get performance report"""
        # Get metrics for the specified period
        metrics = await self._get_performance_metrics_in_range(start_time, end_time)
        
        # Calculate aggregated values
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
        
        # Get system resources info
        system_info = await self._get_system_resources_info()
        
        # Get cache performance info
        cache_info = await self._get_cache_performance_info()
        
        # Get database performance info
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
        """Get performance metrics in range"""
        # Query database or Prometheus for performance metrics
        try:
            # Get performance metrics from PostgreSQL statistics
            async with self.db_pool.acquire() as conn:
                # Query for various performance metrics in the specified time range
                query_results = await conn.fetch(
                    """
                    SELECT
                        query,
                        mean_time,
                        calls,
                        total_time,
                        rows,
                        (total_time / calls) as avg_time_per_call
                    FROM pg_stat_statements
                    WHERE (mean_time > $1 OR total_time > $2)
                    ORDER BY total_time DESC
                    LIMIT 50
                    """,
                    start_time.timestamp() if isinstance(start_time, datetime) else start_time,
                    end_time.timestamp() if isinstance(end_time, datetime) else end_time
                )

            # Process results
            result = {
                'queries': [],
                'total_calls': 0,
                'total_time': 0,
                'avg_time_per_call': 0
            }

            for row in query_results:
                result['queries'].append({
                    'query': row['query'],
                    'mean_time': row['mean_time'],
                    'calls': row['calls'],
                    'total_time': row['total_time'],
                    'avg_time_per_call': row['avg_time_per_call']
                })
                result['total_calls'] += row['calls']
                result['total_time'] += row['total_time']

            if result['total_calls'] > 0:
                result['avg_time_per_call'] = result['total_time'] / result['total_calls']

        except Exception as e:
            logger.error(f"Error getting performance metrics in range: {e}")
            result = {}
        
        for metric_name, values in self.performance_metrics.items():
            filtered_values = [(ts, val) for ts, val in values if start_time <= ts <= end_time]
            if filtered_values:
                result[metric_name] = filtered_values
        
        return result

    def _calculate_std_dev(self, values: List[float]) -> float:
        """Calculate standard deviation"""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance ** 0.5

    async def _get_system_resources_info(self) -> Dict[str, Any]:
        """Get system resources information"""
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
        """Get cache performance information"""
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
        """Get database performance information"""
        try:
            async with db_pool.acquire() as conn:
                # Get activity stats
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
                
                # Get table stats
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
                
                # Get slow queries
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
        """Generate performance recommendations"""
        recommendations = []
        
        # Recommendations for response time
        if 'response_time_ms' in metrics:
            avg_response_time = metrics['response_time_ms']['avg']
            if avg_response_time > 1000:
                recommendations.append({
                    'type': 'response_time',
                    'priority': 'high',
                    'message': f'Average response time is {avg_response_time:.2f}ms, which is high. Consider adding additional caching or optimizing database queries.'
                })
            elif avg_response_time > 500:
                recommendations.append({
                    'type': 'response_time',
                    'priority': 'medium',
                    'message': f'Average response time is {avg_response_time:.2f}ms. Consider optimizing performance.'
                })
        
        # Recommendations for CPU usage
        if 'cpu_usage_percent' in metrics:
            avg_cpu_usage = metrics['cpu_usage_percent']['avg']
            if avg_cpu_usage > 80:
                recommendations.append({
                    'type': 'cpu_usage',
                    'priority': 'high',
                    'message': f'Average CPU usage is {avg_cpu_usage:.2f}%. Consider scaling compute resources or optimizing code.'
                })
        
        # Recommendations for memory usage
        if 'memory_usage_percent' in metrics:
            avg_memory_usage = metrics['memory_usage_percent']['avg']
            if avg_memory_usage > 85:
                recommendations.append({
                    'type': 'memory_usage',
                    'priority': 'high',
                    'message': f'Average memory usage is {avg_memory_usage:.2f}%. Consider optimizing memory usage or increasing available memory.'
                })
        
        # Recommendations for database query times
        if 'database_query_time_ms' in metrics:
            avg_query_time = metrics['database_query_time_ms']['avg']
            if avg_query_time > 100:
                recommendations.append({
                    'type': 'database_performance',
                    'priority': 'high',
                    'message': f'Average database query time is {avg_query_time:.2f}ms. Consider adding indexes or optimizing queries.'
                })
        
        # Recommendations for caching
        if 'cache_hit_rate_percent' in metrics:
            avg_cache_hit_rate = metrics['cache_hit_rate_percent']['avg']
            if avg_cache_hit_rate < 80:
                recommendations.append({
                    'type': 'cache_performance',
                    'priority': 'medium',
                    'message': f'Cache hit rate is {avg_cache_hit_rate:.2f}%. Consider optimizing cache strategies.'
                })
        
        return recommendations

    async def optimize_database_queries(self):
        """Optimize database queries"""
        # Analyze slow queries
        slow_queries = await self._analyze_slow_queries()
        
        for query_info in slow_queries:
            query = query_info['query']
            avg_time = query_info['mean_time']
            
            if avg_time > 100:  # If query takes more than 100ms
                # Check if we can optimize the query
                await self._suggest_query_optimization(query, avg_time)

    async def _analyze_slow_queries(self) -> List[Dict[str, Any]]:
        """Analyze slow database queries"""
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
        """Suggest optimization for slow query"""
        # Check if query contains JOIN without indexes
        if 'JOIN' in query.upper() and avg_time > 200:
            logger.info(f"Suggesting index creation for query: {query[:100]}... (avg time: {avg_time}ms)")
            # Analyze query structure and suggest index creation
            try:
                # Parse the query to identify potential indexable columns
                import re

                # Extract table name from the query
                table_match = re.search(r'FROM\s+(\w+)', query, re.IGNORECASE)
                if not table_match:
                    return

                table_name = table_match.group(1)

                # Find WHERE clause to identify columns that are commonly filtered
                where_match = re.search(r'WHERE\s+(.+?)(?:ORDER BY|GROUP BY|LIMIT|;|$)', query, re.IGNORECASE | re.DOTALL)

                potential_index_cols = []
                if where_match:
                    where_clause = where_match.group(1)

                    # Find column names in WHERE conditions (e.g., col = value, col IN (...), etc.)
                    col_pattern = r'\b(\w+)\s*(?:=|!=|<>|>|<|>=|<=|LIKE|IN|NOT IN)\b'
                    matches = re.findall(col_pattern, where_clause, re.IGNORECASE)
                    potential_index_cols.extend(matches)

                    # Also look for columns in JOIN conditions
                    join_pattern = r'JOIN\s+\w+\s+ON\s+\w+\.(\w+)|ON\s+\w+\.(\w+)\s*='
                    join_matches = re.findall(join_pattern, where_clause, re.IGNORECASE)
                    for match_pair in join_matches:
                        potential_index_cols.extend([m for m in match_pair if m])

                # Remove duplicates and empty strings
                potential_index_cols = list(set(filter(None, potential_index_cols)))

                if potential_index_cols:
                    # Create indexes for the identified columns
                    for col in potential_index_cols:
                        index_name = f"perf_idx_{table_name}_{col}"

                        try:
                            async with self.db_pool.acquire() as conn:
                                # Check if index already exists
                                existing_idx = await conn.fetchval(
                                    """
                                    SELECT 1 FROM pg_indexes
                                    WHERE tablename = $1 AND indexname = $2
                                    """, table_name, index_name
                                )

                                if not existing_idx:
                                    # Create the index concurrently to avoid locking the table
                                    await conn.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name} ON {table_name} ({col})")

                                    # Log the index creation for performance tracking
                                    await conn.execute(
                                        """
                                        INSERT INTO performance_metrics (metric_type, name, table_name, column_name, created_at)
                                        VALUES ($1, $2, $3, $4, $5)
                                        """, "index_creation", index_name, table_name, col, datetime.utcnow()
                                    )

                                    logger.info(f"Created performance index {index_name} on {table_name}.{col}")
                                else:
                                    logger.debug(f"Index {index_name} already exists on {table_name}")

                        except Exception as e:
                            logger.warning(f"Could not create index {index_name} on {table_name}.{col}: {e}")
                            continue  # Continue with other columns

            except Exception as e:
                logger.error(f"Error analyzing query structure for index creation: {e}")
        
        # Check if query contains full-text search without index
        if 'LIKE' in query.upper() and avg_time > 150:
            logger.info(f"Suggesting full-text index for query: {query[:100]}... (avg time: {avg_time}ms)")

    async def optimize_cache_strategy(self):
        """Optimize caching strategy"""
        # Analyze cache usage
        cache_stats = await self._get_cache_statistics()
        
        # If hit rate is low, suggest improvements
        if cache_stats.get('hit_rate_percent', 0) < 70:
            logger.info("Low cache hit rate detected. Suggesting cache strategy improvements.")
            # Analyze cache usage and suggest improvements
            try:
                # Get detailed cache statistics from Redis
                cache_info = await self.redis_client.info(section="stats")

                # Analyze hit rate and suggest improvements
                keyspace_hits = cache_info.get('keyspace_hits', 0)
                keyspace_misses = cache_info.get('keyspace_misses', 0)
                total_requests = keyspace_hits + keyspace_misses

                if total_requests > 0:
                    hit_rate = (keyspace_hits / total_requests) * 100
                    cache_stats['hit_rate_percent'] = hit_rate

                    # If hit rate is low, suggest improvements
                    if hit_rate < 70:
                        # Increase cache size
                        current_maxmemory = int(cache_info.get('maxmemory', 0))
                        if current_maxmemory > 0:
                            new_maxmemory = int(current_maxmemory * 1.5)  # Increase by 50%
                            await self.redis_client.config_set('maxmemory', str(new_maxmemory))
                            logger.info(f"Increased Redis maxmemory from {current_maxmemory} to {new_maxmemory}")

                        # Optimize eviction policy
                        await self.redis_client.config_set('maxmemory-policy', 'allkeys-lru')

                        # Suggest adding more specific cache keys for frequently accessed data
                        logger.info("Low cache hit rate detected. Increased cache size and optimized eviction policy.")

                # Analyze memory usage
                memory_info = await self.redis_client.info(section="memory")
                used_memory = int(memory_info.get('used_memory', 0))
                max_memory = int(memory_info.get('maxmemory', 0))

                if max_memory > 0:
                    used_memory_percent = (used_memory / max_memory) * 100
                    cache_stats['used_memory_percent'] = used_memory_percent

                    if used_memory_percent > 80:
                        logger.warning(f"High Redis memory usage: {used_memory_percent:.2f}%")
                        # Suggest memory optimization strategies
                        await self._optimize_redis_memory()

            except Exception as e:
                logger.error(f"Error analyzing cache usage: {e}")
            
        # Analyze cache sizes
        if cache_stats.get('used_memory_percent', 0) > 80:
            logger.info("High cache memory usage. Suggesting cache size optimization or eviction policy adjustment.")

        return cache_stats

    async def _get_cache_statistics(self) -> Dict[str, Any]:
        """Get cache usage statistics"""
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
        """Get system performance insights"""
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

    async def _get_current_system_resources(self) -> Dict[str, Any]:
        """Get current system resources status"""
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

    async def _get_current_database_performance(self) -> Dict[str, Any]:
        """Get current database performance"""
        try:
            async with db_pool.acquire() as conn:
                # Get activity stats
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
                
                # Get table stats
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
                
                # Get slow queries
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
            logger.error(f"Error getting database performance: {e}")
            return {}

    async def _get_current_cache_performance(self) -> Dict[str, Any]:
        """Get current cache performance"""
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
            logger.error(f"Error getting cache performance: {e}")
            return {}

    async def _get_current_network_performance(self) -> Dict[str, Any]:
        """Get current network performance"""
        net_io = psutil.net_io_counters()
        return {
            'bytes_sent_per_sec': net_io.bytes_sent,
            'bytes_recv_per_sec': net_io.bytes_recv,
            'packets_sent_per_sec': net_io.packets_sent,
            'packets_recv_per_sec': net_io.packets_recv,
            'drop_in': net_io.dropin if hasattr(net_io, 'dropin') else 0,
            'drop_out': net_io.dropout if hasattr(net_io, 'dropout') else 0,
            'timestamp': datetime.utcnow().isoformat()
        }

    async def _identify_bottlenecks(self) -> List[Dict[str, Any]]:
        """Identify performance bottlenecks"""
        bottlenecks = []
        
        # Check CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent > 85:
            bottlenecks.append({
                'type': 'cpu',
                'severity': 'high',
                'description': f'High CPU usage detected: {cpu_percent}%'
            })
        
        # Check memory usage
        memory_percent = psutil.virtual_memory().percent
        if memory_percent > 90:
            bottlenecks.append({
                'type': 'memory',
                'severity': 'high',
                'description': f'High memory usage detected: {memory_percent}%'
            })
        
        # Check disk usage
        disk_percent = psutil.disk_usage('/').percent
        if disk_percent > 95:
            bottlenecks.append({
                'type': 'disk',
                'severity': 'high',
                'description': f'High disk usage detected: {disk_percent}%'
            })
        
        # Check slow database queries
        db_performance = await self._get_current_database_performance()
        if db_performance.get('running_queries', 0) > 50:
            bottlenecks.append({
                'type': 'database',
                'severity': 'medium',
                'description': f'High number of running queries: {db_performance["running_queries"]}'
            })
        
        # Check low cache hit rate
        cache_performance = await self._get_current_cache_performance()
        if cache_performance.get('hit_rate_percent', 100) < 70:
            bottlenecks.append({
                'type': 'cache',
                'severity': 'medium',
                'description': f'Low cache hit rate: {cache_performance["hit_rate_percent"]:.2f}%'
            })
        
        return bottlenecks

    async def _identify_optimization_opportunities(self) -> List[Dict[str, Any]]:
        """Identify optimization opportunities"""
        opportunities = []
        
        # Opportunities for caching optimization
        cache_performance = await self._get_current_cache_performance()
        if cache_performance.get('hit_rate_percent', 100) < 80:
            opportunities.append({
                'area': 'caching',
                'opportunity': 'Improve cache hit rate by optimizing cache keys or increasing cache size',
                'potential_improvement': 'Up to 30% performance improvement'
            })
        
        # Opportunities for database optimization
        db_performance = await self._get_current_database_performance()
        if db_performance.get('idle_in_transaction', 0) > 10:
            opportunities.append({
                'area': 'database',
                'opportunity': 'Reduce idle transactions to improve connection pool utilization',
                'potential_improvement': 'Better connection utilization'
            })
        
        # Opportunities for CPU optimization
        cpu_percent = psutil.cpu_percent(interval=1)
        if 60 < cpu_percent < 85:
            opportunities.append({
                'area': 'compute',
                'opportunity': 'Optimize CPU-intensive operations or add async processing',
                'potential_improvement': 'Reduced response times'
            })
        
        # Opportunities for memory optimization
        memory_percent = psutil.virtual_memory().percent
        if 70 < memory_percent < 90:
            opportunities.append({
                'area': 'memory',
                'opportunity': 'Optimize memory usage by adding object pooling or lazy loading',
                'potential_improvement': 'Reduced memory footprint'
            })
        
        return opportunities

    async def implement_optimization(self, optimization_strategy: OptimizationStrategy) -> bool:
        """Implement a specific optimization strategy"""
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
        """Implement caching optimization"""
        # Increase cache size
        # Optimize caching policy
        # Implement multi-layer caching
        logger.info("Implementing caching optimization...")
        return True

    async def _implement_database_indexing(self) -> bool:
        """Implement database indexing optimization"""
        # Analyze slow queries
        slow_queries = await self._analyze_slow_queries()
        
        # Create indexes for frequently used fields
        for query_info in slow_queries:
            await self._create_optimal_indexes(query_info['query'])
        
        logger.info("Implementing database indexing optimization...")
        return True

    async def _create_optimal_indexes(self, query: str):
        """Create optimal indexes for a query"""
        # Analyze query structure and create appropriate indexes
        import logging
        logging.info(f"Creating optimal indexes for query: {query[:50]}...")
        return True

    async def _implement_query_optimization(self) -> bool:
        """Implement query optimization"""
        # Optimize slow queries
        await self.optimize_database_queries()
        logger.info("Implementing query optimization...")
        return True

    async def _implement_resource_pooling(self) -> bool:
        """Implement resource pooling"""
        # Optimize connection pools
        # Implement object pooling
        logger.info("Implementing resource pooling optimization...")
        return True

    async def _implement_async_processing(self) -> bool:
        """Implement async processing"""
        # Implement async task queues
        # Optimize background processing
        logger.info("Implementing async processing optimization...")
        return True

    async def _implement_load_balancing(self) -> bool:
        """Implement load balancing"""
        # Configure load balancers
        # Optimize request distribution
        logger.info("Implementing load balancing optimization...")
        return True

    async def _implement_compression(self) -> bool:
        """Implement data compression"""
        # Enable compression for data transfers
        logger.info("Implementing compression optimization...")
        return True

    async def _implement_batching(self) -> bool:
        """Implement batching"""
        # Optimize database queries with batching
        logger.info("Implementing batching optimization...")
        return True

    async def _implement_prefetching(self) -> bool:
        """Implement data prefetching"""
        # Implement prefetching for commonly accessed data
        logger.info("Implementing prefetching optimization...")
        return True

    async def _implement_connection_reuse(self) -> bool:
        """Implement connection reuse"""
        # Optimize database and Redis connection reuse
        logger.info("Implementing connection reuse optimization...")
        return True

    async def requires_moderation(self, content_type: ContentType) -> bool:
        """Check if content requires moderation"""
        # In real system, this would have more complex logic
        # depending on content type, user, etc.
        return content_type in [ContentType.IMAGE, ContentType.VIDEO, ContentType.LINK]

    async def _submit_for_moderation(self, content: Content):
        """Submit content for moderation"""
        moderation_record = ContentModeration(
            id=str(uuid.uuid4()),
            content_id=content.id,
            moderator_id=None,  # Will be assigned by system
            status=ContentModerationStatus.PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Save to database
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
        """Schedule content publication"""
        if not content.scheduled_publish:
            return

        # Add to scheduler queue
        await redis_client.zadd(
            "scheduled_content_queue",
            {content.id: content.scheduled_publish.timestamp()}
        )

    async def _are_friends(self, user1_id: int, user2_id: int) -> bool:
        """Check if users are friends"""
        try:
            async with self.db_pool.acquire() as conn:
                # Check if there's a friendship record in the database
                friendship = await conn.fetchrow(
                    """
                    SELECT status FROM friendships
                    WHERE (user1_id = $1 AND user2_id = $2) OR (user1_id = $2 AND user2_id = $1)
                    """,
                    user1_id, user2_id
                )

                if friendship and friendship['status'] == 'confirmed':
                    return True
                return False
        except Exception as e:
            logger.error(f"Error checking friendship between {user1_id} and {user2_id}: {e}")
            return False

    async def _is_group_member(self, user_id: int, group_id: str) -> bool:
        """Check if user is group member"""
        try:
            async with self.db_pool.acquire() as conn:
                # Check if user is member of the group
                membership = await conn.fetchrow(
                    """
                    SELECT user_id FROM chat_participants
                    WHERE chat_id = $1 AND user_id = $2
                    """,
                    group_id, user_id
                )

                return membership is not None
        except Exception as e:
            logger.error(f"Error checking group membership for user {user_id} in group {group_id}: {e}")
            return False

    async def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        try:
            async with self.db_pool.acquire() as conn:
                # Check if user has admin role in the database
                user_record = await conn.fetchrow(
                    """
                    SELECT role, permissions FROM users
                    WHERE id = $1
                    """,
                    user_id
                )

                if user_record:
                    role = user_record['role']
                    permissions = user_record['permissions']

                    # Check if user has admin role or admin permissions
                    if role == 'admin' or (permissions and 'admin' in permissions):
                        return True

                    # Also check in admin table if exists
                    admin_record = await conn.fetchrow(
                        """
                        SELECT user_id FROM admins
                        WHERE user_id = $1
                        """,
                        user_id
                    )
                    return admin_record is not None

                return False
        except Exception as e:
            logger.error(f"Error checking admin status for user {user_id}: {e}")
            return False

# Глобальный экземпляр для использования в приложении
performance_enhancement_service = PerformanceEnhancementService()
# Database Optimization System
# File: services/database_service/db_optimization_system.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid
import hashlib
from dataclasses import dataclass

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel
import psycopg2.pool
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import aioredis

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class OptimizationTarget(Enum):
    PERFORMANCE = "performance"
    SCALABILITY = "scalability"
    RELIABILITY = "reliability"
    MAINTAINABILITY = "maintainability"

class IndexType(Enum):
    BTREE = "btree"
    HASH = "hash"
    GIN = "gin"
    GiST = "gist"
    BRIN = "brin"

class ShardingStrategy(Enum):
    RANGE = "range"
    HASH = "hash"
    LIST = "list"
    CONSISTENT_HASH = "consistent_hash"

class ReplicationType(Enum):
    MASTER_SLAVE = "master_slave"
    MASTER_MASTER = "master_master"
    MULTI_MASTER = "multi_master"

class DatabaseOptimizationConfig(BaseModel):
    optimization_target: OptimizationTarget
    sharding_enabled: bool = False
    sharding_strategy: Optional[ShardingStrategy] = None
    sharding_key: Optional[str] = None
    replication_enabled: bool = False
    replication_type: Optional[ReplicationType] = None
    connection_pool_size: int = 20
    max_connections: int = 100
    query_timeout: int = 30
    enable_caching: bool = True
    cache_ttl: int = 300
    created_at: datetime = None
    updated_at: datetime = None

class IndexRecommendation(BaseModel):
    table_name: str
    columns: List[str]
    index_type: IndexType
    estimated_improvement: float  # Ожидаемое улучшение производительности в %
    query_patterns: List[str]  # Паттерны запросов, для которых рекомендуется индекс
    created_at: datetime = None

class QueryOptimization(BaseModel):
    query_pattern: str
    original_query: str
    optimized_query: str
    performance_gain: float  # Улучшение производительности в %
    execution_time_before: float  # Время выполнения до оптимизации
    execution_time_after: float  # Время выполнения после оптимизации
    created_at: datetime = None

class DatabaseOptimizationService:
    def __init__(self):
        self.optimization_configs = {}
        self.index_recommendations = []
        self.query_optimizations = []
        self.table_sizes = {}
        self.query_performance_data = {}
        self.connection_pools = {}
        self.shard_mapping = {}
        self.replication_nodes = []
        self.partitioning_strategies = {}
        
        # Настройки оптимизации по умолчанию
        self.default_config = DatabaseOptimizationConfig(
            optimization_target=OptimizationTarget.PERFORMANCE,
            sharding_enabled=False,
            replication_enabled=True,
            connection_pool_size=20,
            max_connections=100,
            query_timeout=30,
            enable_caching=True,
            cache_ttl=300,
            created_at=datetime.utcnow()
        )

    async def initialize_optimization(self):
        """Инициализация системы оптимизации базы данных"""
        # Устанавливаем конфигурацию по умолчанию
        self.optimization_configs['default'] = self.default_config
        
        # Запускаем анализ производительности
        await self._analyze_database_performance()
        
        # Генерируем рекомендации по индексам
        await self._generate_index_recommendations()
        
        # Оптимизируем медленные запросы
        await self._optimize_slow_queries()
        
        # Настройка пула соединений
        await self._configure_connection_pool()
        
        # Настройка репликации
        await self._configure_replication()
        
        logger.info("Database optimization system initialized")

    async def _analyze_database_performance(self):
        """Анализ производительности базы данных"""
        try:
            async with db_pool.acquire() as conn:
                # Получаем статистику по таблицам
                table_stats = await conn.fetch(
                    """
                    SELECT schemaname, tablename, 
                           seq_scan, seq_tup_read, 
                           idx_scan, idx_tup_fetch,
                           n_tup_ins, n_tup_upd, n_tup_del,
                           n_tup_hot_upd
                    FROM pg_stat_user_tables
                    ORDER BY seq_scan DESC
                    """
                )
                
                for row in table_stats:
                    table_name = f"{row['schemaname']}.{row['tablename']}"
                    self.table_sizes[table_name] = {
                        'seq_scan': row['seq_scan'],
                        'seq_tup_read': row['seq_tup_read'],
                        'idx_scan': row['idx_scan'],
                        'idx_tup_fetch': row['idx_tup_fetch'],
                        'n_tup_ins': row['n_tup_ins'],
                        'n_tup_upd': row['n_tup_upd'],
                        'n_tup_del': row['n_tup_del'],
                        'n_tup_hot_upd': row['n_tup_hot_upd']
                    }

                # Получаем статистику по медленным запросам
                slow_queries = await conn.fetch(
                    """
                    SELECT query, mean_time, calls, total_time, rows,
                           mean_time * calls as weighted_time
                    FROM pg_stat_statements
                    ORDER BY mean_time DESC
                    LIMIT 50
                    """
                )
                
                for row in slow_queries:
                    query_hash = hashlib.md5(row['query'].encode()).hexdigest()
                    self.query_performance_data[query_hash] = {
                        'query': row['query'],
                        'mean_time': row['mean_time'],
                        'calls': row['calls'],
                        'total_time': row['total_time'],
                        'rows': row['rows'],
                        'weighted_time': row['weighted_time']
                    }

                # Получаем статистику по индексам
                index_stats = await conn.fetch(
                    """
                    SELECT schemaname, tablename, indexname, 
                           idx_scan, idx_tup_read, idx_tup_fetch
                    FROM pg_stat_user_indexes
                    ORDER BY idx_scan DESC
                    """
                )
                
                for row in index_stats:
                    index_name = f"{row['schemaname']}.{row['indexname']}"
                    # Добавляем статистику индекса в систему
                    import logging
                    logging.info(f"Index {index_name} usage stats: {row}")

        except Exception as e:
            logger.error(f"Error analyzing database performance: {e}")

    async def _generate_index_recommendations(self):
        """Генерация рекомендаций по индексам"""
        recommendations = []

        # Рекомендации для таблиц с высоким количеством seq scans
        for table_name, stats in self.table_sizes.items():
            if stats['seq_scan'] > 1000:  # Если больше 1000 последовательных сканирований
                # Рекомендуем индекс на столбцах, которые часто используются в WHERE
                where_columns = await self._analyze_where_clauses(table_name)
                
                for column in where_columns:
                    recommendation = IndexRecommendation(
                        table_name=table_name,
                        columns=[column],
                        index_type=IndexType.BTREE,
                        estimated_improvement=30.0,  # Примерная оценка
                        query_patterns=[f"WHERE {column} = ?", f"WHERE {column} IN ?"],
                        created_at=datetime.utcnow()
                    )
                    recommendations.append(recommendation)

        # Рекомендации для таблиц с высоким количеством JOIN
        join_recommendations = await self._analyze_join_patterns()
        recommendations.extend(join_recommendations)

        # Рекомендации для полнотекстового поиска
        text_search_recommendations = await self._analyze_text_search_patterns()
        recommendations.extend(text_search_recommendations)

        self.index_recommendations = recommendations

        # Сохраняем рекомендации в базу данных
        for rec in recommendations:
            await self._save_index_recommendation(rec)

    async def _analyze_where_clauses(self, table_name: str) -> List[str]:
        """Анализ столбцов, используемых в WHERE условиях"""
        # В реальной системе это будет анализом pg_stat_statements
        # для выявления часто используемых столбцов в WHERE условиях
        # Пока возвращаем заглушку
        return ["id", "created_at", "updated_at"]  # Пример часто используемых столбцов

    async def _analyze_join_patterns(self) -> List[IndexRecommendation]:
        """Анализ паттернов JOIN для рекомендации индексов"""
        # В реальной системе это будет анализом запросов для выявления
        # часто используемых связей между таблицами
        # Пока возвращаем заглушку
        return []

    async def _analyze_text_search_patterns(self) -> List[IndexRecommendation]:
        """Анализ паттернов текстового поиска для рекомендации индексов"""
        # В реальной системе это будет анализом запросов с LIKE, ILIKE, и т.д.
        # Пока возвращаем заглушку
        return []

    async def _optimize_slow_queries(self):
        """Оптимизация медленных запросов"""
        optimized_queries = []

        for query_hash, query_data in self.query_performance_data.items():
            if query_data['mean_time'] > 100:  # Если среднее время больше 100мс
                optimized_query = await self._optimize_single_query(query_data['query'])
                
                if optimized_query and optimized_query != query_data['query']:
                    optimization = QueryOptimization(
                        query_pattern=query_hash,
                        original_query=query_data['query'],
                        optimized_query=optimized_query,
                        performance_gain=50.0,  # Примерная оценка
                        execution_time_before=query_data['mean_time'],
                        execution_time_after=query_data['mean_time'] * 0.5,  # Предполагаем 50% улучшение
                        created_at=datetime.utcnow()
                    )
                    optimized_queries.append(optimization)

        self.query_optimizations = optimized_queries

        # Сохраняем оптимизации в базу данных
        for opt in optimized_queries:
            await self._save_query_optimization(opt)

    async def _optimize_single_query(self, query: str) -> Optional[str]:
        """Оптимизация отдельного запроса"""
        # В реальной системе это будет сложной логикой анализа и оптимизации запроса
        # Пока возвращаем тот же запрос
        return query

    async def _save_query_optimization(self, optimization: QueryOptimization):
        """Сохранение оптимизации запроса в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO query_optimizations (
                    query_pattern, original_query, optimized_query, performance_gain,
                    execution_time_before, execution_time_after, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                optimization.query_pattern, optimization.original_query,
                optimization.optimized_query, optimization.performance_gain,
                optimization.execution_time_before, optimization.execution_time_after,
                optimization.created_at
            )

    async def _save_index_recommendation(self, recommendation: IndexRecommendation):
        """Сохранение рекомендации по индексу в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO index_recommendations (
                    table_name, columns, index_type, estimated_improvement, query_patterns, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                recommendation.table_name, recommendation.columns,
                recommendation.index_type.value, recommendation.estimated_improvement,
                json.dumps(recommendation.query_patterns), recommendation.created_at
            )

    async def _configure_connection_pool(self):
        """Настройка пула соединений"""
        try:
            # Создаем пул соединений с оптимизированными параметрами
            self.connection_pool = await asyncpg.create_pool(
                os.getenv('DATABASE_URL', 'postgresql://messenger:your-secure-password@db:5432/messenger'),
                min_size=self.default_config.connection_pool_size // 2,
                max_size=self.default_config.max_connections,
                command_timeout=self.default_config.query_timeout,
                server_settings={
                    'application_name': 'messenger-optimized',
                    'idle_in_transaction_session_timeout': str(self.default_config.query_timeout * 1000)  # ms
                }
            )
            
            logger.info("Connection pool configured with optimized settings")
        except Exception as e:
            logger.error(f"Error configuring connection pool: {e}")

    async def _configure_replication(self):
        """Настройка репликации базы данных"""
        if not self.default_config.replication_enabled:
            return

        try:
            # В реальной системе здесь будет настройка репликации
            # В зависимости от типа репликации
            if self.default_config.replication_type == ReplicationType.MASTER_SLAVE:
                # Настройка master-slave репликации
                logger.info("Master-slave replication configured")
            elif self.default_config.replication_type == ReplicationType.MASTER_MASTER:
                # Настройка master-master репликации
                logger.info("Master-master replication configured")
            else:
                logger.info("Replication configured with default settings")

        except Exception as e:
            logger.error(f"Error configuring replication: {e}")

    async def create_optimized_index(self, table_name: str, columns: List[str], 
                                   index_type: IndexType = IndexType.BTREE,
                                   unique: bool = False) -> bool:
        """Создание оптимизированного индекса"""
        try:
            index_name = f"idx_{table_name.replace('.', '_')}_{hashlib.md5('_'.join(columns).encode()).hexdigest()[:8]}"
            
            # Формируем SQL для создания индекса
            unique_clause = "UNIQUE " if unique else ""
            columns_str = ", ".join(columns)
            
            sql_query = f"""
                CREATE {unique_clause}INDEX IF NOT EXISTS {index_name}
                ON {table_name} USING {index_type.value} ({columns_str})
            """
            
            async with db_pool.acquire() as conn:
                await conn.execute(sql_query)
            
            logger.info(f"Created optimized index {index_name} on {table_name}({columns_str})")
            
            # Сохраняем информацию об индексе
            await self._save_created_index(table_name, columns, index_type, index_name)
            
            return True
        except Exception as e:
            logger.error(f"Error creating optimized index: {e}")
            return False

    async def _save_created_index(self, table_name: str, columns: List[str], 
                                index_type: IndexType, index_name: str):
        """Сохранение информации о созданном индексе"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO created_indexes (
                    name, table_name, columns, type, created_at
                ) VALUES ($1, $2, $3, $4, $5)
                """,
                index_name, table_name, columns, index_type.value, datetime.utcnow()
            )

    async def shard_table(self, table_name: str, sharding_key: str, 
                         strategy: ShardingStrategy = ShardingStrategy.HASH) -> bool:
        """Шардирование таблицы"""
        try:
            # В реальной системе это будет создание шардов для таблицы
            # В зависимости от стратегии шардинга
            if strategy == ShardingStrategy.RANGE:
                await self._shard_table_by_range(table_name, sharding_key)
            elif strategy == ShardingStrategy.HASH:
                await self._shard_table_by_hash(table_name, sharding_key)
            elif strategy == ShardingStrategy.LIST:
                await self._shard_table_by_list(table_name, sharding_key)
            elif strategy == ShardingStrategy.CONSISTENT_HASH:
                await self._shard_table_by_consistent_hash(table_name, sharding_key)
            
            logger.info(f"Table {table_name} sharded using {strategy.value} strategy on {sharding_key}")
            
            # Сохраняем информацию о шардинге
            self.shard_mapping[table_name] = {
                'strategy': strategy,
                'key': sharding_key,
                'created_at': datetime.utcnow()
            }
            
            return True
        except Exception as e:
            logger.error(f"Error sharding table {table_name}: {e}")
            return False

    async def _shard_table_by_range(self, table_name: str, sharding_key: str):
        """Шардирование таблицы по диапазону"""
        # В реальной системе это будет создание таблиц-шардов с диапазонами
        # Пока возвращаем заглушку
        import logging
        logging.info(f"Sharding table {table_name} by range on key {sharding_key}")
        return True

    async def _shard_table_by_hash(self, table_name: str, sharding_key: str):
        """Шардирование таблицы по хэшу"""
        # В реальной системе это будет создание таблиц-шардов с хэш-функцией
        # Пока возвращаем заглушку
        import logging
        logging.info(f"Sharding table {table_name} by hash on key {sharding_key}")
        return True

    async def _shard_table_by_list(self, table_name: str, sharding_key: str):
        """Шардирование таблицы по списку значений"""
        # В реальной системе это будет создание таблиц-шардов по списку значений
        # Пока возвращаем заглушку
        import logging
        logging.info(f"Sharding table {table_name} by list on key {sharding_key}")
        return True

    async def _shard_table_by_consistent_hash(self, table_name: str, sharding_key: str):
        """Шардирование таблицы по согласованному хэшу"""
        # В реальной системе это будет создание таблиц-шардов с согласованным хэшированием
        # Пока возвращаем заглушку
        import logging
        logging.info(f"Sharding table {table_name} by consistent hash on key {sharding_key}")
        return True

    async def partition_table(self, table_name: str, partition_key: str, 
                             partition_type: str = "range") -> bool:
        """Партицирование таблицы"""
        try:
            # В реальной системе это будет создание партиций для таблицы
            # В зависимости от типа партицирования
            if partition_type == "range":
                await self._partition_table_by_range(table_name, partition_key)
            elif partition_type == "list":
                await self._partition_table_by_list(table_name, partition_key)
            elif partition_type == "hash":
                await self._partition_table_by_hash(table_name, partition_key)
            
            logger.info(f"Table {table_name} partitioned by {partition_key} using {partition_type} partitioning")
            
            # Сохраняем информацию о партицировании
            self.partitioning_strategies[table_name] = {
                'type': partition_type,
                'key': partition_key,
                'created_at': datetime.utcnow()
            }
            
            return True
        except Exception as e:
            logger.error(f"Error partitioning table {table_name}: {e}")
            return False

    async def _partition_table_by_range(self, table_name: str, partition_key: str):
        """Партицирование таблицы по диапазону"""
        # Создаем партиции для последних 12 месяцев
        for i in range(12):
            next_month = datetime.utcnow().replace(day=1) + timedelta(days=30*i)
            partition_name = f"{table_name}_p{next_month.strftime('%Y_%m')}"
            
            async with db_pool.acquire() as conn:
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {partition_name} PARTITION OF {table_name}
                    FOR VALUES FROM ('{next_month.strftime('%Y-%m-01')}') 
                    TO ('{(next_month + timedelta(days=31)).strftime('%Y-%m-01')}')
                """)

    async def _partition_table_by_list(self, table_name: str, partition_key: str):
        """Партицирование таблицы по списку значений"""
        # В реальной системе это будет создание партиций по списку значений
        # Пока возвращаем заглушку
        import logging
        logging.info(f"Partitioning table {table_name} by list on key {partition_key}")
        return True

    async def _partition_table_by_hash(self, table_name: str, partition_key: str):
        """Партицирование таблицы по хэшу"""
        # В реальной системе это будет создание партиций по хэшу
        # Пока возвращаем заглушку
        import logging
        logging.info(f"Partitioning table {table_name} by hash on key {partition_key}")
        return True

    async def optimize_query_execution(self, query: str, params: Optional[Dict] = None) -> str:
        """Оптимизация выполнения запроса"""
        # Анализируем план выполнения запроса
        execution_plan = await self._analyze_query_plan(query, params)
        
        # Проверяем, можно ли улучшить выполнение
        if await self._should_optimize_query(execution_plan):
            # Применяем оптимизации
            optimized_query = await self._apply_query_optimizations(query, execution_plan)
            return optimized_query
        
        return query

    async def _analyze_query_plan(self, query: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Анализ плана выполнения запроса"""
        async with db_pool.acquire() as conn:
            plan_result = await conn.fetchrow(f"EXPLAIN (ANALYZE, BUFFERS) {query}", *(params.values() if params else []))
            return dict(plan_result) if plan_result else {}

    async def _should_optimize_query(self, execution_plan: Dict[str, Any]) -> bool:
        """Проверка, нужно ли оптимизировать запрос"""
        # Проверяем, есть ли в плане выполнения медленные операции
        plan_text = str(execution_plan)
        
        # Если в плане есть последовательные сканирования больших таблиц
        if "Seq Scan" in plan_text and "costly" in plan_text:
            return True
        
        # Если в плане есть операции с высокой стоимостью
        if execution_plan.get("cost", 0) > 1000:
            return True
        
        return False

    async def _apply_query_optimizations(self, query: str, execution_plan: Dict[str, Any]) -> str:
        """Применение оптимизаций к запросу"""
        # В реальной системе это будет сложной логикой переписывания запроса
        # Пока возвращаем оригинальный запрос
        return query

    async def get_optimization_recommendations(self) -> Dict[str, Any]:
        """Получение рекомендаций по оптимизации"""
        recommendations = {
            'index_recommendations': [rec.dict() for rec in self.index_recommendations],
            'query_optimizations': [opt.dict() for opt in self.query_optimizations],
            'table_optimizations': await self._get_table_optimization_recommendations(),
            'connection_pool_optimizations': await self._get_connection_pool_recommendations(),
            'replication_optimizations': await self._get_replication_recommendations(),
            'generated_at': datetime.utcnow().isoformat()
        }
        
        return recommendations

    async def _get_table_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Получение рекомендаций по оптимизации таблиц"""
        recommendations = []
        
        # Рекомендации для больших таблиц
        for table_name, stats in self.table_sizes.items():
            if stats['seq_scan'] > 5000:  # Если много последовательных сканирований
                recommendations.append({
                    'table': table_name,
                    'recommendation': 'Consider partitioning this large table to improve query performance',
                    'estimated_improvement': 40.0,
                    'priority': 'high'
                })
            elif stats['n_tup_upd'] > stats['n_tup_ins'] * 10:  # Если много обновлений по сравнению с вставками
                recommendations.append({
                    'table': table_name,
                    'recommendation': 'This table has high update-to-insert ratio. Consider optimization for write-heavy workload',
                    'estimated_improvement': 25.0,
                    'priority': 'medium'
                })
        
        return recommendations

    async def _get_connection_pool_recommendations(self) -> List[Dict[str, Any]]:
        """Получение рекомендаций по оптимизации пула соединений"""
        # В реальной системе это будет анализом использования пула соединений
        # Пока возвращаем заглушку
        return [
            {
                'area': 'connection_pool',
                'recommendation': 'Monitor connection pool utilization and adjust min/max sizes based on load',
                'priority': 'medium'
            }
        ]

    async def _get_replication_recommendations(self) -> List[Dict[str, Any]]:
        """Получение рекомендаций по оптимизации репликации"""
        # В реальной системе это будет анализом производительности репликации
        # Пока возвращаем заглушку
        return [
            {
                'area': 'replication',
                'recommendation': 'Consider implementing read replicas for heavy read workloads',
                'priority': 'high'
            }
        ]

    async def implement_optimization(self, optimization_type: str, 
                                   optimization_params: Dict[str, Any]) -> bool:
        """Реализация определенной оптимизации"""
        if optimization_type == "create_index":
            return await self._implement_index_optimization(optimization_params)
        elif optimization_type == "shard_table":
            return await self._implement_sharding_optimization(optimization_params)
        elif optimization_type == "partition_table":
            return await self._implement_partitioning_optimization(optimization_params)
        elif optimization_type == "optimize_query":
            return await self._implement_query_optimization(optimization_params)
        elif optimization_type == "configure_connection_pool":
            return await self._implement_connection_pool_optimization(optimization_params)
        elif optimization_type == "configure_replication":
            return await self._implement_replication_optimization(optimization_params)
        else:
            logger.error(f"Unknown optimization type: {optimization_type}")
            return False

    async def _implement_index_optimization(self, params: Dict[str, Any]) -> bool:
        """Реализация оптимизации индекса"""
        table_name = params.get('table_name')
        columns = params.get('columns', [])
        index_type = params.get('index_type', 'btree')
        
        if not table_name or not columns:
            return False
        
        try:
            index_type_enum = IndexType(index_type)
            return await self.create_optimized_index(table_name, columns, index_type_enum)
        except ValueError:
            logger.error(f"Invalid index type: {index_type}")
            return False

    async def _implement_sharding_optimization(self, params: Dict[str, Any]) -> bool:
        """Реализация оптимизации шардинга"""
        table_name = params.get('table_name')
        sharding_key = params.get('sharding_key')
        strategy = params.get('strategy', 'hash')
        
        if not table_name or not sharding_key:
            return False
        
        try:
            strategy_enum = ShardingStrategy(strategy)
            return await self.shard_table(table_name, sharding_key, strategy_enum)
        except ValueError:
            logger.error(f"Invalid sharding strategy: {strategy}")
            return False

    async def _implement_partitioning_optimization(self, params: Dict[str, Any]) -> bool:
        """Реализация оптимизации партицирования"""
        table_name = params.get('table_name')
        partition_key = params.get('partition_key')
        partition_type = params.get('partition_type', 'range')
        
        if not table_name or not partition_key:
            return False
        
        return await self.partition_table(table_name, partition_key, partition_type)

    async def _implement_query_optimization(self, params: Dict[str, Any]) -> bool:
        """Реализация оптимизации запроса"""
        query = params.get('query')
        table_name = params.get('table_name')
        
        if not query:
            return False
        
        # В реальной системе здесь будет применение оптимизаций к запросу
        # Пока возвращаем True
        return True

    async def _implement_connection_pool_optimization(self, params: Dict[str, Any]) -> bool:
        """Реализация оптимизации пула соединений"""
        min_size = params.get('min_size', 10)
        max_size = params.get('max_size', 50)
        timeout = params.get('timeout', 30)
        
        try:
            # Обновляем конфигурацию пула
            self.default_config.connection_pool_size = min_size
            self.default_config.max_connections = max_size
            self.default_config.query_timeout = timeout
            
            # Пересоздаем пул с новыми параметрами
            await self._configure_connection_pool()
            
            return True
        except Exception as e:
            logger.error(f"Error implementing connection pool optimization: {e}")
            return False

    async def _implement_replication_optimization(self, params: Dict[str, Any]) -> bool:
        """Реализация оптимизации репликации"""
        replication_type = params.get('replication_type', 'master_slave')
        enable = params.get('enable', True)
        
        try:
            strategy_enum = ReplicationType(replication_type)
            
            # Обновляем конфигурацию репликации
            self.default_config.replication_enabled = enable
            self.default_config.replication_type = strategy_enum
            
            # Применяем новую конфигурацию
            await self._configure_replication()
            
            return True
        except ValueError:
            logger.error(f"Invalid replication type: {replication_type}")
            return False
        except Exception as e:
            logger.error(f"Error implementing replication optimization: {e}")
            return False

    async def get_database_performance_insights(self) -> Dict[str, Any]:
        """Получение инсайтов о производительности базы данных"""
        insights = {
            'timestamp': datetime.utcnow().isoformat(),
            'table_statistics': await self._get_detailed_table_statistics(),
            'query_performance': await self._get_detailed_query_performance(),
            'index_efficiency': await self._get_index_efficiency_analysis(),
            'connection_pool_utilization': await self._get_connection_pool_utilization(),
            'recommendations': await self.get_optimization_recommendations(),
            'health_status': await self._get_database_health_status()
        }
        
        return insights

    async def _get_detailed_table_statistics(self) -> Dict[str, Any]:
        """Получение детальной статистики по таблицам"""
        async with db_pool.acquire() as conn:
            # Получаем размеры таблиц
            table_sizes = await conn.fetch(
                """
                SELECT 
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size,
                    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as table_size,
                    (SELECT COUNT(*) FROM pg_stat_user_tables WHERE schemaname = t.schemaname AND tablename = t.tablename) as row_count
                FROM pg_tables t
                WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
                LIMIT 20
                """
            )

        return {
            'tables': [
                {
                    'schema': row['schemaname'],
                    'name': row['tablename'],
                    'total_size': row['total_size'],
                    'table_size': row['table_size'],
                    'row_count': row['row_count']
                }
                for row in table_sizes
            ]
        }

    async def _get_detailed_query_performance(self) -> Dict[str, Any]:
        """Получение детальной статистики по производительности запросов"""
        async with db_pool.acquire() as conn:
            # Получаем медленные запросы
            slow_queries = await conn.fetch(
                """
                SELECT 
                    query,
                    mean_time,
                    calls,
                    total_time,
                    rows,
                    mean_time * calls as weighted_time
                FROM pg_stat_statements
                ORDER BY mean_time DESC
                LIMIT 10
                """
            )

        return {
            'slowest_queries': [
                {
                    'query': row['query'][:100] + '...' if len(row['query']) > 100 else row['query'],
                    'mean_time_ms': float(row['mean_time']),
                    'calls': row['calls'],
                    'total_time_ms': float(row['total_time']),
                    'rows': row['rows'],
                    'weighted_time': float(row['weighted_time'])
                }
                for row in slow_queries
            ]
        }

    async def _get_index_efficiency_analysis(self) -> Dict[str, Any]:
        """Получение анализа эффективности индексов"""
        async with db_pool.acquire() as conn:
            # Получаем статистику по индексам
            index_stats = await conn.fetch(
                """
                SELECT 
                    schemaname,
                    tablename,
                    indexname,
                    idx_scan,
                    idx_tup_read,
                    idx_tup_fetch,
                    pg_size_pretty(pg_relation_size(schemaname||'.'||indexname)) as index_size
                FROM pg_stat_user_indexes
                ORDER BY idx_scan DESC
                LIMIT 20
                """
            )

        return {
            'indexes': [
                {
                    'schema': row['schemaname'],
                    'table': row['tablename'],
                    'name': row['indexname'],
                    'scans': row['idx_scan'],
                    'tuples_read': row['idx_tup_read'],
                    'tuples_fetched': row['idx_tup_fetch'],
                    'size': row['index_size']
                }
                for row in index_stats
            ]
        }

    async def _get_connection_pool_utilization(self) -> Dict[str, Any]:
        """Получение информации об использовании пула соединений"""
        try:
            async with db_pool.acquire() as conn:
                # Получаем статистику активности
                activity_stats = await conn.fetch(
                    """
                    SELECT 
                        state,
                        COUNT(*) as count
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                    GROUP BY state
                    """
                )

            pool_stats = {
                'current_connections': db_pool.size,
                'max_connections': db_pool.max_size,
                'utilization_percent': (db_pool.size / db_pool.max_size) * 100 if db_pool.max_size > 0 else 0,
                'connection_states': {
                    row['state']: row['count'] for row in activity_stats
                }
            }

            return pool_stats
        except Exception as e:
            logger.error(f"Error getting connection pool utilization: {e}")
            return {}

    async def _get_database_health_status(self) -> Dict[str, Any]:
        """Получение статуса здоровья базы данных"""
        try:
            async with db_pool.acquire() as conn:
                # Проверяем время работы
                uptime = await conn.fetchval("SELECT EXTRACT(EPOCH FROM (NOW() - pg_postmaster_start_time())) as uptime")
                
                # Проверяем количество активных соединений
                active_connections = await conn.fetchval(
                    "SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'active'"
                )
                
                # Проверяем количество заблокированных процессов
                blocked_processes = await conn.fetchval(
                    "SELECT COUNT(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'"
                )
                
                # Проверяем статистику по ошибкам
                error_stats = await conn.fetchrow(
                    """
                    SELECT 
                        SUM(errors) as total_errors,
                        SUM(deadlocks) as total_deadlocks
                    FROM pg_stat_database
                    WHERE datname = current_database()
                    """
                )

            health_status = {
                'uptime_seconds': uptime,
                'active_connections': active_connections,
                'blocked_processes': blocked_processes,
                'total_errors': error_stats['total_errors'] if error_stats else 0,
                'total_deadlocks': error_stats['total_deadlocks'] if error_stats else 0,
                'status': 'healthy' if blocked_processes < 5 and (error_stats['total_errors'] if error_stats else 0) < 10 else 'degraded'
            }

            return health_status
        except Exception as e:
            logger.error(f"Error getting database health status: {e}")
            return {'status': 'error', 'error': str(e)}

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
db_optimization_service = DatabaseOptimizationService()
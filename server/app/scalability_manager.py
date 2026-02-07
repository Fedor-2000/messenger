# server/app/scalability_manager.py
import asyncio
import aioredis
import asyncpg
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
import time
import logging
from enum import Enum
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import aiokafka
from aioredis.cluster import RedisCluster
import asyncpg.pool
from abc import ABC, abstractmethod
import weakref
import gc

logger = logging.getLogger(__name__)

class NodeType(Enum):
    MASTER = "master"
    SLAVE = "slave"
    SHARD = "shard"
    CACHE = "cache"
    QUEUE = "queue"

@dataclass
class NodeInfo:
    id: str
    host: str
    port: int
    node_type: NodeType
    status: str
    load: float
    connections: int
    memory_usage: float

class ClusterManager:
    """Менеджер кластера для горизонтального масштабирования"""
    
    def __init__(self):
        self.nodes: Dict[str, NodeInfo] = {}
        self.node_pools: Dict[str, asyncpg.Pool] = {}
        self.redis_clusters: Dict[str, aioredis.Redis] = {}
        self.kafka_producers: Dict[str, aiokafka.AIOKafkaProducer] = {}
        self.kafka_consumers: Dict[str, aiokafka.AIOKafkaConsumer] = {}
        self.current_node_id = None
        self.heartbeat_interval = 30  # seconds
        self.monitoring_task = None
    
    async def initialize_cluster(self, config: Dict[str, Any]):
        """Инициализация кластера"""
        # Подключение к управляющему узлу
        controller_host = config.get('controller_host', 'localhost')
        controller_port = config.get('controller_port', 6379)
        
        self.controller_redis = aioredis.from_url(
            f"redis://{controller_host}:{controller_port}",
            decode_responses=True
        )
        
        # Регистрация текущего узла
        await self.register_node()
        
        # Запуск мониторинга
        self.monitoring_task = asyncio.create_task(self.start_monitoring())
        
        # Подключение к другим узлам
        await self.discover_nodes()
    
    async def register_node(self):
        """Регистрация текущего узла в кластере"""
        node_id = f"node_{int(time.time())}_{multiprocessing.current_process().pid}"
        self.current_node_id = node_id
        
        node_info = {
            'id': node_id,
            'host': self.get_local_ip(),
            'port': 8080,  # порт приложения
            'type': 'messenger',
            'status': 'active',
            'registered_at': time.time(),
            'capabilities': ['message_processing', 'user_management', 'file_storage']
        }
        
        # Сохраняем информацию о себе
        await self.controller_redis.hset(f"nodes:{node_id}", mapping=node_info)
        await self.controller_redis.sadd("active_nodes", node_id)
        
        # Устанавливаем TTL для автоматического удаления при падении
        await self.controller_redis.expire(f"nodes:{node_id}", 60)  # 1 minute
    
    async def discover_nodes(self):
        """Обнаружение других узлов в кластере"""
        while True:
            try:
                active_nodes = await self.controller_redis.smembers("active_nodes")
                
                for node_id in active_nodes:
                    if node_id != self.current_node_id:
                        node_data = await self.controller_redis.hgetall(f"nodes:{node_id}")
                        if node_data:
                            # Обновляем информацию о узле
                            self.update_node_info(node_data)
                
                # Обновляем TTL для своего узла
                await self.controller_redis.expire(f"nodes:{self.current_node_id}", 60)
                
            except Exception as e:
                logger.error(f"Error discovering nodes: {e}")
            
            await asyncio.sleep(30)  # Проверяем каждые 30 секунд
    
    async def start_monitoring(self):
        """Запуск мониторинга узлов кластера"""
        while True:
            try:
                await self.health_check()
                await self.load_balancing()
            except Exception as e:
                logger.error(f"Error in cluster monitoring: {e}")
            
            await asyncio.sleep(10)  # Проверяем каждые 10 секунд
    
    async def health_check(self):
        """Проверка здоровья узлов"""
        for node_id, node_info in self.nodes.items():
            try:
                # Проверяем доступность узла
                redis_conn = aioredis.from_url(f"redis://{node_info.host}:{node_info.port}")
                await redis_conn.ping()
                
                # Обновляем статус
                node_info.status = 'healthy'
                node_info.load = await self.get_node_load(node_id)
                
            except Exception:
                node_info.status = 'unhealthy'
    
    async def get_node_load(self, node_id: str) -> float:
        """Получение уровня загрузки узла"""
        # В реальном приложении это будет более сложная логика
        # с учетом CPU, памяти, количества соединений и т.д.
        return 0.5  # Заглушка
    
    async def load_balancing(self):
        """Балансировка нагрузки между узлами"""
        healthy_nodes = [node for node in self.nodes.values() if node.status == 'healthy']
        if not healthy_nodes:
            return
        
        # Сортируем по уровню загрузки
        healthy_nodes.sort(key=lambda x: x.load)
        
        # Перераспределяем нагрузку если нужно
        if healthy_nodes[0].load > 0.8 and len(healthy_nodes) > 1:
            # Перенаправляем часть нагрузки с самого загруженного узла
            await self.redistribute_load(healthy_nodes[0], healthy_nodes[1:])
    
    async def redistribute_load(self, overloaded_node: NodeInfo, available_nodes: List[NodeInfo]):
        """Перераспределение нагрузки"""
        # Логика перенаправления соединений
        import logging
        if not available_nodes:
            logging.warning(f"No available nodes to redistribute load from {overloaded_node.node_id}")
            return False

        # Находим узел с наименьшей нагрузкой
        target_node = min(available_nodes, key=lambda x: x.load)

        # Логика перенаправления нагрузки между узлами
        logging.info(f"Redistributing load from {overloaded_node.node_id} to {target_node.node_id}")

        # В реальном приложении: перенаправление соединений, перенос данных и т.д.
        return True
    
    def get_optimal_node(self) -> Optional[NodeInfo]:
        """Получение оптимального узла для обработки запроса"""
        healthy_nodes = [node for node in self.nodes.values() if node.status == 'healthy']
        if not healthy_nodes:
            return None
        
        # Возвращаем узел с минимальной загрузкой
        return min(healthy_nodes, key=lambda x: x.load)
    
    def get_local_ip(self) -> str:
        """Получение локального IP адреса"""
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            return "127.0.0.1"
    
    def update_node_info(self, node_data: Dict[str, Any]):
        """Обновление информации о узле"""
        node_id = node_data.get('id')
        if node_id and node_id not in self.nodes:
            self.nodes[node_id] = NodeInfo(
                id=node_id,
                host=node_data.get('host', ''),
                port=node_data.get('port', 0),
                node_type=NodeType(node_data.get('type', 'slave')),
                status=node_data.get('status', 'unknown'),
                load=float(node_data.get('load', 0)),
                connections=int(node_data.get('connections', 0)),
                memory_usage=float(node_data.get('memory_usage', 0))
            )

class ShardingManager:
    """Менеджер шардинга для распределения данных"""
    
    def __init__(self):
        self.shards: Dict[int, asyncpg.Pool] = {}
        self.shard_mapping: Dict[str, int] = {}  # entity_id -> shard_id
        self.consistent_hash_ring = ConsistentHashRing()
    
    async def initialize_shards(self, shard_configs: List[Dict[str, Any]]):
        """Инициализация шардов"""
        for i, config in enumerate(shard_configs):
            pool = await asyncpg.create_pool(
                config['dsn'],
                min_size=config.get('min_size', 5),
                max_size=config.get('max_size', 20)
            )
            self.shards[i] = pool
            self.consistent_hash_ring.add_node(i, config.get('weight', 1))
    
    def get_shard_for_entity(self, entity_id: str) -> int:
        """Получение шарда для сущности"""
        return self.consistent_hash_ring.get_node(entity_id)
    
    def get_shard_pool(self, entity_id: str) -> asyncpg.Pool:
        """Получение пула соединений для шарда сущности"""
        shard_id = self.get_shard_for_entity(entity_id)
        return self.shards[shard_id]
    
    async def rebalance_shards(self):
        """Перебалансировка шардов"""
        # Логика перебалансировки при изменении количества шардов
        import logging
        logging.info("Starting shard rebalancing...")

        # В реальном приложении: логика перебалансировки шардов
        # Перенос данных между шардами, обновление маппинга и т.д.
        return True

class ConsistentHashRing:
    """Консистентное кольцо для шардинга"""
    
    def __init__(self, replicas: int = 128):
        self.replicas = replicas
        self.ring = {}
        self.sorted_keys = []
    
    def add_node(self, node_id: int, weight: int = 1):
        """Добавление узла в кольцо"""
        for i in range(self.replicas * weight):
            key = hash(f"{node_id}:{i}")
            self.ring[key] = node_id
            self.sorted_keys.append(key)
        
        self.sorted_keys.sort()
    
    def remove_node(self, node_id: int):
        """Удаление узла из кольца"""
        for i in range(self.replicas):
            key = hash(f"{node_id}:{i}")
            if key in self.ring:
                del self.ring[key]
                self.sorted_keys.remove(key)
        
        self.sorted_keys.sort()
    
    def get_node(self, key: str) -> int:
        """Получение узла для ключа"""
        if not self.ring:
            return None
        
        hash_key = hash(key)
        
        # Бинарный поиск
        start = 0
        end = len(self.sorted_keys) - 1
        
        while start <= end:
            mid = (start + end) // 2
            if self.sorted_keys[mid] < hash_key:
                start = mid + 1
            else:
                end = mid - 1
        
        if start == len(self.sorted_keys):
            start = 0
        
        return self.ring[self.sorted_keys[start]]

class MessageQueueSystem:
    """Система очередей сообщений для масштабируемости"""
    
    def __init__(self, kafka_bootstrap_servers: List[str]):
        self.kafka_servers = kafka_bootstrap_servers
        self.producers: Dict[str, aiokafka.AIOKafkaProducer] = {}
        self.consumers: Dict[str, aiokafka.AIOKafkaConsumer] = {}
        self.consumer_tasks: Dict[str, asyncio.Task] = {}
    
    async def initialize(self):
        """Инициализация системы очередей"""
        # Создаем продюсера для отправки сообщений
        producer = aiokafka.AIOKafkaProducer(
            bootstrap_servers=self.kafka_servers,
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
        await producer.start()
        self.producers['default'] = producer
    
    async def send_message(self, topic: str, message: Dict[str, Any], partition: Optional[int] = None):
        """Отправка сообщения в очередь"""
        producer = self.producers.get('default')
        if not producer:
            await self.initialize()
            producer = self.producers['default']
        
        await producer.send_and_wait(topic, message, partition=partition)
    
    async def consume_messages(self, topic: str, consumer_group: str, handler: Callable[[Dict[str, Any]], None]):
        """Потребление сообщений из очереди"""
        consumer = aiokafka.AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.kafka_servers,
            group_id=consumer_group,
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        await consumer.start()
        
        async def consume_loop():
            try:
                async for msg in consumer:
                    await handler(msg.value)
            finally:
                await consumer.stop()
        
        task = asyncio.create_task(consume_loop())
        self.consumer_tasks[topic] = task
    
    async def stop_consumer(self, topic: str):
        """Остановка потребителя"""
        if topic in self.consumer_tasks:
            self.consumer_tasks[topic].cancel()
            await self.consumer_tasks[topic]
            del self.consumer_tasks[topic]

class LoadBalancer:
    """Балансировщик нагрузки"""
    
    def __init__(self):
        self.servers = []
        self.current_index = 0
        self.server_stats = {}
    
    def add_server(self, server_info: Dict[str, Any]):
        """Добавление сервера в пул"""
        self.servers.append(server_info)
        self.server_stats[server_info['id']] = {
            'requests_handled': 0,
            'avg_response_time': 0,
            'last_active': time.time()
        }
    
    def get_next_server(self) -> Optional[Dict[str, Any]]:
        """Получение следующего сервера по алгоритму round-robin"""
        if not self.servers:
            return None
        
        # Round-robin
        server = self.servers[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.servers)
        
        # Обновляем статистику
        self.server_stats[server['id']]['requests_handled'] += 1
        self.server_stats[server['id']]['last_active'] = time.time()
        
        return server
    
    def get_least_loaded_server(self) -> Optional[Dict[str, Any]]:
        """Получение наименее загруженного сервера"""
        if not self.servers:
            return None
        
        # Находим сервер с минимальным количеством обработанных запросов
        least_loaded = min(self.servers, 
                          key=lambda s: self.server_stats[s['id']]['requests_handled'])
        return least_loaded

class CircuitBreaker:
    """Цепной выключатель для отказоустойчивости"""
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func: Callable, *args, **kwargs):
        """Вызов функции с цепным выключателем"""
        if self.state == 'OPEN':
            if time.time() - self.last_failure_time > self.timeout:
                self.state = 'HALF_OPEN'
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise e
    
    def on_success(self):
        """Обработка успешного вызова"""
        self.failure_count = 0
        self.state = 'CLOSED'
    
    def on_failure(self):
        """Обработка неудачного вызова"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'

class ResourcePoolManager:
    """Менеджер пулов ресурсов для эффективного использования"""
    
    def __init__(self):
        self.pools = {}
        self.pool_configs = {}
        self.resource_limits = {}
    
    async def create_pool(self, pool_name: str, resource_type: str, config: Dict[str, Any]):
        """Создание пула ресурсов"""
        if resource_type == 'database':
            pool = await asyncpg.create_pool(**config)
        elif resource_type == 'redis':
            pool = aioredis.ConnectionPool.from_url(config['url'])
        else:
            raise ValueError(f"Unknown resource type: {resource_type}")
        
        self.pools[pool_name] = pool
        self.pool_configs[pool_name] = config
        self.resource_limits[pool_name] = config.get('max_size', 10)
    
    async def get_resource(self, pool_name: str):
        """Получение ресурса из пула"""
        if pool_name not in self.pools:
            raise ValueError(f"Pool {pool_name} not found")
        
        return self.pools[pool_name]
    
    async def return_resource(self, pool_name: str, resource):
        """Возврат ресурса в пул"""
        # В зависимости от типа ресурса
        import logging
        if pool_name not in self.pools:
            logging.error(f"Pool {pool_name} not found for resource return")
            return False

        # Возвращаем ресурс в пул
        pool = self.pools[pool_name]
        pool.append(resource)  # Добавляем ресурс обратно в пул
        logging.debug(f"Resource returned to pool {pool_name}")
        return True
    
    async def scale_pool(self, pool_name: str, new_size: int):
        """Масштабирование пула"""
        if pool_name in self.pools:
            # Логика масштабирования пула
            import logging
            current_size = len(self.pools[pool_name])
            if new_size > current_size:
                # Увеличиваем размер пула
                logging.info(f"Scaling up pool {pool_name} from {current_size} to {new_size}")
                # В реальном приложении: создание новых ресурсов и добавление в пул
            elif new_size < current_size:
                # Уменьшаем размер пула
                logging.info(f"Scaling down pool {pool_name} from {current_size} to {new_size}")
                # В реальном приложении: удаление ресурсов из пула
            return True
        return False

class AutoScaler:
    """Автоматический масштабировщик"""
    
    def __init__(self, metrics_provider, target_utilization: float = 0.7):
        self.metrics_provider = metrics_provider
        self.target_utilization = target_utilization
        self.current_instances = 1
        self.max_instances = 10
        self.min_instances = 1
        self.scale_up_threshold = 0.8
        self.scale_down_threshold = 0.3
        self.scale_cooldown = 300  # 5 minutes
        self.last_scale_time = 0
    
    async def check_scaling_needed(self) -> bool:
        """Проверка необходимости масштабирования"""
        current_time = time.time()
        if current_time - self.last_scale_time < self.scale_cooldown:
            return False
        
        utilization = await self.metrics_provider.get_current_utilization()
        
        if utilization > self.scale_up_threshold and self.current_instances < self.max_instances:
            return True
        elif utilization < self.scale_down_threshold and self.current_instances > self.min_instances:
            return True
        
        return False
    
    async def scale_up(self):
        """Масштабирование вверх"""
        if self.current_instances < self.max_instances:
            self.current_instances += 1
            self.last_scale_time = time.time()
            await self.deploy_new_instance()
    
    async def scale_down(self):
        """Масштабирование вниз"""
        if self.current_instances > self.min_instances:
            self.current_instances -= 1
            self.last_scale_time = time.time()
            await self.terminate_instance()
    
    async def deploy_new_instance(self):
        """Разворачивание нового экземпляра"""
        # Логика развертывания нового экземпляра
        logger.info(f"Deploying new instance. Current instances: {self.current_instances}")
    
    async def terminate_instance(self):
        """Завершение экземпляра"""
        # Логика завершения экземпляра
        logger.info(f"Terminating instance. Current instances: {self.current_instances}")

class MetricsProvider:
    """Поставщик метрик для автомасштабирования"""
    
    def __init__(self):
        self.metrics = {}
    
    async def get_current_utilization(self) -> float:
        """Получение текущей загрузки системы"""
        # В реальном приложении это будет более сложная логика
        # с учетом CPU, памяти, количества соединений и т.д.
        return 0.5  # Заглушка
    
    async def get_request_rate(self) -> float:
        """Получение скорости поступления запросов"""
        return 100.0  # Заглушка
    
    async def get_error_rate(self) -> float:
        """Получение скорости ошибок"""
        return 0.01  # Заглушка

# Глобальные экземпляры
cluster_manager = ClusterManager()
sharding_manager = ShardingManager()
message_queue_system = MessageQueueSystem(['localhost:9092'])
load_balancer = LoadBalancer()
circuit_breaker = CircuitBreaker()
resource_pool_manager = ResourcePoolManager()
auto_scaler = AutoScaler(MetricsProvider())
# Performance and Monitoring Enhancement System
# File: services/monitoring_service/performance_monitoring.py

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import uuid
import psutil
import GPUtil
from prometheus_client import Counter, Histogram, Gauge, Summary
import aioredis
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"

class PerformanceMetric(BaseModel):
    id: str
    name: str
    type: MetricType
    value: float
    labels: Dict[str, str] = {}
    timestamp: datetime = None

class SystemResource(Enum):
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK = "network"
    DATABASE = "database"
    CACHE = "cache"
    FILESYSTEM = "filesystem"

class ResourceUsage(BaseModel):
    resource: SystemResource
    usage_percentage: float
    details: Dict[str, Any] = {}
    timestamp: datetime = None

class PerformanceAlert(BaseModel):
    id: str
    metric_name: str
    threshold: float
    current_value: float
    severity: str  # 'low', 'medium', 'high', 'critical'
    message: str
    triggered_at: datetime = None
    resolved_at: Optional[datetime] = None
    is_resolved: bool = False

class PerformanceReport(BaseModel):
    id: str
    start_time: datetime
    end_time: datetime
    metrics: List[PerformanceMetric] = []
    resource_usage: List[ResourceUsage] = []
    alerts: List[PerformanceAlert] = []
    created_at: datetime = None

class PerformanceMonitoringService:
    def __init__(self):
        # Prometheus метрики
        self.request_counter = Counter('messenger_requests_total', 'Total requests', ['method', 'endpoint'])
        self.response_time_histogram = Histogram('messenger_response_time_seconds', 'Response time in seconds', ['endpoint'])
        self.active_connections_gauge = Gauge('messenger_active_connections', 'Active connections')
        self.database_connections_gauge = Gauge('messenger_database_connections', 'Database connections')
        self.memory_usage_gauge = Gauge('messenger_memory_usage_bytes', 'Memory usage in bytes')
        self.cpu_usage_gauge = Gauge('messenger_cpu_usage_percent', 'CPU usage percentage')
        
        # Конфигурация мониторинга
        self.monitoring_interval = 10  # секунды
        self.alert_thresholds = {
            'cpu_usage': 80.0,  # процент
            'memory_usage': 85.0,  # процент
            'disk_usage': 90.0,  # процент
            'database_connections': 90.0,  # процент от максимума
            'response_time': 2.0,  # секунды
            'error_rate': 0.05  # 5%
        }
        
        # Хранилище для временных метрик
        self.temp_metrics: Dict[str, List[tuple]] = {}  # metric_name -> [(timestamp, value)]
        self.temp_resource_usage: List[ResourceUsage] = []
        self.active_alerts: List[PerformanceAlert] = []
        
        # Статистика производительности
        self.performance_stats = {
            'requests_per_second': 0,
            'average_response_time': 0.0,
            'error_rate': 0.0,
            'active_users': 0
        }

    async def start_monitoring(self):
        """Запуск системы мониторинга"""
        logger.info("Starting performance monitoring...")
        
        # Запускаем асинхронные задачи мониторинга
        monitoring_tasks = [
            self._monitor_system_resources(),
            self._monitor_database_performance(),
            self._monitor_cache_performance(),
            self._monitor_network_performance(),
            self._check_alerts(),
            self._aggregate_metrics()
        ]
        
        await asyncio.gather(*monitoring_tasks)

    async def _monitor_system_resources(self):
        """Мониторинг системных ресурсов"""
        while True:
            try:
                # CPU usage
                cpu_percent = psutil.cpu_percent(interval=1)
                await self.record_metric("cpu_usage_percent", cpu_percent, {"resource": "cpu"})
                
                # Memory usage
                memory = psutil.virtual_memory()
                memory_percent = memory.percent
                await self.record_metric("memory_usage_percent", memory_percent, {"resource": "memory"})
                
                # Disk usage
                disk = psutil.disk_usage('/')
                disk_percent = (disk.used / disk.total) * 100
                await self.record_metric("disk_usage_percent", disk_percent, {"resource": "disk"})
                
                # Network usage
                net_io = psutil.net_io_counters()
                await self.record_metric("network_bytes_sent", net_io.bytes_sent, {"direction": "out"})
                await self.record_metric("network_bytes_recv", net_io.bytes_recv, {"direction": "in"})
                
                # GPU usage (если доступна)
                gpus = GPUtil.getGPUs()
                for gpu in gpus:
                    await self.record_metric("gpu_usage_percent", gpu.load * 100, {"gpu_id": str(gpu.id)})
                    await self.record_metric("gpu_memory_percent", gpu.memoryUtil * 100, {"gpu_id": str(gpu.id)})
                
                # Обновляем Prometheus метрики
                self.cpu_usage_gauge.set(cpu_percent)
                self.memory_usage_gauge.set(memory.used)
                
                await asyncio.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Error monitoring system resources: {e}")
                await asyncio.sleep(self.monitoring_interval)

    async def _monitor_database_performance(self):
        """Мониторинг производительности базы данных"""
        while True:
            try:
                start_time = time.time()
                
                # Проверяем соединение с базой данных
                async with db_pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")  # Простой запрос для проверки
                
                response_time = time.time() - start_time
                await self.record_metric("database_response_time_seconds", response_time, {"operation": "ping"})
                
                # Получаем статистику соединений
                connections_used = db_pool.size
                connections_max = db_pool.max_size
                connections_utilization = (connections_used / connections_max) * 100 if connections_max > 0 else 0
                
                await self.record_metric("database_connections_utilization", connections_utilization, {})
                self.database_connections_gauge.set(connections_used)
                
                # Мониторим медленные запросы
                # В реальной системе здесь будет логика для отслеживания медленных запросов
                
                await asyncio.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Error monitoring database performance: {e}")
                await asyncio.sleep(self.monitoring_interval)

    async def _monitor_cache_performance(self):
        """Мониторинг производительности кэша"""
        while True:
            try:
                start_time = time.time()
                
                # Проверяем соединение с Redis
                await redis_client.ping()
                
                response_time = time.time() - start_time
                await self.record_metric("cache_response_time_seconds", response_time, {"operation": "ping"})
                
                # Получаем статистику использования кэша
                info = await redis_client.info()
                keyspace_hits = info.get('keyspace_hits', 0)
                keyspace_misses = info.get('keyspace_misses', 0)
                
                hit_rate = keyspace_hits / (keyspace_hits + keyspace_misses) if (keyspace_hits + keyspace_misses) > 0 else 0
                await self.record_metric("cache_hit_rate", hit_rate, {})
                
                # Размер базы данных
                db_size = await redis_client.dbsize()
                await self.record_metric("cache_keys_count", db_size, {})
                
                await asyncio.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Error monitoring cache performance: {e}")
                await asyncio.sleep(self.monitoring_interval)

    async def _monitor_network_performance(self):
        """Мониторинг сетевой производительности"""
        prev_net_io = psutil.net_io_counters()
        
        while True:
            try:
                await asyncio.sleep(self.monitoring_interval)
                
                current_net_io = psutil.net_io_counters()
                
                # Вычисляем скорость передачи данных
                bytes_sent_diff = current_net_io.bytes_sent - prev_net_io.bytes_sent
                bytes_recv_diff = current_net_io.bytes_recv - prev_net_io.bytes_recv
                
                time_diff = self.monitoring_interval
                send_speed = bytes_sent_diff / time_diff
                recv_speed = bytes_recv_diff / time_diff
                
                await self.record_metric("network_send_speed_bps", send_speed, {"direction": "out"})
                await self.record_metric("network_recv_speed_bps", recv_speed, {"direction": "in"})
                
                prev_net_io = current_net_io
                
            except Exception as e:
                logger.error(f"Error monitoring network performance: {e}")
                await asyncio.sleep(self.monitoring_interval)

    async def record_metric(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Запись метрики"""
        metric_id = str(uuid.uuid4())
        labels = labels or {}
        
        metric = PerformanceMetric(
            id=metric_id,
            name=name,
            type=MetricType.GAUGE,  # По умолчанию
            value=value,
            labels=labels,
            timestamp=datetime.utcnow()
        )
        
        # Добавляем в промежуточное хранилище
        if name not in self.temp_metrics:
            self.temp_metrics[name] = []
        self.temp_metrics[name].append((metric.timestamp, value))
        
        # Ограничиваем размер промежуточного хранилища
        if len(self.temp_metrics[name]) > 1000:
            self.temp_metrics[name] = self.temp_metrics[name][-500:]  # Оставляем последние 500 значений
        
        # Проверяем пороговые значения для алертов
        await self._check_metric_threshold(metric)

    async def _check_metric_threshold(self, metric: PerformanceMetric):
        """Проверка пороговых значений метрики"""
        threshold_key = metric.name.replace('_percent', '').replace('_seconds', '').replace('_bytes', '')
        
        if threshold_key in self.alert_thresholds:
            threshold = self.alert_thresholds[threshold_key]
            
            if metric.value > threshold:
                severity = self._determine_severity(metric.value, threshold)
                
                alert = PerformanceAlert(
                    id=str(uuid.uuid4()),
                    metric_name=metric.name,
                    threshold=threshold,
                    current_value=metric.value,
                    severity=severity,
                    message=f"Metric {metric.name} exceeded threshold: {metric.value} > {threshold}",
                    triggered_at=datetime.utcnow()
                )
                
                self.active_alerts.append(alert)
                
                # Логируем алерт
                logger.warning(f"Performance alert: {alert.message}")
                
                # Отправляем уведомление
                await self._notify_alert(alert)

    def _determine_severity(self, value: float, threshold: float) -> str:
        """Определение уровня серьезности алерта"""
        ratio = value / threshold
        
        if ratio > 2.0:
            return "critical"
        elif ratio > 1.5:
            return "high"
        elif ratio > 1.2:
            return "medium"
        else:
            return "low"

    async def _notify_alert(self, alert: PerformanceAlert):
        """Уведомление о производительности"""
        notification = {
            'type': 'performance_alert',
            'alert': {
                'id': alert.id,
                'metric_name': alert.metric_name,
                'threshold': alert.threshold,
                'current_value': alert.current_value,
                'severity': alert.severity,
                'message': alert.message,
                'triggered_at': alert.triggered_at.isoformat()
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем в канал уведомлений
        await redis_client.publish("system_alerts", json.dumps(notification))

    async def _check_alerts(self):
        """Проверка алертов"""
        while True:
            try:
                # Проверяем, не разрешились ли какие-то алерты
                resolved_alerts = []
                for alert in self.active_alerts:
                    # Получаем последнее значение метрики
                    if alert.metric_name in self.temp_metrics:
                        last_value = self.temp_metrics[alert.metric_name][-1][1] if self.temp_metrics[alert.metric_name] else 0
                        
                        # Если значение снова ниже порога, считаем алерт разрешенным
                        if last_value <= alert.threshold * 0.9:  # 10% гистерезис
                            alert.resolved_at = datetime.utcnow()
                            alert.is_resolved = True
                            resolved_alerts.append(alert)
                
                # Удаляем разрешенные алерты из активных
                for alert in resolved_alerts:
                    if alert in self.active_alerts:
                        self.active_alerts.remove(alert)
                
                await asyncio.sleep(30)  # Проверяем раз в 30 секунд
                
            except Exception as e:
                logger.error(f"Error checking alerts: {e}")
                await asyncio.sleep(30)

    async def _aggregate_metrics(self):
        """Агрегация метрик"""
        while True:
            try:
                # Агрегируем метрики за последнюю минуту
                minute_ago = datetime.utcnow() - timedelta(minutes=1)
                
                # Вычисляем агрегированные значения
                aggregated_data = {}
                for metric_name, values in self.temp_metrics.items():
                    recent_values = [(ts, val) for ts, val in values if ts >= minute_ago]
                    if recent_values:
                        values_only = [val for _, val in recent_values]
                        aggregated_data[metric_name] = {
                            'avg': sum(values_only) / len(values_only),
                            'min': min(values_only),
                            'max': max(values_only),
                            'count': len(values_only)
                        }
                
                # Сохраняем агрегированные метрики
                await self._save_aggregated_metrics(aggregated_data)
                
                await asyncio.sleep(60)  # Агрегируем каждую минуту
                
            except Exception as e:
                logger.error(f"Error aggregating metrics: {e}")
                await asyncio.sleep(60)

    async def _save_aggregated_metrics(self, aggregated_data: Dict[str, Dict]):
        """Сохранение агрегированных метрик"""
        # В реальной системе здесь будет сохранение в базу данных или в Prometheus
        # Для упрощения просто логируем
        logger.info(f"Aggregated metrics: {aggregated_data}")

    async def get_performance_report(self, start_time: datetime, 
                                   end_time: datetime) -> PerformanceReport:
        """Получение отчета о производительности"""
        report_id = str(uuid.uuid4())
        
        # Получаем метрики за указанный период
        metrics = await self._get_metrics_in_range(start_time, end_time)
        
        # Получаем использование ресурсов за период
        resource_usage = await self._get_resource_usage_in_range(start_time, end_time)
        
        # Получаем алерты за период
        alerts = await self._get_alerts_in_range(start_time, end_time)
        
        report = PerformanceReport(
            id=report_id,
            start_time=start_time,
            end_time=end_time,
            metrics=metrics,
            resource_usage=resource_usage,
            alerts=alerts,
            created_at=datetime.utcnow()
        )
        
        return report

    async def _get_metrics_in_range(self, start_time: datetime, end_time: datetime) -> List[PerformanceMetric]:
        """Получение метрик за указанный период"""
        # В реальной системе здесь будет запрос к базе данных или Prometheus
        # Временно возвращаем данные из промежуточного хранилища
        metrics = []
        
        for metric_name, values in self.temp_metrics.items():
            for timestamp, value in values:
                if start_time <= timestamp <= end_time:
                    metric = PerformanceMetric(
                        id=str(uuid.uuid4()),
                        name=metric_name,
                        type=MetricType.GAUGE,
                        value=value,
                        timestamp=timestamp
                    )
                    metrics.append(metric)
        
        # Сортируем по времени
        metrics.sort(key=lambda x: x.timestamp)
        
        return metrics

    async def _get_resource_usage_in_range(self, start_time: datetime, 
                                         end_time: datetime) -> List[ResourceUsage]:
        """Получение использования ресурсов за указанный период"""
        # В реальной системе здесь будет запрос к базе данных
        # Временно возвращаем последние данные из временного хранилища
        return self.temp_resource_usage

    async def _get_alerts_in_range(self, start_time: datetime, 
                                 end_time: datetime) -> List[PerformanceAlert]:
        """Получение алертов за указанный период"""
        # В реальной системе здесь будет запрос к базе данных
        # Временно возвращаем активные алерты
        return [alert for alert in self.active_alerts 
                if start_time <= alert.triggered_at <= end_time]

    async def get_system_health_status(self) -> Dict[str, Any]:
        """Получение статуса здоровья системы"""
        health_status = {
            'timestamp': datetime.utcnow().isoformat(),
            'overall_status': 'healthy',
            'components': {},
            'metrics': {}
        }

        try:
            # Проверяем статус базы данных
            db_status = await self._check_database_health()
            health_status['components']['database'] = db_status

            # Проверяем статус кэша
            cache_status = await self._check_cache_health()
            health_status['components']['cache'] = cache_status

            # Проверяем статус основных сервисов
            services_status = await self._check_services_health()
            health_status['components']['services'] = services_status

            # Получаем текущие метрики
            current_metrics = await self._get_current_metrics()
            health_status['metrics'] = current_metrics

            # Определяем общий статус
            if any(comp['status'] == 'unhealthy' for comp in health_status['components'].values()):
                health_status['overall_status'] = 'unhealthy'
            elif any(comp['status'] == 'degraded' for comp in health_status['components'].values()):
                health_status['overall_status'] = 'degraded'

        except Exception as e:
            logger.error(f"Error getting system health status: {e}")
            health_status['overall_status'] = 'error'
            health_status['error'] = str(e)

        return health_status

    async def _check_database_health(self) -> Dict[str, Any]:
        """Проверка статуса базы данных"""
        try:
            start_time = time.time()
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            response_time = time.time() - start_time

            # Проверяем использование соединений
            connections_used = db_pool.size
            connections_max = db_pool.max_size
            utilization = (connections_used / connections_max) * 100 if connections_max > 0 else 0

            status = 'healthy' if response_time < 1.0 and utilization < 80 else 'degraded'

            return {
                'status': status,
                'response_time_ms': round(response_time * 1000, 2),
                'connections_used': connections_used,
                'connections_max': connections_max,
                'utilization_percent': round(utilization, 2)
            }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e)
            }

    async def _check_cache_health(self) -> Dict[str, Any]:
        """Проверка статуса кэша"""
        try:
            start_time = time.time()
            await redis_client.ping()
            response_time = time.time() - start_time

            # Получаем статистику кэша
            info = await redis_client.info()
            keyspace_hits = info.get('keyspace_hits', 0)
            keyspace_misses = info.get('keyspace_misses', 0)
            hit_rate = keyspace_hits / (keyspace_hits + keyspace_misses) if (keyspace_hits + keyspace_misses) > 0 else 0

            status = 'healthy' if response_time < 0.1 and hit_rate > 0.8 else 'degraded'

            return {
                'status': status,
                'response_time_ms': round(response_time * 1000, 2),
                'hit_rate': round(hit_rate, 3),
                'total_commands_processed': info.get('total_commands_processed', 0),
                'connected_clients': info.get('connected_clients', 0)
            }
        except Exception as e:
            logger.error(f"Cache health check failed: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e)
            }

    async def _check_services_health(self) -> Dict[str, Any]:
        """Проверка статуса сервисов"""
        # В реальной системе здесь будет проверка статуса всех микросервисов
        # Пока возвращаем заглушку
        return {
            'status': 'healthy',
            'active_services': 5,
            'total_services': 5,
            'unhealthy_services': 0
        }

    async def _get_current_metrics(self) -> Dict[str, float]:
        """Получение текущих метрик"""
        # Возвращаем последние значения основных метрик
        current_metrics = {}
        
        for metric_name in ['cpu_usage_percent', 'memory_usage_percent', 'database_response_time_seconds']:
            if metric_name in self.temp_metrics and self.temp_metrics[metric_name]:
                current_metrics[metric_name] = self.temp_metrics[metric_name][-1][1]
        
        return current_metrics

    async def get_performance_dashboard_data(self) -> Dict[str, Any]:
        """Получение данных для дашборда производительности"""
        dashboard_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'system_resources': {},
            'recent_alerts': [],
            'performance_trends': {},
            'top_metrics': {}
        }

        # Получаем текущее использование системных ресурсов
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        dashboard_data['system_resources'] = {
            'cpu': {
                'usage_percent': cpu_percent,
                'count': psutil.cpu_count()
            },
            'memory': {
                'usage_percent': memory.percent,
                'total_gb': round(memory.total / (1024**3), 2),
                'available_gb': round(memory.available / (1024**3), 2)
            },
            'disk': {
                'usage_percent': (disk.used / disk.total) * 100,
                'total_gb': round(disk.total / (1024**3), 2),
                'free_gb': round(disk.free / (1024**3), 2)
            }
        }

        # Получаем недавние алерты
        recent_alerts = [alert for alert in self.active_alerts 
                        if datetime.utcnow() - alert.triggered_at < timedelta(hours=1)]
        dashboard_data['recent_alerts'] = [
            {
                'id': alert.id,
                'metric_name': alert.metric_name,
                'severity': alert.severity,
                'message': alert.message,
                'triggered_at': alert.triggered_at.isoformat()
            }
            for alert in recent_alerts
        ]

        # Получаем тренды производительности
        dashboard_data['performance_trends'] = await self._get_performance_trends()

        # Получаем топ метрик
        dashboard_data['top_metrics'] = await self._get_top_metrics()

        return dashboard_data

    async def _get_performance_trends(self) -> Dict[str, List[Dict[str, Any]]]:
        """Получение трендов производительности"""
        trends = {}
        
        # Получаем данные за последние 24 часа
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        
        for metric_name, values in self.temp_metrics.items():
            recent_values = [(ts, val) for ts, val in values if ts >= twenty_four_hours_ago]
            if recent_values:
                # Берем каждые 10 значений для уменьшения объема данных
                sampled_values = recent_values[::max(1, len(recent_values) // 20)]
                trends[metric_name] = [
                    {'timestamp': ts.isoformat(), 'value': val}
                    for ts, val in sampled_values
                ]
        
        return trends

    async def _get_top_metrics(self) -> Dict[str, float]:
        """Получение топ метрик"""
        top_metrics = {}
        
        for metric_name, values in self.temp_metrics.items():
            if values:
                # Берем среднее значение за последние 10 минут
                ten_minutes_ago = datetime.utcnow() - timedelta(minutes=10)
                recent_values = [val for ts, val in values if ts >= ten_minutes_ago]
                
                if recent_values:
                    avg_value = sum(recent_values) / len(recent_values)
                    top_metrics[metric_name] = round(avg_value, 3)
        
        return top_metrics

    async def export_metrics(self, format: str = "json") -> str:
        """Экспорт метрик в различных форматах"""
        metrics_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'metrics': {},
            'alerts': [alert.dict() for alert in self.active_alerts],
            'system_resources': await self._get_current_system_resources()
        }

        for metric_name, values in self.temp_metrics.items():
            # Берем последние 100 значений для экспорта
            recent_values = values[-100:]
            metrics_data['metrics'][metric_name] = [
                {'timestamp': ts.isoformat(), 'value': val}
                for ts, val in recent_values
            ]

        if format.lower() == "json":
            return json.dumps(metrics_data, indent=2, ensure_ascii=False)
        elif format.lower() == "csv":
            return self._export_to_csv(metrics_data)
        elif format.lower() == "prometheus":
            return self._export_to_prometheus_format()
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def _export_to_csv(self, metrics_data: Dict[str, Any]) -> str:
        """Экспорт метрик в CSV формат"""
        import csv
        from io import StringIO

        output = StringIO()
        writer = csv.writer(output)

        # Заголовки
        writer.writerow(['metric_name', 'timestamp', 'value'])

        # Данные
        for metric_name, values in metrics_data['metrics'].items():
            for value_data in values:
                writer.writerow([metric_name, value_data['timestamp'], value_data['value']])

        return output.getvalue()

    def _export_to_prometheus_format(self) -> str:
        """Экспорт метрик в формат Prometheus"""
        prometheus_output = []
        
        for metric_name, values in self.temp_metrics.items():
            if values:
                # Используем последнее значение
                last_ts, last_val = values[-1]
                prometheus_output.append(f'{metric_name} {last_val} {int(last_ts.timestamp())}')
        
        return '\n'.join(prometheus_output)

    async def _get_current_system_resources(self) -> Dict[str, Any]:
        """Получение текущего состояния системных ресурсов"""
        return {
            'cpu_percent': psutil.cpu_percent(),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': (psutil.disk_usage('/').used / psutil.disk_usage('/').total) * 100,
            'network_io': psutil.net_io_counters()._asdict(),
            'timestamp': datetime.utcnow().isoformat()
        }

    async def get_performance_insights(self) -> Dict[str, Any]:
        """Получение инсайтов о производительности"""
        insights = {
            'timestamp': datetime.utcnow().isoformat(),
            'recommendations': [],
            'bottlenecks': [],
            'optimization_opportunities': []
        }

        # Анализируем метрики для выявления проблем
        for metric_name, values in self.temp_metrics.items():
            if values:
                # Получаем последние значения
                recent_values = values[-10:]  # последние 10 значений
                if len(recent_values) >= 2:
                    # Проверяем тренд
                    first_val = recent_values[0][1]
                    last_val = recent_values[-1][1]
                    
                    if last_val > first_val * 1.5:  # Рост более чем на 50%
                        insights['bottlenecks'].append({
                            'metric': metric_name,
                            'trend': 'increasing',
                            'change_percent': round(((last_val - first_val) / first_val) * 100, 2)
                        })

        # Рекомендации на основе текущих метрик
        current_cpu = psutil.cpu_percent()
        current_memory = psutil.virtual_memory().percent

        if current_cpu > 80:
            insights['recommendations'].append({
                'type': 'cpu',
                'message': 'High CPU usage detected. Consider optimizing code or scaling horizontally.',
                'severity': 'high'
            })

        if current_memory > 85:
            insights['recommendations'].append({
                'type': 'memory',
                'message': 'High memory usage detected. Consider optimizing memory usage or increasing available memory.',
                'severity': 'high'
            })

        # Возможности оптимизации
        if 'database_response_time_seconds' in self.temp_metrics:
            db_times = [val for _, val in self.temp_metrics['database_response_time_seconds'][-20:]]
            if db_times and sum(db_times) / len(db_times) > 0.5:  # Среднее > 500ms
                insights['optimization_opportunities'].append({
                    'area': 'database',
                    'opportunity': 'Slow database queries detected. Consider adding indexes or optimizing queries.',
                    'potential_improvement': 'Reducing average query time by 50%'
                })

        return insights

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
performance_monitoring_service = PerformanceMonitoringService()
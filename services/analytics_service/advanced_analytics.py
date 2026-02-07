# Advanced Analytics and Reporting System
# File: services/analytics_service/advanced_analytics.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
import matplotlib.pyplot as plt
import seaborn as sns
from io import BytesIO
import base64

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class AnalyticsType(Enum):
    USER_BEHAVIOR = "user_behavior"
    CONTENT_ANALYTICS = "content_analytics"
    PERFORMANCE_METRICS = "performance_metrics"
    BUSINESS_INTELLIGENCE = "business_intelligence"
    CUSTOM_ANALYTICS = "custom_analytics"

class ReportFormat(Enum):
    JSON = "json"
    CSV = "csv"
    PDF = "pdf"
    EXCEL = "excel"
    HTML = "html"
    IMAGE = "image"

class ReportFrequency(Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"

class ChartType(Enum):
    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    SCATTER = "scatter"
    HEATMAP = "heatmap"
    AREA = "area"
    COLUMN = "column"

class AnalyticsMetric(BaseModel):
    id: str
    name: str
    description: str
    category: str  # 'user_engagement', 'content_consumption', 'system_performance', etc.
    calculation_method: str  # 'count', 'sum', 'avg', 'rate', 'ratio', etc.
    aggregation_period: str  # 'minute', 'hour', 'day', 'week', 'month'
    filters: Optional[Dict[str, Any]] = None
    created_at: datetime = None
    updated_at: datetime = None

class AnalyticsReport(BaseModel):
    id: str
    title: str
    description: str
    type: AnalyticsType
    format: ReportFormat
    frequency: Optional[ReportFrequency] = None
    filters: Dict[str, Any]  # Фильтры для генерации отчета
    metrics: List[str]  # Названия метрик для включения в отчет
    charts: List[Dict[str, Any]]  # [{'type': 'line', 'metric': 'metric_name', 'title': 'Chart Title'}]
    data: Optional[Dict[str, Any]] = None  # Сгенерированные данные отчета
    generated_at: Optional[datetime] = None
    scheduled_for: Optional[datetime] = None
    created_at: datetime = None
    updated_at: datetime = None
    is_automatic: bool = False
    is_subscribed: bool = False

class AdvancedAnalyticsService:
    def __init__(self):
        self.default_metrics = {
            'user_engagement': [
                'messages_sent_per_day',
                'messages_received_per_day',
                'active_users_daily',
                'active_users_weekly',
                'session_duration_average',
                'login_frequency',
                'feature_usage_rate'
            ],
            'content_consumption': [
                'files_shared_per_day',
                'media_consumption_rate',
                'content_interaction_rate',
                'content_sharing_frequency',
                'download_vs_view_ratio'
            ],
            'system_performance': [
                'response_time_average',
                'error_rate',
                'database_query_time_average',
                'cache_hit_rate',
                'throughput_requests_per_second'
            ],
            'business_metrics': [
                'user_retention_rate',
                'conversion_rate',
                'revenue_per_user',
                'customer_acquisition_cost',
                'lifetime_value'
            ]
        }

        self.default_charts = {
            'user_engagement': [
                {'type': 'line', 'metric': 'active_users_daily', 'title': 'Daily Active Users'},
                {'type': 'bar', 'metric': 'messages_sent_per_day', 'title': 'Messages Sent Daily'},
                {'type': 'line', 'metric': 'session_duration_average', 'title': 'Avg Session Duration'}
            ],
            'content_consumption': [
                {'type': 'bar', 'metric': 'files_shared_per_day', 'title': 'Files Shared Daily'},
                {'type': 'pie', 'metric': 'content_type_distribution', 'title': 'Content Type Distribution'}
            ],
            'system_performance': [
                {'type': 'line', 'metric': 'response_time_average', 'title': 'Avg Response Time'},
                {'type': 'area', 'metric': 'throughput_requests_per_second', 'title': 'Requests Per Second'}
            ]
        }

    async def create_custom_metric(self, name: str, description: str, category: str,
                                 calculation_method: str, aggregation_period: str,
                                 filters: Optional[Dict] = None) -> Optional[str]:
        """Создание пользовательской метрики"""
        metric_id = str(uuid.uuid4())

        metric = AnalyticsMetric(
            id=metric_id,
            name=name,
            description=description,
            category=category,
            calculation_method=calculation_method,
            aggregation_period=aggregation_period,
            filters=filters or {},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем метрику в базу данных
        await self._save_analytics_metric(metric)

        # Добавляем в кэш
        await self._cache_analytics_metric(metric)

        # Создаем запись активности
        await self._log_activity("custom_metric_created", {
            "metric_id": metric_id,
            "metric_name": name,
            "category": category
        })

        return metric_id

    async def _save_analytics_metric(self, metric: AnalyticsMetric):
        """Сохранение метрики аналитики в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO analytics_metrics (
                    id, name, description, category, calculation_method,
                    aggregation_period, filters, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                metric.id, metric.name, metric.description, metric.category,
                metric.calculation_method, metric.aggregation_period,
                json.dumps(metric.filters) if metric.filters else None,
                metric.created_at, metric.updated_at
            )

    async def create_analytics_report(self, title: str, description: str,
                                    report_type: AnalyticsType,
                                    metrics: List[str],
                                    charts: Optional[List[Dict[str, Any]]] = None,
                                    filters: Optional[Dict[str, Any]] = None,
                                    format: ReportFormat = ReportFormat.JSON,
                                    frequency: Optional[ReportFrequency] = None,
                                    is_automatic: bool = False) -> Optional[str]:
        """Создание отчета аналитики"""
        report_id = str(uuid.uuid4())

        report = AnalyticsReport(
            id=report_id,
            title=title,
            description=description,
            type=report_type,
            format=format,
            frequency=frequency,
            filters=filters or {},
            metrics=metrics,
            charts=charts or self.default_charts.get(report_type.value, []),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            is_automatic=is_automatic
        )

        # Генерируем данные отчета
        report_data = await self._generate_report_data(report)
        report.data = report_data
        report.generated_at = datetime.utcnow()

        # Если отчет автоматический, планируем его генерацию
        if is_automatic and frequency:
            report.scheduled_for = self._calculate_next_schedule(datetime.utcnow(), frequency)

        # Сохраняем отчет
        await self._save_analytics_report(report)

        # Добавляем в кэш
        await self._cache_analytics_report(report)

        # Если отчет автоматический, добавляем в планировщик
        if is_automatic and report.scheduled_for:
            await self._schedule_report_generation(report)

        # Создаем запись активности
        await self._log_activity("analytics_report_created", {
            "report_id": report_id,
            "report_type": report_type.value,
            "metrics_count": len(metrics)
        })

        return report_id

    async def _generate_report_data(self, report: AnalyticsReport) -> Dict[str, Any]:
        """Генерация данных для отчета"""
        data = {}

        # Получаем данные для каждой метрики
        for metric_name in report.metrics:
            metric_data = await self._get_metric_data(metric_name, report.filters)
            data[metric_name] = metric_data

        # Генерируем данные для диаграмм
        chart_data = {}
        for chart_config in report.charts:
            chart_type = chart_config['type']
            metric_name = chart_config['metric']
            chart_title = chart_config.get('title', f'{chart_type.title()} Chart for {metric_name}')

            if metric_name in data:
                chart_data[f"{metric_name}_{chart_type}"] = await self._generate_chart_data(
                    data[metric_name], chart_type, chart_title
                )

        result = {
            'metrics_data': data,
            'charts_data': chart_data,
            'report_metadata': {
                'generated_at': datetime.utcnow().isoformat(),
                'filters_applied': report.filters,
                'metrics_included': report.metrics
            }
        }

        return result

    async def _get_metric_data(self, metric_name: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение данных для метрики"""
        # В зависимости от типа метрики, выполняем соответствующий запрос
        if metric_name == 'active_users_daily':
            return await self._get_active_users_data(filters)
        elif metric_name == 'messages_sent_per_day':
            return await self._get_messages_sent_data(filters)
        elif metric_name == 'response_time_average':
            return await self._get_response_time_data(filters)
        elif metric_name == 'files_shared_per_day':
            return await self._get_files_shared_data(filters)
        elif metric_name == 'content_type_distribution':
            return await self._get_content_type_distribution(filters)
        else:
            # Для пользовательских метрик
            return await self._get_custom_metric_data(metric_name, filters)

    async def _get_active_users_data(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение данных об активных пользователях"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        granularity = filters.get('granularity', 'day')  # 'hour', 'day', 'week', 'month'

        # Формируем SQL запрос в зависимости от гранулярности
        if granularity == 'hour':
            time_group = "DATE_TRUNC('hour', timestamp)"
            date_format = "%Y-%m-%d %H:00"
        elif granularity == 'day':
            time_group = "DATE_TRUNC('day', timestamp)"
            date_format = "%Y-%m-%d"
        elif granularity == 'week':
            time_group = "DATE_TRUNC('week', timestamp)"
            date_format = "%Y-W%V"
        elif granularity == 'month':
            time_group = "DATE_TRUNC('month', timestamp)"
            date_format = "%Y-%m"
        else:
            time_group = "DATE_TRUNC('day', timestamp)"
            date_format = "%Y-%m-%d"

        sql_query = f"""
            SELECT 
                {time_group} as time_period,
                COUNT(DISTINCT user_id) as active_users
            FROM user_activities
            WHERE timestamp BETWEEN $1 AND $2
            GROUP BY time_period
            ORDER BY time_period
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, start_date, end_date)

        return [
            {
                'timestamp': row['time_period'].strftime(date_format),
                'value': row['active_users'],
                'label': f"Active Users ({row['time_period'].strftime(date_format)})"
            }
            for row in rows
        ]

    async def _get_messages_sent_data(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение данных о отправленных сообщениях"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        granularity = filters.get('granularity', 'day')

        # Формируем SQL запрос в зависимости от гранулярности
        if granularity == 'hour':
            time_group = "DATE_TRUNC('hour', timestamp)"
            date_format = "%Y-%m-%d %H:00"
        elif granularity == 'day':
            time_group = "DATE_TRUNC('day', timestamp)"
            date_format = "%Y-%m-%d"
        elif granularity == 'week':
            time_group = "DATE_TRUNC('week', timestamp)"
            date_format = "%Y-W%V"
        elif granularity == 'month':
            time_group = "DATE_TRUNC('month', timestamp)"
            date_format = "%Y-%m"
        else:
            time_group = "DATE_TRUNC('day', timestamp)"
            date_format = "%Y-%m-%d"

        sql_query = f"""
            SELECT 
                {time_group} as time_period,
                COUNT(*) as messages_sent
            FROM messages
            WHERE timestamp BETWEEN $1 AND $2
            GROUP BY time_period
            ORDER BY time_period
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, start_date, end_date)

        return [
            {
                'timestamp': row['time_period'].strftime(date_format),
                'value': row['messages_sent'],
                'label': f"Messages Sent ({row['time_period'].strftime(date_format)})"
            }
            for row in rows
        ]

    async def _get_response_time_data(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение данных о времени отклика"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=7))
        end_date = filters.get('end_date', datetime.utcnow())
        granularity = filters.get('granularity', 'hour')

        # Формируем SQL запрос в зависимости от гранулярности
        if granularity == 'minute':
            time_group = "DATE_TRUNC('minute', timestamp)"
            date_format = "%Y-%m-%d %H:%M"
        elif granularity == 'hour':
            time_group = "DATE_TRUNC('hour', timestamp)"
            date_format = "%Y-%m-%d %H:00"
        elif granularity == 'day':
            time_group = "DATE_TRUNC('day', timestamp)"
            date_format = "%Y-%m-%d"
        else:
            time_group = "DATE_TRUNC('hour', timestamp)"
            date_format = "%Y-%m-%d %H:00"

        sql_query = f"""
            SELECT 
                {time_group} as time_period,
                AVG(response_time) as avg_response_time,
                MIN(response_time) as min_response_time,
                MAX(response_time) as max_response_time
            FROM system_performance
            WHERE timestamp BETWEEN $1 AND $2
            GROUP BY time_period
            ORDER BY time_period
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, start_date, end_date)

        return [
            {
                'timestamp': row['time_period'].strftime(date_format),
                'avg_value': float(row['avg_response_time']) if row['avg_response_time'] else 0,
                'min_value': float(row['min_response_time']) if row['min_response_time'] else 0,
                'max_value': float(row['max_response_time']) if row['max_response_time'] else 0,
                'label': f"Avg Response Time ({row['time_period'].strftime(date_format)})"
            }
            for row in rows
        ]

    async def _get_files_shared_data(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение данных о файлах"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        granularity = filters.get('granularity', 'day')

        # Формируем SQL запрос в зависимости от гранулярности
        if granularity == 'hour':
            time_group = "DATE_TRUNC('hour', uploaded_at)"
            date_format = "%Y-%m-%d %H:00"
        elif granularity == 'day':
            time_group = "DATE_TRUNC('day', uploaded_at)"
            date_format = "%Y-%m-%d"
        elif granularity == 'week':
            time_group = "DATE_TRUNC('week', uploaded_at)"
            date_format = "%Y-W%V"
        elif granularity == 'month':
            time_group = "DATE_TRUNC('month', uploaded_at)"
            date_format = "%Y-%m"
        else:
            time_group = "DATE_TRUNC('day', uploaded_at)"
            date_format = "%Y-%m-%d"

        sql_query = f"""
            SELECT 
                {time_group} as time_period,
                COUNT(*) as files_shared,
                SUM(size) as total_size_bytes
            FROM files
            WHERE uploaded_at BETWEEN $1 AND $2
            GROUP BY time_period
            ORDER BY time_period
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, start_date, end_date)

        return [
            {
                'timestamp': row['time_period'].strftime(date_format),
                'value': row['files_shared'],
                'total_size_bytes': row['total_size_bytes'],
                'label': f"Files Shared ({row['time_period'].strftime(date_format)})"
            }
            for row in rows
        ]

    async def _get_content_type_distribution(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение распределения по типам контента"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())

        sql_query = """
            SELECT 
                mime_type,
                COUNT(*) as count,
                SUM(size) as total_size
            FROM files
            WHERE uploaded_at BETWEEN $1 AND $2
            GROUP BY mime_type
            ORDER BY count DESC
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, start_date, end_date)

        return [
            {
                'type': row['mime_type'],
                'count': row['count'],
                'total_size': row['total_size'],
                'percentage': 0  # Будет рассчитано позже
            }
            for row in rows
        ]

    async def _get_custom_metric_data(self, metric_name: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение данных для пользовательской метрики"""
        # Получаем определение метрики из базы данных
        async with db_pool.acquire() as conn:
            metric_def = await conn.fetchrow(
                "SELECT id, name, description, category, calculation_method, aggregation_period, filters FROM analytics_metrics WHERE name = $1",
                metric_name
            )

        if not metric_def:
            return []

        # Используем определение метрики для выполнения соответствующего запроса
        # В реальной системе здесь будет более сложная логика в зависимости от calculation_method
        return []

    async def _generate_chart_data(self, metric_data: List[Dict[str, Any]], 
                                 chart_type: ChartType, title: str) -> Dict[str, Any]:
        """Генерация данных для диаграммы"""
        if chart_type == ChartType.LINE:
            return self._generate_line_chart_data(metric_data, title)
        elif chart_type == ChartType.BAR:
            return self._generate_bar_chart_data(metric_data, title)
        elif chart_type == ChartType.PIE:
            return self._generate_pie_chart_data(metric_data, title)
        elif chart_type == ChartType.SCATTER:
            return self._generate_scatter_chart_data(metric_data, title)
        elif chart_type == ChartType.HEATMAP:
            return self._generate_heatmap_data(metric_data, title)
        elif chart_type == ChartType.AREA:
            return self._generate_area_chart_data(metric_data, title)
        elif chart_type == ChartType.COLUMN:
            return self._generate_column_chart_data(metric_data, title)
        else:
            return self._generate_default_chart_data(metric_data, title)

    def _generate_line_chart_data(self, metric_data: List[Dict[str, Any]], title: str) -> Dict[str, Any]:
        """Генерация данных для линейной диаграммы"""
        timestamps = [item['timestamp'] for item in metric_data]
        values = [item.get('value') or item.get('avg_value', 0) for item in metric_data]

        return {
            'type': 'line',
            'title': title,
            'x_axis': timestamps,
            'y_axis': values,
            'data_points': len(metric_data)
        }

    def _generate_bar_chart_data(self, metric_data: List[Dict[str, Any]], title: str) -> Dict[str, Any]:
        """Генерация данных для столбчатой диаграммы"""
        labels = [item.get('label', item['timestamp']) for item in metric_data]
        values = [item.get('value') or item.get('avg_value', 0) for item in metric_data]

        return {
            'type': 'bar',
            'title': title,
            'labels': labels,
            'values': values,
            'data_points': len(metric_data)
        }

    def _generate_pie_chart_data(self, metric_data: List[Dict[str, Any]], title: str) -> Dict[str, Any]:
        """Генерация данных для круговой диаграммы"""
        # Рассчитываем проценты для распределения
        total = sum(item['count'] for item in metric_data)
        for item in metric_data:
            item['percentage'] = (item['count'] / total) * 100 if total > 0 else 0

        labels = [item['type'] for item in metric_data]
        values = [item['percentage'] for item in metric_data]
        counts = [item['count'] for item in metric_data]

        return {
            'type': 'pie',
            'title': title,
            'labels': labels,
            'values': values,
            'counts': counts,
            'data_points': len(metric_data)
        }

    async def _save_analytics_report(self, report: AnalyticsReport):
        """Сохранение отчета аналитики в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO analytics_reports (
                    id, title, description, type, format, frequency, filters,
                    metrics, charts, data, generated_at, scheduled_for, created_at, updated_at,
                    is_automatic, is_subscribed
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                """,
                report.id, report.title, report.description, report.type.value,
                report.format.value, report.frequency.value if report.frequency else None,
                json.dumps(report.filters), report.metrics,
                json.dumps(report.charts), json.dumps(report.data) if report.data else None,
                report.generated_at, report.scheduled_for, report.created_at,
                report.updated_at, report.is_automatic, report.is_subscribed
            )

    async def _cache_analytics_report(self, report: AnalyticsReport):
        """Кэширование отчета аналитики"""
        await redis_client.setex(f"analytics_report:{report.id}", 3600, report.model_dump_json())

    async def _calculate_next_schedule(self, current_time: datetime, 
                                     frequency: ReportFrequency) -> datetime:
        """Расчет времени следующего запуска отчета"""
        if frequency == ReportFrequency.HOURLY:
            return current_time + timedelta(hours=1)
        elif frequency == ReportFrequency.DAILY:
            next_day = current_time.date() + timedelta(days=1)
            return datetime.combine(next_day, current_time.time().replace(minute=0, second=0, microsecond=0))
        elif frequency == ReportFrequency.WEEKLY:
            next_week = current_time + timedelta(weeks=1)
            return next_week.replace(hour=0, minute=0, second=0, microsecond=0)
        elif frequency == ReportFrequency.MONTHLY:
            # Простая реализация - через 30 дней
            next_month = current_time + timedelta(days=30)
            return next_month.replace(hour=0, minute=0, second=0, microsecond=0)
        elif frequency == ReportFrequency.QUARTERLY:
            # Через 3 месяца
            next_quarter = current_time + timedelta(days=90)
            return next_quarter.replace(hour=0, minute=0, second=0, microsecond=0)
        elif frequency == ReportFrequency.YEARLY:
            # Через год
            next_year = current_time.replace(year=current_time.year + 1)
            return next_year.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            return current_time

    async def _schedule_report_generation(self, report: AnalyticsReport):
        """Планирование генерации отчета"""
        if not report.scheduled_for:
            return

        # Добавляем в очередь планировщика
        await redis_client.zadd(
            "scheduled_analytics_reports",
            {report.id: report.scheduled_for.timestamp()}
        )

    async def get_user_analytics(self, user_id: int, start_date: datetime,
                               end_date: datetime, metrics: List[str]) -> Dict[str, Any]:
        """Получение аналитики пользователя"""
        user_analytics = {}

        for metric in metrics:
            if metric == 'user_engagement':
                user_analytics[metric] = await self._get_user_engagement_data(user_id, start_date, end_date)
            elif metric == 'content_consumption':
                user_analytics[metric] = await self._get_user_content_consumption_data(user_id, start_date, end_date)
            elif metric == 'feature_usage':
                user_analytics[metric] = await self._get_user_feature_usage_data(user_id, start_date, end_date)
            else:
                user_analytics[metric] = await self._get_custom_user_metric_data(user_id, metric, start_date, end_date)

        return {
            'user_id': user_id,
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'metrics': user_analytics
        }

    async def _get_user_engagement_data(self, user_id: int, start_date: datetime,
                                      end_date: datetime) -> Dict[str, Any]:
        """Получение данных об участии пользователя"""
        async with db_pool.acquire() as conn:
            # Количество отправленных сообщений
            sent_messages = await conn.fetchval(
                """
                SELECT COUNT(*) FROM messages
                WHERE sender_id = $1 AND timestamp BETWEEN $2 AND $3
                """,
                user_id, start_date, end_date
            )

            # Количество полученных сообщений
            received_messages = await conn.fetchval(
                """
                SELECT COUNT(*) FROM messages m
                JOIN chat_participants cp ON m.chat_id = cp.chat_id
                WHERE cp.user_id = $1 AND m.sender_id != $1 AND m.timestamp BETWEEN $2 AND $3
                """,
                user_id, start_date, end_date
            )

            # Количество файлов, загруженных пользователем
            uploaded_files = await conn.fetchval(
                """
                SELECT COUNT(*) FROM files
                WHERE uploader_id = $1 AND uploaded_at BETWEEN $2 AND $3
                """,
                user_id, start_date, end_date
            )

            # Количество задач, созданных пользователем
            created_tasks = await conn.fetchval(
                """
                SELECT COUNT(*) FROM tasks
                WHERE creator_id = $1 AND created_at BETWEEN $2 AND $3
                """,
                user_id, start_date, end_date
            )

            # Количество задач, выполненных пользователем
            completed_tasks = await conn.fetchval(
                """
                SELECT COUNT(*) FROM tasks
                WHERE $1 = ANY(assignee_ids) AND status = 'completed' AND completed_at BETWEEN $2 AND $3
                """,
                user_id, start_date, end_date
            )

        return {
            'messages_sent': sent_messages or 0,
            'messages_received': received_messages or 0,
            'files_uploaded': uploaded_files or 0,
            'tasks_created': created_tasks or 0,
            'tasks_completed': completed_tasks or 0,
            'engagement_score': self._calculate_engagement_score(
                sent_messages or 0, received_messages or 0, uploaded_files or 0
            )
        }

    def _calculate_engagement_score(self, messages_sent: int, messages_received: int, 
                                  files_uploaded: int) -> float:
        """Расчет оценки участия пользователя"""
        # Простая формула расчета - в реальности может быть более сложной
        score = (messages_sent * 0.5 + messages_received * 0.3 + files_uploaded * 0.2)
        return min(score, 100.0)  # Ограничиваем максимальное значение

    async def _get_user_content_consumption_data(self, user_id: int, start_date: datetime,
                                               end_date: datetime) -> Dict[str, Any]:
        """Получение данных о потреблении контента пользователем"""
        async with db_pool.acquire() as conn:
            # Количество просмотров файлов
            file_views = await conn.fetchval(
                """
                SELECT COUNT(*) FROM file_access_log
                WHERE user_id = $1 AND access_type = 'view' AND accessed_at BETWEEN $2 AND $3
                """,
                user_id, start_date, end_date
            )

            # Количество скачиваний файлов
            file_downloads = await conn.fetchval(
                """
                SELECT COUNT(*) FROM file_access_log
                WHERE user_id = $1 AND access_type = 'download' AND accessed_at BETWEEN $2 AND $3
                """,
                user_id, start_date, end_date
            )

            # Количество просмотров медиа
            media_views = await conn.fetchval(
                """
                SELECT COUNT(*) FROM media_access_log
                WHERE user_id = $1 AND accessed_at BETWEEN $2 AND $3
                """,
                user_id, start_date, end_date
            )

        return {
            'file_views': file_views or 0,
            'file_downloads': file_downloads or 0,
            'media_views': media_views or 0,
            'consumption_ratio': (file_downloads or 0) / ((file_views or 1) + (file_downloads or 0)) * 100
        }

    async def _get_user_feature_usage_data(self, user_id: int, start_date: datetime,
                                         end_date: datetime) -> Dict[str, Any]:
        """Получение данных об использовании функций пользователем"""
        async with db_pool.acquire() as conn:
            # Использование чатов
            chat_usage = await conn.fetchrow(
                """
                SELECT COUNT(DISTINCT chat_id) as unique_chats,
                       COUNT(*) as total_messages
                FROM messages
                WHERE sender_id = $1 AND timestamp BETWEEN $2 AND $3
                """,
                user_id, start_date, end_date
            )

            # Использование голосований
            poll_participation = await conn.fetchval(
                """
                SELECT COUNT(*) FROM poll_votes
                WHERE user_id = $1 AND voted_at BETWEEN $2 AND $3
                """,
                user_id, start_date, end_date
            )

            # Использование задач
            task_interactions = await conn.fetchval(
                """
                SELECT COUNT(*) FROM task_interactions
                WHERE user_id = $1 AND action IN ('create', 'update', 'complete') 
                AND created_at BETWEEN $2 AND $3
                """,
                user_id, start_date, end_date
            )

            # Использование календаря
            calendar_events = await conn.fetchval(
                """
                SELECT COUNT(*) FROM calendar_events
                WHERE creator_id = $1 AND created_at BETWEEN $2 AND $3
                """,
                user_id, start_date, end_date
            )

        return {
            'unique_chats_used': chat_usage['unique_chats'] or 0,
            'messages_sent': chat_usage['total_messages'] or 0,
            'polls_participated': poll_participation or 0,
            'tasks_interacted': task_interactions or 0,
            'calendar_events_created': calendar_events or 0
        }

    async def _get_custom_user_metric_data(self, user_id: int, metric_name: str,
                                         start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Получение данных для пользовательской метрики пользователя"""
        # В реальной системе здесь будет специфическая логика для каждой метрики
        return {}

    async def generate_visualization(self, data: List[Dict[str, Any]], 
                                   chart_type: ChartType, title: str,
                                   format: ReportFormat = ReportFormat.IMAGE) -> str:
        """Генерация визуализации данных"""
        if format == ReportFormat.IMAGE:
            return await self._generate_chart_image(data, chart_type, title)
        elif format == ReportFormat.HTML:
            return await self._generate_chart_html(data, chart_type, title)
        else:
            # Для других форматов возвращаем JSON с данными
            return json.dumps({
                'type': chart_type.value,
                'title': title,
                'data': data
            })

    async def _generate_chart_image(self, data: List[Dict[str, Any]], 
                                  chart_type: ChartType, title: str) -> str:
        """Генерация изображения диаграммы"""
        try:
            # Подготовка данных
            if chart_type == ChartType.LINE:
                x_values = [item['timestamp'] for item in data]
                y_values = [item.get('value') or item.get('avg_value', 0) for item in data]
                
                plt.figure(figsize=(12, 6))
                plt.plot(x_values, y_values, marker='o')
                plt.title(title)
                plt.xlabel('Time')
                plt.ylabel('Value')
                plt.xticks(rotation=45)
                plt.tight_layout()
                
            elif chart_type == ChartType.BAR:
                labels = [item.get('label', item['timestamp']) for item in data]
                values = [item.get('value') or item.get('avg_value', 0) for item in data]
                
                plt.figure(figsize=(12, 6))
                plt.bar(labels, values)
                plt.title(title)
                plt.xlabel('Category')
                plt.ylabel('Value')
                plt.xticks(rotation=45)
                plt.tight_layout()
                
            elif chart_type == ChartType.PIE:
                labels = [item['type'] for item in data]
                sizes = [item['percentage'] for item in data]
                
                plt.figure(figsize=(8, 8))
                plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
                plt.title(title)
                plt.axis('equal')
                
            elif chart_type == ChartType.AREA:
                x_values = [item['timestamp'] for item in data]
                y_values = [item.get('value') or item.get('avg_value', 0) for item in data]
                
                plt.figure(figsize=(12, 6))
                plt.fill_between(x_values, y_values, alpha=0.3)
                plt.plot(x_values, y_values)
                plt.title(title)
                plt.xlabel('Time')
                plt.ylabel('Value')
                plt.xticks(rotation=45)
                plt.tight_layout()

            # Сохраняем в байтовый буфер
            buf = BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            
            # Конвертируем в base64
            image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            plt.close()  # Закрываем фигуру, чтобы освободить память
            
            return f"data:image/png;base64,{image_base64}"
            
        except Exception as e:
            logger.error(f"Error generating chart image: {e}")
            return ""

    async def _generate_chart_html(self, data: List[Dict[str, Any]], 
                                 chart_type: ChartType, title: str) -> str:
        """Генерация HTML диаграммы"""
        # В реальной системе здесь будет генерация HTML с использованием библиотеки типа Plotly
        # или другого инструмента визуализации
        return f"<div><h3>{title}</h3><p>Chart data: {json.dumps(data)}</p></div>"

    async def get_business_intelligence_metrics(self, start_date: datetime,
                                              end_date: datetime) -> Dict[str, Any]:
        """Получение метрик бизнес-аналитики"""
        async with db_pool.acquire() as conn:
            # Количество новых пользователей
            new_users = await conn.fetchval(
                """
                SELECT COUNT(*) FROM users
                WHERE created_at BETWEEN $1 AND $2
                """,
                start_date, end_date
            )

            # Количество активных пользователей
            active_users = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT user_id) FROM user_activities
                WHERE timestamp BETWEEN $1 AND $2
                """,
                start_date, end_date
            )

            # Количество новых чатов
            new_chats = await conn.fetchval(
                """
                SELECT COUNT(*) FROM chats
                WHERE created_at BETWEEN $1 AND $2
                """,
                start_date, end_date
            )

            # Количество отправленных сообщений
            sent_messages = await conn.fetchval(
                """
                SELECT COUNT(*) FROM messages
                WHERE timestamp BETWEEN $1 AND $2
                """,
                start_date, end_date
            )

            # Количество загруженных файлов
            uploaded_files = await conn.fetchval(
                """
                SELECT COUNT(*) FROM files
                WHERE uploaded_at BETWEEN $1 AND $2
                """,
                start_date, end_date
            )

            # Среднее время отклика системы
            avg_response_time = await conn.fetchval(
                """
                SELECT AVG(response_time) FROM system_performance
                WHERE timestamp BETWEEN $1 AND $2
                """,
                start_date, end_date
            )

        return {
            'new_users': new_users or 0,
            'active_users': active_users or 0,
            'new_chats': new_chats or 0,
            'sent_messages': sent_messages or 0,
            'uploaded_files': uploaded_files or 0,
            'avg_response_time_ms': float(avg_response_time) if avg_response_time else 0,
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            }
        }

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
advanced_analytics_service = AdvancedAnalyticsService()
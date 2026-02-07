# Analytics and Reporting System
# File: services/analytics_service/analytics_reporting.py

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

class ReportType(Enum):
    USER_ACTIVITY = "user_activity"
    CHAT_STATISTICS = "chat_statistics"
    MESSAGE_ANALYTICS = "message_analytics"
    FILE_USAGE = "file_usage"
    TASK_PERFORMANCE = "task_performance"
    POLL_RESULTS = "poll_results"
    SYSTEM_PERFORMANCE = "system_performance"
    CUSTOM = "custom"

class ReportFormat(Enum):
    JSON = "json"
    CSV = "csv"
    PDF = "pdf"
    EXCEL = "excel"
    IMAGE = "image"

class ReportFrequency(Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"

class AnalyticsMetric(Enum):
    # Метрики пользовательской активности
    MESSAGES_SENT = "messages_sent"
    MESSAGES_RECEIVED = "messages_received"
    CHATS_JOINED = "chats_joined"
    FILES_SHARED = "files_shared"
    TASKS_CREATED = "tasks_created"
    TASKS_COMPLETED = "tasks_completed"
    POLLS_PARTICIPATED = "polls_participated"
    LOGIN_COUNT = "login_count"
    SESSION_DURATION = "session_duration"
    
    # Метрики производительности
    RESPONSE_TIME = "response_time"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"
    CONCURRENT_USERS = "concurrent_users"
    DATABASE_LATENCY = "database_latency"
    
    # Метрики контента
    CONTENT_SHARING_RATE = "content_sharing_rate"
    MEDIA_CONSUMPTION = "media_consumption"
    LINK_CLICK_RATE = "link_click_rate"

class Report(BaseModel):
    id: str
    user_id: int
    report_type: ReportType
    title: str
    description: str
    filters: Dict[str, Any]  # Фильтры для генерации отчета
    metrics: List[AnalyticsMetric]  # Метрики для включения в отчет
    frequency: Optional[ReportFrequency] = None  # Для автоматических отчетов
    format: ReportFormat
    data: Optional[Dict[str, Any]] = None  # Сгенерированные данные отчета
    generated_at: Optional[datetime] = None
    scheduled_for: Optional[datetime] = None
    created_at: datetime = None
    updated_at: datetime = None
    is_automatic: bool = False
    is_subscribed: bool = False

class UserActivity(BaseModel):
    user_id: int
    metric: AnalyticsMetric
    value: float
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None

class SystemPerformance(BaseModel):
    metric: AnalyticsMetric
    value: float
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None

class AnalyticsService:
    def __init__(self):
        self.cache_ttl = 3600  # 1 час кэширования
        self.aggregation_intervals = {
            'hourly': timedelta(hours=1),
            'daily': timedelta(days=1),
            'weekly': timedelta(weeks=1),
            'monthly': timedelta(days=30)
        }

    async def track_user_activity(self, user_id: int, metric: AnalyticsMetric, 
                                 value: float, metadata: Optional[Dict] = None):
        """Отслеживание активности пользователя"""
        activity = UserActivity(
            user_id=user_id,
            metric=metric,
            value=value,
            timestamp=datetime.utcnow(),
            metadata=metadata
        )

        # Сохраняем в базу данных
        await self._save_user_activity(activity)

        # Кэшируем для быстрого доступа
        await self._cache_user_activity(activity)

        # Обновляем агрегированные метрики
        await self._update_aggregated_metrics(activity)

    async def track_system_performance(self, metric: AnalyticsMetric, 
                                      value: float, metadata: Optional[Dict] = None):
        """Отслеживание метрик производительности системы"""
        perf_data = SystemPerformance(
            metric=metric,
            value=value,
            timestamp=datetime.utcnow(),
            metadata=metadata
        )

        # Сохраняем в базу данных
        await self._save_system_performance(perf_data)

        # Кэшируем для быстрого доступа
        await self._cache_system_performance(perf_data)

        # Обновляем агрегированные метрики
        await self._update_aggregated_system_metrics(perf_data)

    async def generate_report(self, user_id: int, report_type: ReportType,
                             filters: Dict[str, Any], metrics: List[AnalyticsMetric],
                             format: ReportFormat = ReportFormat.JSON,
                             title: str = "", description: str = "") -> Optional[Report]:
        """Генерация отчета"""
        report_id = str(uuid.uuid4())

        report = Report(
            id=report_id,
            user_id=user_id,
            report_type=report_type,
            title=title or f"{report_type.value.replace('_', ' ').title()} Report",
            description=description,
            filters=filters,
            metrics=metrics,
            format=format,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Генерируем данные отчета
        report_data = await self._generate_report_data(report)
        report.data = report_data
        report.generated_at = datetime.utcnow()

        # Сохраняем отчет
        await self._save_report(report)

        # Кэшируем отчет
        await self._cache_report(report)

        return report

    async def _generate_report_data(self, report: Report) -> Dict[str, Any]:
        """Генерация данных для отчета"""
        data = {}

        if report.report_type == ReportType.USER_ACTIVITY:
            data = await self._generate_user_activity_data(report)
        elif report.report_type == ReportType.CHAT_STATISTICS:
            data = await self._generate_chat_statistics_data(report)
        elif report.report_type == ReportType.MESSAGE_ANALYTICS:
            data = await self._generate_message_analytics_data(report)
        elif report.report_type == ReportType.FILE_USAGE:
            data = await self._generate_file_usage_data(report)
        elif report.report_type == ReportType.TASK_PERFORMANCE:
            data = await self._generate_task_performance_data(report)
        elif report.report_type == ReportType.POLL_RESULTS:
            data = await self._generate_poll_results_data(report)
        elif report.report_type == ReportType.SYSTEM_PERFORMANCE:
            data = await self._generate_system_performance_data(report)
        elif report.report_type == ReportType.CUSTOM:
            data = await self._generate_custom_report_data(report)

        return data

    async def _generate_user_activity_data(self, report: Report) -> Dict[str, Any]:
        """Генерация данных об активности пользователей"""
        filters = report.filters
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        user_ids = filters.get('user_ids', [])

        # Формируем SQL запрос
        sql_conditions = ["ua.timestamp BETWEEN $1 AND $2"]
        params = [start_date, end_date]
        param_idx = 3

        if user_ids:
            sql_conditions.append(f"ua.user_id = ANY(${'$'.join([str(i) for i in range(param_idx, param_idx + len(user_ids))])})")
            params.extend(user_ids)
            param_idx += len(user_ids)

        where_clause = " AND ".join(sql_conditions)
        sql_query = f"""
            SELECT ua.user_id, u.username, ua.metric, SUM(ua.value) as total_value,
                   COUNT(*) as record_count, AVG(ua.value) as avg_value,
                   MIN(ua.timestamp) as first_activity, MAX(ua.timestamp) as last_activity
            FROM user_activities ua
            JOIN users u ON ua.user_id = u.id
            WHERE {where_clause}
            GROUP BY ua.user_id, u.username, ua.metric
            ORDER BY ua.user_id, ua.metric
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        # Группируем данные
        user_data = {}
        for row in rows:
            user_id = row['user_id']
            metric = row['metric']
            
            if user_id not in user_data:
                user_data[user_id] = {
                    'username': row['username'],
                    'metrics': {},
                    'first_activity': row['first_activity'],
                    'last_activity': row['last_activity']
                }
            
            user_data[user_id]['metrics'][metric] = {
                'total_value': float(row['total_value']),
                'record_count': row['record_count'],
                'avg_value': float(row['avg_value'])
            }

        # Добавляем временные ряды если запрошено
        if filters.get('include_timeseries', False):
            timeseries_sql = f"""
                SELECT ua.user_id, ua.metric, DATE_TRUNC('day', ua.timestamp) as day,
                       SUM(ua.value) as daily_value
                FROM user_activities ua
                WHERE {where_clause}
                GROUP BY ua.user_id, ua.metric, DATE_TRUNC('day', ua.timestamp)
                ORDER BY ua.user_id, ua.metric, day
            """
            
            timeseries_rows = await conn.fetch(timeseries_sql, *params)
            
            for row in timeseries_rows:
                user_id = row['user_id']
                metric = row['metric']
                day = row['day'].isoformat()
                value = float(row['daily_value'])
                
                if 'timeseries' not in user_data[user_id]:
                    user_data[user_id]['timeseries'] = {}
                
                if metric not in user_data[user_id]['timeseries']:
                    user_data[user_id]['timeseries'][metric] = {}
                
                user_data[user_id]['timeseries'][metric][day] = value

        return {
            'users': user_data,
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'total_users': len(user_data)
        }

    async def _generate_chat_statistics_data(self, report: Report) -> Dict[str, Any]:
        """Генерация статистики по чатам"""
        filters = report.filters
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        chat_ids = filters.get('chat_ids', [])

        # Формируем SQL запрос
        sql_conditions = ["m.timestamp BETWEEN $1 AND $2"]
        params = [start_date, end_date]
        param_idx = 3

        if chat_ids:
            sql_conditions.append(f"m.chat_id = ANY(${'$'.join([str(i) for i in range(param_idx, param_idx + len(chat_ids))])})")
            params.extend(chat_ids)
            param_idx += len(chat_ids)

        where_clause = " AND ".join(sql_conditions)
        sql_query = f"""
            SELECT m.chat_id, c.name as chat_name, c.type as chat_type,
                   COUNT(m.id) as message_count,
                   COUNT(DISTINCT m.sender_id) as unique_senders,
                   COUNT(DISTINCT f.id) as file_count,
                   AVG(EXTRACT(EPOCH FROM (m.timestamp - lag(m.timestamp) OVER (PARTITION BY m.chat_id ORDER BY m.timestamp)))) as avg_response_time
            FROM messages m
            JOIN chats c ON m.chat_id = c.id
            LEFT JOIN files f ON f.chat_id = m.chat_id AND f.uploaded_at BETWEEN $1 AND $2
            WHERE {where_clause}
            GROUP BY m.chat_id, c.name, c.type
            ORDER BY message_count DESC
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        chat_data = {}
        for row in rows:
            chat_data[row['chat_id']] = {
                'name': row['chat_name'],
                'type': row['chat_type'],
                'message_count': row['message_count'],
                'unique_senders': row['unique_senders'],
                'file_count': row['file_count'],
                'avg_response_time': float(row['avg_response_time']) if row['avg_response_time'] else 0
            }

        return {
            'chats': chat_data,
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'total_chats': len(chat_data)
        }

    async def _generate_message_analytics_data(self, report: Report) -> Dict[str, Any]:
        """Генерация аналитики сообщений"""
        filters = report.filters
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        user_ids = filters.get('user_ids', [])
        chat_ids = filters.get('chat_ids', [])

        # Формируем SQL запрос
        sql_conditions = ["m.timestamp BETWEEN $1 AND $2"]
        params = [start_date, end_date]
        param_idx = 3

        if user_ids:
            sql_conditions.append(f"m.sender_id = ANY(${'$'.join([str(i) for i in range(param_idx, param_idx + len(user_ids))])})")
            params.extend(user_ids)
            param_idx += len(user_ids)

        if chat_ids:
            sql_conditions.append(f"m.chat_id = ANY(${'$'.join([str(i) for i in range(param_idx, param_idx + len(chat_ids))])})")
            params.extend(chat_ids)
            param_idx += len(chat_ids)

        where_clause = " AND ".join(sql_conditions)
        sql_query = f"""
            SELECT 
                COUNT(m.id) as total_messages,
                COUNT(CASE WHEN LENGTH(m.content) > 100 THEN 1 END) as long_messages,
                COUNT(CASE WHEN LENGTH(m.content) < 10 THEN 1 END) as short_messages,
                AVG(LENGTH(m.content)) as avg_message_length,
                COUNT(DISTINCT m.sender_id) as unique_senders,
                COUNT(DISTINCT m.chat_id) as unique_chats,
                DATE_TRUNC('hour', m.timestamp) as hour,
                COUNT(*) as messages_per_hour
            FROM messages m
            WHERE {where_clause}
            GROUP BY DATE_TRUNC('hour', m.timestamp)
            ORDER BY hour
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        total_messages = sum(row['total_messages'] for row in rows) if rows else 0
        avg_length = sum(row['avg_message_length'] for row in rows if row['avg_message_length']) / len([r for r in rows if r['avg_message_length']]) if rows else 0

        hourly_data = {}
        for row in rows:
            hour_key = row['hour'].isoformat()
            hourly_data[hour_key] = row['messages_per_hour']

        return {
            'total_messages': total_messages,
            'avg_message_length': avg_length,
            'long_messages_count': sum(row['long_messages'] for row in rows) if rows else 0,
            'short_messages_count': sum(row['short_messages'] for row in rows) if rows else 0,
            'unique_senders': sum(row['unique_senders'] for row in rows) if rows else 0,
            'unique_chats': sum(row['unique_chats'] for row in rows) if rows else 0,
            'hourly_distribution': hourly_data,
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            }
        }

    async def _generate_file_usage_data(self, report: Report) -> Dict[str, Any]:
        """Генерация данных об использовании файлов"""
        filters = report.filters
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        user_ids = filters.get('user_ids', [])
        chat_ids = filters.get('chat_ids', [])

        # Формируем SQL запрос
        sql_conditions = ["f.uploaded_at BETWEEN $1 AND $2"]
        params = [start_date, end_date]
        param_idx = 3

        if user_ids:
            sql_conditions.append(f"f.uploader_id = ANY(${'$'.join([str(i) for i in range(param_idx, param_idx + len(user_ids))])})")
            params.extend(user_ids)
            param_idx += len(user_ids)

        if chat_ids:
            sql_conditions.append(f"f.chat_id = ANY(${'$'.join([str(i) for i in range(param_idx, param_idx + len(chat_ids))])})")
            params.extend(chat_ids)
            param_idx += len(chat_ids)

        where_clause = " AND ".join(sql_conditions)
        sql_query = f"""
            SELECT 
                COUNT(f.id) as total_files,
                SUM(f.size) as total_size,
                AVG(f.size) as avg_file_size,
                COUNT(DISTINCT f.uploader_id) as unique_uploaders,
                COUNT(DISTINCT f.chat_id) as unique_chats,
                f.mime_type,
                COUNT(*) as files_by_type
            FROM files f
            WHERE {where_clause}
            GROUP BY f.mime_type
            ORDER BY files_by_type DESC
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        total_files = sum(row['total_files'] for row in rows) if rows else 0
        total_size = sum(row['total_size'] for row in rows) if rows else 0
        avg_size = sum(row['avg_file_size'] for row in rows if row['avg_file_size']) / len([r for r in rows if r['avg_file_size']]) if rows else 0

        file_types = {}
        for row in rows:
            file_types[row['mime_type']] = {
                'count': row['files_by_type'],
                'total_size': row['total_size']
            }

        return {
            'total_files': total_files,
            'total_size': total_size,
            'avg_file_size': avg_size,
            'unique_uploaders': sum(row['unique_uploaders'] for row in rows) if rows else 0,
            'unique_chats': sum(row['unique_chats'] for row in rows) if rows else 0,
            'file_types': file_types,
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            }
        }

    async def _generate_task_performance_data(self, report: Report) -> Dict[str, Any]:
        """Генерация данных о производительности задач"""
        filters = report.filters
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        user_ids = filters.get('user_ids', [])
        project_ids = filters.get('project_ids', [])

        # Формируем SQL запрос
        sql_conditions = ["t.created_at BETWEEN $1 AND $2"]
        params = [start_date, end_date]
        param_idx = 3

        if user_ids:
            sql_conditions.append(f"(t.creator_id = ANY(${'$'.join([str(i) for i in range(param_idx, param_idx + len(user_ids))])}) OR $param_idx = ANY(t.assignee_ids))")
            params.extend(user_ids)
            param_idx += 1

        if project_ids:
            sql_conditions.append(f"t.project_id = ANY(${'$'.join([str(i) for i in range(param_idx, param_idx + len(project_ids))])})")
            params.extend(project_ids)
            param_idx += len(project_ids)

        where_clause = " AND ".join(sql_conditions)
        sql_query = f"""
            SELECT 
                COUNT(t.id) as total_tasks,
                COUNT(CASE WHEN t.status = 'done' THEN 1 END) as completed_tasks,
                COUNT(CASE WHEN t.status = 'in_progress' THEN 1 END) as in_progress_tasks,
                COUNT(CASE WHEN t.status = 'todo' THEN 1 END) as todo_tasks,
                AVG(EXTRACT(EPOCH FROM (t.completed_at - t.created_at))) as avg_completion_time,
                t.priority,
                COUNT(*) as tasks_by_priority
            FROM tasks t
            WHERE {where_clause}
            GROUP BY t.priority
            ORDER BY t.priority
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        total_tasks = sum(row['total_tasks'] for row in rows) if rows else 0
        completed_tasks = sum(row['completed_tasks'] for row in rows) if rows else 0
        in_progress_tasks = sum(row['in_progress_tasks'] for row in rows) if rows else 0
        todo_tasks = sum(row['todo_tasks'] for row in rows) if rows else 0
        avg_completion_time = sum(row['avg_completion_time'] for row in rows if row['avg_completion_time']) / len([r for r in rows if r['avg_completion_time']]) if rows else 0

        priority_breakdown = {}
        for row in rows:
            priority_breakdown[row['priority']] = row['tasks_by_priority']

        return {
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'completion_rate': completed_tasks / total_tasks if total_tasks > 0 else 0,
            'in_progress_tasks': in_progress_tasks,
            'todo_tasks': todo_tasks,
            'avg_completion_time': avg_completion_time,
            'priority_breakdown': priority_breakdown,
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            }
        }

    async def _generate_poll_results_data(self, report: Report) -> Dict[str, Any]:
        """Генерация данных о результатах опросов"""
        filters = report.filters
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        user_ids = filters.get('user_ids', [])
        chat_ids = filters.get('chat_ids', [])

        # Формируем SQL запрос
        sql_conditions = ["p.created_at BETWEEN $1 AND $2"]
        params = [start_date, end_date]
        param_idx = 3

        if user_ids:
            sql_conditions.append(f"p.creator_id = ANY(${'$'.join([str(i) for i in range(param_idx, param_idx + len(user_ids))])})")
            params.extend(user_ids)
            param_idx += len(user_ids)

        if chat_ids:
            sql_conditions.append(f"p.chat_id = ANY(${'$'.join([str(i) for i in range(param_idx, param_idx + len(chat_ids))])})")
            params.extend(chat_ids)
            param_idx += len(chat_ids)

        where_clause = " AND ".join(sql_conditions)
        sql_query = f"""
            SELECT 
                COUNT(p.id) as total_polls,
                COUNT(CASE WHEN p.status = 'closed' THEN 1 END) as closed_polls,
                AVG(p.total_votes) as avg_votes_per_poll,
                p.type as poll_type,
                COUNT(*) as polls_by_type
            FROM polls p
            WHERE {where_clause}
            GROUP BY p.type
            ORDER BY polls_by_type DESC
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        total_polls = sum(row['total_polls'] for row in rows) if rows else 0
        closed_polls = sum(row['closed_polls'] for row in rows) if rows else 0
        avg_votes = sum(row['avg_votes_per_poll'] for row in rows if row['avg_votes_per_poll']) / len([r for r in rows if r['avg_votes_per_poll']]) if rows else 0

        type_breakdown = {}
        for row in rows:
            type_breakdown[row['poll_type']] = row['polls_by_type']

        return {
            'total_polls': total_polls,
            'closed_polls': closed_polls,
            'participation_rate': closed_polls / total_polls if total_polls > 0 else 0,
            'avg_votes_per_poll': avg_votes,
            'type_breakdown': type_breakdown,
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            }
        }

    async def _generate_system_performance_data(self, report: Report) -> Dict[str, Any]:
        """Генерация данных о производительности системы"""
        filters = report.filters
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=7))
        end_date = filters.get('end_date', datetime.utcnow())
        metrics = filters.get('metrics', [])

        # Формируем SQL запрос
        sql_conditions = ["sp.timestamp BETWEEN $1 AND $2"]
        params = [start_date, end_date]
        param_idx = 3

        if metrics:
            sql_conditions.append(f"sp.metric = ANY(${'$'.join([str(i) for i in range(param_idx, param_idx + len(metrics))])})")
            params.extend(metrics)
            param_idx += len(metrics)

        where_clause = " AND ".join(sql_conditions)
        sql_query = f"""
            SELECT 
                sp.metric,
                AVG(sp.value) as avg_value,
                MIN(sp.value) as min_value,
                MAX(sp.value) as max_value,
                STDDEV(sp.value) as stddev_value,
                COUNT(*) as sample_count
            FROM system_performance sp
            WHERE {where_clause}
            GROUP BY sp.metric
            ORDER BY sp.metric
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        performance_data = {}
        for row in rows:
            performance_data[row['metric']] = {
                'avg_value': float(row['avg_value']) if row['avg_value'] else 0,
                'min_value': float(row['min_value']) if row['min_value'] else 0,
                'max_value': float(row['max_value']) if row['max_value'] else 0,
                'stddev_value': float(row['stddev_value']) if row['stddev_value'] else 0,
                'sample_count': row['sample_count']
            }

        return {
            'performance_metrics': performance_data,
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            }
        }

    async def _generate_custom_report_data(self, report: Report) -> Dict[str, Any]:
        """Генерация пользовательского отчета"""
        # Для пользовательских отчетов используем специфические фильтры
        custom_query = report.filters.get('custom_query', '')
        query_params = report.filters.get('query_params', [])

        if custom_query:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch(custom_query, *query_params)

            # Преобразуем результаты в словарь
            result_data = []
            for row in rows:
                result_data.append(dict(row))

            return {
                'custom_data': result_data,
                'row_count': len(result_data)
            }
        else:
            return {'error': 'No custom query provided'}

    async def _save_user_activity(self, activity: UserActivity):
        """Сохранение активности пользователя в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_activities (
                    user_id, metric, value, timestamp, metadata
                ) VALUES ($1, $2, $3, $4, $5)
                """,
                activity.user_id, activity.metric.value, activity.value,
                activity.timestamp, json.dumps(activity.metadata) if activity.metadata else None
            )

    async def _save_system_performance(self, perf_data: SystemPerformance):
        """Сохранение метрик производительности в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO system_performance (
                    metric, value, timestamp, metadata
                ) VALUES ($1, $2, $3, $4)
                """,
                perf_data.metric.value, perf_data.value,
                perf_data.timestamp, json.dumps(perf_data.metadata) if perf_data.metadata else None
            )

    async def _save_report(self, report: Report):
        """Сохранение отчета в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO analytics_reports (
                    id, user_id, report_type, title, description, filters, metrics,
                    frequency, format, data, generated_at, scheduled_for, created_at, updated_at,
                    is_automatic, is_subscribed
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                """,
                report.id, report.user_id, report.report_type.value, report.title,
                report.description, json.dumps(report.filters),
                [m.value for m in report.metrics], 
                report.frequency.value if report.frequency else None,
                report.format.value, json.dumps(report.data) if report.data else None,
                report.generated_at, report.scheduled_for, report.created_at,
                report.updated_at, report.is_automatic, report.is_subscribed
            )

    async def _cache_user_activity(self, activity: UserActivity):
        """Кэширование активности пользователя"""
        cache_key = f"user_activity:{activity.user_id}:{activity.metric.value}:{activity.timestamp.strftime('%Y%m%d')}"
        await redis_client.setex(cache_key, self.cache_ttl, json.dumps({
            'value': activity.value,
            'timestamp': activity.timestamp.isoformat(),
            'metadata': activity.metadata
        }))

    async def _cache_system_performance(self, perf_data: SystemPerformance):
        """Кэширование метрик производительности"""
        cache_key = f"system_perf:{perf_data.metric.value}:{perf_data.timestamp.strftime('%Y%m%d%H')}"
        await redis_client.setex(cache_key, self.cache_ttl, json.dumps({
            'value': perf_data.value,
            'timestamp': perf_data.timestamp.isoformat(),
            'metadata': perf_data.metadata
        }))

    async def _cache_report(self, report: Report):
        """Кэширование отчета"""
        cache_key = f"report:{report.id}"
        await redis_client.setex(cache_key, self.cache_ttl * 24, report.model_dump_json())

    async def _update_aggregated_metrics(self, activity: UserActivity):
        """Обновление агрегированных метрик пользователя"""
        # Обновляем суточные метрики
        day_key = activity.timestamp.strftime('%Y%m%d')
        daily_key = f"daily_user_metrics:{activity.user_id}:{day_key}:{activity.metric.value}"
        
        await redis_client.incrbyfloat(daily_key, activity.value)
        await redis_client.expire(daily_key, 30 * 24 * 60 * 60)  # 30 дней

        # Обновляем общие метрики
        total_key = f"total_user_metrics:{activity.user_id}:{activity.metric.value}"
        await redis_client.incrbyfloat(total_key, activity.value)

    async def _update_aggregated_system_metrics(self, perf_data: SystemPerformance):
        """Обновление агрегированных метрик системы"""
        # Обновляем почасовые метрики
        hour_key = perf_data.timestamp.strftime('%Y%m%d%H')
        hourly_key = f"hourly_system_metrics:{hour_key}:{perf_data.metric.value}"
        
        await redis_client.incrbyfloat(hourly_key, perf_data.value)
        await redis_client.expire(hourly_key, 7 * 24 * 60 * 60)  # 7 дней

        # Обновляем средние значения
        avg_key = f"avg_system_metrics:{perf_data.metric.value}"
        count_key = f"avg_system_metrics_count:{perf_data.metric.value}"
        
        current_avg = await redis_client.get(avg_key)
        current_count = await redis_client.get(count_key)
        
        current_avg = float(current_avg) if current_avg else 0
        current_count = int(current_count) if current_count else 0
        
        new_count = current_count + 1
        new_avg = (current_avg * current_count + perf_data.value) / new_count
        
        await redis_client.set(avg_key, new_avg)
        await redis_client.set(count_key, new_count)

    async def get_user_analytics(self, user_id: int, 
                                start_date: datetime, 
                                end_date: datetime,
                                metrics: List[AnalyticsMetric]) -> Dict[str, Any]:
        """Получение аналитики пользователя"""
        # Сначала проверяем кэш
        cache_key = f"user_analytics:{user_id}:{start_date.strftime('%Y%m%d')}:{end_date.strftime('%Y%m%d')}"
        cached_data = await redis_client.get(cache_key)
        
        if cached_data:
            return json.loads(cached_data)

        # Если в кэше нет, получаем из базы данных
        result = {}
        
        for metric in metrics:
            sql_query = """
                SELECT SUM(value) as total_value, COUNT(*) as record_count, AVG(value) as avg_value
                FROM user_activities
                WHERE user_id = $1 AND metric = $2 AND timestamp BETWEEN $3 AND $4
            """
            
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(sql_query, user_id, metric.value, start_date, end_date)
            
            result[metric.value] = {
                'total_value': float(row['total_value']) if row['total_value'] else 0,
                'record_count': row['record_count'],
                'avg_value': float(row['avg_value']) if row['avg_value'] else 0
            }

        # Кэшируем результат
        await redis_client.setex(cache_key, self.cache_ttl, json.dumps(result))

        return result

    async def get_system_analytics(self, start_date: datetime, 
                                  end_date: datetime,
                                  metrics: List[AnalyticsMetric]) -> Dict[str, Any]:
        """Получение системной аналитики"""
        # Сначала проверяем кэш
        cache_key = f"system_analytics:{start_date.strftime('%Y%m%d')}:{end_date.strftime('%Y%m%d')}"
        cached_data = await redis_client.get(cache_key)
        
        if cached_data:
            return json.loads(cached_data)

        # Если в кэше нет, получаем из базы данных
        result = {}
        
        for metric in metrics:
            sql_query = """
                SELECT AVG(value) as avg_value, MIN(value) as min_value, 
                       MAX(value) as max_value, COUNT(*) as sample_count
                FROM system_performance
                WHERE metric = $1 AND timestamp BETWEEN $2 AND $3
            """
            
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(sql_query, metric.value, start_date, end_date)
            
            result[metric.value] = {
                'avg_value': float(row['avg_value']) if row['avg_value'] else 0,
                'min_value': float(row['min_value']) if row['min_value'] else 0,
                'max_value': float(row['max_value']) if row['max_value'] else 0,
                'sample_count': row['sample_count']
            }

        # Кэшируем результат
        await redis_client.setex(cache_key, self.cache_ttl, json.dumps(result))

        return result

    async def create_scheduled_report(self, user_id: int, report_type: ReportType,
                                     filters: Dict[str, Any], metrics: List[AnalyticsMetric],
                                     frequency: ReportFrequency, title: str = "",
                                     description: str = "", format: ReportFormat = ReportFormat.JSON) -> Optional[str]:
        """Создание запланированного отчета"""
        report_id = str(uuid.uuid4())

        report = Report(
            id=report_id,
            user_id=user_id,
            report_type=report_type,
            title=title or f"{report_type.value.replace('_', ' ').title()} Scheduled Report",
            description=description,
            filters=filters,
            metrics=metrics,
            frequency=frequency,
            format=format,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            is_automatic=True
        )

        # Рассчитываем следующее время генерации
        next_run = self._calculate_next_run(datetime.utcnow(), frequency)
        report.scheduled_for = next_run

        # Сохраняем отчет
        await self._save_report(report)

        # Добавляем в очередь планировщика
        await self._schedule_report_generation(report)

        return report_id

    def _calculate_next_run(self, current_time: datetime, frequency: ReportFrequency) -> datetime:
        """Расчет времени следующего запуска отчета"""
        if frequency == ReportFrequency.HOURLY:
            return current_time + timedelta(hours=1)
        elif frequency == ReportFrequency.DAILY:
            next_day = current_time.date() + timedelta(days=1)
            return datetime.combine(next_day, current_time.time()).replace(minute=0, second=0, microsecond=0)
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

    async def _schedule_report_generation(self, report: Report):
        """Планирование генерации отчета"""
        if report.scheduled_for:
            # Добавляем в очередь Redis
            await redis_client.zadd(
                "scheduled_reports_queue",
                {report.id: report.scheduled_for.timestamp()}
            )

    async def get_user_reports(self, user_id: int, 
                              report_type: Optional[ReportType] = None,
                              start_date: Optional[datetime] = None,
                              end_date: Optional[datetime] = None) -> List[Report]:
        """Получение отчетов пользователя"""
        conditions = ["user_id = $1"]
        params = [user_id]
        param_idx = 2

        if report_type:
            conditions.append(f"report_type = ${param_idx}")
            params.append(report_type.value)
            param_idx += 1

        if start_date:
            conditions.append(f"created_at >= ${param_idx}")
            params.append(start_date)
            param_idx += 1

        if end_date:
            conditions.append(f"created_at <= ${param_idx}")
            params.append(end_date)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, user_id, report_type, title, description, filters, metrics,
                   frequency, format, data, generated_at, scheduled_for, created_at, updated_at,
                   is_automatic, is_subscribed
            FROM analytics_reports
            WHERE {where_clause}
            ORDER BY created_at DESC
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        reports = []
        for row in rows:
            report = Report(
                id=row['id'],
                user_id=row['user_id'],
                report_type=ReportType(row['report_type']),
                title=row['title'],
                description=row['description'],
                filters=json.loads(row['filters']) if row['filters'] else {},
                metrics=[AnalyticsMetric(m) for m in row['metrics']] if row['metrics'] else [],
                frequency=ReportFrequency(row['frequency']) if row['frequency'] else None,
                format=ReportFormat(row['format']),
                data=json.loads(row['data']) if row['data'] else None,
                generated_at=row['generated_at'],
                scheduled_for=row['scheduled_for'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                is_automatic=row['is_automatic'],
                is_subscribed=row['is_subscribed']
            )
            reports.append(report)

        return reports

    async def generate_visualization(self, report_data: Dict[str, Any], 
                                   chart_type: str = "bar",
                                   title: str = "Analytics Visualization") -> str:
        """Генерация визуализации данных отчета"""
        try:
            # Подготовка данных для визуализации
            if 'users' in report_data:
                # Визуализация активности пользователей
                users_data = report_data['users']
                user_names = [data['username'] for data in users_data.values()]
                message_counts = [data['metrics'].get('messages_sent', {}).get('total_value', 0) for data in users_data.values()]
                
                plt.figure(figsize=(12, 6))
                if chart_type == "bar":
                    plt.bar(user_names, message_counts)
                elif chart_type == "line":
                    plt.plot(user_names, message_counts, marker='o')
                elif chart_type == "pie":
                    plt.pie(message_counts, labels=user_names, autopct='%1.1f%%')
                
                plt.title(title)
                plt.xlabel('Users')
                plt.ylabel('Message Count')
                plt.xticks(rotation=45)
                plt.tight_layout()
            
            elif 'chats' in report_data:
                # Визуализация статистики чатов
                chats_data = report_data['chats']
                chat_names = [data['name'] for data in chats_data.values()]
                message_counts = [data['message_count'] for data in chats_data.values()]
                
                plt.figure(figsize=(12, 6))
                if chart_type == "bar":
                    plt.bar(chat_names, message_counts)
                elif chart_type == "line":
                    plt.plot(chat_names, message_counts, marker='o')
                
                plt.title(title)
                plt.xlabel('Chats')
                plt.ylabel('Message Count')
                plt.xticks(rotation=45)
                plt.tight_layout()
            
            # Сохраняем график в байтовый буфер
            buf = BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            
            # Конвертируем в base64
            image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            plt.close()  # Закрываем фигуру, чтобы освободить память
            
            return f"data:image/png;base64,{image_base64}"
        
        except Exception as e:
            logger.error(f"Error generating visualization: {e}")
            return ""

# Глобальный экземпляр для использования в приложении
analytics_service = AnalyticsService()
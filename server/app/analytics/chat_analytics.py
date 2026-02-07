# server/app/analytics/chat_analytics.py
import asyncio
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import asyncpg
from dataclasses import dataclass
from enum import Enum
import logging
from collections import defaultdict, Counter
import matplotlib.pyplot as plt
import seaborn as sns
from io import BytesIO
import base64

logger = logging.getLogger(__name__)

class MetricType(Enum):
    MESSAGE_COUNT = "message_count"
    ACTIVE_USERS = "active_users"
    RESPONSE_TIME = "response_time"
    ENGAGEMENT_RATE = "engagement_rate"
    PEAK_HOURS = "peak_hours"
    TOP_CHANNELS = "top_channels"
    USER_RETENTION = "user_retention"
    SENTIMENT_ANALYSIS = "sentiment_analysis"

@dataclass
class TimeRange:
    start: datetime
    end: datetime

@dataclass
class AnalyticsResult:
    metric_type: MetricType
    data: Dict[str, Any]
    timestamp: datetime
    period: str  # daily, weekly, monthly, custom

class ChatAnalyticsManager:
    """Менеджер аналитики чатов"""
    
    def __init__(self, db_pool, redis_client):
        self.db_pool = db_pool
        self.redis = redis_client
        self.cache_ttl = 3600  # 1 час кэширования
        self.analytics_cache = {}
    
    async def get_message_statistics(self, chat_id: str, time_range: TimeRange) -> Dict[str, Any]:
        """Получение статистики сообщений для чата"""
        cache_key = f"message_stats:{chat_id}:{time_range.start}:{time_range.end}"
        
        # Проверяем кэш
        cached_result = await self._get_from_cache(cache_key)
        if cached_result:
            return cached_result
        
        query = """
            SELECT 
                COUNT(*) as total_messages,
                COUNT(DISTINCT sender_id) as unique_senders,
                AVG(LENGTH(content)) as avg_message_length,
                COUNT(*) FILTER (WHERE message_type = 'text') as text_messages,
                COUNT(*) FILTER (WHERE message_type = 'image') as image_messages,
                COUNT(*) FILTER (WHERE message_type = 'file') as file_messages,
                MIN(timestamp) as first_message,
                MAX(timestamp) as last_message
            FROM messages 
            WHERE chat_id = $1 
                AND timestamp BETWEEN $2 AND $3
        """
        
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, chat_id, time_range.start, time_range.end)
        
        result = {
            'total_messages': row['total_messages'] or 0,
            'unique_senders': row['unique_senders'] or 0,
            'avg_message_length': float(row['avg_message_length']) if row['avg_message_length'] else 0,
            'text_messages': row['text_messages'] or 0,
            'image_messages': row['image_messages'] or 0,
            'file_messages': row['file_messages'] or 0,
            'first_message': row['first_message'].isoformat() if row['first_message'] else None,
            'last_message': row['last_message'].isoformat() if row['last_message'] else None,
            'period_start': time_range.start.isoformat(),
            'period_end': time_range.end.isoformat()
        }
        
        # Кэшируем результат
        await self._set_to_cache(cache_key, result)
        
        return result
    
    async def get_active_users_statistics(self, chat_id: str, time_range: TimeRange) -> Dict[str, Any]:
        """Получение статистики активных пользователей"""
        cache_key = f"active_users_stats:{chat_id}:{time_range.start}:{time_range.end}"
        
        cached_result = await self._get_from_cache(cache_key)
        if cached_result:
            return cached_result
        
        # DAU (Daily Active Users) за период
        dau_query = """
            SELECT 
                DATE(timestamp) as date,
                COUNT(DISTINCT sender_id) as daily_active_users
            FROM messages 
            WHERE chat_id = $1 
                AND timestamp BETWEEN $2 AND $3
            GROUP BY DATE(timestamp)
            ORDER BY date
        """
        
        async with self.db_pool.acquire() as conn:
            dau_rows = await conn.fetch(dau_query, chat_id, time_range.start, time_range.end)
        
        dau_data = [(row['date'].isoformat(), row['daily_active_users']) for row in dau_rows]
        
        # WAU (Weekly Active Users)
        wau_query = """
            SELECT COUNT(DISTINCT sender_id) as weekly_active_users
            FROM messages 
            WHERE chat_id = $1 
                AND timestamp BETWEEN $2 AND $3
                AND timestamp >= $2 - INTERVAL '7 days'
        """
        
        wau_row = await conn.fetchrow(wau_query, chat_id, time_range.start, time_range.end)
        wau = wau_row['weekly_active_users'] or 0
        
        # MAU (Monthly Active Users)
        mau_query = """
            SELECT COUNT(DISTINCT sender_id) as monthly_active_users
            FROM messages 
            WHERE chat_id = $1 
                AND timestamp BETWEEN $2 AND $3
                AND timestamp >= $2 - INTERVAL '30 days'
        """
        
        mau_row = await conn.fetchrow(mau_query, chat_id, time_range.start, time_range.end)
        mau = mau_row['monthly_active_users'] or 0
        
        result = {
            'dau_data': dau_data,
            'wau': wau,
            'mau': mau,
            'period_start': time_range.start.isoformat(),
            'period_end': time_range.end.isoformat()
        }
        
        await self._set_to_cache(cache_key, result)
        
        return result
    
    async def get_response_time_analysis(self, chat_id: str, time_range: TimeRange) -> Dict[str, Any]:
        """Анализ времени ответа между сообщениями пользователей"""
        cache_key = f"response_time:{chat_id}:{time_range.start}:{time_range.end}"
        
        cached_result = await self._get_from_cache(cache_key)
        if cached_result:
            return cached_result
        
        query = """
            WITH ordered_messages AS (
                SELECT 
                    sender_id,
                    timestamp,
                    ROW_NUMBER() OVER (ORDER BY timestamp) as rn
                FROM messages 
                WHERE chat_id = $1 
                    AND timestamp BETWEEN $2 AND $3
            ),
            response_times AS (
                SELECT 
                    m1.sender_id as sender1,
                    m2.sender_id as sender2,
                    m2.timestamp - m1.timestamp as response_time
                FROM ordered_messages m1
                JOIN ordered_messages m2 ON m1.rn = m2.rn - 1
                WHERE m1.sender_id != m2.sender_id
            )
            SELECT 
                AVG(EXTRACT(EPOCH FROM response_time)) as avg_response_time_seconds,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM response_time)) as median_response_time_seconds,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM response_time)) as p95_response_time_seconds,
                MIN(EXTRACT(EPOCH FROM response_time)) as min_response_time_seconds,
                MAX(EXTRACT(EPOCH FROM response_time)) as max_response_time_seconds
            FROM response_times
        """
        
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, chat_id, time_range.start, time_range.end)
        
        result = {
            'avg_response_time_seconds': float(row['avg_response_time_seconds']) if row['avg_response_time_seconds'] else 0,
            'median_response_time_seconds': float(row['median_response_time_seconds']) if row['median_response_time_seconds'] else 0,
            'p95_response_time_seconds': float(row['p95_response_time_seconds']) if row['p95_response_time_seconds'] else 0,
            'min_response_time_seconds': float(row['min_response_time_seconds']) if row['min_response_time_seconds'] else 0,
            'max_response_time_seconds': float(row['max_response_time_seconds']) if row['max_response_time_seconds'] else 0,
            'period_start': time_range.start.isoformat(),
            'period_end': time_range.end.isoformat()
        }
        
        await self._set_to_cache(cache_key, result)
        
        return result
    
    async def get_engagement_metrics(self, chat_id: str, time_range: TimeRange) -> Dict[str, Any]:
        """Получение метрик вовлеченности"""
        cache_key = f"engagement:{chat_id}:{time_range.start}:{time_range.end}"
        
        cached_result = await self._get_from_cache(cache_key)
        if cached_result:
            return cached_result
        
        # Общая активность
        activity_query = """
            SELECT 
                COUNT(*) as total_messages,
                COUNT(DISTINCT sender_id) as unique_participants,
                COUNT(*) * 1.0 / COUNT(DISTINCT sender_id) as messages_per_user
            FROM messages 
            WHERE chat_id = $1 
                AND timestamp BETWEEN $2 AND $3
        """
        
        async with self.db_pool.acquire() as conn:
            activity_row = await conn.fetchrow(activity_query, chat_id, time_range.start, time_range.end)
        
        # Активность по дням недели
        weekday_query = """
            SELECT 
                EXTRACT(DOW FROM timestamp) as day_of_week,
                COUNT(*) as message_count
            FROM messages 
            WHERE chat_id = $1 
                AND timestamp BETWEEN $2 AND $3
            GROUP BY EXTRACT(DOW FROM timestamp)
            ORDER BY day_of_week
        """
        
        weekday_rows = await conn.fetch(weekday_query, chat_id, time_range.start, time_range.end)
        weekday_activity = {str(row['day_of_week']): row['message_count'] for row in weekday_rows}
        
        # Активность по часам
        hourly_query = """
            SELECT 
                EXTRACT(HOUR FROM timestamp) as hour,
                COUNT(*) as message_count
            FROM messages 
            WHERE chat_id = $1 
                AND timestamp BETWEEN $2 AND $3
            GROUP BY EXTRACT(HOUR FROM timestamp)
            ORDER BY hour
        """
        
        hourly_rows = await conn.fetch(hourly_query, chat_id, time_range.start, time_range.end)
        hourly_activity = {str(row['hour']): row['message_count'] for row in hourly_rows}
        
        result = {
            'total_messages': activity_row['total_messages'] or 0,
            'unique_participants': activity_row['unique_participants'] or 0,
            'messages_per_user': float(activity_row['messages_per_user']) if activity_row['messages_per_user'] else 0,
            'weekday_activity': weekday_activity,
            'hourly_activity': hourly_activity,
            'period_start': time_range.start.isoformat(),
            'period_end': time_range.end.isoformat()
        }
        
        await self._set_to_cache(cache_key, result)
        
        return result
    
    async def get_top_channels(self, time_range: TimeRange, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение топ чатов по активности"""
        cache_key = f"top_channels:{time_range.start}:{time_range.end}:{limit}"
        
        cached_result = await self._get_from_cache(cache_key)
        if cached_result:
            return cached_result
        
        query = """
            SELECT 
                chat_id,
                COUNT(*) as message_count,
                COUNT(DISTINCT sender_id) as unique_users,
                AVG(LENGTH(content)) as avg_message_length
            FROM messages 
            WHERE timestamp BETWEEN $1 AND $2
            GROUP BY chat_id
            ORDER BY message_count DESC
            LIMIT $3
        """
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, time_range.start, time_range.end, limit)
        
        result = [
            {
                'chat_id': row['chat_id'],
                'message_count': row['message_count'],
                'unique_users': row['unique_users'],
                'avg_message_length': float(row['avg_message_length']) if row['avg_message_length'] else 0
            }
            for row in rows
        ]
        
        await self._set_to_cache(cache_key, result)
        
        return result
    
    async def get_user_retention(self, time_range: TimeRange) -> Dict[str, Any]:
        """Анализ удержания пользователей"""
        cache_key = f"user_retention:{time_range.start}:{time_range.end}"
        
        cached_result = await self._get_from_cache(cache_key)
        if cached_result:
            return cached_result
        
        # Находим новых пользователей за первую неделю
        cohort_start = time_range.start
        cohort_end = cohort_start + timedelta(weeks=1)
        
        # Запрос для определения когорт
        query = """
            WITH new_users AS (
                SELECT DISTINCT sender_id
                FROM messages
                WHERE timestamp BETWEEN $1 AND $2
            ),
            retention_periods AS (
                SELECT 
                    nu.sender_id,
                    COUNT(DISTINCT DATE_TRUNC('week', m.timestamp)) as weeks_active
                FROM new_users nu
                LEFT JOIN messages m ON nu.sender_id = m.sender_id
                WHERE m.timestamp BETWEEN $1 AND $3
                GROUP BY nu.sender_id
            )
            SELECT 
                COUNT(*) as total_new_users,
                COUNT(*) FILTER (WHERE weeks_active >= 2) as retained_2w,
                COUNT(*) FILTER (WHERE weeks_active >= 4) as retained_4w,
                COUNT(*) FILTER (WHERE weeks_active >= 8) as retained_8w
            FROM retention_periods
        """
        
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, cohort_start, cohort_end, time_range.end)
        
        total_new = row['total_new_users'] or 0
        result = {
            'cohort_start': cohort_start.isoformat(),
            'cohort_end': cohort_end.isoformat(),
            'total_new_users': total_new,
            'retained_2w': row['retained_2w'] or 0,
            'retained_4w': row['retained_4w'] or 0,
            'retained_8w': row['retained_8w'] or 0,
            'retention_2w_rate': (row['retained_2w'] or 0) / total_new if total_new > 0 else 0,
            'retention_4w_rate': (row['retained_4w'] or 0) / total_new if total_new > 0 else 0,
            'retention_8w_rate': (row['retained_8w'] or 0) / total_new if total_new > 0 else 0,
            'period_end': time_range.end.isoformat()
        }
        
        await self._set_to_cache(cache_key, result)
        
        return result
    
    async def generate_analytics_report(self, chat_id: str, time_range: TimeRange) -> Dict[str, Any]:
        """Генерация полного отчета по аналитике чата"""
        # Получаем все метрики
        message_stats = await self.get_message_statistics(chat_id, time_range)
        active_users_stats = await self.get_active_users_statistics(chat_id, time_range)
        engagement_metrics = await self.get_engagement_metrics(chat_id, time_range)
        response_time = await self.get_response_time_analysis(chat_id, time_range)
        
        # Собираем отчет
        report = {
            'chat_id': chat_id,
            'period': {
                'start': time_range.start.isoformat(),
                'end': time_range.end.isoformat()
            },
            'message_statistics': message_stats,
            'active_users_statistics': active_users_stats,
            'engagement_metrics': engagement_metrics,
            'response_time_analysis': response_time,
            'generated_at': datetime.utcnow().isoformat()
        }
        
        return report
    
    async def get_analytics_dashboard_data(self, time_range: TimeRange) -> Dict[str, Any]:
        """Получение данных для аналитической панели"""
        # Получаем основные метрики
        top_channels = await self.get_top_channels(time_range, limit=5)
        user_retention = await self.get_user_retention(time_range)
        
        # Общая статистика по всем чатам
        total_messages_query = """
            SELECT 
                COUNT(*) as total_messages,
                COUNT(DISTINCT sender_id) as total_active_users,
                COUNT(DISTINCT chat_id) as total_chats
            FROM messages 
            WHERE timestamp BETWEEN $1 AND $2
        """
        
        async with self.db_pool.acquire() as conn:
            total_row = await conn.fetchrow(total_messages_query, time_range.start, time_range.end)
        
        dashboard_data = {
            'total_messages': total_row['total_messages'] or 0,
            'total_active_users': total_row['total_active_users'] or 0,
            'total_chats': total_row['total_chats'] or 0,
            'top_channels': top_channels,
            'user_retention': user_retention,
            'period': {
                'start': time_range.start.isoformat(),
                'end': time_range.end.isoformat()
            }
        }
        
        return dashboard_data
    
    async def _get_from_cache(self, key: str) -> Optional[Any]:
        """Получение данных из кэша"""
        if key in self.analytics_cache:
            data, timestamp = self.analytics_cache[key]
            if datetime.utcnow().timestamp() - timestamp < self.cache_ttl:
                return data
            else:
                # Удаляем просроченные данные
                del self.analytics_cache[key]
        return None
    
    async def _set_to_cache(self, key: str, value: Any):
        """Сохранение данных в кэш"""
        self.analytics_cache[key] = (value, datetime.utcnow().timestamp())
    
    def generate_visualization(self, data: Dict[str, Any], chart_type: str = "line") -> str:
        """Генерация визуализации аналитики"""
        # Устанавливаем стиль matplotlib
        plt.style.use('seaborn-v0_8')
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        if chart_type == "line" and "dau_data" in data:
            # График DAU
            dates = [datetime.fromisoformat(d[0]) for d in data["dau_data"]]
            values = [d[1] for d in data["dau_data"]]
            
            ax.plot(dates, values, marker='o', linewidth=2, markersize=6)
            ax.set_title("Daily Active Users")
            ax.set_xlabel("Date")
            ax.set_ylabel("Number of Users")
            plt.xticks(rotation=45)
        
        elif chart_type == "bar" and "hourly_activity" in data:
            # График активности по часам
            hours = list(data["hourly_activity"].keys())
            counts = list(data["hourly_activity"].values())
            
            ax.bar(hours, counts)
            ax.set_title("Hourly Message Activity")
            ax.set_xlabel("Hour of Day")
            ax.set_ylabel("Number of Messages")
        
        elif chart_type == "pie" and "message_types" in data:
            # Круговая диаграмма типов сообщений
            labels = list(data["message_types"].keys())
            sizes = list(data["message_types"].values())
            
            ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
            ax.set_title("Message Types Distribution")
        
        plt.tight_layout()
        
        # Сохраняем график в байтовый буфер
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        
        # Конвертируем в base64
        image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        plt.close(fig)  # Закрываем фигуру, чтобы освободить память
        
        return f"data:image/png;base64,{image_base64}"

# Глобальный экземпляр для использования в приложении
chat_analytics_manager = ChatAnalyticsManager(None, None)  # Будет инициализирован в основном приложении
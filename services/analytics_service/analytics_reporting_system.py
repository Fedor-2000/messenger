# Analytics and Reporting System
# File: services/analytics_service/analytics_reporting_system.py

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
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt
import seaborn as sns
from io import BytesIO
import base64
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

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

class ReportType(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    CUSTOM = "custom"

class ReportFormat(Enum):
    JSON = "json"
    CSV = "csv"
    PDF = "pdf"
    EXCEL = "excel"
    HTML = "html"
    IMAGE = "image"

class ChartType(Enum):
    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    SCATTER = "scatter"
    HEATMAP = "heatmap"
    AREA = "area"
    COLUMN = "column"
    RADAR = "radar"
    GAUGE = "gauge"
    TREEMAP = "treemap"
    SANKEY = "sankey"
    SUNBURST = "sunburst"

class AnalyticsMetric(Enum):
    USER_REGISTRATIONS = "user_registrations"
    ACTIVE_USERS = "active_users"
    MESSAGES_SENT = "messages_sent"
    FILES_SHARED = "files_shared"
    TASKS_CREATED = "tasks_created"
    CALLS_MADE = "calls_made"
    POLLS_CREATED = "polls_created"
    CONTENT_LIKES = "content_likes"
    CONTENT_COMMENTS = "content_comments"
    CONTENT_SHARES = "content_shares"
    RESPONSE_TIME_MS = "response_time_ms"
    THROUGHPUT_RPS = "throughput_rps"
    CPU_USAGE_PERCENT = "cpu_usage_percent"
    MEMORY_USAGE_PERCENT = "memory_usage_percent"
    DATABASE_QUERY_TIME_MS = "database_query_time_ms"
    CACHE_HIT_RATE = "cache_hit_rate"
    CONNECTION_POOL_UTILIZATION = "connection_pool_utilization"
    ERROR_RATE = "error_rate"
    CHURN_RATE = "churn_rate"
    RETENTION_RATE = "retention_rate"
    ENGAGEMENT_SCORE = "engagement_score"

class AnalyticsQuery(BaseModel):
    id: str
    user_id: int
    query: str  # SQL или другой язык запросов
    filters: Dict[str, Any]  # Фильтры для запроса
    group_by: Optional[List[str]] = None
    order_by: Optional[List[str]] = None
    limit: Optional[int] = None
    offset: Optional[int] = None
    created_at: datetime = None
    updated_at: datetime = None

class AnalyticsResult(BaseModel):
    id: str
    query_id: str
    data: List[Dict[str, Any]]
    total_count: int
    execution_time_ms: float
    created_at: datetime = None

class Report(BaseModel):
    id: str
    title: str
    description: str
    type: ReportType
    format: ReportFormat
    analytics_type: AnalyticsType
    filters: Dict[str, Any]
    metrics: List[AnalyticsMetric]
    charts: List[Dict[str, Any]]  # [{'type': 'line', 'metric': 'metric_name', 'title': 'Chart Title'}]
    data: Optional[Dict[str, Any]] = None
    generated_at: datetime = None
    created_at: datetime = None
    updated_at: datetime = None

class AnalyticsService:
    def __init__(self):
        self.default_metrics = {
            AnalyticsType.USER_BEHAVIOR: [
                'user_registrations',
                'active_users_daily',
                'active_users_weekly',
                'session_duration_average',
                'login_frequency',
                'feature_usage_rate'
            ],
            AnalyticsType.CONTENT_ANALYTICS: [
                'messages_sent',
                'files_shared',
                'content_likes',
                'content_comments',
                'content_shares',
                'media_consumption_rate'
            ],
            AnalyticsType.PERFORMANCE_METRICS: [
                'response_time_average',
                'throughput_requests_per_second',
                'cpu_usage_average',
                'memory_usage_average',
                'database_query_time_average',
                'cache_hit_rate_average'
            ],
            AnalyticsType.BUSINESS_INTELLIGENCE: [
                'user_retention_rate',
                'user_churn_rate',
                'conversion_rate',
                'revenue_per_user',
                'customer_acquisition_cost',
                'lifetime_value'
            ]
        }
        
        self.analytics_functions = {
            AnalyticsMetric.USER_REGISTRATIONS: self._get_user_registration_metrics,
            AnalyticsMetric.ACTIVE_USERS: self._get_active_user_metrics,
            AnalyticsMetric.MESSAGES_SENT: self._get_message_metrics,
            AnalyticsMetric.FILES_SHARED: self._get_file_metrics,
            AnalyticsMetric.TASKS_CREATED: self._get_task_metrics,
            AnalyticsMetric.CALLS_MADE: self._get_call_metrics,
            AnalyticsMetric.POLLS_CREATED: self._get_poll_metrics,
            AnalyticsMetric.CONTENT_LIKES: self._get_content_like_metrics,
            AnalyticsMetric.CONTENT_COMMENTS: self._get_content_comment_metrics,
            AnalyticsMetric.CONTENT_SHARES: self._get_content_share_metrics,
            AnalyticsMetric.RESPONSE_TIME_MS: self._get_response_time_metrics,
            AnalyticsMetric.THROUGHPUT_RPS: self._get_throughput_metrics,
            AnalyticsMetric.CPU_USAGE_PERCENT: self._get_cpu_usage_metrics,
            AnalyticsMetric.MEMORY_USAGE_PERCENT: self._get_memory_usage_metrics,
            AnalyticsMetric.DATABASE_QUERY_TIME_MS: self._get_database_query_time_metrics,
            AnalyticsMetric.CACHE_HIT_RATE: self._get_cache_hit_rate_metrics,
            AnalyticsMetric.CONNECTION_POOL_UTILIZATION: self._get_connection_pool_metrics,
            AnalyticsMetric.ERROR_RATE: self._get_error_rate_metrics,
            AnalyticsMetric.CHURN_RATE: self._get_churn_rate_metrics,
            AnalyticsMetric.RETENTION_RATE: self._get_retention_rate_metrics,
            AnalyticsMetric.ENGAGEMENT_SCORE: self._get_engagement_score_metrics
        }

    async def execute_analytics_query(self, query: AnalyticsQuery) -> Optional[AnalyticsResult]:
        """Выполнение аналитического запроса"""
        start_time = time.time()
        
        try:
            # В реальной системе здесь будет выполнение SQL запроса
            # с использованием фильтров и параметров
            # Для упрощения возвращаем заглушку
            
            # Генерируем фиктивные данные для демонстрации
            data = await self._generate_sample_analytics_data(query)
            
            execution_time = (time.time() - start_time) * 1000  # в миллисекундах
            
            result = AnalyticsResult(
                id=str(uuid.uuid4()),
                query_id=query.id,
                data=data,
                total_count=len(data),
                execution_time_ms=execution_time,
                created_at=datetime.utcnow()
            )
            
            # Сохраняем результат в кэш
            await self._cache_analytics_result(result)
            
            # Создаем запись активности
            await self._log_activity(query.user_id, "analytics_query_executed", {
                "query_id": query.id,
                "execution_time_ms": execution_time,
                "result_count": len(data)
            })
            
            return result
        except Exception as e:
            logger.error(f"Error executing analytics query: {e}")
            return None

    async def _generate_sample_analytics_data(self, query: AnalyticsQuery) -> List[Dict[str, Any]]:
        """Генерация образцовых аналитических данных"""
        # В реальной системе здесь будет выполнение запроса к базе данных
        # Для упрощения возвращаем фиктивные данные
        sample_data = [
            {"date": "2023-01-01", "value": 100},
            {"date": "2023-01-02", "value": 120},
            {"date": "2023-01-03", "value": 95},
            {"date": "2023-01-04", "value": 140},
            {"date": "2023-01-05", "value": 160}
        ]
        return sample_data

    async def _cache_analytics_result(self, result: AnalyticsResult):
        """Кэширование результата аналитики"""
        await redis_client.setex(f"analytics_result:{result.id}", 300, result.model_dump_json())

    async def _get_cached_analytics_result(self, result_id: str) -> Optional[AnalyticsResult]:
        """Получение результата аналитики из кэша"""
        cached = await redis_client.get(f"analytics_result:{result_id}")
        if cached:
            return AnalyticsResult(**json.loads(cached.decode()))
        return None

    async def generate_report(self, title: str, description: str, report_type: ReportType,
                            analytics_type: AnalyticsType, filters: Dict[str, Any],
                            metrics: List[AnalyticsMetric],
                            charts: Optional[List[Dict[str, Any]]] = None,
                            format: ReportFormat = ReportFormat.JSON) -> Optional[str]:
        """Генерация отчета"""
        report_id = str(uuid.uuid4())
        
        # Получаем данные для отчета
        report_data = await self._generate_report_data(analytics_type, filters, metrics)
        
        # Создаем диаграммы для отчета
        if charts:
            chart_data = await self._generate_report_charts(charts, report_data)
        else:
            chart_data = []
        
        report = Report(
            id=report_id,
            title=title,
            description=description,
            type=report_type,
            format=format,
            analytics_type=analytics_type,
            filters=filters,
            metrics=metrics,
            charts=charts or [],
            data={
                'metrics_data': report_data,
                'charts_data': chart_data
            },
            generated_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Сохраняем отчет в базу данных
        await self._save_report(report)
        
        # Добавляем в кэш
        await self._cache_report(report)
        
        # Создаем запись активности
        await self._log_activity("system", "report_generated", {
            "report_id": report_id,
            "report_type": report_type.value,
            "analytics_type": analytics_type.value,
            "metrics_count": len(metrics)
        })
        
        return report_id

    async def _generate_report_data(self, analytics_type: AnalyticsType, 
                                  filters: Dict[str, Any], 
                                  metrics: List[AnalyticsMetric]) -> Dict[str, Any]:
        """Генерация данных для отчета"""
        report_data = {}
        
        for metric in metrics:
            if metric in self.analytics_functions:
                data = await self.analytics_functions[metric](filters)
                report_data[metric.value] = data
        
        return report_data

    async def _generate_report_charts(self, charts: List[Dict[str, Any]], 
                                    report_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Генерация диаграмм для отчета"""
        chart_results = []
        
        for chart_config in charts:
            chart_type = ChartType(chart_config['type'])
            metric_name = chart_config['metric']
            chart_title = chart_config.get('title', f'{chart_type.value.title()} Chart for {metric_name}')
            
            if metric_name in report_data:
                chart_data = await self._generate_chart_data(
                    report_data[metric_name], chart_type, chart_title
                )
                chart_results.append({
                    'type': chart_type.value,
                    'metric': metric_name,
                    'title': chart_title,
                    'data': chart_data
                })
        
        return chart_results

    async def _generate_chart_data(self, metric_data: List[Dict[str, Any]], 
                                 chart_type: ChartType, title: str) -> str:
        """Генерация данных диаграммы"""
        try:
            if chart_type == ChartType.LINE:
                return await self._generate_line_chart(metric_data, title)
            elif chart_type == ChartType.BAR:
                return await self._generate_bar_chart(metric_data, title)
            elif chart_type == ChartType.PIE:
                return await self._generate_pie_chart(metric_data, title)
            elif chart_type == ChartType.SCATTER:
                return await self._generate_scatter_chart(metric_data, title)
            elif chart_type == ChartType.HEATMAP:
                return await self._generate_heatmap_chart(metric_data, title)
            elif chart_type == ChartType.AREA:
                return await self._generate_area_chart(metric_data, title)
            elif chart_type == ChartType.COLUMN:
                return await self._generate_column_chart(metric_data, title)
            elif chart_type == ChartType.RADAR:
                return await self._generate_radar_chart(metric_data, title)
            elif chart_type == ChartType.GAUGE:
                return await self._generate_gauge_chart(metric_data, title)
            elif chart_type == ChartType.TREEMAP:
                return await self._generate_treemap_chart(metric_data, title)
            elif chart_type == ChartType.SANKEY:
                return await self._generate_sankey_chart(metric_data, title)
            elif chart_type == ChartType.SUNBURST:
                return await self._generate_sunburst_chart(metric_data, title)
            else:
                return await self._generate_default_chart(metric_data, title)
        except Exception as e:
            logger.error(f"Error generating chart data: {e}")
            return ""

    async def _generate_line_chart(self, data: List[Dict[str, Any]], title: str) -> str:
        """Генерация линейной диаграммы"""
        try:
            # Подготавливаем данные
            dates = [item['date'] for item in data]
            values = [item['value'] for item in data]
            
            # Создаем диаграмму с Plotly
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=dates, y=values, mode='lines+markers', name='Value'))
            fig.update_layout(title=title, xaxis_title='Date', yaxis_title='Value')
            
            # Конвертируем в HTML
            chart_html = fig.to_html(include_plotlyjs=True, div_id=f"chart_{uuid.uuid4()}")
            
            return chart_html
        except Exception as e:
            logger.error(f"Error generating line chart: {e}")
            return ""

    async def _generate_bar_chart(self, data: List[Dict[str, Any]], title: str) -> str:
        """Генерация столбчатой диаграммы"""
        try:
            # Подготавливаем данные
            labels = [item.get('label', item['date']) for item in data]
            values = [item['value'] for item in data]
            
            # Создаем диаграмму с Plotly
            fig = go.Figure()
            fig.add_trace(go.Bar(x=labels, y=values))
            fig.update_layout(title=title, xaxis_title='Category', yaxis_title='Value')
            
            # Конвертируем в HTML
            chart_html = fig.to_html(include_plotlyjs=True, div_id=f"chart_{uuid.uuid4()}")
            
            return chart_html
        except Exception as e:
            logger.error(f"Error generating bar chart: {e}")
            return ""

    async def _generate_pie_chart(self, data: List[Dict[str, Any]], title: str) -> str:
        """Генерация круговой диаграммы"""
        try:
            # Подготавливаем данные
            labels = [item.get('label', item['date']) for item in data]
            values = [item['value'] for item in data]
            
            # Создаем диаграмму с Plotly
            fig = go.Figure(data=[go.Pie(labels=labels, values=values)])
            fig.update_layout(title=title)
            
            # Конвертируем в HTML
            chart_html = fig.to_html(include_plotlyjs=True, div_id=f"chart_{uuid.uuid4()}")
            
            return chart_html
        except Exception as e:
            logger.error(f"Error generating pie chart: {e}")
            return ""

    async def _generate_scatter_chart(self, data: List[Dict[str, Any]], title: str) -> str:
        """Генерация точечной диаграммы"""
        try:
            # Подготавливаем данные
            x_values = [item.get('x', item['date']) for item in data]
            y_values = [item.get('y', item['value']) for item in data]
            
            # Создаем диаграмму с Plotly
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=x_values, y=y_values, mode='markers'))
            fig.update_layout(title=title, xaxis_title='X Value', yaxis_title='Y Value')
            
            # Конвертируем в HTML
            chart_html = fig.to_html(include_plotlyjs=True, div_id=f"chart_{uuid.uuid4()}")
            
            return chart_html
        except Exception as e:
            logger.error(f"Error generating scatter chart: {e}")
            return ""

    async def _generate_heatmap_chart(self, data: List[Dict[str, Any]], title: str) -> str:
        """Генерация тепловой карты"""
        try:
            # Подготавливаем данные для тепловой карты
            # В реальной системе это будет двумерный массив
            values = [[item['value'] for item in data]]
            x_labels = [item['date'] for item in data]
            y_labels = ['Metric']
            
            # Создаем диаграмму с Plotly
            fig = go.Figure(data=go.Heatmap(z=values, x=x_labels, y=y_labels))
            fig.update_layout(title=title)
            
            # Конвертируем в HTML
            chart_html = fig.to_html(include_plotlyjs=True, div_id=f"chart_{uuid.uuid4()}")
            
            return chart_html
        except Exception as e:
            logger.error(f"Error generating heatmap chart: {e}")
            return ""

    async def _generate_area_chart(self, data: List[Dict[str, Any]], title: str) -> str:
        """Генерация диаграммы с областями"""
        try:
            # Подготавливаем данные
            dates = [item['date'] for item in data]
            values = [item['value'] for item in data]
            
            # Создаем диаграмму с Plotly
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=dates, y=values, fill='tonexty', mode='lines', name='Value'))
            fig.update_layout(title=title, xaxis_title='Date', yaxis_title='Value')
            
            # Конвертируем в HTML
            chart_html = fig.to_html(include_plotlyjs=True, div_id=f"chart_{uuid.uuid4()}")
            
            return chart_html
        except Exception as e:
            logger.error(f"Error generating area chart: {e}")
            return ""

    async def _generate_column_chart(self, data: List[Dict[str, Any]], title: str) -> str:
        """Генерация столбчатой диаграммы (альтернатива bar chart)"""
        try:
            # Подготавливаем данные
            labels = [item.get('label', item['date']) for item in data]
            values = [item['value'] for item in data]
            
            # Создаем диаграмму с Plotly
            fig = go.Figure()
            fig.add_trace(go.Bar(x=labels, y=values, orientation='v'))
            fig.update_layout(title=title, xaxis_title='Category', yaxis_title='Value')
            
            # Конвертируем в HTML
            chart_html = fig.to_html(include_plotlyjs=True, div_id=f"chart_{uuid.uuid4()}")
            
            return chart_html
        except Exception as e:
            logger.error(f"Error generating column chart: {e}")
            return ""

    async def _generate_radar_chart(self, data: List[Dict[str, Any]], title: str) -> str:
        """Генерация радарной диаграммы"""
        try:
            # Подготавливаем данные
            categories = [item.get('category', item['date']) for item in data]
            values = [item['value'] for item in data]
            
            # Добавляем первый элемент в конец для замыкания диаграммы
            categories.append(categories[0])
            values.append(values[0])
            
            # Создаем диаграмму с Plotly
            fig = go.Figure(data=go.Scatterpolar(r=values, theta=categories, fill='toself'))
            fig.update_layout(title=title, polar=dict(radialaxis=dict(visible=True)))
            
            # Конвертируем в HTML
            chart_html = fig.to_html(include_plotlyjs=True, div_id=f"chart_{uuid.uuid4()}")
            
            return chart_html
        except Exception as e:
            logger.error(f"Error generating radar chart: {e}")
            return ""

    async def _generate_gauge_chart(self, data: List[Dict[str, Any]], title: str) -> str:
        """Генерация индикаторной диаграммы (gauge)"""
        try:
            # Берем последнее значение для индикатора
            if data:
                value = data[-1]['value']
            else:
                value = 0
            
            # Создаем диаграмму с Plotly
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=value,
                domain={'x': [0, 1], 'y': [0, 1]},
                title={'text': title}
            ))
            
            # Конвертируем в HTML
            chart_html = fig.to_html(include_plotlyjs=True, div_id=f"chart_{uuid.uuid4()}")
            
            return chart_html
        except Exception as e:
            logger.error(f"Error generating gauge chart: {e}")
            return ""

    async def _generate_treemap_chart(self, data: List[Dict[str, Any]], title: str) -> str:
        """Генерация древовидной карты"""
        try:
            # Подготавливаем данные для древовидной карты
            df = pd.DataFrame(data)
            
            # Создаем диаграмму с Plotly
            fig = px.treemap(df, path=['date'], values='value', title=title)
            
            # Конвертируем в HTML
            chart_html = fig.to_html(include_plotlyjs=True, div_id=f"chart_{uuid.uuid4()}")
            
            return chart_html
        except Exception as e:
            logger.error(f"Error generating treemap chart: {e}")
            return ""

    async def _generate_sankey_chart(self, data: List[Dict[str, Any]], title: str) -> str:
        """Генерация диаграммы Sankey"""
        try:
            # Для диаграммы Sankey нужно специфическое форматирование данных
            # Временно возвращаем заглушку
            fig = go.Figure()
            fig.update_layout(title=title)
            
            # Конвертируем в HTML
            chart_html = fig.to_html(include_plotlyjs=True, div_id=f"chart_{uuid.uuid4()}")
            
            return chart_html
        except Exception as e:
            logger.error(f"Error generating sankey chart: {e}")
            return ""

    async def _generate_sunburst_chart(self, data: List[Dict[str, Any]], title: str) -> str:
        """Генерация солнечной диаграммы"""
        try:
            # Подготавливаем данные для солнечной диаграммы
            df = pd.DataFrame(data)
            
            # Создаем диаграмму с Plotly
            fig = px.sunburst(df, path=['date'], values='value', title=title)
            
            # Конвертируем в HTML
            chart_html = fig.to_html(include_plotlyjs=True, div_id=f"chart_{uuid.uuid4()}")
            
            return chart_html
        except Exception as e:
            logger.error(f"Error generating sunburst chart: {e}")
            return ""

    async def _generate_default_chart(self, data: List[Dict[str, Any]], title: str) -> str:
        """Генерация диаграммы по умолчанию"""
        try:
            # Создаем простую линейную диаграмму по умолчанию
            dates = [item['date'] for item in data]
            values = [item['value'] for item in data]
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=dates, y=values, mode='lines+markers', name='Value'))
            fig.update_layout(title=title, xaxis_title='Date', yaxis_title='Value')
            
            # Конвертируем в HTML
            chart_html = fig.to_html(include_plotlyjs=True, div_id=f"chart_{uuid.uuid4()}")
            
            return chart_html
        except Exception as e:
            logger.error(f"Error generating default chart: {e}")
            return ""

    async def _save_report(self, report: Report):
        """Сохранение отчета в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO reports (
                    id, title, description, type, format, analytics_type, filters,
                    metrics, charts, data, generated_at, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """,
                report.id, report.title, report.description, report.type.value,
                report.format.value, report.analytics_type.value,
                json.dumps(report.filters), [m.value for m in report.metrics],
                json.dumps(report.charts), json.dumps(report.data) if report.data else None,
                report.generated_at, report.created_at, report.updated_at
            )

    async def _cache_report(self, report: Report):
        """Кэширование отчета"""
        await redis_client.setex(f"report:{report.id}", 3600, report.model_dump_json())

    async def _get_cached_report(self, report_id: str) -> Optional[Report]:
        """Получение отчета из кэша"""
        cached = await redis_client.get(f"report:{report_id}")
        if cached:
            return Report(**json.loads(cached.decode()))
        return None

    async def get_report(self, report_id: str, user_id: Optional[int] = None) -> Optional[Report]:
        """Получение отчета"""
        # Сначала проверяем кэш
        cached_report = await self._get_cached_report(report_id)
        if cached_report:
            return cached_report

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, title, description, type, format, analytics_type, filters,
                       metrics, charts, data, generated_at, created_at, updated_at
                FROM reports WHERE id = $1
                """,
                report_id
            )

        if not row:
            return None

        report = Report(
            id=row['id'],
            title=row['title'],
            description=row['description'],
            type=ReportType(row['type']),
            format=ReportFormat(row['format']),
            analytics_type=AnalyticsType(row['analytics_type']),
            filters=json.loads(row['filters']) if row['filters'] else {},
            metrics=[AnalyticsMetric(m) for m in row['metrics']] if row['metrics'] else [],
            charts=json.loads(row['charts']) if row['charts'] else [],
            data=json.loads(row['data']) if row['data'] else None,
            generated_at=row['generated_at'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

        # Кэшируем отчет
        await self._cache_report(report)

        return report

    async def get_user_analytics(self, user_id: int, start_date: datetime, 
                               end_date: datetime, metrics: List[AnalyticsMetric]) -> Dict[str, Any]:
        """Получение аналитики пользователя"""
        user_analytics = {}

        for metric in metrics:
            if metric in self.analytics_functions:
                data = await self.analytics_functions[metric]({
                    'user_id': user_id,
                    'start_date': start_date,
                    'end_date': end_date
                })
                user_analytics[metric.value] = data

        return {
            'user_id': user_id,
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'metrics': user_analytics,
            'timestamp': datetime.utcnow().isoformat()
        }

    async def _get_user_registration_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик регистрации пользователей"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DATE_TRUNC('day', created_at) as date, COUNT(*) as count
                FROM users
                WHERE created_at BETWEEN $1 AND $2
                GROUP BY DATE_TRUNC('day', created_at)
                ORDER BY date
                """,
                start_date, end_date
            )

        return [
            {
                'date': row['date'].isoformat(),
                'value': row['count']
            }
            for row in rows
        ]

    async def _get_active_user_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик активных пользователей"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DATE_TRUNC('day', timestamp) as date, COUNT(DISTINCT user_id) as count
                FROM user_activities
                WHERE timestamp BETWEEN $1 AND $2
                GROUP BY DATE_TRUNC('day', timestamp)
                ORDER BY date
                """,
                start_date, end_date
            )

        return [
            {
                'date': row['date'].isoformat(),
                'value': row['count']
            }
            for row in rows
        ]

    async def _get_message_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик сообщений"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        user_id = filters.get('user_id')
        
        conditions = ["timestamp BETWEEN $1 AND $2"]
        params = [start_date, end_date]
        param_idx = 3

        if user_id:
            conditions.append(f"sender_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT DATE_TRUNC('day', timestamp) as date, COUNT(*) as count
            FROM messages
            WHERE {where_clause}
            GROUP BY DATE_TRUNC('day', timestamp)
            ORDER BY date
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        return [
            {
                'date': row['date'].isoformat(),
                'value': row['count']
            }
            for row in rows
        ]

    async def _get_file_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик файлов"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        user_id = filters.get('user_id')
        
        conditions = ["uploaded_at BETWEEN $1 AND $2"]
        params = [start_date, end_date]
        param_idx = 3

        if user_id:
            conditions.append(f"uploader_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT DATE_TRUNC('day', uploaded_at) as date, COUNT(*) as count, SUM(size) as total_size
            FROM files
            WHERE {where_clause}
            GROUP BY DATE_TRUNC('day', uploaded_at)
            ORDER BY date
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        return [
            {
                'date': row['date'].isoformat(),
                'value': row['count'],
                'total_size': row['total_size']
            }
            for row in rows
        ]

    async def _get_task_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик задач"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        user_id = filters.get('user_id')
        
        conditions = ["created_at BETWEEN $1 AND $2"]
        params = [start_date, end_date]
        param_idx = 3

        if user_id:
            conditions.append(f"creator_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT DATE_TRUNC('day', created_at) as date, COUNT(*) as count
            FROM tasks
            WHERE {where_clause}
            GROUP BY DATE_TRUNC('day', created_at)
            ORDER BY date
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        return [
            {
                'date': row['date'].isoformat(),
                'value': row['count']
            }
            for row in rows
        ]

    async def _get_call_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик звонков"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        user_id = filters.get('user_id')
        
        conditions = ["started_at BETWEEN $1 AND $2"]
        params = [start_date, end_date]
        param_idx = 3

        if user_id:
            conditions.append(f"initiator_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT DATE_TRUNC('day', started_at) as date, COUNT(*) as count, AVG(duration) as avg_duration
            FROM calls
            WHERE {where_clause}
            GROUP BY DATE_TRUNC('day', started_at)
            ORDER BY date
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        return [
            {
                'date': row['date'].isoformat(),
                'value': row['count'],
                'avg_duration': row['avg_duration']
            }
            for row in rows
        ]

    async def _get_poll_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик опросов"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        user_id = filters.get('user_id')
        
        conditions = ["created_at BETWEEN $1 AND $2"]
        params = [start_date, end_date]
        param_idx = 3

        if user_id:
            conditions.append(f"creator_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT DATE_TRUNC('day', created_at) as date, COUNT(*) as count
            FROM polls
            WHERE {where_clause}
            GROUP BY DATE_TRUNC('day', created_at)
            ORDER BY date
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        return [
            {
                'date': row['date'].isoformat(),
                'value': row['count']
            }
            for row in rows
        ]

    async def _get_content_like_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик лайков контента"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        user_id = filters.get('user_id')
        
        conditions = ["timestamp BETWEEN $1 AND $2"]
        params = [start_date, end_date]
        param_idx = 3

        if user_id:
            conditions.append(f"user_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT DATE_TRUNC('day', timestamp) as date, COUNT(*) as count
            FROM content_likes
            WHERE {where_clause}
            GROUP BY DATE_TRUNC('day', timestamp)
            ORDER BY date
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        return [
            {
                'date': row['date'].isoformat(),
                'value': row['count']
            }
            for row in rows
        ]

    async def _get_content_comment_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик комментариев к контенту"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        user_id = filters.get('user_id')
        
        conditions = ["created_at BETWEEN $1 AND $2"]
        params = [start_date, end_date]
        param_idx = 3

        if user_id:
            conditions.append(f"user_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT DATE_TRUNC('day', created_at) as date, COUNT(*) as count
            FROM content_comments
            WHERE {where_clause}
            GROUP BY DATE_TRUNC('day', created_at)
            ORDER BY date
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        return [
            {
                'date': row['date'].isoformat(),
                'value': row['count']
            }
            for row in rows
        ]

    async def _get_content_share_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик шеринга контента"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        user_id = filters.get('user_id')
        
        conditions = ["created_at BETWEEN $1 AND $2"]
        params = [start_date, end_date]
        param_idx = 3

        if user_id:
            conditions.append(f"creator_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT DATE_TRUNC('day', created_at) as date, COUNT(*) as count
            FROM content_shares
            WHERE {where_clause}
            GROUP BY DATE_TRUNC('day', created_at)
            ORDER BY date
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        return [
            {
                'date': row['date'].isoformat(),
                'value': row['count']
            }
            for row in rows
        ]

    async def _get_response_time_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик времени отклика"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=7))
        end_date = filters.get('end_date', datetime.utcnow())
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DATE_TRUNC('hour', timestamp) as time, AVG(value) as avg_response_time
                FROM performance_metrics
                WHERE metric_name = 'response_time_ms' AND timestamp BETWEEN $1 AND $2
                GROUP BY DATE_TRUNC('hour', timestamp)
                ORDER BY time
                """,
                start_date, end_date
            )

        return [
            {
                'date': row['time'].isoformat(),
                'value': float(row['avg_response_time'])
            }
            for row in rows
        ]

    async def _get_throughput_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик пропускной способности"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=7))
        end_date = filters.get('end_date', datetime.utcnow())
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DATE_TRUNC('hour', timestamp) as time, AVG(value) as avg_throughput
                FROM performance_metrics
                WHERE metric_name = 'throughput_rps' AND timestamp BETWEEN $1 AND $2
                GROUP BY DATE_TRUNC('hour', timestamp)
                ORDER BY time
                """,
                start_date, end_date
            )

        return [
            {
                'date': row['time'].isoformat(),
                'value': float(row['avg_throughput'])
            }
            for row in rows
        ]

    async def _get_cpu_usage_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик использования CPU"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=7))
        end_date = filters.get('end_date', datetime.utcnow())
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DATE_TRUNC('hour', timestamp) as time, AVG(value) as avg_cpu_usage
                FROM performance_metrics
                WHERE metric_name = 'cpu_usage_percent' AND timestamp BETWEEN $1 AND $2
                GROUP BY DATE_TRUNC('hour', timestamp)
                ORDER BY time
                """,
                start_date, end_date
            )

        return [
            {
                'date': row['time'].isoformat(),
                'value': float(row['avg_cpu_usage'])
            }
            for row in rows
        ]

    async def _get_memory_usage_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик использования памяти"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=7))
        end_date = filters.get('end_date', datetime.utcnow())
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DATE_TRUNC('hour', timestamp) as time, AVG(value) as avg_memory_usage
                FROM performance_metrics
                WHERE metric_name = 'memory_usage_percent' AND timestamp BETWEEN $1 AND $2
                GROUP BY DATE_TRUNC('hour', timestamp)
                ORDER BY time
                """,
                start_date, end_date
            )

        return [
            {
                'date': row['time'].isoformat(),
                'value': float(row['avg_memory_usage'])
            }
            for row in rows
        ]

    async def _get_database_query_time_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик времени выполнения запросов к базе данных"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=7))
        end_date = filters.get('end_date', datetime.utcnow())
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DATE_TRUNC('hour', timestamp) as time, AVG(value) as avg_query_time
                FROM performance_metrics
                WHERE metric_name = 'database_query_time_ms' AND timestamp BETWEEN $1 AND $2
                GROUP BY DATE_TRUNC('hour', timestamp)
                ORDER BY time
                """,
                start_date, end_date
            )

        return [
            {
                'date': row['time'].isoformat(),
                'value': float(row['avg_query_time'])
            }
            for row in rows
        ]

    async def _get_cache_hit_rate_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик hit rate кэша"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=7))
        end_date = filters.get('end_date', datetime.utcnow())
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DATE_TRUNC('hour', timestamp) as time, AVG(value) as avg_cache_hit_rate
                FROM performance_metrics
                WHERE metric_name = 'cache_hit_rate' AND timestamp BETWEEN $1 AND $2
                GROUP BY DATE_TRUNC('hour', timestamp)
                ORDER BY time
                """,
                start_date, end_date
            )

        return [
            {
                'date': row['time'].isoformat(),
                'value': float(row['avg_cache_hit_rate'])
            }
            for row in rows
        ]

    async def _get_connection_pool_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик использования пула соединений"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=7))
        end_date = filters.get('end_date', datetime.utcnow())
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DATE_TRUNC('hour', timestamp) as time, AVG(value) as avg_pool_utilization
                FROM performance_metrics
                WHERE metric_name = 'connection_pool_utilization' AND timestamp BETWEEN $1 AND $2
                GROUP BY DATE_TRUNC('hour', timestamp)
                ORDER BY time
                """,
                start_date, end_date
            )

        return [
            {
                'date': row['time'].isoformat(),
                'value': float(row['avg_pool_utilization'])
            }
            for row in rows
        ]

    async def _get_error_rate_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик частоты ошибок"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=7))
        end_date = filters.get('end_date', datetime.utcnow())
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DATE_TRUNC('hour', timestamp) as time, AVG(value) as avg_error_rate
                FROM performance_metrics
                WHERE metric_name = 'error_rate' AND timestamp BETWEEN $1 AND $2
                GROUP BY DATE_TRUNC('hour', timestamp)
                ORDER BY time
                """,
                start_date, end_date
            )

        return [
            {
                'date': row['time'].isoformat(),
                'value': float(row['avg_error_rate'])
            }
            for row in rows
        ]

    async def _get_churn_rate_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик оттока пользователей"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DATE_TRUNC('day', timestamp) as date, COUNT(*) as churned_users
                FROM user_deactivations
                WHERE timestamp BETWEEN $1 AND $2
                GROUP BY DATE_TRUNC('day', timestamp)
                ORDER BY date
                """,
                start_date, end_date
            )

        return [
            {
                'date': row['date'].isoformat(),
                'value': row['churned_users']
            }
            for row in rows
        ]

    async def _get_retention_rate_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик удержания пользователей"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DATE_TRUNC('day', activity_date) as date, 
                       COUNT(DISTINCT user_id) as retained_users
                FROM user_activities
                WHERE activity_date BETWEEN $1 AND $2
                GROUP BY DATE_TRUNC('day', activity_date)
                ORDER BY date
                """,
                start_date, end_date
            )

        return [
            {
                'date': row['date'].isoformat(),
                'value': row['retained_users']
            }
            for row in rows
        ]

    async def _get_engagement_score_metrics(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Получение метрик оценки вовлеченности"""
        start_date = filters.get('start_date', datetime.utcnow() - timedelta(days=30))
        end_date = filters.get('end_date', datetime.utcnow())
        user_id = filters.get('user_id')
        
        conditions = ["timestamp BETWEEN $1 AND $2"]
        params = [start_date, end_date]
        param_idx = 3

        if user_id:
            conditions.append(f"user_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT DATE_TRUNC('day', timestamp) as date, AVG(engagement_score) as avg_engagement
            FROM user_engagement_scores
            WHERE {where_clause}
            GROUP BY DATE_TRUNC('day', timestamp)
            ORDER BY date
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        return [
            {
                'date': row['date'].isoformat(),
                'value': float(row['avg_engagement'])
            }
            for row in rows
        ]

    async def get_system_analytics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Получение системной аналитики"""
        # Получаем общую статистику
        total_users = await self._get_total_users_count()
        total_messages = await self._get_total_messages_count()
        total_files = await self._get_total_files_count()
        total_tasks = await self._get_total_tasks_count()
        total_calls = await self._get_total_calls_count()
        
        # Получаем активность за период
        daily_active_users = await self._get_daily_active_users(start_date, end_date)
        daily_messages_sent = await self._get_daily_messages_sent(start_date, end_date)
        daily_files_shared = await self._get_daily_files_shared(start_date, end_date)
        
        # Получаем производительность системы
        system_performance = await self._get_system_performance_metrics(start_date, end_date)
        
        analytics = {
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'system_overview': {
                'total_users': total_users,
                'total_messages': total_messages,
                'total_files': total_files,
                'total_tasks': total_tasks,
                'total_calls': total_calls
            },
            'user_activity': {
                'daily_active_users': daily_active_users,
                'daily_messages_sent': daily_messages_sent,
                'daily_files_shared': daily_files_shared
            },
            'system_performance': system_performance,
            'growth_metrics': await self._calculate_growth_metrics(start_date, end_date),
            'engagement_metrics': await self._calculate_engagement_metrics(start_date, end_date),
            'retention_metrics': await self._calculate_retention_metrics(start_date, end_date),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return analytics

    async def _get_total_users_count(self) -> int:
        """Получение общего количества пользователей"""
        async with db_pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM users")
        return count or 0

    async def _get_total_messages_count(self) -> int:
        """Получение общего количества сообщений"""
        async with db_pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM messages")
        return count or 0

    async def _get_total_files_count(self) -> int:
        """Получение общего количества файлов"""
        async with db_pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM files")
        return count or 0

    async def _get_total_tasks_count(self) -> int:
        """Получение общего количества задач"""
        async with db_pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM tasks")
        return count or 0

    async def _get_total_calls_count(self) -> int:
        """Получение общего количества звонков"""
        async with db_pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM calls")
        return count or 0

    async def _get_daily_active_users(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Получение ежедневной активности пользователей"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DATE_TRUNC('day', timestamp) as date, COUNT(DISTINCT user_id) as count
                FROM user_activities
                WHERE timestamp BETWEEN $1 AND $2
                GROUP BY DATE_TRUNC('day', timestamp)
                ORDER BY date
                """,
                start_date, end_date
            )

        return [
            {
                'date': row['date'].isoformat(),
                'value': row['count']
            }
            for row in rows
        ]

    async def _get_daily_messages_sent(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Получение ежедневной статистики отправленных сообщений"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DATE_TRUNC('day', timestamp) as date, COUNT(*) as count
                FROM messages
                WHERE timestamp BETWEEN $1 AND $2
                GROUP BY DATE_TRUNC('day', timestamp)
                ORDER BY date
                """,
                start_date, end_date
            )

        return [
            {
                'date': row['date'].isoformat(),
                'value': row['count']
            }
            for row in rows
        ]

    async def _get_daily_files_shared(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Получение ежедневной статистики общих файлов"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DATE_TRUNC('day', uploaded_at) as date, COUNT(*) as count
                FROM files
                WHERE uploaded_at BETWEEN $1 AND $2
                GROUP BY DATE_TRUNC('day', uploaded_at)
                ORDER BY date
                """,
                start_date, end_date
            )

        return [
            {
                'date': row['date'].isoformat(),
                'value': row['count']
            }
            for row in rows
        ]

    async def _get_system_performance_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Получение метрик производительности системы"""
        async with db_pool.acquire() as conn:
            # Среднее время отклика
            avg_response_time = await conn.fetchval(
                """
                SELECT AVG(value) FROM performance_metrics
                WHERE metric_name = 'response_time_ms' AND timestamp BETWEEN $1 AND $2
                """,
                start_date, end_date
            )
            
            # Средняя загрузка CPU
            avg_cpu_usage = await conn.fetchval(
                """
                SELECT AVG(value) FROM performance_metrics
                WHERE metric_name = 'cpu_usage_percent' AND timestamp BETWEEN $1 AND $2
                """,
                start_date, end_date
            )
            
            # Средняя загрузка памяти
            avg_memory_usage = await conn.fetchval(
                """
                SELECT AVG(value) FROM performance_metrics
                WHERE metric_name = 'memory_usage_percent' AND timestamp BETWEEN $1 AND $2
                """,
                start_date, end_date
            )
            
            # Среднее время запросов к базе данных
            avg_db_query_time = await conn.fetchval(
                """
                SELECT AVG(value) FROM performance_metrics
                WHERE metric_name = 'database_query_time_ms' AND timestamp BETWEEN $1 AND $2
                """,
                start_date, end_date
            )
            
            # Средний hit rate кэша
            avg_cache_hit_rate = await conn.fetchval(
                """
                SELECT AVG(value) FROM performance_metrics
                WHERE metric_name = 'cache_hit_rate' AND timestamp BETWEEN $1 AND $2
                """,
                start_date, end_date
            )

        return {
            'avg_response_time_ms': float(avg_response_time) if avg_response_time else 0.0,
            'avg_cpu_usage_percent': float(avg_cpu_usage) if avg_cpu_usage else 0.0,
            'avg_memory_usage_percent': float(avg_memory_usage) if avg_memory_usage else 0.0,
            'avg_db_query_time_ms': float(avg_db_query_time) if avg_db_query_time else 0.0,
            'avg_cache_hit_rate_percent': float(avg_cache_hit_rate) if avg_cache_hit_rate else 0.0
        }

    async def _calculate_growth_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Расчет метрик роста"""
        # Рассчитываем рост пользователей
        users_growth = await self._calculate_user_growth(start_date, end_date)
        
        # Рассчитываем рост сообщений
        messages_growth = await self._calculate_message_growth(start_date, end_date)
        
        # Рассчитываем рост файлов
        files_growth = await self._calculate_file_growth(start_date, end_date)
        
        return {
            'users_growth': users_growth,
            'messages_growth': messages_growth,
            'files_growth': files_growth,
            'overall_growth_rate': (users_growth['rate'] + messages_growth['rate'] + files_growth['rate']) / 3
        }

    async def _calculate_user_growth(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Расчет роста пользователей"""
        async with db_pool.acquire() as conn:
            # Количество пользователей в начале периода
            start_users = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at < $1",
                start_date
            )
            
            # Количество пользователей в конце периода
            end_users = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at < $1",
                end_date
            )
        
        start_count = start_users or 0
        end_count = end_users or 0
        growth = end_count - start_count
        growth_rate = (growth / start_count * 100) if start_count > 0 else 0
        
        return {
            'start_count': start_count,
            'end_count': end_count,
            'growth': growth,
            'growth_rate': growth_rate
        }

    async def _calculate_message_growth(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Расчет роста сообщений"""
        async with db_pool.acquire() as conn:
            # Количество сообщений в начале периода
            start_messages = await conn.fetchval(
                "SELECT COUNT(*) FROM messages WHERE timestamp < $1",
                start_date
            )
            
            # Количество сообщений в конце периода
            end_messages = await conn.fetchval(
                "SELECT COUNT(*) FROM messages WHERE timestamp < $1",
                end_date
            )
        
        start_count = start_messages or 0
        end_count = end_messages or 0
        growth = end_count - start_count
        growth_rate = (growth / start_count * 100) if start_count > 0 else 0
        
        return {
            'start_count': start_count,
            'end_count': end_count,
            'growth': growth,
            'growth_rate': growth_rate
        }

    async def _calculate_file_growth(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Расчет роста файлов"""
        async with db_pool.acquire() as conn:
            # Количество файлов в начале периода
            start_files = await conn.fetchval(
                "SELECT COUNT(*) FROM files WHERE uploaded_at < $1",
                start_date
            )
            
            # Количество файлов в конце периода
            end_files = await conn.fetchval(
                "SELECT COUNT(*) FROM files WHERE uploaded_at < $1",
                end_date
            )
        
        start_count = start_files or 0
        end_count = end_files or 0
        growth = end_count - start_count
        growth_rate = (growth / start_count * 100) if start_count > 0 else 0
        
        return {
            'start_count': start_count,
            'end_count': end_count,
            'growth': growth,
            'growth_rate': growth_rate
        }

    async def _calculate_engagement_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Расчет метрик вовлеченности"""
        async with db_pool.acquire() as conn:
            # Средняя оценка вовлеченности
            avg_engagement = await conn.fetchval(
                """
                SELECT AVG(engagement_score) FROM user_engagement_scores
                WHERE timestamp BETWEEN $1 AND $2
                """,
                start_date, end_date
            )
            
            # Количество активных пользователей (с оценкой вовлеченности > 0.5)
            active_users = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT user_id) FROM user_engagement_scores
                WHERE timestamp BETWEEN $1 AND $2 AND engagement_score > 0.5
                """,
                start_date, end_date
            )
            
            # Количество пользователей с высокой вовлеченностью (> 0.8)
            highly_engaged_users = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT user_id) FROM user_engagement_scores
                WHERE timestamp BETWEEN $1 AND $2 AND engagement_score > 0.8
                """,
                start_date, end_date
            )

        return {
            'avg_engagement_score': float(avg_engagement) if avg_engagement else 0.0,
            'active_users_count': active_users or 0,
            'highly_engaged_users_count': highly_engaged_users or 0,
            'active_user_ratio': (active_users or 0) / (await self._get_total_users_count() or 1)
        }

    async def _calculate_retention_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Расчет метрик удержания"""
        async with db_pool.acquire() as conn:
            # Количество пользователей, зарегистрированных в начале периода
            cohort_start_date = start_date - timedelta(days=30)  # 30-дневная когорта
            cohort_users = await conn.fetchval(
                """
                SELECT COUNT(*) FROM users
                WHERE created_at BETWEEN $1 AND $2
                """,
                cohort_start_date, start_date
            )
            
            # Количество пользователей из когорты, которые были активны в конце периода
            retained_users = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT ua.user_id) 
                FROM user_activities ua
                JOIN users u ON ua.user_id = u.id
                WHERE u.created_at BETWEEN $1 AND $2
                  AND ua.timestamp BETWEEN $3 AND $4
                """,
                cohort_start_date, start_date, end_date - timedelta(days=1), end_date
            )

        cohort_count = cohort_users or 0
        retained_count = retained_users or 0
        retention_rate = (retained_count / cohort_count * 100) if cohort_count > 0 else 0
        
        return {
            'cohort_size': cohort_count,
            'retained_users': retained_count,
            'retention_rate': retention_rate
        }

    async def get_user_analytics_insights(self, user_id: int) -> Dict[str, Any]:
        """Получение инсайтов аналитики пользователя"""
        # Получаем поведенческий профиль пользователя
        behavior_profile = await self._get_user_behavior_profile(user_id)
        
        # Получаем последние взаимодействия
        recent_interactions = await self._get_recent_user_interactions(user_id, 50)
        
        # Получаем статистику использования
        usage_stats = await self._get_user_usage_statistics(user_id)
        
        # Генерируем рекомендации
        recommendations = await self._generate_user_analytics_recommendations(user_id, behavior_profile, usage_stats)
        
        insights = {
            'user_id': user_id,
            'behavior_profile': behavior_profile,
            'recent_interactions': recent_interactions,
            'usage_statistics': usage_stats,
            'engagement_trends': await self._analyze_engagement_trends(user_id),
            'feature_usage_patterns': await self._analyze_feature_usage_patterns(user_id),
            'recommendations': recommendations,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return insights

    async def _get_user_behavior_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение профиля поведения пользователя"""
        # В реальной системе это будет из сервиса поведенческого анализа
        # Пока возвращаем заглушку
        return {
            'user_id': user_id,
            'activity_level': 'medium',
            'peak_usage_times': ['morning', 'evening'],
            'preferred_features': ['messaging', 'file_sharing'],
            'engagement_score': 0.65,
            'churn_risk_score': 0.15
        }

    async def _get_recent_user_interactions(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Получение последних взаимодействий пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT interaction_type, target_id, action_details, timestamp, duration, satisfaction_score
                FROM user_interactions
                WHERE user_id = $1
                ORDER BY timestamp DESC
                LIMIT $2
                """,
                user_id, limit
            )

        interactions = []
        for row in rows:
            interaction = {
                'type': row['interaction_type'],
                'target_id': row['target_id'],
                'action_details': json.loads(row['action_details']) if row['action_details'] else {},
                'timestamp': row['timestamp'].isoformat(),
                'duration': row['duration'],
                'satisfaction_score': row['satisfaction_score']
            }
            interactions.append(interaction)

        return interactions

    async def _get_user_usage_statistics(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики использования пользователя"""
        async with db_pool.acquire() as conn:
            # Сообщения
            message_stats = await conn.fetchrow(
                """
                SELECT COUNT(*) as total_messages, 
                       COUNT(CASE WHEN timestamp > NOW() - INTERVAL '7 days' THEN 1 END) as messages_last_7_days,
                       COUNT(CASE WHEN timestamp > NOW() - INTERVAL '30 days' THEN 1 END) as messages_last_30_days
                FROM messages WHERE sender_id = $1
                """,
                user_id
            )
            
            # Файлы
            file_stats = await conn.fetchrow(
                """
                SELECT COUNT(*) as total_files, 
                       SUM(size) as total_size_bytes,
                       COUNT(CASE WHEN uploaded_at > NOW() - INTERVAL '7 days' THEN 1 END) as files_last_7_days
                FROM files WHERE uploader_id = $1
                """,
                user_id
            )
            
            # Задачи
            task_stats = await conn.fetchrow(
                """
                SELECT COUNT(*) as total_tasks,
                       COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_tasks,
                       COUNT(CASE WHEN created_at > NOW() - INTERVAL '7 days' THEN 1 END) as tasks_last_7_days
                FROM tasks WHERE $1 = ANY(assignee_ids) OR creator_id = $1
                """,
                user_id
            )

        return {
            'messages': {
                'total': message_stats['total_messages'] or 0,
                'last_7_days': message_stats['messages_last_7_days'] or 0,
                'last_30_days': message_stats['messages_last_30_days'] or 0
            },
            'files': {
                'total': file_stats['total_files'] or 0,
                'total_size_bytes': file_stats['total_size_bytes'] or 0,
                'total_size_formatted': self._format_bytes(file_stats['total_size_bytes'] or 0),
                'last_7_days': file_stats['files_last_7_days'] or 0
            },
            'tasks': {
                'total': task_stats['total_tasks'] or 0,
                'completed': task_stats['completed_tasks'] or 0,
                'completion_rate': (task_stats['completed_tasks'] or 0) / (task_stats['total_tasks'] or 1) * 100,
                'last_7_days': task_stats['tasks_last_7_days'] or 0
            }
        }

    def _format_bytes(self, bytes_value: int) -> str:
        """Форматирование байтов в человекочитаемый вид"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.2f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.2f} PB"

    async def _analyze_engagement_trends(self, user_id: int) -> Dict[str, Any]:
        """Анализ тенденций вовлеченности пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DATE_TRUNC('day', timestamp) as day, AVG(engagement_score) as avg_score
                FROM user_engagement_scores
                WHERE user_id = $1
                GROUP BY DATE_TRUNC('day', timestamp)
                ORDER BY day DESC
                LIMIT 30
                """,
                user_id
            )

        daily_scores = []
        for row in rows:
            daily_scores.append({
                'date': row['day'].isoformat(),
                'score': float(row['avg_score'])
            })

        # Рассчитываем тренд
        if len(daily_scores) >= 2:
            first_score = daily_scores[-1]['score']
            last_score = daily_scores[0]['score']
            trend_direction = "increasing" if last_score > first_score else "decreasing"
            trend_strength = abs(last_score - first_score)
        else:
            trend_direction = "stable"
            trend_strength = 0

        return {
            'daily_scores': daily_scores,
            'trend_direction': trend_direction,
            'trend_strength': trend_strength,
            'current_score': daily_scores[0]['score'] if daily_scores else 0.0
        }

    async def _analyze_feature_usage_patterns(self, user_id: int) -> Dict[str, Any]:
        """Анализ паттернов использования функций пользователем"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT feature_name, COUNT(*) as usage_count
                FROM user_feature_usage
                WHERE user_id = $1
                GROUP BY feature_name
                ORDER BY usage_count DESC
                """,
                user_id
            )

        feature_usage = {}
        for row in rows:
            feature_usage[row['feature_name']] = row['usage_count']

        # Определяем доминирующие функции
        total_usage = sum(feature_usage.values())
        dominant_features = []
        for feature, count in feature_usage.items():
            if count / total_usage > 0.2:  # Если используется более 20% времени
                dominant_features.append(feature)

        return {
            'feature_usage': feature_usage,
            'dominant_features': dominant_features,
            'total_features_used': len(feature_usage),
            'usage_diversity': len(feature_usage) / 10  # Предполагаем, что всего 10 функций
        }

    async def _generate_user_analytics_recommendations(self, user_id: int, 
                                                     behavior_profile: Dict[str, Any],
                                                     usage_stats: Dict[str, Any]) -> List[Dict[str, str]]:
        """Генерация рекомендаций на основе аналитики пользователя"""
        recommendations = []

        # Рекомендации для пользователей с низкой вовлеченностью
        if behavior_profile.get('engagement_score', 0) < 0.5:
            recommendations.append({
                'type': 'engagement',
                'message': 'We noticed you\'re not very active. Try exploring our new features!',
                'action': 'show_feature_discovery_tour'
            })

        # Рекомендации для пользователей, которые часто отправляют сообщения
        if usage_stats['messages']['total'] > 100:
            recommendations.append({
                'type': 'productivity',
                'message': 'You\'re an active chatter! Try our advanced chat shortcuts.',
                'action': 'show_advanced_chat_features'
            })

        # Рекомендации для пользователей, которые часто делятся файлами
        if usage_stats['files']['total'] > 10:
            recommendations.append({
                'type': 'productivity',
                'message': 'You share a lot of files! Try our file organization tools.',
                'action': 'show_file_organization_features'
            })

        # Рекомендации для пользователей, которые часто создают задачи
        if usage_stats['tasks']['total'] > 5:
            recommendations.append({
                'type': 'productivity',
                'message': 'You create many tasks! Try our project templates.',
                'action': 'show_project_templates'
            })

        # Рекомендации для пользователей, которые часто играют
        if behavior_profile.get('preferred_features', []).count('gaming') > 0:
            recommendations.append({
                'type': 'entertainment',
                'message': 'You play games often! Try our new multiplayer games.',
                'action': 'show_multiplayer_games'
            })

        return recommendations

    async def get_business_intelligence_report(self, start_date: datetime, 
                                             end_date: datetime) -> Dict[str, Any]:
        """Получение отчета бизнес-интеллекта"""
        # Получаем метрики пользовательского роста
        user_growth_metrics = await self._get_user_growth_metrics(start_date, end_date)
        
        # Получаем метрики удержания
        retention_metrics = await self._get_retention_metrics(start_date, end_date)
        
        # Получаем метрики оттока
        churn_metrics = await self._get_churn_metrics(start_date, end_date)
        
        # Получаем метрики доходов (если есть платные функции)
        revenue_metrics = await self._get_revenue_metrics(start_date, end_date)
        
        # Получаем метрики конверсии
        conversion_metrics = await self._get_conversion_metrics(start_date, end_date)
        
        # Получаем метрики удовлетворенности
        satisfaction_metrics = await self._get_satisfaction_metrics(start_date, end_date)
        
        report = {
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'user_growth': user_growth_metrics,
            'retention': retention_metrics,
            'churn': churn_metrics,
            'revenue': revenue_metrics,
            'conversion': conversion_metrics,
            'satisfaction': satisfaction_metrics,
            'key_insights': await self._generate_business_insights(
                user_growth_metrics, retention_metrics, churn_metrics
            ),
            'predictions': await self._generate_predictions(start_date, end_date),
            'recommendations': await self._generate_business_recommendations(
                user_growth_metrics, retention_metrics, churn_metrics
            ),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return report

    async def _get_user_growth_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Получение метрик роста пользователей"""
        async with db_pool.acquire() as conn:
            # Новые пользователи
            new_users = await conn.fetchval(
                """
                SELECT COUNT(*) FROM users
                WHERE created_at BETWEEN $1 AND $2
                """,
                start_date, end_date
            )
            
            # Средний рост в день
            days_count = (end_date - start_date).days or 1
            avg_daily_growth = (new_users or 0) / days_count
            
            # Рост по сравнению с предыдущим периодом
            prev_period_start = start_date - (end_date - start_date)
            prev_new_users = await conn.fetchval(
                """
                SELECT COUNT(*) FROM users
                WHERE created_at BETWEEN $1 AND $2
                """,
                prev_period_start, start_date
            )
            
            growth_rate = ((new_users or 0) - (prev_new_users or 0)) / (prev_new_users or 1) * 100

        return {
            'new_users': new_users or 0,
            'avg_daily_growth': avg_daily_growth,
            'growth_rate_percent': growth_rate,
            'cumulative_users': await self._get_total_users_count()
        }

    async def _get_retention_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Получение метрик удержания"""
        async with db_pool.acquire() as conn:
            # 1-дневное удержание
            one_day_retention = await conn.fetchval(
                """
                SELECT 
                    COUNT(DISTINCT ua1.user_id) * 100.0 / COUNT(DISTINCT ua2.user_id) as retention_rate
                FROM user_activities ua1
                JOIN user_activities ua2 ON ua1.user_id = ua2.user_id
                WHERE ua1.timestamp BETWEEN $1 AND $2
                  AND ua2.timestamp BETWEEN $1 + INTERVAL '1 day' AND $2 + INTERVAL '1 day'
                """,
                start_date, start_date + timedelta(days=1)
            )
            
            # 7-дневное удержание
            seven_day_retention = await conn.fetchval(
                """
                SELECT 
                    COUNT(DISTINCT ua1.user_id) * 100.0 / COUNT(DISTINCT ua2.user_id) as retention_rate
                FROM user_activities ua1
                JOIN user_activities ua2 ON ua1.user_id = ua2.user_id
                WHERE ua1.timestamp BETWEEN $1 AND $2
                  AND ua2.timestamp BETWEEN $1 + INTERVAL '7 days' AND $2 + INTERVAL '7 days'
                """,
                start_date, start_date + timedelta(days=1)
            )
            
            # 30-дневное удержание
            thirty_day_retention = await conn.fetchval(
                """
                SELECT 
                    COUNT(DISTINCT ua1.user_id) * 100.0 / COUNT(DISTINCT ua2.user_id) as retention_rate
                FROM user_activities ua1
                JOIN user_activities ua2 ON ua1.user_id = ua2.user_id
                WHERE ua1.timestamp BETWEEN $1 AND $2
                  AND ua2.timestamp BETWEEN $1 + INTERVAL '30 days' AND $2 + INTERVAL '30 days'
                """,
                start_date, start_date + timedelta(days=1)
            )

        return {
            'one_day_retention_percent': float(one_day_retention) if one_day_retention else 0.0,
            'seven_day_retention_percent': float(seven_day_retention) if seven_day_retention else 0.0,
            'thirty_day_retention_percent': float(thirty_day_retention) if thirty_day_retention else 0.0
        }

    async def _get_churn_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Получение метрик оттока"""
        async with db_pool.acquire() as conn:
            # Пользователи, неактивные более 30 дней
            churned_users = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT id) FROM users
                WHERE last_activity < $1 AND created_at < $1
                """,
                end_date - timedelta(days=30)
            )
            
            # Общий счетчик пользователей
            total_users = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at <= $1",
                end_date
            )

        churn_rate = ((churned_users or 0) / (total_users or 1)) * 100

        return {
            'churned_users_count': churned_users or 0,
            'total_users_at_end': total_users or 0,
            'churn_rate_percent': churn_rate
        }

    async def _get_revenue_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Получение метрик доходов"""
        # В реальной системе это будет из таблицы платежей
        # Пока возвращаем заглушку
        return {
            'total_revenue': 0.0,
            'revenue_per_user': 0.0,
            'subscription_revenue': 0.0,
            'in_app_purchase_revenue': 0.0
        }

    async def _get_conversion_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Получение метрик конверсии"""
        # В реальной системе это будет более сложный анализ
        # Пока возвращаем заглушку
        return {
            'registration_to_active_conversion': 0.0,
            'trial_to_paid_conversion': 0.0,
            'feature_usage_conversion': 0.0
        }

    async def _get_satisfaction_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Получение метрик удовлетворенности"""
        async with db_pool.acquire() as conn:
            # Средняя оценка удовлетворенности
            avg_satisfaction = await conn.fetchval(
                """
                SELECT AVG(rating) FROM user_feedback
                WHERE created_at BETWEEN $1 AND $2 AND rating IS NOT NULL
                """,
                start_date, end_date
            )
            
            # Положительные отзывы
            positive_feedback = await conn.fetchval(
                """
                SELECT COUNT(*) FROM user_feedback
                WHERE created_at BETWEEN $1 AND $2 AND rating >= 4
                """,
                start_date, end_date
            )
            
            # Отрицательные отзывы
            negative_feedback = await conn.fetchval(
                """
                SELECT COUNT(*) FROM user_feedback
                WHERE created_at BETWEEN $1 AND $2 AND rating <= 2
                """,
                start_date, end_date
            )

        total_feedback = (positive_feedback or 0) + (negative_feedback or 0)
        positive_ratio = (positive_feedback or 0) / (total_feedback or 1) * 100

        return {
            'avg_satisfaction_rating': float(avg_satisfaction) if avg_satisfaction else 0.0,
            'positive_feedback_count': positive_feedback or 0,
            'negative_feedback_count': negative_feedback or 0,
            'positive_feedback_ratio': positive_ratio
        }

    async def _generate_business_insights(self, user_growth: Dict[str, Any], 
                                        retention: Dict[str, Any], 
                                        churn: Dict[str, Any]) -> List[Dict[str, str]]:
        """Генерация бизнес-инсайтов"""
        insights = []

        # Инсайты по росту
        if user_growth['growth_rate_percent'] > 10:
            insights.append({
                'category': 'growth',
                'message': f'Excellent user growth of {user_growth["growth_rate_percent"]:.2f}% compared to previous period',
                'recommendation': 'Continue current marketing strategies'
            })
        elif user_growth['growth_rate_percent'] < 0:
            insights.append({
                'category': 'growth',
                'message': f'User growth declined by {abs(user_growth["growth_rate_percent"]):.2f}% compared to previous period',
                'recommendation': 'Review marketing strategies and user acquisition channels'
            })

        # Инсайты по удержанию
        if retention['seven_day_retention_percent'] > 50:
            insights.append({
                'category': 'retention',
                'message': f'Good 7-day retention rate of {retention["seven_day_retention_percent"]:.2f}%',
                'recommendation': 'Focus on improving long-term retention'
            })
        else:
            insights.append({
                'category': 'retention',
                'message': f'7-day retention rate of {retention["seven_day_retention_percent"]:.2f}% is below industry standard',
                'recommendation': 'Implement onboarding improvements and user engagement initiatives'
            })

        # Инсайты по оттоку
        if churn['churn_rate_percent'] > 10:
            insights.append({
                'category': 'churn',
                'message': f'High churn rate of {churn["churn_rate_percent"]:.2f}% detected',
                'recommendation': 'Investigate causes of churn and implement retention strategies'
            })

        return insights

    async def _generate_predictions(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Генерация предсказаний"""
        # В реальной системе это будет с использованием ML моделей
        # Пока возвращаем заглушку на основе простой экстраполяции
        days_count = (end_date - start_date).days
        
        # Получаем данные за последний период
        current_growth = await self._get_user_growth_metrics(start_date, end_date)
        
        # Прогнозируем на следующий период (предполагаем линейный тренд)
        predicted_new_users = int(current_growth['avg_daily_growth'] * days_count)
        
        return {
            'predicted_user_growth': {
                'new_users_next_period': predicted_new_users,
                'confidence_level': 0.7  # 70% уверенность
            },
            'predicted_retention': {
                'estimated_7day_retention': current_growth.get('seven_day_retention_percent', 0) * 0.95,  # Снижение на 5%
                'confidence_level': 0.6
            },
            'predicted_churn': {
                'estimated_churn_rate': current_growth.get('churn_rate_percent', 0) * 1.05,  # Увеличение на 5%
                'confidence_level': 0.6
            }
        }

    async def _generate_business_recommendations(self, user_growth: Dict[str, Any], 
                                               retention: Dict[str, Any], 
                                               churn: Dict[str, Any]) -> List[Dict[str, str]]:
        """Генерация бизнес-рекомендаций"""
        recommendations = []

        # Рекомендации по росту
        if user_growth['growth_rate_percent'] < 5:
            recommendations.append({
                'area': 'user_acquisition',
                'priority': 'high',
                'message': 'User growth is below target. Consider expanding marketing efforts.',
                'action': 'increase_marketing_budget_and_channels'
            })

        # Рекомендации по удержанию
        if retention['seven_day_retention_percent'] < 30:
            recommendations.append({
                'area': 'user_retention',
                'priority': 'high',
                'message': 'Low 7-day retention indicates users are not finding value quickly enough.',
                'action': 'improve_onboarding_process_and_initial_user_experience'
            })

        # Рекомендации по оттоку
        if churn['churn_rate_percent'] > 15:
            recommendations.append({
                'area': 'churn_prevention',
                'priority': 'critical',
                'message': 'High churn rate requires immediate attention.',
                'action': 'implement_user_reengagement_programs_and_survey_churn_reasons'
            })

        # Рекомендации по удовлетворенности
        satisfaction_metrics = await self._get_satisfaction_metrics(
            end_date - timedelta(days=30), end_date
        )
        if satisfaction_metrics['avg_satisfaction_rating'] < 3.5:
            recommendations.append({
                'area': 'user_satisfaction',
                'priority': 'high',
                'message': f'Low satisfaction rating of {satisfaction_metrics["avg_satisfaction_rating"]:.2f}.',
                'action': 'address_user_feedback_and_improve_product_quality'
            })

        return recommendations

    async def _log_activity(self, action: str, details: Dict[str, Any]):
        """Логирование активности"""
        activity_id = str(uuid.uuid4())
        activity = {
            'id': activity_id,
            'action': action,
            'details': details,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Сохраняем в Redis для быстрого доступа
        await redis_client.lpush("system_activities", json.dumps(activity))
        await redis_client.ltrim("system_activities", 0, 999)  # Храним последние 1000 активностей

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
analytics_reporting_service = AnalyticsReportingService()
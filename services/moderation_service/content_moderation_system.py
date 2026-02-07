# Data Visualization System
# File: services/visualization_service/data_visualization_system.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid
import hashlib
from dataclasses import dataclass
import io
import base64

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.io as pio
from PIL import Image
import os

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

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

class VisualizationFormat(Enum):
    PNG = "png"
    JPEG = "jpeg"
    SVG = "svg"
    HTML = "html"
    JSON = "json"
    PDF = "pdf"

class DashboardType(Enum):
    USER_ANALYTICS = "user_analytics"
    CHAT_STATISTICS = "chat_statistics"
    CONTENT_ANALYTICS = "content_analytics"
    SYSTEM_PERFORMANCE = "system_performance"
    BUSINESS_INTELLIGENCE = "business_intelligence"
    CUSTOM_DASHBOARD = "custom_dashboard"

class Chart(BaseModel):
    id: str
    title: str
    chart_type: ChartType
    data_source: str  # 'database', 'cache', 'api', 'custom'
    query: Optional[str] = None  # SQL или другой запрос для получения данных
    data: Optional[Dict[str, Any]] = None  # Данные для визуализации
    filters: Optional[Dict[str, Any]] = None  # Фильтры для данных
    settings: Optional[Dict[str, Any]] = None  # Настройки визуализации
    created_at: datetime = None
    updated_at: datetime = None

class Dashboard(BaseModel):
    id: str
    name: str
    description: str
    type: DashboardType
    charts: List[str]  # IDs of charts
    layout: Dict[str, Any]  # Описание расположения элементов
    filters: Optional[Dict[str, Any]] = None  # Общие фильтры для дашборда
    refresh_interval: Optional[int] = None  # Интервал обновления в секундах
    created_at: datetime = None
    updated_at: datetime = None

class DataVisualizationService:
    def __init__(self):
        self.visualization_formats = {
            ChartType.LINE: ['png', 'svg', 'html'],
            ChartType.BAR: ['png', 'svg', 'html'],
            ChartType.PIE: ['png', 'svg', 'html'],
            ChartType.SCATTER: ['png', 'svg', 'html'],
            ChartType.HEATMAP: ['png', 'svg', 'html'],
            ChartType.AREA: ['png', 'svg', 'html'],
            ChartType.COLUMN: ['png', 'svg', 'html'],
            ChartType.RADAR: ['png', 'svg', 'html'],
            ChartType.GAUGE: ['png', 'svg', 'html'],
            ChartType.TREEMAP: ['png', 'svg', 'html'],
            ChartType.SANKEY: ['png', 'svg', 'html'],
            ChartType.SUNBURST: ['png', 'svg', 'html']
        }

        self.color_palettes = {
            'default': ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'],
            'messenger': ['#007AFF', '#5856D6', '#FF2D55', '#4CD964', '#FFCC00', '#FF9500', '#5AC8FA', '#007AFF', '#AF52DE', '#FF3B30'],
            'dark': ['#0A84FF', '#B586FF', '#FF375F', '#30D158', '#FFD60A', '#FF9F0A', '#64D2FF', '#0A84FF', '#C7C7CC', '#AEAEB2'],
            'professional': ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#6A994E', '#386641', '#BC4749', '#F2E8CF', '#F4F1DE', '#E0AED0']
        }

        self.chart_generators = {
            ChartType.LINE: self._generate_line_chart,
            ChartType.BAR: self._generate_bar_chart,
            ChartType.PIE: self._generate_pie_chart,
            ChartType.SCATTER: self._generate_scatter_chart,
            ChartType.HEATMAP: self._generate_heatmap_chart,
            ChartType.AREA: self._generate_area_chart,
            ChartType.COLUMN: self._generate_column_chart,
            ChartType.RADAR: self._generate_radar_chart,
            ChartType.GAUGE: self._generate_gauge_chart,
            ChartType.TREEMAP: self._generate_treemap_chart,
            ChartType.SANKEY: self._generate_sankey_chart,
            ChartType.SUNBURST: self._generate_sunburst_chart
        }

    async def initialize(self):
        """Инициализация сервиса визуализации данных"""
        # Создаем директории для хранения визуализаций
        os.makedirs("/app/visualizations/charts", exist_ok=True)
        os.makedirs("/app/visualizations/dashboards", exist_ok=True)
        
        logger.info("Data visualization service initialized")

    async def create_chart(self, title: str, chart_type: ChartType,
                          data_source: str, query: Optional[str] = None,
                          data: Optional[Dict[str, Any]] = None,
                          filters: Optional[Dict[str, Any]] = None,
                          settings: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Создание новой диаграммы"""
        chart_id = str(uuid.uuid4())

        chart = Chart(
            id=chart_id,
            title=title,
            chart_type=chart_type,
            data_source=data_source,
            query=query,
            data=data,
            filters=filters or {},
            settings=settings or {},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем диаграмму в базу данных
        await self._save_chart_to_db(chart)

        # Добавляем в кэш
        await self._cache_chart(chart)

        # Создаем запись активности
        await self._log_activity("chart_created", {
            "chart_id": chart_id,
            "chart_type": chart_type.value,
            "title": title
        })

        return chart_id

    async def _save_chart_to_db(self, chart: Chart):
        """Сохранение диаграммы в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO charts (
                    id, title, chart_type, data_source, query, data, filters, settings, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                chart.id, chart.title, chart.chart_type.value, chart.data_source,
                chart.query, json.dumps(chart.data) if chart.data else None,
                json.dumps(chart.filters) if chart.filters else None,
                json.dumps(chart.settings) if chart.settings else None,
                chart.created_at, chart.updated_at
            )

    async def _cache_chart(self, chart: Chart):
        """Кэширование диаграммы"""
        await redis_client.setex(f"chart:{chart.id}", 3600, chart.model_dump_json())

    async def _get_cached_chart(self, chart_id: str) -> Optional[Chart]:
        """Получение диаграммы из кэша"""
        cached = await redis_client.get(f"chart:{chart_id}")
        if cached:
            return Chart(**json.loads(cached.decode()))
        return None

    async def get_chart_data(self, chart_id: str) -> Optional[Dict[str, Any]]:
        """Получение данных для диаграммы"""
        # Сначала проверяем кэш
        cached_chart = await self._get_cached_chart(chart_id)
        if cached_chart and cached_chart.data:
            return cached_chart.data

        # Затем получаем из базы данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data_source, query, filters FROM charts WHERE id = $1",
                chart_id
            )

        if not row:
            return None

        data_source = row['data_source']
        query = row['query']
        filters = json.loads(row['filters']) if row['filters'] else {}

        if data_source == 'database' and query:
            # Выполняем SQL запрос для получения данных
            data = await self._execute_query_for_chart(query, filters)
        elif data_source == 'cache':
            # Получаем данные из кэша
            data = await self._get_data_from_cache(filters)
        elif data_source == 'api':
            # Получаем данные через API
            data = await self._get_data_from_api(filters)
        else:
            # Пользовательские данные
            data = await self._get_custom_chart_data(chart_id, filters)

        # Кэшируем данные
        if data:
            chart = await self._get_cached_chart(chart_id)
            if chart:
                chart.data = data
                await self._cache_chart(chart)

        return data

    async def _execute_query_for_chart(self, query: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Выполнение SQL запроса для получения данных диаграммы"""
        try:
            # Заменяем фильтры в запросе
            for key, value in filters.items():
                query = query.replace(f"${key}", str(value))

            async with db_pool.acquire() as conn:
                rows = await conn.fetch(query)

            # Преобразуем результаты в формат, подходящий для визуализации
            data = {
                'columns': [col for col in rows[0].keys()] if rows else [],
                'rows': [dict(row) for row in rows]
            }

            return data
        except Exception as e:
            logger.error(f"Error executing query for chart: {e}")
            return None

    async def _get_data_from_cache(self, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Получение данных из кэша"""
        # В реальной системе здесь будет получение данных из Redis
        # В зависимости от фильтров
        cache_key = f"chart_data:{hash(json.dumps(filters, sort_keys=True))}"
        cached_data = await redis_client.get(cache_key)

        if cached_data:
            return json.loads(cached_data.decode())

        return None

    async def _get_data_from_api(self, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Получение данных через API"""
        # В реальной системе здесь будет вызов внутреннего API
        # для получения данных для диаграммы
        # Пока возвращаем заглушку с фиктивными данными
        return {
            'columns': ['date', 'value'],
            'rows': [
                {'date': '2023-01-01', 'value': 100},
                {'date': '2023-01-02', 'value': 120},
                {'date': '2023-01-03', 'value': 95},
                {'date': '2023-01-04', 'value': 140},
                {'date': '2023-01-05', 'value': 160}
            ]
        }

    async def _get_custom_chart_data(self, chart_id: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Получение пользовательских данных для диаграммы"""
        # В реальной системе здесь будет специфическая логика
        # для получения пользовательских данных
        # Пока возвращаем заглушку с фиктивными данными
        return {
            'columns': ['category', 'value'],
            'rows': [
                {'category': 'A', 'value': 25},
                {'category': 'B', 'value': 35},
                {'category': 'C', 'value': 40},
                {'category': 'D', 'value': 20}
            ]
        }

    async def generate_chart_visualization(self, chart_id: str,
                                         format: VisualizationFormat = VisualizationFormat.PNG,
                                         width: int = 800, height: int = 600) -> Optional[str]:
        """Генерация визуализации диаграммы"""
        chart = await self._get_cached_chart(chart_id)
        if not chart:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM charts WHERE id = $1",
                    chart_id
                )
            if not row:
                return None
            chart = Chart(
                id=row['id'],
                title=row['title'],
                chart_type=ChartType(row['chart_type']),
                data_source=row['data_source'],
                query=row['query'],
                data=json.loads(row['data']) if row['data'] else None,
                filters=json.loads(row['filters']) if row['filters'] else {},
                settings=json.loads(row['settings']) if row['settings'] else {},
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )

        # Получаем данные для диаграммы
        chart_data = await self.get_chart_data(chart_id)
        if not chart_data:
            return None

        # Генерируем визуализацию в зависимости от типа диаграммы
        generator = self.chart_generators.get(chart.chart_type)
        if generator:
            return await generator(chart, chart_data, format, width, height)
        else:
            return await self._generate_default_chart(chart, chart_data, format, width, height)

    async def _generate_line_chart(self, chart: Chart, data: Dict[str, Any],
                                 format: VisualizationFormat, width: int, height: int) -> Optional[str]:
        """Генерация линейной диаграммы"""
        try:
            if format == VisualizationFormat.HTML:
                # Используем Plotly для интерактивной HTML диаграммы
                df = pd.DataFrame(data['rows'])

                fig = px.line(df, x=data['columns'][0], y=data['columns'][1:],
                             title=chart.title)

                # Применяем настройки
                if chart.settings:
                    if 'color_palette' in chart.settings:
                        palette = self.color_palettes.get(chart.settings['color_palette'],
                                                        self.color_palettes['default'])
                        fig.update_traces(line_color=palette[0])

                html_content = pio.to_html(fig, include_plotlyjs=True, div_id=chart.id)
                return html_content

            else:
                # Используем Matplotlib для статичных изображений
                df = pd.DataFrame(data['rows'])

                plt.figure(figsize=(width/100, height/100))

                for col in data['columns'][1:]:  # Все колонки кроме первой (x-axis)
                    plt.plot(df[data['columns'][0]], df[col], label=col, marker='o')

                plt.title(chart.title)
                plt.xlabel(data['columns'][0])
                plt.ylabel('Values')
                plt.legend()
                plt.grid(True)

                # Применяем настройки
                if chart.settings:
                    if 'color_palette' in chart.settings:
                        palette = self.color_palettes.get(chart.settings['color_palette'],
                                                        self.color_palettes['default'])
                        plt.gca().set_prop_cycle(color=palette)

                plt.tight_layout()

                # Сохраняем в байтовый буфер
                buf = io.BytesIO()
                plt.savefig(buf, format=format.value)
                buf.seek(0)

                # Конвертируем в base64
                image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close()  # Закрываем фигуру, чтобы освободить память

                return f"data:image/{format.value};base64,{image_base64}"
        except Exception as e:
            logger.error(f"Error generating line chart: {e}")
            return None

    async def _generate_bar_chart(self, chart: Chart, data: Dict[str, Any],
                                format: VisualizationFormat, width: int, height: int) -> Optional[str]:
        """Генерация столбчатой диаграммы"""
        try:
            if format == VisualizationFormat.HTML:
                # Используем Plotly для интерактивной HTML диаграммы
                df = pd.DataFrame(data['rows'])

                fig = px.bar(df, x=data['columns'][0], y=data['columns'][1:],
                            title=chart.title)

                # Применяем настройки
                if chart.settings:
                    if 'color_palette' in chart.settings:
                        palette = self.color_palettes.get(chart.settings['color_palette'],
                                                        self.color_palettes['default'])
                        fig.update_traces(marker_color=palette[0])

                html_content = pio.to_html(fig, include_plotlyjs=True, div_id=chart.id)
                return html_content
            else:
                # Используем Matplotlib для статичных изображений
                df = pd.DataFrame(data['rows'])

                plt.figure(figsize=(width/100, height/100))

                x_values = df[data['columns'][0]]
                y_values = df[data['columns'][1]].tolist() if len(data['columns']) > 1 else [0] * len(df)

                bars = plt.bar(x_values, y_values)

                plt.title(chart.title)
                plt.xlabel(data['columns'][0])
                plt.ylabel(data['columns'][1] if len(data['columns']) > 1 else 'Values')

                # Применяем настройки
                if chart.settings:
                    if 'color_palette' in chart.settings:
                        palette = self.color_palettes.get(chart.settings['color_palette'],
                                                        self.color_palettes['default'])
                        for bar, color in zip(bars, palette * (len(bars) // len(palette) + 1)):
                            bar.set_color(color)

                plt.xticks(rotation=45)
                plt.tight_layout()

                # Сохраняем в байтовый буфер
                buf = io.BytesIO()
                plt.savefig(buf, format=format.value)
                buf.seek(0)

                # Конвертируем в base64
                image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close()  # Закрываем фигуру, чтобы освободить память

                return f"data:image/{format.value};base64,{image_base64}"
        except Exception as e:
            logger.error(f"Error generating bar chart: {e}")
            return None

    async def _generate_pie_chart(self, chart: Chart, data: Dict[str, Any],
                                format: VisualizationFormat, width: int, height: int) -> Optional[str]:
        """Генерация круговой диаграммы"""
        try:
            if format == VisualizationFormat.HTML:
                # Используем Plotly для интерактивной HTML диаграммы
                df = pd.DataFrame(data['rows'])

                # Предполагаем, что первая колонка - метки, вторая - значения
                labels = df[data['columns'][0]].tolist()
                values = df[data['columns'][1]].tolist() if len(data['columns']) > 1 else [1] * len(df)

                fig = go.Figure(data=[go.Pie(labels=labels, values=values)])
                fig.update_layout(title=chart.title)

                # Применяем настройки
                if chart.settings:
                    if 'color_palette' in chart.settings:
                        palette = self.color_palettes.get(chart.settings['color_palette'],
                                                        self.color_palettes['default'])
                        fig.update_traces(marker_colors=palette)

                html_content = pio.to_html(fig, include_plotlyjs=True, div_id=chart.id)
                return html_content
            else:
                # Используем Matplotlib для статичных изображений
                df = pd.DataFrame(data['rows'])

                labels = df[data['columns'][0]].tolist()
                sizes = df[data['columns'][1]].tolist() if len(data['columns']) > 1 else [1] * len(df)

                plt.figure(figsize=(width/100, height/100))

                # Применяем настройки
                colors = None
                if chart.settings and 'color_palette' in chart.settings:
                    palette = self.color_palettes.get(chart.settings['color_palette'],
                                                    self.color_palettes['default'])
                    colors = palette[:len(labels)]

                plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
                plt.title(chart.title)
                plt.axis('equal')  # Убедиться, что круг круглый

                # Сохраняем в байтовый буфер
                buf = io.BytesIO()
                plt.savefig(buf, format=format.value)
                buf.seek(0)

                # Конвертируем в base64
                image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close()  # Закрываем фигуру, чтобы освободить память

                return f"data:image/{format.value};base64,{image_base64}"
        except Exception as e:
            logger.error(f"Error generating pie chart: {e}")
            return None

    async def _generate_scatter_chart(self, chart: Chart, data: Dict[str, Any],
                                    format: VisualizationFormat, width: int, height: int) -> Optional[str]:
        """Генерация точечной диаграммы"""
        try:
            if format == VisualizationFormat.HTML:
                # Используем Plotly для интерактивной HTML диаграммы
                df = pd.DataFrame(data['rows'])

                fig = px.scatter(df, x=data['columns'][0], y=data['columns'][1],
                                title=chart.title)

                # Применяем настройки
                if chart.settings:
                    if 'color_palette' in chart.settings:
                        palette = self.color_palettes.get(chart.settings['color_palette'],
                                                        self.color_palettes['default'])
                        fig.update_traces(marker=dict(color=palette[0]))

                html_content = pio.to_html(fig, include_plotlyjs=True, div_id=chart.id)
                return html_content
            else:
                # Используем Matplotlib для статичных изображений
                df = pd.DataFrame(data['rows'])

                plt.figure(figsize=(width/100, height/100))

                x_values = df[data['columns'][0]]
                y_values = df[data['columns'][1]] if len(data['columns']) > 1 else [0] * len(df)

                # Применяем настройки
                color = 'blue'
                if chart.settings and 'color_palette' in chart.settings:
                    palette = self.color_palettes.get(chart.settings['color_palette'],
                                                    self.color_palettes['default'])
                    color = palette[0]

                plt.scatter(x_values, y_values, c=color)

                plt.title(chart.title)
                plt.xlabel(data['columns'][0])
                plt.ylabel(data['columns'][1] if len(data['columns']) > 1 else 'Values')

                plt.tight_layout()

                # Сохраняем в байтовый буфер
                buf = io.BytesIO()
                plt.savefig(buf, format=format.value)
                buf.seek(0)

                # Конвертируем в base64
                image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close()  # Закрываем фигуру, чтобы освободить память

                return f"data:image/{format.value};base64,{image_base64}"
        except Exception as e:
            logger.error(f"Error generating scatter chart: {e}")
            return None

    async def _generate_heatmap_chart(self, chart: Chart, data: Dict[str, Any],
                                    format: VisualizationFormat, width: int, height: int) -> Optional[str]:
        """Генерация тепловой карты"""
        try:
            if format == VisualizationFormat.HTML:
                # Используем Plotly для интерактивной HTML диаграммы
                df = pd.DataFrame(data['rows'])

                # Преобразуем данные в матрицу для тепловой карты
                if len(data['columns']) >= 3:
                    pivot_df = df.pivot(index=data['columns'][0],
                                      columns=data['columns'][1],
                                      values=data['columns'][2])

                    fig = px.imshow(pivot_df.values,
                                   x=pivot_df.columns.tolist(),
                                   y=pivot_df.index.tolist(),
                                   title=chart.title)
                else:
                    # Если недостаточно колонок, создаем простую тепловую карту
                    matrix_data = np.array([[row[col] for col in data['columns'][1:]]
                                          for row in data['rows']])
                    fig = px.imshow(matrix_data, title=chart.title)

                html_content = pio.to_html(fig, include_plotlyjs=True, div_id=chart.id)
                return html_content
            else:
                # Используем Matplotlib для статичных изображений
                df = pd.DataFrame(data['rows'])

                plt.figure(figsize=(width/100, height/100))

                # Преобразуем данные в матрицу для тепловой карты
                if len(data['columns']) >= 3:
                    pivot_df = df.pivot(index=data['columns'][0],
                                      columns=data['columns'][1],
                                      values=data['columns'][2])
                    sns.heatmap(pivot_df, annot=True, fmt=".1f", cmap="viridis")
                else:
                    # Если недостаточно колонок, создаем простую тепловую карту
                    matrix_data = np.array([[row.get(col, 0) for col in data['columns'][1:]]
                                          for row in data['rows']])
                    sns.heatmap(matrix_data, annot=True, fmt=".1f", cmap="viridis")

                plt.title(chart.title)

                # Сохраняем в байтовый буфер
                buf = io.BytesIO()
                plt.savefig(buf, format=format.value)
                buf.seek(0)

                # Конвертируем в base64
                image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close()  # Закрываем фигуру, чтобы освободить память

                return f"data:image/{format.value};base64,{image_base64}"
        except Exception as e:
            logger.error(f"Error generating heatmap chart: {e}")
            return None

    async def _generate_area_chart(self, chart: Chart, data: Dict[str, Any],
                                 format: VisualizationFormat, width: int, height: int) -> Optional[str]:
        """Генерация диаграммы с областями"""
        try:
            if format == VisualizationFormat.HTML:
                # Используем Plotly для интерактивной HTML диаграммы
                df = pd.DataFrame(data['rows'])

                fig = px.area(df, x=data['columns'][0], y=data['columns'][1:],
                             title=chart.title)

                # Применяем настройки
                if chart.settings:
                    if 'color_palette' in chart.settings:
                        palette = self.color_palettes.get(chart.settings['color_palette'],
                                                        self.color_palettes['default'])
                        fig.update_traces(fillcolor=palette[0])

                html_content = pio.to_html(fig, include_plotlyjs=True, div_id=chart.id)
                return html_content
            else:
                # Используем Matplotlib для статичных изображений
                df = pd.DataFrame(data['rows'])

                plt.figure(figsize=(width/100, height/100))

                x_values = df[data['columns'][0]]

                # Применяем настройки
                color = 'skyblue'
                if chart.settings and 'color_palette' in chart.settings:
                    palette = self.color_palettes.get(chart.settings['color_palette'],
                                                    self.color_palettes['default'])
                    color = palette[0]

                for col in data['columns'][1:]:
                    plt.fill_between(x_values, df[col], alpha=0.4, color=color)
                    plt.plot(x_values, df[col], alpha=0.8, color=color)

                plt.title(chart.title)
                plt.xlabel(data['columns'][0])
                plt.ylabel('Values')

                plt.tight_layout()

                # Сохраняем в байтовый буфер
                buf = io.BytesIO()
                plt.savefig(buf, format=format.value)
                buf.seek(0)

                # Конвертируем в base64
                image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close()  # Закрываем фигуру, чтобы освободить память

                return f"data:image/{format.value};base64,{image_base64}"
        except Exception as e:
            logger.error(f"Error generating area chart: {e}")
            return None

    async def _generate_column_chart(self, chart: Chart, data: Dict[str, Any],
                                   format: VisualizationFormat, width: int, height: int) -> Optional[str]:
        """Генерация столбчатой диаграммы (альтернатива bar chart)"""
        try:
            if format == VisualizationFormat.HTML:
                # Используем Plotly для интерактивной HTML диаграммы
                df = pd.DataFrame(data['rows'])

                fig = px.histogram(df, x=data['columns'][0], y=data['columns'][1],
                                  title=chart.title)

                # Применяем настройки
                if chart.settings:
                    if 'color_palette' in chart.settings:
                        palette = self.color_palettes.get(chart.settings['color_palette'],
                                                        self.color_palettes['default'])
                        fig.update_traces(marker_color=palette[0])

                html_content = pio.to_html(fig, include_plotlyjs=True, div_id=chart.id)
                return html_content
            else:
                # Используем Matplotlib для статичных изображений
                df = pd.DataFrame(data['rows'])

                plt.figure(figsize=(width/100, height/100))

                x_values = df[data['columns'][0]]
                y_values = df[data['columns'][1]] if len(data['columns']) > 1 else [0] * len(df)

                # Применяем настройки
                color = 'steelblue'
                if chart.settings and 'color_palette' in chart.settings:
                    palette = self.color_palettes.get(chart.settings['color_palette'],
                                                    self.color_palettes['default'])
                    color = palette[0]

                bars = plt.bar(x_values, y_values, color=color)

                plt.title(chart.title)
                plt.xlabel(data['columns'][0])
                plt.ylabel(data['columns'][1] if len(data['columns']) > 1 else 'Values')

                plt.xticks(rotation=45)
                plt.tight_layout()

                # Сохраняем в байтовый буфер
                buf = io.BytesIO()
                plt.savefig(buf, format=format.value)
                buf.seek(0)

                # Конвертируем в base64
                image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close()  # Закрываем фигуру, чтобы освободить память

                return f"data:image/{format.value};base64,{image_base64}"
        except Exception as e:
            logger.error(f"Error generating column chart: {e}")
            return None

    async def _generate_radar_chart(self, chart: Chart, data: Dict[str, Any],
                                  format: VisualizationFormat, width: int, height: int) -> Optional[str]:
        """Генерация радарной диаграммы"""
        try:
            if format == VisualizationFormat.HTML:
                # Используем Plotly для интерактивной HTML диаграммы
                df = pd.DataFrame(data['rows'])

                categories = data['columns'][1:] if len(data['columns']) > 1 else data['columns']
                values = df.iloc[0, 1:].tolist() if len(data['columns']) > 1 else df.iloc[0, :].tolist()

                # Добавляем первый элемент в конец для замыкания диаграммы
                values += values[:1]

                angles = [n / float(len(categories)) * 2 * np.pi for n in range(len(categories))]
                angles += angles[:1]

                fig = go.Figure(data=go.Scatterpolar(
                    r=values,
                    theta=categories + [categories[0]],  # Замыкаем диаграмму
                    fill='toself'
                ))

                fig.update_layout(
                    polar=dict(
                        radialaxis=dict(
                            visible=True
                        )),
                    title=chart.title,
                    showlegend=False
                )

                html_content = pio.to_html(fig, include_plotlyjs=True, div_id=chart.id)
                return html_content
            else:
                # Используем Matplotlib для статичных изображений
                df = pd.DataFrame(data['rows'])

                categories = data['columns'][1:] if len(data['columns']) > 1 else data['columns']
                values = df.iloc[0, 1:].tolist() if len(data['columns']) > 1 else df.iloc[0, :].tolist()

                # Добавляем первый элемент в конец для замыкания диаграммы
                values += values[:1]

                angles = [n / float(len(categories)) * 2 * np.pi for n in range(len(categories))]
                angles += angles[:1]

                plt.figure(figsize=(width/100, height/100))
                ax = plt.subplot(111, projection='polar')

                # Применяем настройки
                color = 'teal'
                if chart.settings and 'color_palette' in chart.settings:
                    palette = self.color_palettes.get(chart.settings['color_palette'],
                                                    self.color_palettes['default'])
                    color = palette[0]

                ax.plot(angles, values, linewidth=1, linestyle='solid', color=color)
                ax.fill(angles, values, color=color, alpha=0.25)

                plt.xticks(angles[:-1], categories, color='grey', size=8)
                ax.set_rlabel_position(0)
                plt.yticks([0.25, 0.5, 0.75], ["0.25", "0.5", "0.75"], color="grey", size=7)
                plt.ylim(0, 1)

                plt.title(chart.title, size=11, y=1.1)

                # Сохраняем в байтовый буфер
                buf = io.BytesIO()
                plt.savefig(buf, format=format.value)
                buf.seek(0)

                # Конвертируем в base64
                image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close()  # Закрываем фигуру, чтобы освободить память

                return f"data:image/{format.value};base64,{image_base64}"
        except Exception as e:
            logger.error(f"Error generating radar chart: {e}")
            return None

    async def _generate_gauge_chart(self, chart: Chart, data: Dict[str, Any],
                                  format: VisualizationFormat, width: int, height: int) -> Optional[str]:
        """Генерация индикаторной диаграммы (gauge)"""
        try:
            if format == VisualizationFormat.HTML:
                # Используем Plotly для интерактивной HTML диаграммы
                df = pd.DataFrame(data['rows'])

                # Получаем значение для индикатора
                value = df.iloc[0, 1] if len(data['columns']) > 1 else df.iloc[0, 0]

                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=value,
                    domain={'x': [0, 1], 'y': [0, 1]},
                    title={'text': chart.title},
                    gauge={'axis': {'range': [None, 100]},
                           'bar': {'color': "darkblue"},
                           'steps': [
                               {'range': [0, 25], 'color': "lightgray"},
                               {'range': [25, 50], 'color': "gray"},
                               {'range': [50, 75], 'color': "lightyellow"},
                               {'range': [75, 100], 'color': "lightgreen"}]))

                html_content = pio.to_html(fig, include_plotlyjs=True, div_id=chart.id)
                return html_content
            else:
                # Для статичных изображений создаем простую визуализацию
                df = pd.DataFrame(data['rows'])

                # Получаем значение для индикатора
                value = df.iloc[0, 1] if len(data['columns']) > 1 else df.iloc[0, 0]

                plt.figure(figsize=(width/100, height/100))

                # Создаем простой индикатор
                plt.text(0.5, 0.6, f"{value:.2f}", fontsize=40, ha='center', va='center')
                plt.text(0.5, 0.4, chart.title, fontsize=16, ha='center', va='center')

                # Рисуем шкалу
                plt.axhline(y=0.2, xmin=0.1, xmax=0.9, color='gray', linewidth=2)

                # Рисуем индикатор
                indicator_pos = 0.1 + (value / 100) * 0.8
                plt.axvline(x=indicator_pos, ymin=0.15, ymax=0.25, color='red', linewidth=3)

                plt.xlim(0, 1)
                plt.ylim(0, 1)
                plt.axis('off')

                # Сохраняем в байтовый буфер
                buf = io.BytesIO()
                plt.savefig(buf, format=format.value)
                buf.seek(0)

                # Конвертируем в base64
                image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close()  # Закрываем фигуру, чтобы освободить память

                return f"data:image/{format.value};base64,{image_base64}"
        except Exception as e:
            logger.error(f"Error generating gauge chart: {e}")
            return None

    async def _generate_treemap_chart(self, chart: Chart, data: Dict[str, Any],
                                    format: VisualizationFormat, width: int, height: int) -> Optional[str]:
        """Генерация древовидной карты"""
        try:
            if format == VisualizationFormat.HTML:
                # Используем Plotly для интерактивной HTML диаграммы
                df = pd.DataFrame(data['rows'])

                # Предполагаем, что у нас есть колонки: category, value, parent
                if len(data['columns']) >= 3:
                    fig = px.treemap(df,
                                    path=[data['columns'][0]],
                                    values=data['columns'][1],
                                    title=chart.title)
                else:
                    # Если недостаточно колонок, используем только значения
                    fig = px.treemap(df,
                                    path=[data['columns'][0]] if len(data['columns']) > 0 else ['index'],
                                    values=data['columns'][1] if len(data['columns']) > 1 else None,
                                    title=chart.title)

                html_content = pio.to_html(fig, include_plotlyjs=True, div_id=chart.id)
                return html_content
            else:
                # Для статичных изображений используем matplotlib
                df = pd.DataFrame(data['rows'])

                plt.figure(figsize=(width/100, height/100))

                # Простая реализация - в реальности treemap требует специализированной библиотеки
                # или более сложной визуализации
                if len(data['columns']) >= 2:
                    labels = df[data['columns'][0]].tolist()
                    sizes = df[data['columns'][1]].tolist()

                    # Создаем простую диаграмму, имитирующую treemap
                    patches, texts = plt.pie(sizes, labels=labels, startangle=90)

                    # Применяем настройки
                    if chart.settings and 'color_palette' in chart.settings:
                        palette = self.color_palettes.get(chart.settings['color_palette'],
                                                        self.color_palettes['default'])
                        for patch, color in zip(patches, palette * (len(patches) // len(palette) + 1)):
                            patch.set_color(color)

                plt.title(chart.title)
                plt.axis('equal')

                # Сохраняем в байтовый буфер
                buf = io.BytesIO()
                plt.savefig(buf, format=format.value)
                buf.seek(0)

                # Конвертируем в base64
                image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close()  # Закрываем фигуру, чтобы освободить память

                return f"data:image/{format.value};base64,{image_base64}"
        except Exception as e:
            logger.error(f"Error generating treemap chart: {e}")
            return None

    async def _generate_sankey_chart(self, chart: Chart, data: Dict[str, Any],
                                   format: VisualizationFormat, width: int, height: int) -> Optional[str]:
        """Генерация диаграммы Sankey"""
        try:
            if format == VisualizationFormat.HTML:
                # Используем Plotly для интерактивной HTML диаграммы
                df = pd.DataFrame(data['rows'])

                # Предполагаем, что у нас есть колонки: source, target, value
                if len(data['columns']) >= 3:
                    sources = df[data['columns'][0]].tolist()
                    targets = df[data['columns'][1]].tolist()
                    values = df[data['columns'][2]].tolist()

                    # Преобразуем в числовые индексы
                    unique_nodes = list(set(sources + targets))
                    source_indices = [unique_nodes.index(s) for s in sources]
                    target_indices = [unique_nodes.index(t) for t in targets]

                    fig = go.Figure(data=[go.Sankey(
                        arrangement="snap",
                        node=dict(
                            pad=15,
                            thickness=20,
                            line=dict(color="black", width=0.5),
                            label=unique_nodes
                        ),
                        link=dict(
                            source=source_indices,
                            target=target_indices,
                            value=values
                        ))])

                    fig.update_layout(title=chart.title)

                    html_content = pio.to_html(fig, include_plotlyjs=True, div_id=chart.id)
                    return html_content
            else:
                # Для статичных изображений создаем простую визуализацию
                plt.figure(figsize=(width/100, height/100))

                # Простая визуализация - в реальности требует специализированной библиотеки
                plt.text(0.5, 0.5, "Sankey Diagram", fontsize=20, ha='center', va='center')
                plt.text(0.5, 0.4, "Interactive visualization available in HTML format",
                        fontsize=12, ha='center', va='center')
                plt.title(chart.title)
                plt.axis('off')

                # Сохраняем в байтовый буфер
                buf = io.BytesIO()
                plt.savefig(buf, format=format.value)
                buf.seek(0)

                # Конвертируем в base64
                image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close()  # Закрываем фигуру, чтобы освободить память

                return f"data:image/{format.value};base64,{image_base64}"
        except Exception as e:
            logger.error(f"Error generating sankey chart: {e}")
            return None

    async def _generate_sunburst_chart(self, chart: Chart, data: Dict[str, Any],
                                     format: VisualizationFormat, width: int, height: int) -> Optional[str]:
        """Генерация солнечной диаграммы"""
        try:
            if format == VisualizationFormat.HTML:
                # Используем Plotly для интерактивной HTML диаграммы
                df = pd.DataFrame(data['rows'])

                # Предполагаем, что у нас есть колонки: parents, labels, values
                if len(data['columns']) >= 3:
                    fig = px.sunburst(df,
                                     path=[data['columns'][0], data['columns'][1]],
                                     values=data['columns'][2],
                                     title=chart.title)
                else:
                    # Если недостаточно колонок, используем только метки и значения
                    fig = px.sunburst(df,
                                     path=[data['columns'][0]] if len(data['columns']) > 0 else ['index'],
                                     values=data['columns'][1] if len(data['columns']) > 1 else None,
                                     title=chart.title)

                html_content = pio.to_html(fig, include_plotlyjs=True, div_id=chart.id)
                return html_content
            else:
                # Для статичных изображений создаем простую визуализацию
                plt.figure(figsize=(width/100, height/100))

                # Простая визуализация - в реальности требует специализированной библиотеки
                plt.text(0.5, 0.5, "Sunburst Diagram", fontsize=20, ha='center', va='center')
                plt.text(0.5, 0.4, "Interactive visualization available in HTML format",
                        fontsize=12, ha='center', va='center')
                plt.title(chart.title)
                plt.axis('off')

                # Сохраняем в байтовый буфер
                buf = io.BytesIO()
                plt.savefig(buf, format=format.value)
                buf.seek(0)

                # Конвертируем в base64
                image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close()  # Закрываем фигуру, чтобы освободить память

                return f"data:image/{format.value};base64,{image_base64}"
        except Exception as e:
            logger.error(f"Error generating sunburst chart: {e}")
            return None

    async def _generate_default_chart(self, chart: Chart, data: Dict[str, Any],
                                    format: VisualizationFormat, width: int, height: int) -> Optional[str]:
        """Генерация диаграммы по умолчанию"""
        try:
            if format == VisualizationFormat.JSON:
                # Возвращаем данные в JSON формате
                return json.dumps({
                    'chart_id': chart.id,
                    'title': chart.title,
                    'data': data,
                    'timestamp': datetime.utcnow().isoformat()
                })
            else:
                # Создаем простую диаграмму по умолчанию
                plt.figure(figsize=(width/100, height/100))

                if data and 'rows' in data and data['rows']:
                    # Используем первую колонку как x, вторую как y
                    if len(data['columns']) >= 2:
                        df = pd.DataFrame(data['rows'])
                        x_values = df[data['columns'][0]]
                        y_values = df[data['columns'][1]]

                        plt.plot(x_values, y_values, marker='o')
                        plt.title(chart.title)
                        plt.xlabel(data['columns'][0])
                        plt.ylabel(data['columns'][1])
                        plt.xticks(rotation=45)
                        plt.tight_layout()
                    else:
                        # Если недостаточно колонок, просто выводим сообщение
                        plt.text(0.5, 0.5, "Insufficient data for visualization",
                                fontsize=16, ha='center', va='center')
                        plt.title(chart.title)
                        plt.axis('off')
                else:
                    plt.text(0.5, 0.5, "No data available", fontsize=16, ha='center', va='center')
                    plt.title(chart.title)
                    plt.axis('off')

                # Сохраняем в байтовый буфер
                buf = io.BytesIO()
                plt.savefig(buf, format=format.value)
                buf.seek(0)

                # Конвертируем в base64
                image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                plt.close()  # Закрываем фигуру, чтобы освободить память

                return f"data:image/{format.value};base64,{image_base64}"
        except Exception as e:
            logger.error(f"Error generating default chart: {e}")
            return None

    async def create_dashboard(self, name: str, description: str, dashboard_type: DashboardType,
                             charts: List[str], layout: Dict[str, Any],
                             filters: Optional[Dict[str, Any]] = None,
                             refresh_interval: Optional[int] = None) -> Optional[str]:
        """Создание дашборда"""
        dashboard_id = str(uuid.uuid4())

        dashboard = Dashboard(
            id=dashboard_id,
            name=name,
            description=description,
            type=dashboard_type,
            charts=charts,
            layout=layout,
            filters=filters or {},
            refresh_interval=refresh_interval,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем дашборд в базу данных
        await self._save_dashboard_to_db(dashboard)

        # Добавляем в кэш
        await self._cache_dashboard(dashboard)

        # Создаем запись активности
        await self._log_activity("dashboard_created", {
            "dashboard_id": dashboard_id,
            "dashboard_type": dashboard_type.value,
            "chart_count": len(charts)
        })

        return dashboard_id

    async def _save_dashboard_to_db(self, dashboard: Dashboard):
        """Сохранение дашборда в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO dashboards (
                    id, name, description, type, charts, layout, filters, refresh_interval, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                dashboard.id, dashboard.name, dashboard.description, dashboard.type.value,
                dashboard.charts, json.dumps(dashboard.layout),
                json.dumps(dashboard.filters) if dashboard.filters else None,
                dashboard.refresh_interval, dashboard.created_at, dashboard.updated_at
            )

    async def _cache_dashboard(self, dashboard: Dashboard):
        """Кэширование дашборда"""
        await redis_client.setex(f"dashboard:{dashboard.id}", 3600, dashboard.model_dump_json())

    async def _get_cached_dashboard(self, dashboard_id: str) -> Optional[Dashboard]:
        """Получение дашборда из кэша"""
        cached = await redis_client.get(f"dashboard:{dashboard_id}")
        if cached:
            return Dashboard(**json.loads(cached.decode()))
        return None

    async def get_dashboard_visualization(self, dashboard_id: str,
                                        format: VisualizationFormat = VisualizationFormat.HTML,
                                        width: int = 1200, height: int = 800) -> Optional[str]:
        """Получение визуализации дашборда"""
        # Получаем дашборд
        dashboard = await self._get_cached_dashboard(dashboard_id)
        if not dashboard:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM dashboards WHERE id = $1",
                    dashboard_id
                )
            if not row:
                return None
            dashboard = Dashboard(
                id=row['id'],
                name=row['name'],
                description=row['description'],
                type=DashboardType(row['type']),
                charts=row['charts'],
                layout=json.loads(row['layout']),
                filters=json.loads(row['filters']) if row['filters'] else {},
                refresh_interval=row['refresh_interval'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )

        # Получаем визуализации для всех диаграмм дашборда
        chart_visualizations = []
        for chart_id in dashboard.charts:
            viz = await self.generate_chart_visualization(chart_id, format, width//2, height//2)
            if viz:
                chart_visualizations.append({
                    'chart_id': chart_id,
                    'visualization': viz
                })

        if format == VisualizationFormat.HTML:
            # Создаем HTML страницу с дашбордом
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>{dashboard.name}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; }}
                    .dashboard-container {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; }}
                    .chart-container {{ border: 1px solid #ddd; border-radius: 8px; padding: 10px; }}
                    .dashboard-header {{ margin-bottom: 20px; }}
                    .dashboard-title {{ font-size: 24px; margin-bottom: 5px; }}
                    .dashboard-description {{ color: #666; }}
                </style>
            </head>
            <body>
                <div class="dashboard-header">
                    <h1 class="dashboard-title">{dashboard.name}</h1>
                    <p class="dashboard-description">{dashboard.description}</p>
                </div>
                <div class="dashboard-container">
            """

            for chart_viz in chart_visualizations:
                html_content += f"""
                    <div class="chart-container">
                        <div id="chart-{chart_viz['chart_id']}">
                            {chart_viz['visualization']}
                        </div>
                    </div>
                """

            html_content += """
                </div>
            </body>
            </html>
            """

            return html_content
        elif format == VisualizationFormat.JSON:
            # Возвращаем JSON с визуализациями
            return json.dumps({
                'dashboard_id': dashboard.id,
                'name': dashboard.name,
                'description': dashboard.description,
                'charts': chart_visualizations,
                'timestamp': datetime.utcnow().isoformat()
            })
        else:
            # Для других форматов создаем объединенное изображение
            return await self._combine_chart_images(chart_visualizations, format, width, height)

    async def _combine_chart_images(self, chart_visualizations: List[Dict[str, str]],
                                  format: VisualizationFormat, width: int, height: int) -> str:
        """Объединение изображений диаграмм в одно изображение дашборда"""
        try:
            # В реальной системе здесь будет объединение изображений
            # с использованием Pillow или другой библиотеки
            # Для упрощения возвращаем заглушку

            plt.figure(figsize=(width/100, height/100))
            plt.text(0.5, 0.5, f"Dashboard with {len(chart_visualizations)} charts",
                    fontsize=20, ha='center', va='center')
            plt.title("Combined Dashboard Visualization")
            plt.axis('off')

            # Сохраняем в байтовый буфер
            buf = io.BytesIO()
            plt.savefig(buf, format=format.value)
            buf.seek(0)

            # Конвертируем в base64
            image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            plt.close()

            return f"data:image/{format.value};base64,{image_base64}"
        except Exception as e:
            logger.error(f"Error combining chart images: {e}")
            return ""

    async def get_user_analytics_dashboard(self, user_id: int) -> Optional[str]:
        """Получение дашборда аналитики пользователя"""
        # Получаем данные пользователя
        user_data = await self._get_user_analytics_data(user_id)

        if not user_data:
            return None

        # Создаем диаграммы для дашборда
        charts = []

        # Диаграмма активности
        activity_chart_id = await self.create_chart(
            title="User Activity Over Time",
            chart_type=ChartType.LINE,
            data_source="custom",
            data=user_data['activity_over_time']
        )
        if activity_chart_id:
            charts.append(activity_chart_id)

        # Диаграмма использования функций
        feature_usage_chart_id = await self.create_chart(
            title="Feature Usage Distribution",
            chart_type=ChartType.PIE,
            data_source="custom",
            data=user_data['feature_usage']
        )
        if feature_usage_chart_id:
            charts.append(feature_usage_chart_id)

        # Диаграмма взаимодействий
        interactions_chart_id = await self.create_chart(
            title="Interaction Types",
            chart_type=ChartType.BAR,
            data_source="custom",
            data=user_data['interactions']
        )
        if interactions_chart_id:
            charts.append(interactions_chart_id)

        # Создаем дашборд
        dashboard_id = await self.create_dashboard(
            name=f"User Analytics Dashboard - {user_id}",
            description=f"Personalized analytics dashboard for user {user_id}",
            dashboard_type=DashboardType.USER_ANALYTICS,
            charts=charts,
            layout={
                'rows': 2,
                'columns': 2,
                'chart_positions': {
                    activity_chart_id: {'row': 0, 'col': 0, 'span': {'rows': 1, 'cols': 2}},
                    feature_usage_chart_id: {'row': 1, 'col': 0, 'span': {'rows': 1, 'cols': 1}},
                    interactions_chart_id: {'row': 1, 'col': 1, 'span': {'rows': 1, 'cols': 1}}
                }
            }
        )

        if dashboard_id:
            # Генерируем визуализацию дашборда
            return await self.get_dashboard_visualization(dashboard_id, VisualizationFormat.HTML)
        else:
            return None

    async def _get_user_analytics_data(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение данных аналитики пользователя"""
        async with db_pool.acquire() as conn:
            # Получаем активность пользователя за последние 30 дней
            activity_data = await conn.fetch(
                """
                SELECT DATE_TRUNC('day', timestamp) as day, COUNT(*) as count
                FROM user_interactions
                WHERE user_id = $1 AND timestamp >= NOW() - INTERVAL '30 days'
                GROUP BY DATE_TRUNC('day', timestamp)
                ORDER BY day
                """,
                user_id
            )

            # Получаем использование функций
            feature_usage = await conn.fetch(
                """
                SELECT interaction_type, COUNT(*) as count
                FROM user_interactions
                WHERE user_id = $1
                GROUP BY interaction_type
                ORDER BY count DESC
                """,
                user_id
            )

            # Получаем типы взаимодействий
            interaction_types = await conn.fetch(
                """
                SELECT action, COUNT(*) as count
                FROM user_activities
                WHERE user_id = $1
                GROUP BY action
                ORDER BY count DESC
                """,
                user_id
            )

        return {
            'activity_over_time': [
                {'date': row['day'].isoformat(), 'count': row['count']}
                for row in activity_data
            ],
            'feature_usage': [
                {'feature': row['interaction_type'], 'count': row['count']}
                for row in feature_usage
            ],
            'interactions': [
                {'type': row['action'], 'count': row['count']}
                for row in interaction_types
            ]
        }

    async def get_system_performance_dashboard(self) -> Optional[str]:
        """Получение дашборда производительности системы"""
        # Получаем системные метрики
        system_metrics = await self._get_system_performance_metrics()

        if not system_metrics:
            return None

        # Создаем диаграммы для дашборда
        charts = []

        # Диаграмма использования CPU
        cpu_chart_id = await self.create_chart(
            title="CPU Usage Over Time",
            chart_type=ChartType.LINE,
            data_source="custom",
            data=system_metrics['cpu_usage']
        )
        if cpu_chart_id:
            charts.append(cpu_chart_id)

        # Диаграмма использования памяти
        memory_chart_id = await self.create_chart(
            title="Memory Usage Over Time",
            chart_type=ChartType.LINE,
            data_source="custom",
            data=system_metrics['memory_usage']
        )
        if memory_chart_id:
            charts.append(memory_chart_id)

        # Диаграмма времени отклика
        response_time_chart_id = await self.create_chart(
            title="Response Time Distribution",
            chart_type=ChartType.AREA,
            data_source="custom",
            data=system_metrics['response_times']
        )
        if response_time_chart_id:
            charts.append(response_time_chart_id)

        # Диаграмма пропускной способности
        throughput_chart_id = await self.create_chart(
            title="System Throughput",
            chart_type=ChartType.COLUMN,
            data_source="custom",
            data=system_metrics['throughput']
        )
        if throughput_chart_id:
            charts.append(throughput_chart_id)

        # Создаем дашборд
        dashboard_id = await self.create_dashboard(
            name="System Performance Dashboard",
            description="Real-time system performance monitoring dashboard",
            dashboard_type=DashboardType.SYSTEM_PERFORMANCE,
            charts=charts,
            layout={
                'rows': 2,
                'columns': 2,
                'chart_positions': {
                    cpu_chart_id: {'row': 0, 'col': 0, 'span': {'rows': 1, 'cols': 1}},
                    memory_chart_id: {'row': 0, 'col': 1, 'span': {'rows': 1, 'cols': 1}},
                    response_time_chart_id: {'row': 1, 'col': 0, 'span': {'rows': 1, 'cols': 1}},
                    throughput_chart_id: {'row': 1, 'col': 1, 'span': {'rows': 1, 'cols': 1}}
                }
            }
        )

        if dashboard_id:
            # Генерируем визуализацию дашборда
            return await self.get_dashboard_visualization(dashboard_id, VisualizationFormat.HTML)
        else:
            return None

    async def _get_system_performance_metrics(self) -> Optional[Dict[str, Any]]:
        """Получение метрик производительности системы"""
        async with db_pool.acquire() as conn:
            # Получаем метрики CPU за последние 24 часа
            cpu_metrics = await conn.fetch(
                """
                SELECT DATE_TRUNC('hour', recorded_at) as hour, AVG(value) as avg_cpu_usage
                FROM performance_metrics
                WHERE metric_name = 'cpu_usage_percent' AND recorded_at >= NOW() - INTERVAL '24 hours'
                GROUP BY DATE_TRUNC('hour', recorded_at)
                ORDER BY hour
                """,
                user_id
            )

            # Получаем метрики памяти за последние 24 часа
            memory_metrics = await conn.fetch(
                """
                SELECT DATE_TRUNC('hour', recorded_at) as hour, AVG(value) as avg_memory_usage
                FROM performance_metrics
                WHERE metric_name = 'memory_usage_percent' AND recorded_at >= NOW() - INTERVAL '24 hours'
                GROUP BY DATE_TRUNC('hour', recorded_at)
                ORDER BY hour
                """,
                user_id
            )

            # Получаем метрики времени отклика за последние 24 часа
            response_time_metrics = await conn.fetch(
                """
                SELECT DATE_TRUNC('hour', recorded_at) as hour, AVG(value) as avg_response_time
                FROM performance_metrics
                WHERE metric_name = 'response_time_ms' AND recorded_at >= NOW() - INTERVAL '24 hours'
                GROUP BY DATE_TRUNC('hour', recorded_at)
                ORDER BY hour
                """,
                user_id
            )

            # Получаем метрики пропускной способности за последние 24 часа
            throughput_metrics = await conn.fetch(
                """
                SELECT DATE_TRUNC('hour', recorded_at) as hour, AVG(value) as avg_throughput
                FROM performance_metrics
                WHERE metric_name = 'throughput_rps' AND recorded_at >= NOW() - INTERVAL '24 hours'
                GROUP BY DATE_TRUNC('hour', recorded_at)
                ORDER BY hour
                """,
                user_id
            )

        return {
            'cpu_usage': [
                {'timestamp': row['hour'].isoformat(), 'value': float(row['avg_cpu_usage'])}
                for row in cpu_metrics
            ],
            'memory_usage': [
                {'timestamp': row['hour'].isoformat(), 'value': float(row['avg_memory_usage'])}
                for row in memory_metrics
            ],
            'response_times': [
                {'timestamp': row['hour'].isoformat(), 'value': float(row['avg_response_time'])}
                for row in response_time_metrics
            ],
            'throughput': [
                {'timestamp': row['hour'].isoformat(), 'value': float(row['avg_throughput'])}
                for row in throughput_metrics
            ]
        }

    async def get_content_analytics_dashboard(self) -> Optional[str]:
        """Получение дашборда аналитики контента"""
        # Получаем метрики контента
        content_metrics = await self._get_content_analytics_metrics()

        if not content_metrics:
            return None

        # Создаем диаграммы для дашборда
        charts = []

        # Диаграмма популярности контента
        popularity_chart_id = await self.create_chart(
            title="Most Popular Content",
            chart_type=ChartType.BAR,
            data_source="custom",
            data=content_metrics['popular_content']
        )
        if popularity_chart_id:
            charts.append(popularity_chart_id)

        # Диаграмма типов контента
        content_type_chart_id = await self.create_chart(
            title="Content Type Distribution",
            chart_type=ChartType.PIE,
            data_source="custom",
            data=content_metrics['content_types']
        )
        if content_type_chart_id:
            charts.append(content_type_chart_id)

        # Диаграмма активности по времени
        time_activity_chart_id = await self.create_chart(
            title="Content Activity Over Time",
            chart_type=ChartType.LINE,
            data_source="custom",
            data=content_metrics['time_activity']
        )
        if time_activity_chart_id:
            charts.append(time_activity_chart_id)

        # Диаграмма взаимодействий с контентом
        interactions_chart_id = await self.create_chart(
            title="Content Interactions",
            chart_type=ChartType.AREA,
            data_source="custom",
            data=content_metrics['interactions']
        )
        if interactions_chart_id:
            charts.append(interactions_chart_id)

        # Создаем дашборд
        dashboard_id = await self.create_dashboard(
            name="Content Analytics Dashboard",
            description="Content performance and engagement analytics dashboard",
            dashboard_type=DashboardType.CONTENT_ANALYTICS,
            charts=charts,
            layout={
                'rows': 2,
                'columns': 2,
                'chart_positions': {
                    popularity_chart_id: {'row': 0, 'col': 0, 'span': {'rows': 1, 'cols': 1}},
                    content_type_chart_id: {'row': 0, 'col': 1, 'span': {'rows': 1, 'cols': 1}},
                    time_activity_chart_id: {'row': 1, 'col': 0, 'span': {'rows': 1, 'cols': 1}},
                    interactions_chart_id: {'row': 1, 'col': 1, 'span': {'rows': 1, 'cols': 1}}
                }
            }
        )

        if dashboard_id:
            # Генерируем визуализацию дашборда
            return await self.get_dashboard_visualization(dashboard_id, VisualizationFormat.HTML)
        else:
            return None

    async def _get_content_analytics_metrics(self) -> Optional[Dict[str, Any]]:
        """Получение метрик аналитики контента"""
        async with db_pool.acquire() as conn:
            # Получаем популярный контент
            popular_content = await conn.fetch(
                """
                SELECT title, type, views, likes, shares, created_at
                FROM content
                ORDER BY views DESC
                LIMIT 10
                """
            )

            # Получаем распределение по типам контента
            content_types = await conn.fetch(
                """
                SELECT type, COUNT(*) as count
                FROM content
                GROUP BY type
                ORDER BY count DESC
                """
            )

            # Получаем активность по времени
            time_activity = await conn.fetch(
                """
                SELECT DATE_TRUNC('day', created_at) as day, COUNT(*) as count
                FROM content
                WHERE created_at >= NOW() - INTERVAL '30 days'
                GROUP BY DATE_TRUNC('day', created_at)
                ORDER BY day
                """
            )

            # Получаем взаимодействия с контентом
            interactions = await conn.fetch(
                """
                SELECT action, COUNT(*) as count
                FROM content_interactions
                WHERE created_at >= NOW() - INTERVAL '30 days'
                GROUP BY action
                ORDER BY count DESC
                """
            )

        return {
            'popular_content': [
                {
                    'title': row['title'],
                    'type': row['type'],
                    'views': row['views'],
                    'likes': row['likes'],
                    'shares': row['shares']
                }
                for row in popular_content
            ],
            'content_types': [
                {'type': row['type'], 'count': row['count']}
                for row in content_types
            ],
            'time_activity': [
                {'date': row['day'].isoformat(), 'count': row['count']}
                for row in time_activity
            ],
            'interactions': [
                {'action': row['action'], 'count': row['count']}
                for row in interactions
            ]
        }

    async def get_chat_statistics_dashboard(self) -> Optional[str]:
        """Получение дашборда статистики чатов"""
        # Получаем статистику чатов
        chat_stats = await self._get_chat_statistics_metrics()

        if not chat_stats:
            return None

        # Создаем диаграммы для дашборда
        charts = []

        # Диаграмма активности чатов
        chat_activity_chart_id = await self.create_chart(
            title="Chat Activity Distribution",
            chart_type=ChartType.BAR,
            data_source="custom",
            data=chat_stats['chat_activity']
        )
        if chat_activity_chart_id:
            charts.append(chat_activity_chart_id)

        # Диаграмма типов сообщений
        message_types_chart_id = await self.create_chart(
            title="Message Type Distribution",
            chart_type=ChartType.PIE,
            data_source="custom",
            data=chat_stats['message_types']
        )
        if message_types_chart_id:
            charts.append(message_types_chart_id)

        # Диаграмма активности пользователей
        user_activity_chart_id = await self.create_chart(
            title="User Activity in Chats",
            chart_type=ChartType.LINE,
            data_source="custom",
            data=chat_stats['user_activity']
        )
        if user_activity_chart_id:
            charts.append(user_activity_chart_id)

        # Диаграмма файлов в чатах
        file_sharing_chart_id = await self.create_chart(
            title="File Sharing in Chats",
            chart_type=ChartType.AREA,
            data_source="custom",
            data=chat_stats['file_sharing']
        )
        if file_sharing_chart_id:
            charts.append(file_sharing_chart_id)

        # Создаем дашборд
        dashboard_id = await self.create_dashboard(
            name="Chat Statistics Dashboard",
            description="Real-time chat activity and engagement statistics",
            dashboard_type=DashboardType.CHAT_STATISTICS,
            charts=charts,
            layout={
                'rows': 2,
                'columns': 2,
                'chart_positions': {
                    chat_activity_chart_id: {'row': 0, 'col': 0, 'span': {'rows': 1, 'cols': 1}},
                    message_types_chart_id: {'row': 0, 'col': 1, 'span': {'rows': 1, 'cols': 1}},
                    user_activity_chart_id: {'row': 1, 'col': 0, 'span': {'rows': 1, 'cols': 1}},
                    file_sharing_chart_id: {'row': 1, 'col': 1, 'span': {'rows': 1, 'cols': 1}}
                }
            }
        )

        if dashboard_id:
            # Генерируем визуализацию дашборда
            return await self.get_dashboard_visualization(dashboard_id, VisualizationFormat.HTML)
        else:
            return None

    async def _get_chat_statistics_metrics(self) -> Optional[Dict[str, Any]]:
        """Получение метрик статистики чатов"""
        async with db_pool.acquire() as conn:
            # Получаем активность чатов
            chat_activity = await conn.fetch(
                """
                SELECT name, type, message_count, member_count, last_activity
                FROM chats
                ORDER BY message_count DESC
                LIMIT 10
                """
            )

            # Получаем типы сообщений
            message_types = await conn.fetch(
                """
                SELECT message_type, COUNT(*) as count
                FROM messages
                WHERE created_at >= NOW() - INTERVAL '7 days'
                GROUP BY message_type
                ORDER BY count DESC
                """
            )

            # Получаем активность пользователей
            user_activity = await conn.fetch(
                """
                SELECT DATE_TRUNC('hour', timestamp) as hour, COUNT(*) as message_count
                FROM messages
                WHERE timestamp >= NOW() - INTERVAL '24 hours'
                GROUP BY DATE_TRUNC('hour', timestamp)
                ORDER BY hour
                """
            )

            # Получаем статистику по файлам
            file_sharing = await conn.fetch(
                """
                SELECT DATE_TRUNC('day', uploaded_at) as day, COUNT(*) as file_count
                FROM files
                WHERE uploaded_at >= NOW() - INTERVAL '30 days'
                GROUP BY DATE_TRUNC('day', uploaded_at)
                ORDER BY day
                """
            )

        return {
            'chat_activity': [
                {
                    'name': row['name'],
                    'type': row['type'],
                    'message_count': row['message_count'],
                    'member_count': row['member_count'],
                    'last_activity': row['last_activity'].isoformat() if row['last_activity'] else None
                }
                for row in chat_activity
            ],
            'message_types': [
                {'type': row['message_type'], 'count': row['count']}
                for row in message_types
            ],
            'user_activity': [
                {'hour': row['hour'].isoformat(), 'message_count': row['message_count']}
                for row in user_activity
            ],
            'file_sharing': [
                {'date': row['day'].isoformat(), 'file_count': row['file_count']}
                for row in file_sharing
            ]
        }

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
content_moderation_service = ContentModerationService()
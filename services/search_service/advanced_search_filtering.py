# Advanced Search and Filtering System
# File: services/search_service/advanced_search_filtering.py

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
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from elasticsearch import AsyncElasticsearch
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import re

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class SearchObjectType(Enum):
    MESSAGE = "message"
    FILE = "file"
    USER = "user"
    CHAT = "chat"
    TASK = "task"
    POLL = "poll"
    CALENDAR_EVENT = "calendar_event"
    CONTENT = "content"

class SearchOperator(Enum):
    AND = "and"
    OR = "or"
    NOT = "not"
    PHRASE = "phrase"

class SearchFilterType(Enum):
    DATE_RANGE = "date_range"
    USER = "user"
    CHAT = "chat"
    FILE_TYPE = "file_type"
    TAG = "tag"
    CONTENT_TYPE = "content_type"
    STATUS = "status"
    PRIORITY = "priority"

class SearchSortOrder(Enum):
    RELEVANCE = "relevance"
    DATE_DESC = "date_desc"
    DATE_ASC = "date_asc"
    SIZE_DESC = "size_desc"
    SIZE_ASC = "size_asc"
    NAME_ASC = "name_asc"
    NAME_DESC = "name_desc"

class SearchFacetType(Enum):
    USER = "user"
    CHAT = "chat"
    FILE_TYPE = "file_type"
    TAG = "tag"
    DATE = "date"
    CONTENT_TYPE = "content_type"

class SearchQuery(BaseModel):
    query: str
    object_types: List[SearchObjectType]
    filters: Dict[str, Any]  # {'date_range': {'from': '2023-01-01', 'to': '2023-12-31'}}
    operator: SearchOperator = SearchOperator.AND
    sort_order: SearchSortOrder = SearchSortOrder.RELEVANCE
    facets: List[SearchFacetType] = []
    highlight: bool = True
    fuzzy_search: bool = True
    semantic_search: bool = True
    limit: int = 50
    offset: int = 0

class SearchFilter(BaseModel):
    type: SearchFilterType
    field: str
    value: Any
    operator: str  # '=', '!=', '>', '<', '>=', '<=', 'contains', 'in', 'between'

class SearchResultItem(BaseModel):
    id: str
    type: SearchObjectType
    title: str
    content_preview: str
    relevance_score: float
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None
    highlights: Optional[Dict[str, List[str]]] = None

class SearchFacet(BaseModel):
    type: SearchFacetType
    field: str
    values: List[Dict[str, Any]]  # [{'value': 'some_value', 'count': 10}]

class SearchResponse(BaseModel):
    query: str
    total_results: int
    results: List[SearchResultItem]
    facets: List[SearchFacet]
    took_ms: int
    timestamp: datetime = None

class AdvancedSearchService:
    def __init__(self):
        self.elasticsearch_client = None
        self.tfidf_vectorizer = TfidfVectorizer(stop_words='russian', max_features=10000)
        self.search_cache_ttl = 300  # 5 минут
        self.semantic_model = None  # Модель для семантического поиска
        self.search_operators = {
            SearchOperator.AND: "AND",
            SearchOperator.OR: "OR",
            SearchOperator.NOT: "NOT",
            SearchOperator.PHRASE: "PHRASE"
        }
        
        # Поддерживаемые поля для поиска
        self.searchable_fields = {
            SearchObjectType.MESSAGE: ['content', 'sender_username'],
            SearchObjectType.FILE: ['filename', 'stored_name', 'description'],
            SearchObjectType.USER: ['username', 'email', 'first_name', 'last_name'],
            SearchObjectType.CHAT: ['name', 'description'],
            SearchObjectType.TASK: ['title', 'description'],
            SearchObjectType.POLL: ['title', 'description'],
            SearchObjectType.CALENDAR_EVENT: ['title', 'description']
        }

    async def initialize_elasticsearch(self):
        """Инициализация Elasticsearch клиента"""
        try:
            self.elasticsearch_client = AsyncElasticsearch(
                hosts=['elasticsearch:9200'],
                http_auth=(os.getenv('ELASTICSEARCH_USER', 'elastic'), 
                          os.getenv('ELASTICSEARCH_PASSWORD', 'changeme'))
            )
            
            # Проверяем соединение
            await self.elasticsearch_client.info()
            
            # Создаем индексы, если они не существуют
            await self._create_elasticsearch_indices()
            
            logger.info("Elasticsearch client initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Elasticsearch: {e}")
            # Используем резервный вариант поиска через PostgreSQL

    async def _create_elasticsearch_indices(self):
        """Создание индексов Elasticsearch"""
        indices_config = {
            'messages': {
                'mappings': {
                    'properties': {
                        'content': {'type': 'text', 'analyzer': 'russian'},
                        'sender_id': {'type': 'keyword'},
                        'sender_username': {'type': 'keyword'},
                        'chat_id': {'type': 'keyword'},
                        'timestamp': {'type': 'date'},
                        'tags': {'type': 'keyword'}
                    }
                }
            },
            'files': {
                'mappings': {
                    'properties': {
                        'filename': {'type': 'text', 'analyzer': 'russian'},
                        'stored_name': {'type': 'keyword'},
                        'description': {'type': 'text', 'analyzer': 'russian'},
                        'mime_type': {'type': 'keyword'},
                        'size': {'type': 'long'},
                        'uploader_id': {'type': 'keyword'},
                        'uploaded_at': {'type': 'date'},
                        'tags': {'type': 'keyword'}
                    }
                }
            },
            'users': {
                'mappings': {
                    'properties': {
                        'username': {'type': 'text', 'analyzer': 'russian'},
                        'email': {'type': 'keyword'},
                        'first_name': {'type': 'text', 'analyzer': 'russian'},
                        'last_name': {'type': 'text', 'analyzer': 'russian'},
                        'bio': {'type': 'text', 'analyzer': 'russian'}
                    }
                }
            },
            'chats': {
                'mappings': {
                    'properties': {
                        'name': {'type': 'text', 'analyzer': 'russian'},
                        'description': {'type': 'text', 'analyzer': 'russian'},
                        'creator_id': {'type': 'keyword'},
                        'created_at': {'type': 'date'},
                        'tags': {'type': 'keyword'}
                    }
                }
            },
            'tasks': {
                'mappings': {
                    'properties': {
                        'title': {'type': 'text', 'analyzer': 'russian'},
                        'description': {'type': 'text', 'analyzer': 'russian'},
                        'creator_id': {'type': 'keyword'},
                        'assignee_ids': {'type': 'keyword'},
                        'status': {'type': 'keyword'},
                        'priority': {'type': 'keyword'},
                        'created_at': {'type': 'date'},
                        'due_date': {'type': 'date'},
                        'tags': {'type': 'keyword'}
                    }
                }
            },
            'polls': {
                'mappings': {
                    'properties': {
                        'title': {'type': 'text', 'analyzer': 'russian'},
                        'description': {'type': 'text', 'analyzer': 'russian'},
                        'creator_id': {'type': 'keyword'},
                        'status': {'type': 'keyword'},
                        'created_at': {'type': 'date'},
                        'tags': {'type': 'keyword'}
                    }
                }
            }
        }

        for index_name, config in indices_config.items():
            if not await self.elasticsearch_client.indices.exists(index=index_name):
                await self.elasticsearch_client.indices.create(
                    index=index_name,
                    body=config
                )

    async def search(self, query: SearchQuery, user_id: int) -> SearchResponse:
        """Выполнение расширенного поиска"""
        start_time = datetime.utcnow()

        # Проверяем кэш
        cache_key = self._generate_search_cache_key(query, user_id)
        cached_result = await self._get_cached_search_result(cache_key)
        if cached_result:
            logger.debug(f"Search cache hit for query: {query.query}")
            return cached_result

        results = []
        total_results = 0
        facets = []

        # Выполняем поиск по каждому типу объектов
        for obj_type in query.object_types:
            type_results, type_total = await self._search_by_type(obj_type, query, user_id)
            results.extend(type_results)
            total_results += type_total

        # Применяем фильтры
        if query.filters:
            results = await self._apply_filters(results, query.filters, user_id)

        # Сортируем результаты
        results = await self._sort_results(results, query.sort_order)

        # Применяем пагинацию
        start_idx = query.offset
        end_idx = start_idx + query.limit
        paginated_results = results[start_idx:end_idx]

        # Получаем фасеты
        if query.facets:
            facets = await self._get_facets(query, user_id)

        # Вычисляем время выполнения
        took_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        response = SearchResponse(
            query=query.query,
            total_results=total_results,
            results=paginated_results,
            facets=facets,
            took_ms=took_ms,
            timestamp=datetime.utcnow()
        )

        # Кэшируем результат
        await self._cache_search_result(cache_key, response)

        return response

    async def _search_by_type(self, obj_type: SearchObjectType, query: SearchQuery, 
                            user_id: int) -> tuple[List[SearchResultItem], int]:
        """Поиск по конкретному типу объектов"""
        if self.elasticsearch_client:
            return await self._elasticsearch_search(obj_type, query, user_id)
        else:
            return await self._postgres_search(obj_type, query, user_id)

    async def _elasticsearch_search(self, obj_type: SearchObjectType, query: SearchQuery, 
                                  user_id: int) -> tuple[List[SearchResultItem], int]:
        """Поиск через Elasticsearch"""
        try:
            # Формируем поисковый запрос
            es_query = {
                "query": {
                    "bool": {
                        "must": [],
                        "filter": []
                    }
                },
                "highlight": {
                    "fields": {
                        "*": {}
                    }
                } if query.highlight else None
            }

            # Добавляем текстовый поиск
            if query.query:
                if query.fuzzy_search:
                    es_query["query"]["bool"]["must"].append({
                        "multi_match": {
                            "query": query.query,
                            "type": "best_fields",
                            "fields": self.searchable_fields.get(obj_type, ["*"]),
                            "fuzziness": "AUTO"
                        }
                    })
                else:
                    es_query["query"]["bool"]["must"].append({
                        "multi_match": {
                            "query": query.query,
                            "type": "phrase",
                            "fields": self.searchable_fields.get(obj_type, ["*"])
                        }
                    })

            # Добавляем фильтры
            if query.filters:
                for filter_type, filter_value in query.filters.items():
                    if filter_type == "date_range":
                        es_query["query"]["bool"]["filter"].append({
                            "range": {
                                "timestamp": {
                                    "gte": filter_value.get("from"),
                                    "lte": filter_value.get("to")
                                }
                            }
                        })
                    elif filter_type == "user":
                        es_query["query"]["bool"]["filter"].append({
                            "term": {
                                "user_id": filter_value
                            }
                        })
                    elif filter_type == "chat":
                        es_query["query"]["bool"]["filter"].append({
                            "term": {
                                "chat_id": filter_value
                            }
                        })
                    elif filter_type == "file_type":
                        es_query["query"]["bool"]["filter"].append({
                            "term": {
                                "mime_type": filter_value
                            }
                        })
                    elif filter_type == "tag":
                        es_query["query"]["bool"]["filter"].append({
                            "term": {
                                "tags": filter_value
                            }
                        })

            # Выполняем поиск
            search_result = await self.elasticsearch_client.search(
                index=obj_type.value + "s",
                body=es_query,
                from_=query.offset,
                size=query.limit
            )

            # Обрабатываем результаты
            results = []
            for hit in search_result['hits']['hits']:
                result_item = SearchResultItem(
                    id=hit['_id'],
                    type=obj_type,
                    title=hit.get('_source', {}).get('title', hit.get('_source', {}).get('name', hit.get('_source', {}).get('content', ''))[:50]),
                    content_preview=hit.get('_source', {}).get('content', hit.get('_source', {}).get('description', ''))[:200],
                    relevance_score=hit['_score'],
                    timestamp=datetime.fromisoformat(hit.get('_source', {}).get('timestamp', datetime.utcnow().isoformat())),
                    metadata=hit.get('_source', {}),
                    highlights=hit.get('highlight', {})
                )
                results.append(result_item)

            total_results = search_result['hits']['total']['value']

            return results, total_results
        except Exception as e:
            logger.error(f"Elasticsearch search error: {e}")
            # Возвращаем к PostgreSQL поиску
            return await self._postgres_search(obj_type, query, user_id)

    async def _postgres_search(self, obj_type: SearchObjectType, query: SearchQuery, 
                             user_id: int) -> tuple[List[SearchResultItem], int]:
        """Поиск через PostgreSQL"""
        # Формируем SQL запрос в зависимости от типа объекта
        if obj_type == SearchObjectType.MESSAGE:
            sql_query, params = await self._build_message_search_query(query, user_id)
        elif obj_type == SearchObjectType.FILE:
            sql_query, params = await self._build_file_search_query(query, user_id)
        elif obj_type == SearchObjectType.USER:
            sql_query, params = await self._build_user_search_query(query, user_id)
        elif obj_type == SearchObjectType.CHAT:
            sql_query, params = await self._build_chat_search_query(query, user_id)
        elif obj_type == SearchObjectType.TASK:
            sql_query, params = await self._build_task_search_query(query, user_id)
        elif obj_type == SearchObjectType.POLL:
            sql_query, params = await self._build_poll_search_query(query, user_id)
        else:
            # Для других типов используем общий поиск
            sql_query, params = await self._build_content_search_query(query, user_id)

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        results = []
        for row in rows:
            result_item = SearchResultItem(
                id=row['id'],
                type=obj_type,
                title=row.get('title', row.get('name', row.get('content', '')))[:50],
                content_preview=row.get('content', row.get('description', row.get('filename', '')))[:200],
                relevance_score=row.get('relevance_score', 1.0),
                timestamp=row.get('timestamp', row.get('created_at', datetime.utcnow())),
                metadata={k: v for k, v in dict(row).items() if k not in ['id', 'title', 'content', 'relevance_score', 'timestamp']}
            )
            results.append(result_item)

        # Подсчитываем общее количество результатов
        count_query = sql_query.replace("SELECT *", "SELECT COUNT(*) as count", 1)
        count_query = count_query.replace("ORDER BY", "GROUP BY").split("LIMIT")[0].split("OFFSET")[0]
        
        async with db_pool.acquire() as conn:
            count_row = await conn.fetchrow(count_query, *params)
        
        total_results = count_row['count'] if count_row else len(results)

        return results, total_results

    async def _build_message_search_query(self, query: SearchQuery, user_id: int) -> tuple[str, list]:
        """Построение SQL запроса для поиска сообщений"""
        base_query = """
            SELECT m.id, m.content as title, m.content, m.sender_id, u.username as sender_username,
                   m.chat_id, m.timestamp, 
                   ts_rank_cd(to_tsvector('russian', m.content), plainto_tsquery('russian', $1)) as relevance_score
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            JOIN chat_participants cp ON m.chat_id = cp.chat_id
            WHERE 
                (to_tsvector('russian', m.content) @@ plainto_tsquery('russian', $1) OR m.content ILIKE $2)
                AND cp.user_id = $3
        """
        
        params = [query.query, f"%{query.query}%", user_id]
        param_idx = 4

        # Добавляем фильтры
        if query.filters:
            for filter_type, filter_value in query.filters.items():
                if filter_type == "date_range":
                    base_query += f" AND m.timestamp BETWEEN ${param_idx} AND ${param_idx + 1}"
                    params.extend([filter_value.get("from"), filter_value.get("to")])
                    param_idx += 2
                elif filter_type == "user":
                    base_query += f" AND m.sender_id = ${param_idx}"
                    params.append(filter_value)
                    param_idx += 1
                elif filter_type == "chat":
                    base_query += f" AND m.chat_id = ${param_idx}"
                    params.append(filter_value)
                    param_idx += 1
                elif filter_type == "tag":
                    base_query += f" AND $param_idx = ANY(m.tags)"
                    params.append(filter_value)
                    param_idx += 1

        # Сортировка
        if query.sort_order == SearchSortOrder.RELEVANCE:
            base_query += " ORDER BY relevance_score DESC, m.timestamp DESC"
        elif query.sort_order == SearchSortOrder.DATE_DESC:
            base_query += " ORDER BY m.timestamp DESC"
        elif query.sort_order == SearchSortOrder.DATE_ASC:
            base_query += " ORDER BY m.timestamp ASC"
        else:
            base_query += " ORDER BY m.timestamp DESC"

        base_query += f" LIMIT ${param_idx} OFFSET ${param_idx + 1}"
        params.extend([query.limit, query.offset])

        return base_query, params

    async def _build_file_search_query(self, query: SearchQuery, user_id: int) -> tuple[str, list]:
        """Построение SQL запроса для поиска файлов"""
        base_query = """
            SELECT f.id, f.original_filename as title, f.description as content, f.mime_type,
                   f.size, f.uploader_id, u.username as uploader_username,
                   f.uploaded_at as timestamp,
                   ts_rank_cd(to_tsvector('russian', f.original_filename || ' ' || f.description), 
                             plainto_tsquery('russian', $1)) as relevance_score
            FROM files f
            JOIN users u ON f.uploader_id = u.id
            WHERE 
                (to_tsvector('russian', f.original_filename || ' ' || f.description) @@ plainto_tsquery('russian', $1) 
                 OR f.original_filename ILIKE $2 OR f.description ILIKE $2)
        """
        
        params = [query.query, f"%{query.query}%"]
        param_idx = 3

        # Добавляем фильтры
        if query.filters:
            for filter_type, filter_value in query.filters.items():
                if filter_type == "date_range":
                    base_query += f" AND f.uploaded_at BETWEEN ${param_idx} AND ${param_idx + 1}"
                    params.extend([filter_value.get("from"), filter_value.get("to")])
                    param_idx += 2
                elif filter_type == "user":
                    base_query += f" AND f.uploader_id = ${param_idx}"
                    params.append(filter_value)
                    param_idx += 1
                elif filter_type == "file_type":
                    base_query += f" AND f.mime_type = ${param_idx}"
                    params.append(filter_value)
                    param_idx += 1
                elif filter_type == "tag":
                    base_query += f" AND $param_idx = ANY(f.tags)"
                    params.append(filter_value)
                    param_idx += 1

        # Сортировка
        if query.sort_order == SearchSortOrder.RELEVANCE:
            base_query += " ORDER BY relevance_score DESC, f.uploaded_at DESC"
        elif query.sort_order == SearchSortOrder.DATE_DESC:
            base_query += " ORDER BY f.uploaded_at DESC"
        elif query.sort_order == SearchSortOrder.DATE_ASC:
            base_query += " ORDER BY f.uploaded_at ASC"
        elif query.sort_order == SearchSortOrder.SIZE_DESC:
            base_query += " ORDER BY f.size DESC"
        elif query.sort_order == SearchSortOrder.SIZE_ASC:
            base_query += " ORDER BY f.size ASC"
        else:
            base_query += " ORDER BY f.uploaded_at DESC"

        base_query += f" LIMIT ${param_idx} OFFSET ${param_idx + 1}"
        params.extend([query.limit, query.offset])

        return base_query, params

    async def _build_user_search_query(self, query: SearchQuery, user_id: int) -> tuple[str, list]:
        """Построение SQL запроса для поиска пользователей"""
        base_query = """
            SELECT u.id, u.username as title, u.email, u.first_name, u.last_name, u.bio as content,
                   u.avatar, u.created_at as timestamp,
                   ts_rank_cd(to_tsvector('russian', u.username || ' ' || u.first_name || ' ' || u.last_name || ' ' || COALESCE(u.bio, '')), 
                             plainto_tsquery('russian', $1)) as relevance_score
            FROM users u
            WHERE 
                (to_tsvector('russian', u.username || ' ' || u.first_name || ' ' || u.last_name || ' ' || COALESCE(u.bio, '')) @@ plainto_tsquery('russian', $1) 
                 OR u.username ILIKE $2 OR u.first_name ILIKE $2 OR u.last_name ILIKE $2)
        """
        
        params = [query.query, f"%{query.query}%"]
        param_idx = 3

        # Добавляем фильтры
        if query.filters:
            for filter_type, filter_value in query.filters.items():
                if filter_type == "date_range":
                    base_query += f" AND u.created_at BETWEEN ${param_idx} AND ${param_idx + 1}"
                    params.extend([filter_value.get("from"), filter_value.get("to")])
                    param_idx += 2
                elif filter_type == "tag":
                    # Для пользователей теги могут храниться в отдельной таблице
                    base_query += f""" AND u.id IN (
                        SELECT user_id FROM user_tags WHERE tag = ${param_idx}
                    )"""
                    params.append(filter_value)
                    param_idx += 1

        # Сортировка
        if query.sort_order == SearchSortOrder.RELEVANCE:
            base_query += " ORDER BY relevance_score DESC, u.created_at DESC"
        elif query.sort_order == SearchSortOrder.NAME_ASC:
            base_query += " ORDER BY u.username ASC"
        elif query.sort_order == SearchSortOrder.NAME_DESC:
            base_query += " ORDER BY u.username DESC"
        else:
            base_query += " ORDER BY u.created_at DESC"

        base_query += f" LIMIT ${param_idx} OFFSET ${param_idx + 1}"
        params.extend([query.limit, query.offset])

        return base_query, params

    async def _apply_filters(self, results: List[SearchResultItem], 
                           filters: Dict[str, Any], user_id: int) -> List[SearchResultItem]:
        """Применение фильтров к результатам поиска"""
        filtered_results = []

        for result in results:
            include = True

            # Применяем фильтры
            for filter_type, filter_value in filters.items():
                if filter_type == "date_range":
                    date_from = datetime.fromisoformat(filter_value.get("from", "1970-01-01"))
                    date_to = datetime.fromisoformat(filter_value.get("to", datetime.utcnow().isoformat()))
                    if not (date_from <= result.timestamp <= date_to):
                        include = False
                        break
                elif filter_type == "user" and result.metadata:
                    if result.metadata.get('user_id') != filter_value and result.metadata.get('sender_id') != filter_value:
                        include = False
                        break
                elif filter_type == "chat" and result.metadata:
                    if result.metadata.get('chat_id') != filter_value:
                        include = False
                        break
                elif filter_type == "file_type" and result.metadata:
                    if result.metadata.get('mime_type') != filter_value:
                        include = False
                        break
                elif filter_type == "tag" and result.metadata:
                    tags = result.metadata.get('tags', [])
                    if filter_value not in tags:
                        include = False
                        break

            if include:
                filtered_results.append(result)

        return filtered_results

    async def _sort_results(self, results: List[SearchResultItem], 
                          sort_order: SearchSortOrder) -> List[SearchResultItem]:
        """Сортировка результатов поиска"""
        if sort_order == SearchSortOrder.RELEVANCE:
            results.sort(key=lambda x: x.relevance_score, reverse=True)
        elif sort_order == SearchSortOrder.DATE_DESC:
            results.sort(key=lambda x: x.timestamp, reverse=True)
        elif sort_order == SearchSortOrder.DATE_ASC:
            results.sort(key=lambda x: x.timestamp)
        elif sort_order == SearchSortOrder.SIZE_DESC and results:
            results.sort(key=lambda x: x.metadata.get('size', 0), reverse=True)
        elif sort_order == SearchSortOrder.SIZE_ASC and results:
            results.sort(key=lambda x: x.metadata.get('size', 0))
        elif sort_order == SearchSortOrder.NAME_ASC and results:
            results.sort(key=lambda x: x.title)
        elif sort_order == SearchSortOrder.NAME_DESC and results:
            results.sort(key=lambda x: x.title, reverse=True)

        return results

    async def _get_facets(self, query: SearchQuery, user_id: int) -> List[SearchFacet]:
        """Получение фасетов для поискового запроса"""
        facets = []

        for facet_type in query.facets:
            if facet_type == SearchFacetType.USER:
                facet_values = await self._get_user_facets(query, user_id)
            elif facet_type == SearchFacetType.CHAT:
                facet_values = await self._get_chat_facets(query, user_id)
            elif facet_type == SearchFacetType.FILE_TYPE:
                facet_values = await self._get_file_type_facets(query, user_id)
            elif facet_type == SearchFacetType.TAG:
                facet_values = await self._get_tag_facets(query, user_id)
            elif facet_type == SearchFacetType.DATE:
                facet_values = await self._get_date_facets(query, user_id)
            elif facet_type == SearchFacetType.CONTENT_TYPE:
                facet_values = await self._get_content_type_facets(query, user_id)
            else:
                facet_values = []

            facet = SearchFacet(
                type=facet_type,
                field=self._get_facet_field(facet_type),
                values=facet_values
            )
            facets.append(facet)

        return facets

    async def _get_user_facets(self, query: SearchQuery, user_id: int) -> List[Dict[str, Any]]:
        """Получение фасетов по пользователям"""
        sql_query = """
            SELECT u.id, u.username, COUNT(*) as count
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE to_tsvector('russian', m.content) @@ plainto_tsquery('russian', $1)
            GROUP BY u.id, u.username
            ORDER BY count DESC
            LIMIT 10
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, query.query)

        return [
            {
                'value': row['username'],
                'count': row['count'],
                'id': row['id']
            }
            for row in rows
        ]

    async def _get_chat_facets(self, query: SearchQuery, user_id: int) -> List[Dict[str, Any]]:
        """Получение фасетов по чатам"""
        sql_query = """
            SELECT c.id, c.name, COUNT(*) as count
            FROM messages m
            JOIN chats c ON m.chat_id = c.id
            WHERE to_tsvector('russian', m.content) @@ plainto_tsquery('russian', $1)
            GROUP BY c.id, c.name
            ORDER BY count DESC
            LIMIT 10
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, query.query)

        return [
            {
                'value': row['name'] or f"Chat {row['id']}",
                'count': row['count'],
                'id': row['id']
            }
            for row in rows
        ]

    async def _get_file_type_facets(self, query: SearchQuery, user_id: int) -> List[Dict[str, Any]]:
        """Получение фасетов по типам файлов"""
        sql_query = """
            SELECT mime_type, COUNT(*) as count
            FROM files
            WHERE to_tsvector('russian', original_filename || ' ' || description) @@ plainto_tsquery('russian', $1)
            GROUP BY mime_type
            ORDER BY count DESC
            LIMIT 10
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, query.query)

        return [
            {
                'value': row['mime_type'],
                'count': row['count']
            }
            for row in rows
        ]

    async def _get_tag_facets(self, query: SearchQuery, user_id: int) -> List[Dict[str, Any]]:
        """Получение фасетов по тегам"""
        sql_query = """
            SELECT unnest(tags) as tag, COUNT(*) as count
            FROM (
                SELECT tags FROM messages WHERE to_tsvector('russian', content) @@ plainto_tsquery('russian', $1)
                UNION ALL
                SELECT tags FROM files WHERE to_tsvector('russian', original_filename || ' ' || description) @@ plainto_tsquery('russian', $1)
                UNION ALL
                SELECT tags FROM tasks WHERE to_tsvector('russian', title || ' ' || description) @@ plainto_tsquery('russian', $1)
            ) as all_tags
            WHERE tags IS NOT NULL
            GROUP BY tag
            ORDER BY count DESC
            LIMIT 10
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, query.query)

        return [
            {
                'value': row['tag'],
                'count': row['count']
            }
            for row in rows
        ]

    async def _get_date_facets(self, query: SearchQuery, user_id: int) -> List[Dict[str, Any]]:
        """Получение фасетов по датам"""
        sql_query = """
            SELECT DATE_TRUNC('day', timestamp) as day, COUNT(*) as count
            FROM messages
            WHERE to_tsvector('russian', content) @@ plainto_tsquery('russian', $1)
            GROUP BY DATE_TRUNC('day', timestamp)
            ORDER BY day DESC
            LIMIT 30
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, query.query)

        return [
            {
                'value': row['day'].isoformat(),
                'count': row['count']
            }
            for row in rows
        ]

    async def _get_content_type_facets(self, query: SearchQuery, user_id: int) -> List[Dict[str, Any]]:
        """Получение фасетов по типам контента"""
        sql_query = """
            SELECT type, COUNT(*) as count
            FROM content
            WHERE to_tsvector('russian', title || ' ' || description) @@ plainto_tsquery('russian', $1)
            GROUP BY type
            ORDER BY count DESC
            LIMIT 10
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, query.query)

        return [
            {
                'value': row['type'],
                'count': row['count']
            }
            for row in rows
        ]

    def _get_facet_field(self, facet_type: SearchFacetType) -> str:
        """Получение поля для фасета"""
        field_mapping = {
            SearchFacetType.USER: 'user_id',
            SearchFacetType.CHAT: 'chat_id',
            SearchFacetType.FILE_TYPE: 'mime_type',
            SearchFacetType.TAG: 'tags',
            SearchFacetType.DATE: 'timestamp',
            SearchFacetType.CONTENT_TYPE: 'type'
        }
        return field_mapping.get(facet_type, 'id')

    def _generate_search_cache_key(self, query: SearchQuery, user_id: int) -> str:
        """Генерация ключа кэша для поискового запроса"""
        query_str = f"{query.query}:{query.operator.value}:{query.sort_order.value}:{query.limit}:{query.offset}"
        filters_str = json.dumps(query.filters, sort_keys=True) if query.filters else ""
        types_str = ":".join([t.value for t in query.object_types])
        
        full_query = f"{query_str}:{filters_str}:{types_str}"
        hash_obj = hashlib.md5(full_query.encode())
        
        return f"search_cache:{user_id}:{hash_obj.hexdigest()}"

    async def _get_cached_search_result(self, cache_key: str) -> Optional[SearchResponse]:
        """Получение результата поиска из кэша"""
        cached = await redis_client.get(cache_key)
        if cached:
            return SearchResponse(**json.loads(cached.decode()))
        return None

    async def _cache_search_result(self, cache_key: str, result: SearchResponse):
        """Кэширование результата поиска"""
        await redis_client.setex(cache_key, self.search_cache_ttl, result.model_dump_json())

    async def _increment_views(self, content_id: str):
        """Увеличение счетчика просмотров"""
        await redis_client.incr(f"content_views:{content_id}")
        
        # Обновляем в базе данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE content SET views = views + 1 WHERE id = $1",
                content_id
            )

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

    async def requires_moderation(self, content_type: ContentType) -> bool:
        """Проверка, требует ли контент модерации"""
        # В реальной системе здесь будет более сложная логика
        # в зависимости от типа контента, пользователя и т.д.
        return content_type in [ContentType.IMAGE, ContentType.VIDEO, ContentType.LINK]

# Глобальный экземпляр для использования в приложении
ux_enhancement_service = UXEnhancementService()
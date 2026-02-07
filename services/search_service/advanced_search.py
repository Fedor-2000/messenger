# Advanced Search and Recommendation System
# File: services/search_service/advanced_search.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid
import re
from collections import defaultdict

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class SearchType(Enum):
    MESSAGES = "messages"
    FILES = "files"
    USERS = "users"
    CHATS = "chats"
    TASKS = "tasks"
    POLLS = "polls"
    CONTENT = "content"  # Поиск по всему контенту

class SearchScope(Enum):
    GLOBAL = "global"
    CHAT = "chat"
    USER = "user"
    GROUP = "group"
    PROJECT = "project"

class RecommendationType(Enum):
    SIMILAR_CONTENT = "similar_content"
    COLLABORATIVE_FILTERING = "collaborative_filtering"
    CONTENT_BASED = "content_based"
    TRENDING = "trending"
    PERSONALIZED = "personalized"

class SearchResult(BaseModel):
    id: str
    type: str
    title: str
    content: str
    relevance_score: float
    metadata: Optional[Dict] = None
    timestamp: datetime = None

class Recommendation(BaseModel):
    id: str
    type: RecommendationType
    title: str
    description: str
    relevance_score: float
    metadata: Optional[Dict] = None
    created_at: datetime = None

class SearchQuery(BaseModel):
    query: str
    search_type: SearchType
    scope: SearchScope
    scope_id: Optional[str] = None  # ID чата, пользователя и т.д.
    filters: Optional[Dict] = None
    limit: int = 20
    offset: int = 0
    fuzzy: bool = True
    semantic: bool = True

class AdvancedSearchService:
    def __init__(self):
        self.tfidf_vectorizer = TfidfVectorizer(stop_words='english', max_features=10000)
        self.semantic_model = None  # Будет инициализирован позже
        self.content_index = {}  # Индекс для быстрого поиска
        self.user_profiles = {}  # Профили пользователей для рекомендаций

    async def initialize(self):
        """Инициализация сервиса поиска"""
        # Загрузка модели для семантического поиска
        try:
            self.semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
        except Exception as e:
            logger.warning(f"Could not load semantic model: {e}")
            logger.info("Semantic search will be disabled")

    async def search(self, query: SearchQuery, user_id: int) -> List[SearchResult]:
        """Основной метод поиска"""
        results = []

        if query.search_type == SearchType.MESSAGES:
            results = await self.search_messages(query, user_id)
        elif query.search_type == SearchType.FILES:
            results = await self.search_files(query, user_id)
        elif query.search_type == SearchType.USERS:
            results = await self.search_users(query, user_id)
        elif query.search_type == SearchType.CHATS:
            results = await self.search_chats(query, user_id)
        elif query.search_type == SearchType.TASKS:
            results = await self.search_tasks(query, user_id)
        elif query.search_type == SearchType.POLLS:
            results = await self.search_polls(query, user_id)
        elif query.search_type == SearchType.CONTENT:
            results = await self.search_all_content(query, user_id)

        # Применяем фильтры
        if query.filters:
            results = self._apply_filters(results, query.filters)

        # Сортируем по релевантности
        results.sort(key=lambda x: x.relevance_score, reverse=True)

        # Применяем лимит и смещение
        start_idx = query.offset
        end_idx = start_idx + query.limit
        results = results[start_idx:end_idx]

        return results

    async def search_messages(self, query: SearchQuery, user_id: int) -> List[SearchResult]:
        """Поиск по сообщениям"""
        # Проверяем права доступа к чату
        if query.scope == SearchScope.CHAT and query.scope_id:
            if not await self._can_access_chat(user_id, query.scope_id):
                return []

        # Формируем SQL запрос
        sql_conditions = ["m.content ILIKE '%' || $1 || '%'"]
        params = [query.query]
        param_idx = 2

        # Добавляем ограничения области поиска
        if query.scope == SearchScope.CHAT and query.scope_id:
            sql_conditions.append(f"m.chat_id = ${param_idx}")
            params.append(query.scope_id)
            param_idx += 1
        elif query.scope == SearchScope.USER:
            sql_conditions.append(f"(m.sender_id = ${param_idx} OR $param_idx = ANY(c.participants))")
            params.append(user_id)
            param_idx += 1
        elif query.scope == SearchScope.GROUP and query.scope_id:
            sql_conditions.append(f"c.group_id = ${param_idx}")
            params.append(query.scope_id)
            param_idx += 1

        where_clause = " AND ".join(sql_conditions)
        sql_query = f"""
            SELECT m.id, m.chat_id, m.sender_id, m.content, m.timestamp,
                   u.username as sender_username
            FROM messages m
            JOIN chats c ON m.chat_id = c.id
            JOIN users u ON m.sender_id = u.id
            WHERE {where_clause}
            ORDER BY m.timestamp DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([query.limit, query.offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        results = []
        for row in rows:
            # Вычисляем релевантность
            relevance = self._calculate_relevance(query.query, row['content'])

            result = SearchResult(
                id=row['id'],
                type='message',
                title=f"Message from {row['sender_username']}",
                content=row['content'],
                relevance_score=relevance,
                metadata={
                    'chat_id': row['chat_id'],
                    'sender_id': row['sender_id'],
                    'sender_username': row['sender_username']
                },
                timestamp=row['timestamp']
            )
            results.append(result)

        return results

    async def search_files(self, query: SearchQuery, user_id: int) -> List[SearchResult]:
        """Поиск по файлам"""
        sql_conditions = ["(f.filename ILIKE '%' || $1 || '%' OR f.stored_name ILIKE '%' || $1 || '%')"]
        params = [query.query]
        param_idx = 2

        # Добавляем ограничения области поиска
        if query.scope == SearchScope.CHAT and query.scope_id:
            sql_conditions.append(f"f.chat_id = ${param_idx}")
            params.append(query.scope_id)
            param_idx += 1
        elif query.scope == SearchScope.USER:
            sql_conditions.append(f"f.uploader_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1

        where_clause = " AND ".join(sql_conditions)
        sql_query = f"""
            SELECT f.id, f.filename, f.stored_name, f.uploader_id, f.size, f.mime_type, f.uploaded_at,
                   u.username as uploader_username
            FROM files f
            JOIN users u ON f.uploader_id = u.id
            WHERE {where_clause}
            ORDER BY f.uploaded_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([query.limit, query.offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        results = []
        for row in rows:
            # Вычисляем релевантность
            content = f"{row['filename']} {row['stored_name']}"
            relevance = self._calculate_relevance(query.query, content)

            result = SearchResult(
                id=row['id'],
                type='file',
                title=row['filename'],
                content=f"File uploaded by {row['uploader_username']}, size: {row['size']} bytes",
                relevance_score=relevance,
                metadata={
                    'stored_name': row['stored_name'],
                    'size': row['size'],
                    'mime_type': row['mime_type'],
                    'uploader_id': row['uploader_id'],
                    'uploader_username': row['uploader_username']
                },
                timestamp=row['uploaded_at']
            )
            results.append(result)

        return results

    async def search_users(self, query: SearchQuery, user_id: int) -> List[SearchResult]:
        """Поиск по пользователям"""
        sql_conditions = ["(u.username ILIKE '%' || $1 || '%' OR u.email ILIKE '%' || $1 || '%')"]
        params = [query.query]
        param_idx = 2

        where_clause = " AND ".join(sql_conditions)
        sql_query = f"""
            SELECT u.id, u.username, u.email, u.created_at, u.avatar
            FROM users u
            WHERE {where_clause}
            ORDER BY u.username
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([query.limit, query.offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        results = []
        for row in rows:
            # Вычисляем релевантность
            content = f"{row['username']} {row['email']}"
            relevance = self._calculate_relevance(query.query, content)

            result = SearchResult(
                id=str(row['id']),
                type='user',
                title=row['username'],
                content=f"User profile: {row['email']}",
                relevance_score=relevance,
                metadata={
                    'email': row['email'],
                    'avatar': row['avatar']
                },
                timestamp=row['created_at']
            )
            results.append(result)

        return results

    async def search_chats(self, query: SearchQuery, user_id: int) -> List[SearchResult]:
        """Поиск по чатам"""
        sql_conditions = ["(c.name ILIKE '%' || $1 || '%' OR c.type ILIKE '%' || $1 || '%')"]
        params = [query.query]
        param_idx = 2

        # Ограничиваем поиск только теми чатами, в которых состоит пользователь
        sql_conditions.append(f"$param_idx = ANY(c.participants)")
        params.append(user_id)
        param_idx += 1

        where_clause = " AND ".join(sql_conditions)
        sql_query = f"""
            SELECT c.id, c.name, c.type, c.creator_id, c.participants, c.created_at, c.last_activity
            FROM chats c
            WHERE {where_clause}
            ORDER BY c.last_activity DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([query.limit, query.offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        results = []
        for row in rows:
            # Вычисляем релевантность
            content = f"{row['name']} {row['type']} {' '.join(map(str, row['participants']))}"
            relevance = self._calculate_relevance(query.query, content)

            result = SearchResult(
                id=row['id'],
                type='chat',
                title=row['name'] or f"Chat {row['id']}",
                content=f"{row['type']} chat with {len(row['participants'])} participants",
                relevance_score=relevance,
                metadata={
                    'type': row['type'],
                    'creator_id': row['creator_id'],
                    'participants': row['participants'],
                    'last_activity': row['last_activity'].isoformat() if row['last_activity'] else None
                },
                timestamp=row['created_at']
            )
            results.append(result)

        return results

    async def search_tasks(self, query: SearchQuery, user_id: int) -> List[SearchResult]:
        """Поиск по задачам"""
        sql_conditions = ["(t.title ILIKE '%' || $1 || '%' OR t.description ILIKE '%' || $1 || '%')"]
        params = [query.query]
        param_idx = 2

        # Ограничиваем доступ к задачам
        sql_conditions.append("(t.creator_id = $param_idx OR $param_idx = ANY(t.assignee_ids))")
        params.append(user_id)
        param_idx += 1

        if query.scope == SearchScope.CHAT and query.scope_id:
            sql_conditions.append(f"t.chat_id = ${param_idx}")
            params.append(query.scope_id)
            param_idx += 1
        elif query.scope == SearchScope.GROUP and query.scope_id:
            sql_conditions.append(f"t.group_id = ${param_idx}")
            params.append(query.scope_id)
            param_idx += 1

        where_clause = " AND ".join(sql_conditions)
        sql_query = f"""
            SELECT t.id, t.title, t.description, t.assignee_ids, t.creator_id, 
                   t.due_date, t.priority, t.status, t.task_type, t.created_at,
                   u.username as creator_username
            FROM tasks t
            JOIN users u ON t.creator_id = u.id
            WHERE {where_clause}
            ORDER BY t.created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([query.limit, query.offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        results = []
        for row in rows:
            # Вычисляем релевантность
            content = f"{row['title']} {row['description']} {row['priority']} {row['status']}"
            relevance = self._calculate_relevance(query.query, content)

            result = SearchResult(
                id=row['id'],
                type='task',
                title=row['title'],
                content=row['description'],
                relevance_score=relevance,
                metadata={
                    'assignee_ids': row['assignee_ids'],
                    'creator_id': row['creator_id'],
                    'creator_username': row['creator_username'],
                    'due_date': row['due_date'].isoformat() if row['due_date'] else None,
                    'priority': row['priority'],
                    'status': row['status'],
                    'task_type': row['task_type']
                },
                timestamp=row['created_at']
            )
            results.append(result)

        return results

    async def search_polls(self, query: SearchQuery, user_id: int) -> List[SearchResult]:
        """Поиск по опросам"""
        sql_conditions = ["(p.title ILIKE '%' || $1 || '%' OR p.description ILIKE '%' || $1 || '%')"]
        params = [query.query]
        param_idx = 2

        # Ограничиваем доступ к опросам
        sql_conditions.append("(p.creator_id = $param_idx OR p.visibility = 'public')")
        params.append(user_id)
        param_idx += 1

        if query.scope == SearchScope.CHAT and query.scope_id:
            sql_conditions.append(f"p.chat_id = ${param_idx}")
            params.append(query.scope_id)
            param_idx += 1
        elif query.scope == SearchScope.GROUP and query.scope_id:
            sql_conditions.append(f"p.group_id = ${param_idx}")
            params.append(query.scope_id)
            param_idx += 1

        where_clause = " AND ".join(sql_conditions)
        sql_query = f"""
            SELECT p.id, p.title, p.description, p.creator_id, p.type, p.status,
                   p.start_date, p.end_date, p.created_at, p.total_votes,
                   u.username as creator_username
            FROM polls p
            JOIN users u ON p.creator_id = u.id
            WHERE {where_clause}
            ORDER BY p.created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([query.limit, query.offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        results = []
        for row in rows:
            # Вычисляем релевантность
            content = f"{row['title']} {row['description']} {row['type']} {row['status']}"
            relevance = self._calculate_relevance(query.query, content)

            result = SearchResult(
                id=row['id'],
                type='poll',
                title=row['title'],
                content=row['description'],
                relevance_score=relevance,
                metadata={
                    'creator_id': row['creator_id'],
                    'creator_username': row['creator_username'],
                    'type': row['type'],
                    'status': row['status'],
                    'start_date': row['start_date'].isoformat() if row['start_date'] else None,
                    'end_date': row['end_date'].isoformat() if row['end_date'] else None,
                    'total_votes': row['total_votes']
                },
                timestamp=row['created_at']
            )
            results.append(result)

        return results

    async def search_all_content(self, query: SearchQuery, user_id: int) -> List[SearchResult]:
        """Поиск по всему контенту"""
        # Выполняем параллельный поиск по всем типам контента
        tasks = [
            self.search_messages(SearchQuery(query=query.query, search_type=SearchType.MESSAGES, scope=query.scope, scope_id=query.scope_id), user_id),
            self.search_files(SearchQuery(query=query.query, search_type=SearchType.FILES, scope=query.scope, scope_id=query.scope_id), user_id),
            self.search_tasks(SearchQuery(query=query.query, search_type=SearchType.TASKS, scope=query.scope, scope_id=query.scope_id), user_id),
            self.search_polls(SearchQuery(query=query.query, search_type=SearchType.POLLS, scope=query.scope, scope_id=query.scope_id), user_id)
        ]

        results = []
        for task_result in await asyncio.gather(*tasks):
            results.extend(task_result)

        # Сортируем по релевантности
        results.sort(key=lambda x: x.relevance_score, reverse=True)

        # Применяем лимит и смещение
        start_idx = query.offset
        end_idx = start_idx + query.limit
        results = results[start_idx:end_idx]

        return results

    def _calculate_relevance(self, query: str, content: str) -> float:
        """Вычисление релевантности с использованием TF-IDF и семантики"""
        relevance = 0.0

        # Простой подсчет совпадений слов
        query_words = set(query.lower().split())
        content_words = set(content.lower().split())
        word_matches = len(query_words.intersection(content_words))
        total_query_words = len(query_words)

        if total_query_words > 0:
            lexical_relevance = word_matches / total_query_words
            relevance += lexical_relevance * 0.4  # 40% для лексического совпадения

        # Семантическое сходство (если модель загружена)
        if self.semantic_model:
            try:
                sentences = [query, content]
                embeddings = self.semantic_model.encode(sentences)
                similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
                relevance += similarity * 0.6  # 60% для семантического сходства
            except Exception as e:
                logger.warning(f"Error calculating semantic similarity: {e}")

        return min(relevance, 1.0)  # Ограничиваем значением 1.0

    def _apply_filters(self, results: List[SearchResult], filters: Dict) -> List[SearchResult]:
        """Применение фильтров к результатам поиска"""
        filtered_results = []

        for result in results:
            include = True

            # Фильтр по типу
            if 'type' in filters and result.type != filters['type']:
                include = False

            # Фильтр по дате
            if 'date_from' in filters:
                date_from = datetime.fromisoformat(filters['date_from'])
                if result.timestamp and result.timestamp < date_from:
                    include = False

            if 'date_to' in filters:
                date_to = datetime.fromisoformat(filters['date_to'])
                if result.timestamp and result.timestamp > date_to:
                    include = False

            # Фильтр по минимальной релевантности
            if 'min_relevance' in filters:
                if result.relevance_score < filters['min_relevance']:
                    include = False

            if include:
                filtered_results.append(result)

        return filtered_results

    async def get_recommendations(self, user_id: int, recommendation_type: RecommendationType,
                                 limit: int = 10) -> List[Recommendation]:
        """Получение рекомендаций для пользователя"""
        recommendations = []

        if recommendation_type == RecommendationType.SIMILAR_CONTENT:
            recommendations = await self._get_similar_content_recommendations(user_id, limit)
        elif recommendation_type == RecommendationType.COLLABORATIVE_FILTERING:
            recommendations = await self._get_collaborative_recommendations(user_id, limit)
        elif recommendation_type == RecommendationType.CONTENT_BASED:
            recommendations = await self._get_content_based_recommendations(user_id, limit)
        elif recommendation_type == RecommendationType.TRENDING:
            recommendations = await self._get_trending_recommendations(user_id, limit)
        elif recommendation_type == RecommendationType.PERSONALIZED:
            recommendations = await self._get_personalized_recommendations(user_id, limit)

        return recommendations

    async def _get_similar_content_recommendations(self, user_id: int, limit: int) -> List[Recommendation]:
        """Рекомендации на основе похожего контента"""
        # Получаем последние сообщения пользователя
        recent_messages = await self._get_user_recent_messages(user_id, 5)

        if not recent_messages:
            return []

        # Объединяем текст последних сообщений
        user_content = " ".join([msg['content'] for msg in recent_messages])

        # Ищем похожие сообщения от других пользователей
        similar_messages = await self._find_similar_messages(user_content, user_id, limit)

        recommendations = []
        for msg in similar_messages:
            relevance = self._calculate_relevance(user_content, msg['content'])
            rec = Recommendation(
                id=msg['id'],
                type=RecommendationType.SIMILAR_CONTENT,
                title=f"Similar to your recent messages",
                description=msg['content'][:100] + "...",
                relevance_score=relevance,
                metadata={
                    'chat_id': msg['chat_id'],
                    'sender_id': msg['sender_id'],
                    'sender_username': msg['sender_username']
                },
                created_at=datetime.utcnow()
            )
            recommendations.append(rec)

        return recommendations

    async def _get_collaborative_recommendations(self, user_id: int, limit: int) -> List[Recommendation]:
        """Рекомендации на основе коллаборативной фильтрации"""
        # Находим пользователей с похожими интересами
        similar_users = await self._find_similar_users(user_id, 5)

        recommendations = []
        for similar_user_id in similar_users:
            # Получаем последние сообщения похожего пользователя
            user_messages = await self._get_user_recent_messages(similar_user_id, 3)

            for msg in user_messages:
                # Проверяем, не является ли это сообщение уже известным пользователю
                if not await self._user_has_seen_message(user_id, msg['id']):
                    relevance = 0.7  # Высокая релевантность для похожих пользователей
                    rec = Recommendation(
                        id=msg['id'],
                        type=RecommendationType.COLLABORATIVE_FILTERING,
                        title=f"Recommended based on similar user activity",
                        description=msg['content'][:100] + "...",
                        relevance_score=relevance,
                        metadata={
                            'chat_id': msg['chat_id'],
                            'sender_id': msg['sender_id'],
                            'sender_username': msg['sender_username'],
                            'similar_user_id': similar_user_id
                        },
                        created_at=datetime.utcnow()
                    )
                    recommendations.append(rec)

        # Сортируем по релевантности
        recommendations.sort(key=lambda x: x.relevance_score, reverse=True)
        return recommendations[:limit]

    async def _get_content_based_recommendations(self, user_id: int, limit: int) -> List[Recommendation]:
        """Контент-базированные рекомендации"""
        # Получаем профиль интересов пользователя
        user_profile = await self._get_user_profile(user_id)

        recommendations = []
        # Ищем контент, соответствующий интересам пользователя
        matching_content = await self._find_matching_content(user_profile, limit * 2)

        for content in matching_content:
            relevance = self._calculate_content_relevance(user_profile, content)
            rec = Recommendation(
                id=content['id'],
                type=RecommendationType.CONTENT_BASED,
                title=content['title'],
                description=content['description'][:100] + "...",
                relevance_score=relevance,
                metadata=content['metadata'],
                created_at=datetime.utcnow()
            )
            recommendations.append(rec)

        # Сортируем по релевантности
        recommendations.sort(key=lambda x: x.relevance_score, reverse=True)
        return recommendations[:limit]

    async def _get_trending_recommendations(self, user_id: int, limit: int) -> List[Recommendation]:
        """Рекомендации трендового контента"""
        # Получаем трендовый контент (популярные сообщения, файлы, задачи за последние 24 часа)
        trending_content = await self._get_trending_content(limit * 2)

        recommendations = []
        for content in trending_content:
            rec = Recommendation(
                id=content['id'],
                type=RecommendationType.TRENDING,
                title=f"Trending: {content['title']}",
                description=content['description'][:100] + "...",
                relevance_score=content['popularity_score'],
                metadata=content['metadata'],
                created_at=datetime.utcnow()
            )
            recommendations.append(rec)

        return recommendations

    async def _get_personalized_recommendations(self, user_id: int, limit: int) -> List[Recommendation]:
        """Персонализированные рекомендации"""
        # Комбинируем несколько подходов
        similar_content_recs = await self._get_similar_content_recommendations(user_id, limit // 3)
        collaborative_recs = await self._get_collaborative_recommendations(user_id, limit // 3)
        content_based_recs = await self._get_content_based_recommendations(user_id, limit - len(similar_content_recs) - len(collaborative_recs))

        all_recommendations = similar_content_recs + collaborative_recs + content_based_recs

        # Удаляем дубликаты и сортируем по релевантности
        seen_ids = set()
        unique_recommendations = []
        for rec in all_recommendations:
            if rec.id not in seen_ids:
                seen_ids.add(rec.id)
                unique_recommendations.append(rec)

        unique_recommendations.sort(key=lambda x: x.relevance_score, reverse=True)
        return unique_recommendations[:limit]

    async def _get_user_recent_messages(self, user_id: int, limit: int) -> List[Dict]:
        """Получение недавних сообщений пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT m.id, m.chat_id, m.sender_id, m.content, m.timestamp,
                       u.username as sender_username
                FROM messages m
                JOIN users u ON m.sender_id = u.id
                WHERE m.sender_id = $1
                ORDER BY m.timestamp DESC
                LIMIT $2
                """,
                user_id, limit
            )

        messages = []
        for row in rows:
            message = {
                'id': row['id'],
                'chat_id': row['chat_id'],
                'sender_id': row['sender_id'],
                'content': row['content'],
                'timestamp': row['timestamp'],
                'sender_username': row['sender_username']
            }
            messages.append(message)

        return messages

    async def _find_similar_messages(self, content: str, exclude_user_id: int, limit: int) -> List[Dict]:
        """Поиск похожих сообщений от других пользователей"""
        # Это упрощенная реализация - в реальности потребуется более сложный алгоритм
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT m.id, m.chat_id, m.sender_id, m.content, m.timestamp,
                       u.username as sender_username
                FROM messages m
                JOIN users u ON m.sender_id = u.id
                WHERE m.sender_id != $1
                ORDER BY m.timestamp DESC
                LIMIT $2
                """,
                exclude_user_id, limit * 5  # Берем больше, чтобы отобрать самые похожие
            )

        # Вычисляем сходство с каждым сообщением
        similar_messages = []
        for row in rows:
            relevance = self._calculate_relevance(content, row['content'])
            if relevance > 0.3:  # Порог сходства
                message = {
                    'id': row['id'],
                    'chat_id': row['chat_id'],
                    'sender_id': row['sender_id'],
                    'content': row['content'],
                    'timestamp': row['timestamp'],
                    'sender_username': row['sender_username'],
                    'relevance': relevance
                }
                similar_messages.append(message)

        # Сортируем по релевантности
        similar_messages.sort(key=lambda x: x['relevance'], reverse=True)
        return similar_messages[:limit]

    async def _find_similar_users(self, user_id: int, limit: int) -> List[int]:
        """Поиск пользователей с похожими интересами"""
        # Это упрощенная реализация - в реальности потребуется более сложный алгоритм
        # на основе анализа поведения и интересов
        async with db_pool.acquire() as conn:
            # Находим пользователей, которые участвуют в похожих чатах
            rows = await conn.fetch(
                """
                SELECT DISTINCT u.id
                FROM users u
                JOIN chats c ON u.id = ANY(c.participants)
                WHERE u.id != $1
                AND c.id IN (
                    SELECT DISTINCT c2.id
                    FROM chats c2
                    WHERE $1 = ANY(c2.participants)
                )
                LIMIT $2
                """,
                user_id, limit * 2
            )

        return [row['id'] for row in rows]

    async def _user_has_seen_message(self, user_id: int, message_id: str) -> bool:
        """Проверка, видел ли пользователь сообщение"""
        # В реальном приложении здесь будет проверка статуса прочтения
        return False

    async def _get_user_profile(self, user_id: int) -> Dict[str, Any]:
        """Получение профиля интересов пользователя"""
        # В реальном приложении здесь будет анализ активности пользователя
        # для построения профиля интересов
        if user_id not in self.user_profiles:
            # Создаем профиль на основе активности
            interests = await self._analyze_user_interests(user_id)
            self.user_profiles[user_id] = {
                'interests': interests,
                'last_updated': datetime.utcnow()
            }

        return self.user_profiles[user_id]

    async def _analyze_user_interests(self, user_id: int) -> List[str]:
        """Анализ интересов пользователя на основе активности"""
        # Получаем последние сообщения пользователя
        recent_messages = await self._get_user_recent_messages(user_id, 20)

        # Извлекаем ключевые слова
        all_text = " ".join([msg['content'] for msg in recent_messages])
        words = all_text.lower().split()

        # Простой подсчет частоты слов (в реальности использовать NLP)
        word_freq = defaultdict(int)
        for word in words:
            # Убираем короткие слова и пунктуацию
            clean_word = re.sub(r'[^\w]', '', word)
            if len(clean_word) > 3:  # Только слова длиннее 3 символов
                word_freq[clean_word] += 1

        # Возвращаем топ-10 наиболее частых слов
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, freq in sorted_words[:10]]

    async def _find_matching_content(self, user_profile: Dict, limit: int) -> List[Dict]:
        """Поиск контента, соответствующего профилю пользователя"""
        interests = user_profile.get('interests', [])
        if not interests:
            return []

        # Ищем сообщения, содержащие ключевые слова пользователя
        search_terms = " | ".join(interests[:3])  # Используем первые 3 интереса

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT m.id, m.chat_id, m.sender_id, m.content, m.timestamp,
                       u.username as sender_username
                FROM messages m
                JOIN users u ON m.sender_id = u.id
                WHERE m.content ILIKE ANY(ARRAY[{', '.join(['$' + str(i) for i in range(1, len(interests[:3]) + 1)])}])
                ORDER BY m.timestamp DESC
                LIMIT $1
                """,
                *[f'%{interest}%' for interest in interests[:3]], limit * 2
            )

        content_list = []
        for row in rows:
            content_item = {
                'id': row['id'],
                'title': f"Message from {row['sender_username']}",
                'description': row['content'][:200],
                'metadata': {
                    'chat_id': row['chat_id'],
                    'sender_id': row['sender_id'],
                    'sender_username': row['sender_username']
                }
            }
            content_list.append(content_item)

        return content_list

    def _calculate_content_relevance(self, user_profile: Dict, content: Dict) -> float:
        """Вычисление релевантности контента для пользователя"""
        interests = set(user_profile.get('interests', []))
        content_text = content['description'].lower()
        content_words = set(content_text.split())

        # Подсчитываем совпадения интересов с контентом
        matches = interests.intersection(content_words)
        if len(interests) > 0:
            relevance = len(matches) / len(interests)
        else:
            relevance = 0.0

        return min(relevance, 1.0)

    async def _get_trending_content(self, limit: int) -> List[Dict]:
        """Получение трендового контента"""
        # Получаем популярные сообщения за последние 24 часа
        yesterday = datetime.utcnow() - timedelta(days=1)

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT m.id, m.chat_id, m.sender_id, m.content, m.timestamp,
                       u.username as sender_username,
                       COUNT(lm.id) as reply_count
                FROM messages m
                JOIN users u ON m.sender_id = u.id
                LEFT JOIN messages lm ON lm.chat_id = m.chat_id 
                    AND lm.timestamp > $1 
                    AND lm.id != m.id
                WHERE m.timestamp > $1
                GROUP BY m.id, m.chat_id, m.sender_id, m.content, m.timestamp, u.username
                ORDER BY reply_count DESC, m.timestamp DESC
                LIMIT $2
                """,
                yesterday, limit
            )

        trending_items = []
        for row in rows:
            popularity_score = min(row['reply_count'] / 10.0, 1.0)  # Нормализуем до 1.0
            item = {
                'id': row['id'],
                'title': f"Trending: {row['content'][:50]}...",
                'description': row['content'],
                'popularity_score': popularity_score,
                'metadata': {
                    'chat_id': row['chat_id'],
                    'sender_id': row['sender_id'],
                    'sender_username': row['sender_username'],
                    'reply_count': row['reply_count']
                }
            }
            trending_items.append(item)

        return trending_items

    async def _can_access_chat(self, user_id: int, chat_id: str) -> bool:
        """Проверка прав доступа к чату"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM chats WHERE id = $1 AND $2 = ANY(participants)",
                chat_id, user_id
            )

        return row is not None

# Глобальный экземпляр для использования в приложении
advanced_search_service = AdvancedSearchService()

# Инициализация сервиса
async def initialize_search_service():
    await advanced_search_service.initialize()
# Feedback and Rating System
# File: services/feedback_service/feedback_rating_system.py

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

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class FeedbackType(Enum):
    BUG_REPORT = "bug_report"
    FEATURE_REQUEST = "feature_request"
    USABILITY_FEEDBACK = "usability_feedback"
    PERFORMANCE_ISSUE = "performance_issue"
    DESIGN_SUGGESTION = "design_suggestion"
    GENERAL_FEEDBACK = "general_feedback"
    SECURITY_ISSUE = "security_issue"
    CONTENT_REPORT = "content_report"
    USER_REPORT = "user_report"

class FeedbackPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class FeedbackStatus(Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"

class RatingType(Enum):
    USER_RATING = "user_rating"
    CONTENT_RATING = "content_rating"
    SERVICE_RATING = "service_rating"
    FEATURE_RATING = "feature_rating"

class FeedbackCategory(Enum):
    TECHNICAL = "technical"
    UI_UX = "ui_ux"
    FUNCTIONALITY = "functionality"
    PERFORMANCE = "performance"
    SECURITY = "security"
    PRIVACY = "privacy"
    ACCESSIBILITY = "accessibility"

class Feedback(BaseModel):
    id: str
    user_id: int
    type: FeedbackType
    category: FeedbackCategory
    title: str
    description: str
    priority: FeedbackPriority
    status: FeedbackStatus
    rating: Optional[int] = None  # 1-5
    is_resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    assigned_to: Optional[int] = None  # ID модератора/разработчика
    duplicate_of: Optional[str] = None  # ID дубликата
    related_issues: List[str] = []  # IDs связанных проблем
    attachments: List[Dict[str, str]] = []  # [{'id': 'file_id', 'name': 'file_name', 'type': 'image'}]
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime = None
    updated_at: datetime = None

class Rating(BaseModel):
    id: str
    user_id: int
    target_id: str  # ID контента, пользователя, сервиса и т.д.
    target_type: RatingType
    rating: int  # 1-5
    review: Optional[str] = None  # Текстовый отзыв
    created_at: datetime = None
    updated_at: datetime = None

class FeedbackComment(BaseModel):
    id: str
    feedback_id: str
    user_id: int
    content: str
    is_internal: bool = False  # Внутренний комментарий для команды
    created_at: datetime = None
    updated_at: datetime = None

class FeedbackTag(BaseModel):
    id: str
    name: str
    description: str
    color: str  # Цвет тега в формате HEX
    created_at: datetime = None

class FeedbackAnalysis(BaseModel):
    feedback_id: str
    sentiment_score: float  # -1.0 to 1.0
    sentiment_label: str  # 'positive', 'neutral', 'negative'
    topic_classification: str  # 'technical', 'usability', 'feature', etc.
    key_phrases: List[str]
    entities: List[Dict[str, str]]  # [{'type': 'feature', 'value': 'chat'}, ...]
    summary: str
    created_at: datetime = None

class FeedbackService:
    def __init__(self):
        self.feedback_categories = {
            FeedbackType.BUG_REPORT: [FeedbackCategory.TECHNICAL, FeedbackCategory.FUNCTIONALITY],
            FeedbackType.FEATURE_REQUEST: [FeedbackCategory.FUNCTIONALITY, FeedbackCategory.UI_UX],
            FeedbackType.USABILITY_FEEDBACK: [FeedbackCategory.UI_UX, FeedbackCategory.ACCESSIBILITY],
            FeedbackType.PERFORMANCE_ISSUE: [FeedbackCategory.PERFORMANCE, FeedbackCategory.TECHNICAL],
            FeedbackType.DESIGN_SUGGESTION: [FeedbackCategory.UI_UX],
            FeedbackType.SECURITY_ISSUE: [FeedbackCategory.SECURITY, FeedbackCategory.PRIVACY],
            FeedbackType.CONTENT_REPORT: [FeedbackCategory.SECURITY],
            FeedbackType.USER_REPORT: [FeedbackCategory.SECURITY]
        }
        
        self.default_feedback_priorities = {
            FeedbackType.BUG_REPORT: FeedbackPriority.HIGH,
            FeedbackType.SECURITY_ISSUE: FeedbackPriority.URGENT,
            FeedbackType.CONTENT_REPORT: FeedbackPriority.HIGH,
            FeedbackType.USER_REPORT: FeedbackPriority.HIGH,
            FeedbackType.FEATURE_REQUEST: FeedbackPriority.MEDIUM,
            FeedbackType.USABILITY_FEEDBACK: FeedbackPriority.MEDIUM,
            FeedbackType.PERFORMANCE_ISSUE: FeedbackPriority.HIGH,
            FeedbackType.DESIGN_SUGGESTION: FeedbackPriority.LOW,
            FeedbackType.GENERAL_FEEDBACK: FeedbackPriority.LOW
        }
        
        self.sentiment_analysis_model = None
        self.topic_classification_model = None

    async def initialize_feedback_system(self):
        """Инициализация системы обратной связи"""
        # Загружаем модели анализа (если доступны)
        await self._load_analysis_models()
        
        logger.info("Feedback and rating system initialized")

    async def _load_analysis_models(self):
        """Загрузка моделей анализа обратной связи"""
        try:
            # В реальной системе здесь будет загрузка ML моделей
            # для анализа тональности и классификации тем
            # Пока используем заглушку, но инициализируем базовые модели
            self.sentiment_model = {
                'loaded': True,
                'version': '1.0.0',
                'features': ['sentiment_analysis', 'topic_classification']
            }

            self.topic_classifier = {
                'loaded': True,
                'version': '1.0.0',
                'categories': ['bug_report', 'feature_request', 'complaint', 'praise', 'suggestion']
            }

            logger.info("Analysis models loaded successfully")
        except Exception as e:
            logger.error(f"Error loading analysis models: {e}")

    async def submit_feedback(self, user_id: int, feedback_type: FeedbackType,
                            title: str, description: str,
                            category: Optional[FeedbackCategory] = None,
                            rating: Optional[int] = None,
                            attachments: Optional[List[Dict[str, str]]] = None,
                            metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Отправка обратной связи"""
        feedback_id = str(uuid.uuid4())

        # Определяем категорию, если не указана
        if not category:
            category = self.feedback_categories.get(feedback_type, [FeedbackCategory.TECHNICAL])[0]

        # Определяем приоритет
        priority = self.default_feedback_priorities.get(feedback_type, FeedbackPriority.MEDIUM)

        feedback = Feedback(
            id=feedback_id,
            user_id=user_id,
            type=feedback_type,
            category=category,
            title=title,
            description=description,
            priority=priority,
            status=FeedbackStatus.PENDING,
            rating=rating,
            attachments=attachments or [],
            metadata=metadata or {},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем обратную связь в базу данных
        await self._save_feedback_to_db(feedback)

        # Добавляем в кэш
        await self._cache_feedback(feedback)

        # Анализируем обратную связь
        await self._analyze_feedback(feedback)

        # Уведомляем команду поддержки
        await self._notify_support_team(feedback)

        # Создаем запись активности
        await self._log_activity(user_id, "feedback_submitted", {
            "feedback_id": feedback_id,
            "type": feedback_type.value,
            "category": category.value,
            "title": title
        })

        return feedback_id

    async def _save_feedback_to_db(self, feedback: Feedback):
        """Сохранение обратной связи в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO feedback (
                    id, user_id, type, category, title, description, priority, status,
                    rating, is_resolved, resolved_at, resolution_notes, assigned_to,
                    duplicate_of, related_issues, attachments, metadata, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
                """,
                feedback.id, feedback.user_id, feedback.type.value, feedback.category.value,
                feedback.title, feedback.description, feedback.priority.value, feedback.status.value,
                feedback.rating, feedback.is_resolved, feedback.resolved_at,
                feedback.resolution_notes, feedback.assigned_to, feedback.duplicate_of,
                feedback.related_issues, json.dumps(feedback.attachments),
                json.dumps(feedback.metadata) if feedback.metadata else None,
                feedback.created_at, feedback.updated_at
            )

    async def _cache_feedback(self, feedback: Feedback):
        """Кэширование обратной связи"""
        await redis_client.setex(f"feedback:{feedback.id}", 3600, feedback.model_dump_json())

    async def _get_cached_feedback(self, feedback_id: str) -> Optional[Feedback]:
        """Получение обратной связи из кэша"""
        cached = await redis_client.get(f"feedback:{feedback_id}")
        if cached:
            return Feedback(**json.loads(cached.decode()))
        return None

    async def _analyze_feedback(self, feedback: Feedback):
        """Анализ обратной связи"""
        try:
            # В реальной системе здесь будет использование ML моделей
            # для анализа тональности, классификации тем и извлечения ключевых фраз
            # Пока возвращаем заглушку
            
            analysis = FeedbackAnalysis(
                feedback_id=feedback.id,
                sentiment_score=0.0,
                sentiment_label="neutral",
                topic_classification=feedback.category.value,
                key_phrases=self._extract_key_phrases(feedback.description),
                entities=self._extract_entities(feedback.description),
                summary=feedback.description[:100] + "..." if len(feedback.description) > 100 else feedback.description,
                created_at=datetime.utcnow()
            )

            # Сохраняем анализ в базу данных
            await self._save_feedback_analysis(analysis)

            # Обновляем теги обратной связи
            await self._update_feedback_tags(feedback.id, analysis)

        except Exception as e:
            logger.error(f"Error analyzing feedback: {e}")

    def _extract_key_phrases(self, text: str) -> List[str]:
        """Извлечение ключевых фраз из текста"""
        # В реальной системе здесь будет использование NLP библиотек
        # Пока возвращаем простые фразы
        words = text.split()
        phrases = []
        for i in range(len(words) - 2):
            phrases.append(" ".join(words[i:i+3]))
        return phrases[:10]  # Возвращаем первые 10 фраз

    def _extract_entities(self, text: str) -> List[Dict[str, str]]:
        """Извлечение сущностей из текста"""
        # В реальной системе здесь будет использование NLP библиотек
        # Пока возвращаем заглушку
        return [
            {"type": "feature", "value": "chat"},
            {"type": "problem", "value": "slow"}
        ]

    async def _save_feedback_analysis(self, analysis: FeedbackAnalysis):
        """Сохранение анализа обратной связи в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO feedback_analysis (
                    feedback_id, sentiment_score, sentiment_label, topic_classification,
                    key_phrases, entities, summary, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                analysis.feedback_id, analysis.sentiment_score, analysis.sentiment_label,
                analysis.topic_classification, analysis.key_phrases, json.dumps(analysis.entities),
                analysis.summary, analysis.created_at
            )

    async def _update_feedback_tags(self, feedback_id: str, analysis: FeedbackAnalysis):
        """Обновление тегов обратной связи на основе анализа"""
        # В реальной системе здесь будет логика обновления тегов
        # на основе анализа тональности и классификации
        try:
            # Получаем текущую обратную связь
            feedback = await self._get_feedback_from_db(feedback_id)
            if not feedback:
                logger.warning(f"Could not find feedback with ID {feedback_id}")
                return

            # Обновляем теги на основе анализа
            updated_tags = []

            # Добавляем теги на основе тональности
            if analysis.sentiment_score > 0.5:
                updated_tags.append('positive')
            elif analysis.sentiment_score < -0.5:
                updated_tags.append('negative')
            else:
                updated_tags.append('neutral')

            # Добавляем теги на основе категорий
            if analysis.topics:
                updated_tags.extend(analysis.topics)

            # Добавляем теги на основе ключевых слов
            if analysis.keywords:
                updated_tags.extend(analysis.keywords)

            # Удаляем дубликаты
            updated_tags = list(set(updated_tags))

            # Обновляем теги в базе данных
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE feedback SET tags = $1 WHERE id = $2
                    """,
                    updated_tags, feedback_id
                )

            # Обновляем в кэше
            feedback.tags = updated_tags
            await self._cache_feedback(feedback)

            logger.info(f"Updated tags for feedback {feedback_id}: {updated_tags}")
        except Exception as e:
            logger.error(f"Error updating feedback tags for {feedback_id}: {e}")

    async def _notify_support_team(self, feedback: Feedback):
        """Уведомление команды поддержки о новой обратной связи"""
        notification = {
            'type': 'new_feedback',
            'feedback': {
                'id': feedback.id,
                'user_id': feedback.user_id,
                'type': feedback.type.value,
                'category': feedback.category.value,
                'title': feedback.title,
                'priority': feedback.priority.value,
                'created_at': feedback.created_at.isoformat()
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем в канал поддержки
        await redis_client.publish("support_notifications", json.dumps(notification))

    async def rate_content(self, user_id: int, target_id: str, target_type: RatingType,
                          rating: int, review: Optional[str] = None) -> bool:
        """Оценка контента/пользователя/сервиса"""
        if not 1 <= rating <= 5:
            return False

        rating_id = str(uuid.uuid4())

        rating_obj = Rating(
            id=rating_id,
            user_id=user_id,
            target_id=target_id,
            target_type=target_type,
            rating=rating,
            review=review,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем оценку в базу данных
        await self._save_rating_to_db(rating_obj)

        # Обновляем среднюю оценку цели
        await self._update_target_average_rating(target_id, target_type)

        # Добавляем в кэш
        await self._cache_rating(rating_obj)

        # Создаем запись активности
        await self._log_activity(user_id, "content_rated", {
            "target_id": target_id,
            "target_type": target_type.value,
            "rating": rating,
            "review_present": review is not None
        })

        return True

    async def _save_rating_to_db(self, rating: Rating):
        """Сохранение оценки в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ratings (
                    id, user_id, target_id, target_type, rating, review, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                rating.id, rating.user_id, rating.target_id, rating.target_type.value,
                rating.rating, rating.review, rating.created_at, rating.updated_at
            )

    async def _update_target_average_rating(self, target_id: str, target_type: RatingType):
        """Обновление средней оценки цели"""
        async with db_pool.acquire() as conn:
            avg_rating = await conn.fetchval(
                """
                SELECT AVG(rating) FROM ratings
                WHERE target_id = $1 AND target_type = $2
                """,
                target_id, target_type.value
            )

        # Обновляем в зависимости от типа цели
        if target_type == RatingType.CONTENT_RATING:
            await self._update_content_rating(target_id, avg_rating)
        elif target_type == RatingType.USER_RATING:
            await self._update_user_rating(target_id, avg_rating)
        elif target_type == RatingType.SERVICE_RATING:
            await self._update_service_rating(target_id, avg_rating)
        elif target_type == RatingType.FEATURE_RATING:
            await self._update_feature_rating(target_id, avg_rating)

    async def _update_content_rating(self, content_id: str, avg_rating: float):
        """Обновление рейтинга контента"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE content SET average_rating = $2, updated_at = $3
                WHERE id = $1
                """,
                content_id, avg_rating, datetime.utcnow()
            )

    async def _update_user_rating(self, user_id: str, avg_rating: float):
        """Обновление рейтинга пользователя"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users SET average_rating = $2, updated_at = $3
                WHERE id = $1
                """,
                user_id, avg_rating, datetime.utcnow()
            )

    async def _update_service_rating(self, service_id: str, avg_rating: float):
        """Обновление рейтинга сервиса"""
        # В реальной системе здесь будет обновление рейтинга сервиса
        try:
            # Обновляем рейтинг в базе данных
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO service_ratings (service_id, avg_rating, updated_at)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (service_id)
                    DO UPDATE SET avg_rating = $2, updated_at = $3
                    """,
                    service_id, avg_rating, datetime.utcnow()
                )

            # Обновляем в кэше
            cache_key = f"service_rating:{service_id}"
            rating_data = {
                'service_id': service_id,
                'avg_rating': avg_rating,
                'updated_at': datetime.utcnow().isoformat()
            }
            await redis_client.setex(cache_key, 3600, json.dumps(rating_data))  # Кэшируем на 1 час

            # Публикуем событие обновления рейтинга
            rating_event = {
                'type': 'service_rating_updated',
                'service_id': service_id,
                'new_rating': avg_rating,
                'timestamp': datetime.utcnow().isoformat()
            }
            await redis_client.publish('service_events', json.dumps(rating_event))

            logger.info(f"Service rating updated for {service_id}: {avg_rating}")
        except Exception as e:
            logger.error(f"Error updating service rating for {service_id}: {e}")

    async def _update_feature_rating(self, feature_id: str, avg_rating: float):
        """Обновление рейтинга функции"""
        # В реальной системе здесь будет обновление рейтинга функции
        try:
            # Обновляем рейтинг функции в базе данных
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO feature_ratings (feature_id, avg_rating, updated_at)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (feature_id)
                    DO UPDATE SET avg_rating = $2, updated_at = $3
                    """,
                    feature_id, avg_rating, datetime.utcnow()
                )

            # Обновляем в кэше
            cache_key = f"feature_rating:{feature_id}"
            rating_data = {
                'feature_id': feature_id,
                'avg_rating': avg_rating,
                'updated_at': datetime.utcnow().isoformat()
            }
            await redis_client.setex(cache_key, 3600, json.dumps(rating_data))  # Кэшируем на 1 час

            # Публикуем событие обновления рейтинга
            rating_event = {
                'type': 'feature_rating_updated',
                'feature_id': feature_id,
                'new_rating': avg_rating,
                'timestamp': datetime.utcnow().isoformat()
            }
            await redis_client.publish('feature_events', json.dumps(rating_event))

            logger.info(f"Feature rating updated for {feature_id}: {avg_rating}")
        except Exception as e:
            logger.error(f"Error updating feature rating for {feature_id}: {e}")

    async def _cache_rating(self, rating: Rating):
        """Кэширование оценки"""
        await redis_client.setex(f"rating:{rating.id}", 1800, rating.model_dump_json())

    async def _get_cached_rating(self, rating_id: str) -> Optional[Rating]:
        """Получение оценки из кэша"""
        cached = await redis_client.get(f"rating:{rating_id}")
        if cached:
            return Rating(**json.loads(cached.decode()))
        return None

    async def get_user_feedback(self, user_id: int, feedback_type: Optional[FeedbackType] = None,
                              status: Optional[FeedbackStatus] = None,
                              limit: int = 50, offset: int = 0) -> List[Feedback]:
        """Получение обратной связи пользователя"""
        conditions = ["user_id = $1"]
        params = [user_id]
        param_idx = 2

        if feedback_type:
            conditions.append(f"type = ${param_idx}")
            params.append(feedback_type.value)
            param_idx += 1

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, user_id, type, category, title, description, priority, status,
                   rating, is_resolved, resolved_at, resolution_notes, assigned_to,
                   duplicate_of, related_issues, attachments, metadata, created_at, updated_at
            FROM feedback
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        feedback_list = []
        for row in rows:
            feedback = Feedback(
                id=row['id'],
                user_id=row['user_id'],
                type=FeedbackType(row['type']),
                category=FeedbackCategory(row['category']),
                title=row['title'],
                description=row['description'],
                priority=FeedbackPriority(row['priority']),
                status=FeedbackStatus(row['status']),
                rating=row['rating'],
                is_resolved=row['is_resolved'],
                resolved_at=row['resolved_at'],
                resolution_notes=row['resolution_notes'],
                assigned_to=row['assigned_to'],
                duplicate_of=row['duplicate_of'],
                related_issues=row['related_issues'] or [],
                attachments=json.loads(row['attachments']) if row['attachments'] else [],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            feedback_list.append(feedback)

        return feedback_list

    async def get_content_ratings(self, content_id: str) -> Dict[str, Any]:
        """Получение оценок контента"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT rating, COUNT(*) as count
                FROM ratings
                WHERE target_id = $1 AND target_type = $2
                GROUP BY rating
                ORDER BY rating
                """,
                content_id, RatingType.CONTENT_RATING.value
            )

        rating_counts = {i: 0 for i in range(1, 6)}
        total_ratings = 0
        sum_ratings = 0

        for row in rows:
            rating_value = row['rating']
            count = row['count']
            rating_counts[rating_value] = count
            total_ratings += count
            sum_ratings += rating_value * count

        average_rating = sum_ratings / total_ratings if total_ratings > 0 else 0

        return {
            'content_id': content_id,
            'average_rating': round(average_rating, 2),
            'total_ratings': total_ratings,
            'rating_distribution': rating_counts,
            'breakdown': [
                {
                    'rating': i,
                    'count': rating_counts[i],
                    'percentage': round((rating_counts[i] / total_ratings) * 100, 2) if total_ratings > 0 else 0
                }
                for i in range(5, 0, -1)
            ]
        }

    async def get_user_ratings(self, user_id: int) -> Dict[str, Any]:
        """Получение оценок пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT rating, COUNT(*) as count
                FROM ratings
                WHERE target_id = $1 AND target_type = $2
                GROUP BY rating
                ORDER BY rating
                """,
                user_id, RatingType.USER_RATING.value
            )

        rating_counts = {i: 0 for i in range(1, 6)}
        total_ratings = 0
        sum_ratings = 0

        for row in rows:
            rating_value = row['rating']
            count = row['count']
            rating_counts[rating_value] = count
            total_ratings += count
            sum_ratings += rating_value * count

        average_rating = sum_ratings / total_ratings if total_ratings > 0 else 0

        return {
            'user_id': user_id,
            'average_rating': round(average_rating, 2),
            'total_ratings': total_ratings,
            'rating_distribution': rating_counts,
            'breakdown': [
                {
                    'rating': i,
                    'count': rating_counts[i],
                    'percentage': round((rating_counts[i] / total_ratings) * 100, 2) if total_ratings > 0 else 0
                }
                for i in range(5, 0, -1)
            ]
        }

    async def add_comment_to_feedback(self, feedback_id: str, user_id: int, 
                                    content: str, is_internal: bool = False) -> Optional[str]:
        """Добавление комментария к обратной связи"""
        feedback = await self._get_cached_feedback(feedback_id)
        if not feedback:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT id, user_id FROM feedback WHERE id = $1",
                    feedback_id
                )
            if not row:
                return None
            feedback = Feedback(id=row['id'], user_id=row['user_id'])

        # Проверяем права на комментирование
        if not await self._can_comment_feedback(feedback, user_id, is_internal):
            return None

        comment_id = str(uuid.uuid4())

        comment = FeedbackComment(
            id=comment_id,
            feedback_id=feedback_id,
            user_id=user_id,
            content=content,
            is_internal=is_internal,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем комментарий в базу данных
        await self._save_feedback_comment(comment)

        # Увеличиваем счетчик комментариев
        await self._increment_feedback_comment_count(feedback_id)

        # Уведомляем заинтересованные стороны
        await self._notify_feedback_commented(feedback, comment)

        # Создаем запись активности
        await self._log_activity(user_id, "feedback_commented", {
            "feedback_id": feedback_id,
            "comment_id": comment_id,
            "is_internal": is_internal
        })

        return comment_id

    async def _save_feedback_comment(self, comment: FeedbackComment):
        """Сохранение комментария к обратной связи в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO feedback_comments (
                    id, feedback_id, user_id, content, is_internal, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                comment.id, comment.feedback_id, comment.user_id, comment.content,
                comment.is_internal, comment.created_at, comment.updated_at
            )

    async def _increment_feedback_comment_count(self, feedback_id: str):
        """Увеличение счетчика комментариев к обратной связи"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE feedback SET metadata = metadata || $2::jsonb, updated_at = $3
                WHERE id = $1
                """,
                feedback_id,
                json.dumps({'comments_count': await self._get_feedback_comment_count(feedback_id) + 1}),
                datetime.utcnow()
            )

    async def _get_feedback_comment_count(self, feedback_id: str) -> int:
        """Получение количества комментариев к обратной связи"""
        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM feedback_comments WHERE feedback_id = $1",
                feedback_id
            )
        return count or 0

    async def _can_comment_feedback(self, feedback: Feedback, user_id: int, 
                                  is_internal: bool) -> bool:
        """Проверка прав на комментирование обратной связи"""
        if is_internal:
            # Только модераторы и администраторы могут оставлять внутренние комментарии
            return await self._is_moderator(user_id) or await self._is_admin(user_id)
        else:
            # Любой пользователь может оставить внешний комментарий
            return True

    async def _notify_feedback_commented(self, feedback: Feedback, comment: FeedbackComment):
        """Уведомление о комментировании обратной связи"""
        notification = {
            'type': 'feedback_commented',
            'feedback_id': feedback.id,
            'comment': {
                'id': comment.id,
                'user_id': comment.user_id,
                'content': comment.content[:50] + '...' if len(comment.content) > 50 else comment.content,
                'is_internal': comment.is_internal
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        # Уведомляем создателя обратной связи
        await redis_client.publish(f"user:{feedback.user_id}:feedback", json.dumps(notification))

        # Если обратная связь назначена кому-то, уведомляем этого пользователя
        if feedback.assigned_to:
            await redis_client.publish(f"user:{feedback.assigned_to}:feedback", json.dumps(notification))

    async def update_feedback_status(self, feedback_id: str, user_id: int, 
                                   status: FeedbackStatus, 
                                   resolution_notes: Optional[str] = None) -> bool:
        """Обновление статуса обратной связи"""
        feedback = await self._get_cached_feedback(feedback_id)
        if not feedback:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT id, user_id, assigned_to FROM feedback WHERE id = $1",
                    feedback_id
                )
            if not row:
                return False
            feedback = Feedback(
                id=row['id'],
                user_id=row['user_id'],
                assigned_to=row['assigned_to']
            )

        # Проверяем права на обновление статуса
        if not await self._can_update_feedback_status(feedback, user_id):
            return False

        # Обновляем статус в базе данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE feedback SET
                    status = $2, is_resolved = $3, resolved_at = CASE WHEN $3 = true THEN $4 ELSE resolved_at END,
                    resolution_notes = $5, updated_at = $6
                WHERE id = $1
                """,
                feedback_id, status.value, status == FeedbackStatus.RESOLVED,
                datetime.utcnow() if status == FeedbackStatus.RESOLVED else feedback.resolved_at,
                resolution_notes, datetime.utcnow()
            )

        # Обновляем в кэше
        feedback.status = status
        feedback.is_resolved = status == FeedbackStatus.RESOLVED
        if status == FeedbackStatus.RESOLVED:
            feedback.resolved_at = datetime.utcnow()
        feedback.resolution_notes = resolution_notes
        feedback.updated_at = datetime.utcnow()
        
        await self._cache_feedback(feedback)

        # Уведомляем пользователя о изменении статуса
        await self._notify_feedback_status_changed(feedback)

        # Создаем запись активности
        await self._log_activity(user_id, "feedback_status_updated", {
            "feedback_id": feedback_id,
            "new_status": status.value,
            "resolution_notes_present": resolution_notes is not None
        })

        return True

    async def _can_update_feedback_status(self, feedback: Feedback, user_id: int) -> bool:
        """Проверка прав на обновление статуса обратной связи"""
        # Создатель может обновить статус
        if feedback.user_id == user_id:
            return True

        # Назначенный модератор может обновить статус
        if feedback.assigned_to == user_id:
            return True

        # Администраторы могут обновить статус
        if await self._is_admin(user_id):
            return True

        # Модераторы могут обновить статус
        if await self._is_moderator(user_id):
            return True

        return False

    async def _notify_feedback_status_changed(self, feedback: Feedback):
        """Уведомление об изменении статуса обратной связи"""
        notification = {
            'type': 'feedback_status_changed',
            'feedback': {
                'id': feedback.id,
                'title': feedback.title,
                'status': feedback.status.value,
                'resolution_notes': feedback.resolution_notes
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        # Уведомляем создателя обратной связи
        await redis_client.publish(f"user:{feedback.user_id}:feedback", json.dumps(notification))

        # Если обратная связь была назначена кому-то, уведомляем этого пользователя
        if feedback.assigned_to:
            await redis_client.publish(f"user:{feedback.assigned_to}:feedback", json.dumps(notification))

    async def assign_feedback(self, feedback_id: str, assignee_id: int, 
                            user_id: int) -> bool:
        """Назначение обратной связи модератору/разработчику"""
        feedback = await self._get_cached_feedback(feedback_id)
        if not feedback:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT id, user_id, assigned_to FROM feedback WHERE id = $1",
                    feedback_id
                )
            if not row:
                return False
            feedback = Feedback(
                id=row['id'],
                user_id=row['user_id'],
                assigned_to=row['assigned_to']
            )

        # Проверяем права на назначение
        if not await self._can_assign_feedback(user_id):
            return False

        # Обновляем назначение в базе данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE feedback SET assigned_to = $2, updated_at = $3 WHERE id = $1",
                feedback_id, assignee_id, datetime.utcnow()
            )

        # Обновляем в кэше
        feedback.assigned_to = assignee_id
        feedback.updated_at = datetime.utcnow()
        await self._cache_feedback(feedback)

        # Уведомляем назначенного пользователя
        await self._notify_feedback_assigned(assignee_id, feedback)

        # Создаем запись активности
        await self._log_activity(user_id, "feedback_assigned", {
            "feedback_id": feedback_id,
            "assignee_id": assignee_id
        })

        return True

    async def _can_assign_feedback(self, user_id: int) -> bool:
        """Проверка прав на назначение обратной связи"""
        # Только администраторы и модераторы могут назначать обратную связь
        return await self._is_admin(user_id) or await self._is_moderator(user_id)

    async def _notify_feedback_assigned(self, assignee_id: int, feedback: Feedback):
        """Уведомление о назначении обратной связи"""
        notification = {
            'type': 'feedback_assigned',
            'feedback': {
                'id': feedback.id,
                'title': feedback.title,
                'type': feedback.type.value,
                'priority': feedback.priority.value,
                'created_at': feedback.created_at.isoformat()
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        await redis_client.publish(f"user:{assignee_id}:feedback", json.dumps(notification))

    async def get_feedback_statistics(self) -> Dict[str, Any]:
        """Получение статистики по обратной связи"""
        async with db_pool.acquire() as conn:
            # Общая статистика
            total_feedback = await conn.fetchval("SELECT COUNT(*) FROM feedback")
            
            # Статистика по типам
            type_stats = await conn.fetch(
                "SELECT type, COUNT(*) as count FROM feedback GROUP BY type"
            )
            
            # Статистика по статусам
            status_stats = await conn.fetch(
                "SELECT status, COUNT(*) as count FROM feedback GROUP BY status"
            )
            
            # Статистика по приоритетам
            priority_stats = await conn.fetch(
                "SELECT priority, COUNT(*) as count FROM feedback GROUP BY priority"
            )
            
            # Среднее время решения
            avg_resolution_time = await conn.fetchval(
                """
                SELECT AVG(EXTRACT(EPOCH FROM (resolved_at - created_at))/3600) as avg_hours
                FROM feedback
                WHERE status = 'resolved' AND resolved_at IS NOT NULL
                """
            )

        stats = {
            'total_feedback': total_feedback or 0,
            'by_type': {row['type']: row['count'] for row in type_stats},
            'by_status': {row['status']: row['count'] for row in status_stats},
            'by_priority': {row['priority']: row['count'] for row in priority_stats},
            'average_resolution_time_hours': avg_resolution_time or 0,
            'resolution_rate': await self._calculate_resolution_rate(),
            'satisfaction_rate': await self._calculate_satisfaction_rate(),
            'timestamp': datetime.utcnow().isoformat()
        }

        return stats

    async def _calculate_resolution_rate(self) -> float:
        """Расчет процента решенных обращений"""
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM feedback")
            resolved = await conn.fetchval("SELECT COUNT(*) FROM feedback WHERE status = 'resolved'")
        
        return (resolved or 0) / (total or 1) * 100

    async def _calculate_satisfaction_rate(self) -> float:
        """Расчет процента удовлетворенности"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT rating FROM feedback WHERE rating IS NOT NULL AND rating >= 4"
            )
            
            total_with_rating = await conn.fetchval("SELECT COUNT(*) FROM feedback WHERE rating IS NOT NULL")
            satisfied_count = len(rows)

        return (satisfied_count / (total_with_rating or 1)) * 100

    async def get_user_feedback_insights(self, user_id: int) -> Dict[str, Any]:
        """Получение инсайтов по обратной связи пользователя"""
        feedback_list = await self.get_user_feedback(user_id)
        
        # Подсчитываем статистику
        total_feedback = len(feedback_list)
        resolved_feedback = sum(1 for fb in feedback_list if fb.is_resolved)
        avg_rating = sum(fb.rating for fb in feedback_list if fb.rating) / len([fb for fb in feedback_list if fb.rating]) if [fb for fb in feedback_list if fb.rating] else 0
        
        # Подсчитываем по типам
        type_breakdown = {}
        for fb in feedback_list:
            fb_type = fb.type.value
            type_breakdown[fb_type] = type_breakdown.get(fb_type, 0) + 1
        
        # Подсчитываем по приоритетам
        priority_breakdown = {}
        for fb in feedback_list:
            priority = fb.priority.value
            priority_breakdown[priority] = priority_breakdown.get(priority, 0) + 1
        
        # Подсчитываем по статусам
        status_breakdown = {}
        for fb in feedback_list:
            status = fb.status.value
            status_breakdown[status] = status_breakdown.get(status, 0) + 1

        insights = {
            'user_id': user_id,
            'total_feedback': total_feedback,
            'resolved_feedback': resolved_feedback,
            'resolution_rate': (resolved_feedback / total_feedback * 100) if total_feedback > 0 else 0,
            'average_rating': round(avg_rating, 2),
            'type_breakdown': type_breakdown,
            'priority_breakdown': priority_breakdown,
            'status_breakdown': status_breakdown,
            'most_common_categories': await self._get_most_common_categories_for_user(user_id),
            'feedback_trends': await self._get_feedback_trends_for_user(user_id),
            'timestamp': datetime.utcnow().isoformat()
        }

        return insights

    async def _get_most_common_categories_for_user(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение наиболее частых категорий обратной связи пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT category, COUNT(*) as count
                FROM feedback
                WHERE user_id = $1
                GROUP BY category
                ORDER BY count DESC
                LIMIT 5
                """,
                user_id
            )

        return [
            {
                'category': row['category'],
                'count': row['count']
            }
            for row in rows
        ]

    async def _get_feedback_trends_for_user(self, user_id: int) -> Dict[str, Any]:
        """Получение трендов обратной связи пользователя"""
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DATE_TRUNC('day', created_at) as day, type, COUNT(*) as count
                FROM feedback
                WHERE user_id = $1 AND created_at >= $2
                GROUP BY DATE_TRUNC('day', created_at), type
                ORDER BY day
                """,
                user_id, thirty_days_ago
            )

        # Группируем по дням и типам
        trends = {}
        for row in rows:
            day = row['day'].strftime('%Y-%m-%d')
            fb_type = row['type']
            
            if day not in trends:
                trends[day] = {}
            
            trends[day][fb_type] = row['count']

        return trends

    async def _is_moderator(self, user_id: int) -> bool:
        """Проверка, является ли пользователь модератором"""
        # В реальной системе здесь будет проверка в таблице модераторов
        return False

    async def _is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        # В реальной системе здесь будет проверка в таблице администраторов
        return False

    async def _log_activity(self, user_id: int, action: str, details: Dict[str, Any]):
        """Логирование активности пользователя"""
        activity_id = str(uuid.uuid4())
        activity = {
            'id': activity_id,
            'user_id': user_id,
            'action': action,
            'details': details,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Сохраняем в Redis для быстрого доступа
        await redis_client.lpush(f"user_activities:{user_id}", json.dumps(activity))
        await redis_client.ltrim(f"user_activities:{user_id}", 0, 99)  # Храним последние 100 активностей

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
feedback_service = FeedbackService()
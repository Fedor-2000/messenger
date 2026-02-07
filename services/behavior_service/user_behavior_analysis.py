# User Behavior Analysis System
# File: services/behavior_service/user_behavior_analysis.py

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
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import IsolationForest
import matplotlib.pyplot as plt
import seaborn as sns
from io import BytesIO
import base64

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class UserActivityType(Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    MESSAGE_SENT = "message_sent"
    MESSAGE_RECEIVED = "message_received"
    FILE_UPLOADED = "file_uploaded"
    FILE_DOWNLOADED = "file_downloaded"
    TASK_CREATED = "task_created"
    TASK_COMPLETED = "task_completed"
    POLL_VOTED = "poll_voted"
    CALL_INITIATED = "call_initiated"
    CALL_JOINED = "call_joined"
    GAME_STARTED = "game_started"
    GAME_COMPLETED = "game_completed"
    UI_ACTION = "ui_action"
    SETTINGS_CHANGED = "settings_changed"
    CONTENT_SHARED = "content_shared"
    CONTENT_LIKED = "content_liked"
    CONTENT_COMMENTED = "content_commented"

class UserSegment(Enum):
    NEW_USER = "new_user"
    ACTIVE_USER = "active_user"
    PASSIVE_USER = "passive_user"
    POWER_USER = "power_user"
    CHURN_RISK = "churn_risk"
    ENGAGED_USER = "engaged_user"
    INFREQUENT_USER = "infrequent_user"

class UserBehaviorPattern(Enum):
    ACTIVE_CHATTER = "active_chatter"
    PASSIVE_READER = "passive_reader"
    FILE_SHARER = "file_sharer"
    TASK_ORGANIZER = "task_organizer"
    GAMER = "gamer"
    CALLER = "caller"
    CUSTOMIZER = "customizer"
    NIGHT_OWL = "night_owl"
    MORNING_PERSON = "morning_person"
    WEEKEND_USER = "weekend_user"

class UserActivity(BaseModel):
    id: str
    user_id: int
    activity_type: UserActivityType
    timestamp: datetime = None
    duration: Optional[float] = None  # Продолжительность действия в секундах
    metadata: Optional[Dict[str, Any]] = None  # Дополнительные данные
    session_id: Optional[str] = None

class UserBehaviorProfile(BaseModel):
    user_id: int
    segments: List[UserSegment]
    patterns: List[UserBehaviorPattern]
    preferences: Dict[str, Any]  # Предпочтения пользователя
    activity_level: str  # 'high', 'medium', 'low'
    peak_usage_times: List[str]  # ['morning', 'afternoon', 'evening', 'night']
    preferred_features: List[str]
    last_interaction: Optional[datetime] = None
    engagement_score: float = 0.0  # 0.0 - 1.0
    churn_risk_score: float = 0.0  # 0.0 - 1.0
    retention_probability: float = 0.0  # 0.0 - 1.0
    created_at: datetime = None
    updated_at: datetime = None

class UserBehaviorAnalysisService:
    def __init__(self):
        self.activity_weights = {
            UserActivityType.MESSAGE_SENT: 1.0,
            UserActivityType.FILE_UPLOADED: 1.5,
            UserActivityType.TASK_CREATED: 1.2,
            UserActivityType.POLL_VOTED: 0.8,
            UserActivityType.CALL_INITIATED: 1.3,
            UserActivityType.GAME_STARTED: 1.0,
            UserActivityType.CONTENT_SHARED: 1.1,
            UserActivityType.CONTENT_LIKED: 0.5,
            UserActivityType.CONTENT_COMMENTED: 0.7,
            UserActivityType.LOGIN: 0.3,
            UserActivityType.MESSAGE_RECEIVED: 0.2,
            UserActivityType.FILE_DOWNLOADED: 0.4,
            UserActivityType.TASK_COMPLETED: 1.0,
            UserActivityType.CALL_JOINED: 1.0,
            UserActivityType.GAME_COMPLETED: 0.8,
            UserActivityType.UI_ACTION: 0.1,
            UserActivityType.SETTINGS_CHANGED: 0.2
        }
        
        self.segmentation_rules = {
            'engagement_score': {
                'high': 0.7,
                'medium': 0.4,
                'low': 0.0
            },
            'churn_risk_score': {
                'high': 0.7,
                'medium': 0.4,
                'low': 0.0
            },
            'activity_frequency': {
                'daily': 5,
                'weekly': 2,
                'monthly': 1
            }
        }
        
        self.ml_models = {}  # Модели машинного обучения для анализа поведения

    async def track_user_activity(self, user_id: int, activity_type: UserActivityType,
                                 metadata: Optional[Dict] = None,
                                 duration: Optional[float] = None,
                                 session_id: Optional[str] = None) -> bool:
        """Отслеживание активности пользователя"""
        try:
            activity_id = str(uuid.uuid4())
            timestamp = datetime.utcnow()

            activity = UserActivity(
                id=activity_id,
                user_id=user_id,
                activity_type=activity_type,
                timestamp=timestamp,
                duration=duration,
                metadata=metadata or {},
                session_id=session_id
            )

            # Сохраняем активность в базу данных
            await self._save_user_activity(activity)

            # Обновляем профиль поведения пользователя
            await self._update_user_behavior_profile(user_id, activity)

            # Добавляем в кэш
            await self._cache_user_activity(activity)

            # Увеличиваем счетчики в Redis
            await self._increment_activity_counters(user_id, activity_type)

            # Создаем запись активности
            await self._log_activity(user_id, "user_activity_tracked", {
                "activity_type": activity_type.value,
                "session_id": session_id
            })

            return True
        except Exception as e:
            logger.error(f"Error tracking user activity: {e}")
            return False

    async def _save_user_activity(self, activity: UserActivity):
        """Сохранение активности пользователя в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_activities (
                    id, user_id, activity_type, timestamp, duration, metadata, session_id
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                activity.id, activity.user_id, activity.activity_type.value,
                activity.timestamp, activity.duration,
                json.dumps(activity.metadata) if activity.metadata else None,
                activity.session_id
            )

    async def _update_user_behavior_profile(self, user_id: int, activity: UserActivity):
        """Обновление профиля поведения пользователя"""
        profile = await self.get_user_behavior_profile(user_id)
        if not profile:
            profile = await self._create_default_behavior_profile(user_id)

        # Обновляем время последнего взаимодействия
        profile.last_interaction = datetime.utcnow()

        # Обновляем уровень активности
        await self._update_activity_level(profile)

        # Обновляем предпочтительные функции
        feature_name = self._get_feature_name_from_activity(activity.activity_type)
        if feature_name and feature_name not in profile.preferred_features:
            profile.preferred_features.append(feature_name)

        # Обновляем пики использования
        current_hour = datetime.utcnow().hour
        time_slot = self._get_time_slot(current_hour)
        if time_slot not in profile.peak_usage_times:
            profile.peak_usage_times.append(time_slot)

        # Определяем паттерны поведения
        await self._detect_behavior_patterns(profile)

        # Обновляем оценку вовлеченности
        await self._update_engagement_score(profile)

        # Обновляем риск оттока
        await self._update_churn_risk_score(profile)

        # Обновляем вероятность удержания
        await self._update_retention_probability(profile)

        # Обновляем сегменты пользователя
        await self._update_user_segments(profile)

        # Обновляем в базе данных
        await self._update_behavior_profile_in_db(profile)

        # Обновляем кэш
        await self._cache_behavior_profile(profile)

    async def _create_default_behavior_profile(self, user_id: int) -> UserBehaviorProfile:
        """Создание профиля поведения по умолчанию для нового пользователя"""
        profile = UserBehaviorProfile(
            user_id=user_id,
            segments=[UserSegment.NEW_USER],
            patterns=[],
            preferences={},
            activity_level="low",
            peak_usage_times=[],
            preferred_features=[],
            last_interaction=datetime.utcnow(),
            engagement_score=0.0,
            churn_risk_score=0.0,
            retention_probability=0.8,  # Новый пользователь имеет высокую вероятность удержания
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем в базу данных
        await self._save_behavior_profile(profile)

        # Кэшируем
        await self._cache_behavior_profile(profile)

        return profile

    async def _update_activity_level(self, profile: UserBehaviorProfile):
        """Обновление уровня активности пользователя"""
        # Получаем количество активностей за последние 7 дней
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_activities = await self._get_user_activities_since(
            profile.user_id, week_ago
        )

        # Рассчитываем взвешенную активность
        weighted_activity = 0
        for activity in recent_activities:
            activity_weight = self.activity_weights.get(activity.activity_type, 0.1)
            weighted_activity += activity_weight

        if weighted_activity > 50:
            profile.activity_level = "high"
        elif weighted_activity > 20:
            profile.activity_level = "medium"
        else:
            profile.activity_level = "low"

    def _get_feature_name_from_activity(self, activity_type: UserActivityType) -> Optional[str]:
        """Получение названия функции из типа активности"""
        mapping = {
            UserActivityType.MESSAGE_SENT: "messaging",
            UserActivityType.MESSAGE_RECEIVED: "messaging",
            UserActivityType.FILE_UPLOADED: "file_sharing",
            UserActivityType.FILE_DOWNLOADED: "file_sharing",
            UserActivityType.TASK_CREATED: "task_management",
            UserActivityType.TASK_COMPLETED: "task_management",
            UserActivityType.POLL_VOTED: "polls",
            UserActivityType.CALL_INITIATED: "calling",
            UserActivityType.CALL_JOINED: "calling",
            UserActivityType.GAME_STARTED: "gaming",
            UserActivityType.GAME_COMPLETED: "gaming",
            UserActivityType.CONTENT_SHARED: "content_sharing",
            UserActivityType.CONTENT_LIKED: "content_interaction",
            UserActivityType.CONTENT_COMMENTED: "content_interaction"
        }
        return mapping.get(activity_type)

    def _get_time_slot(self, hour: int) -> str:
        """Определение временного слота по часу"""
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 22:
            return "evening"
        else:
            return "night"

    async def _detect_behavior_patterns(self, profile: UserBehaviorProfile):
        """Определение паттернов поведения пользователя"""
        # Получаем историю активностей за последние 30 дней
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        activities = await self._get_user_activities_since(
            profile.user_id, thirty_days_ago
        )

        # Подсчитываем различные типы активностей
        activity_counts = {}
        for activity in activities:
            activity_type = activity.activity_type.value
            activity_counts[activity_type] = activity_counts.get(activity_type, 0) + 1

        # Определяем паттерны на основе пороговых значений
        for pattern, rules in self.behavior_detection_rules.items():
            if await self._matches_behavior_pattern(activity_counts, rules):
                if pattern not in profile.patterns:
                    profile.patterns.append(pattern)

        # Определяем временные паттерны
        time_usage_patterns = await self._analyze_time_usage_patterns(activities)
        for pattern in time_usage_patterns:
            if pattern not in profile.patterns:
                profile.patterns.append(pattern)

    async def _analyze_time_usage_patterns(self, activities: List[UserActivity]) -> List[UserBehaviorPattern]:
        """Анализ временных паттернов использования"""
        patterns = []

        # Подсчитываем активности по времени суток
        time_usage = {
            'morning': 0,
            'afternoon': 0,
            'evening': 0,
            'night': 0
        }

        for activity in activities:
            hour = activity.timestamp.hour
            time_slot = self._get_time_slot(hour)
            time_usage[time_slot] += 1

        # Определяем преобладающее время использования
        max_time_slot = max(time_usage, key=time_usage.get)
        usage_percentage = time_usage[max_time_slot] / len(activities) if activities else 0

        if max_time_slot == 'night' and usage_percentage > 0.4:
            patterns.append(UserBehaviorPattern.NIGHT_OWL)
        elif max_time_slot == 'morning' and usage_percentage > 0.4:
            patterns.append(UserBehaviorPattern.MORNING_PERSON)

        # Анализируем использование по дням недели
        weekday_usage = [0] * 7  # Понедельник-Воскресенье
        for activity in activities:
            weekday = activity.timestamp.weekday()
            weekday_usage[weekday] += 1

        weekend_activity = sum(weekday_usage[5:7])  # Суббота и воскресенье
        total_activity = sum(weekday_usage)
        weekend_ratio = weekend_activity / total_activity if total_activity > 0 else 0

        if weekend_ratio > 0.5:
            patterns.append(UserBehaviorPattern.WEEKEND_USER)

        return patterns

    async def _matches_behavior_pattern(self, activity_counts: Dict[str, int], 
                                      rules: Dict[str, Any]) -> bool:
        """Проверка соответствия активностей паттерну поведения"""
        # Реализация логики проверки соответствия паттерну
        # В реальной системе здесь будет более сложная логика
        return True

    async def _update_engagement_score(self, profile: UserBehaviorProfile):
        """Обновление оценки вовлеченности пользователя"""
        # Рассчитываем оценку вовлеченности на основе различных факторов
        base_score = 0.3  # Базовая оценка

        # Увеличиваем за активность
        if profile.activity_level == "high":
            base_score += 0.4
        elif profile.activity_level == "medium":
            base_score += 0.2

        # Увеличиваем за разнообразие функций
        feature_diversity_bonus = min(len(profile.preferred_features) * 0.05, 0.2)
        base_score += feature_diversity_bonus

        # Увеличиваем за частые взаимодействия
        if profile.last_interaction:
            days_since_last = (datetime.utcnow() - profile.last_interaction).days
            if days_since_last <= 1:
                base_score += 0.2
            elif days_since_last <= 3:
                base_score += 0.1

        # Увеличиваем за участие в социальных функциях
        social_patterns = [UserBehaviorPattern.ACTIVE_CHATTER, UserBehaviorPattern.GAMER, UserBehaviorPattern.CALLER]
        social_pattern_count = sum(1 for pattern in social_patterns if pattern in profile.patterns)
        base_score += min(social_pattern_count * 0.1, 0.2)

        profile.engagement_score = max(0.0, min(1.0, base_score))

    async def _update_churn_risk_score(self, profile: UserBehaviorProfile):
        """Обновление оценки риска оттока пользователя"""
        risk_score = 0.2  # Базовый риск

        # Увеличиваем риск за низкую активность
        if profile.activity_level == "low":
            risk_score += 0.3

        # Увеличиваем риск за отсутствие активности
        if profile.last_interaction:
            days_since_last = (datetime.utcnow() - profile.last_interaction).days
            if days_since_last > 60:
                risk_score += 0.5
            elif days_since_last > 30:
                risk_score += 0.3
            elif days_since_last > 14:
                risk_score += 0.1

        # Уменьшаем риск за участие в социальных функциях
        if UserBehaviorPattern.ACTIVE_CHATTER in profile.patterns:
            risk_score -= 0.2

        # Уменьшаем риск за участие в продуктивных функциях
        if UserBehaviorPattern.TASK_ORGANIZER in profile.patterns:
            risk_score -= 0.1

        profile.churn_risk_score = max(0.0, min(1.0, risk_score))

    async def _update_retention_probability(self, profile: UserBehaviorProfile):
        """Обновление вероятности удержания пользователя"""
        base_probability = 0.7  # Базовая вероятность

        # Увеличиваем за высокую вовлеченность
        if profile.engagement_score >= 0.7:
            base_probability += 0.2
        elif profile.engagement_score >= 0.5:
            base_probability += 0.1

        # Уменьшаем за высокий риск оттока
        base_probability -= profile.churn_risk_score * 0.3

        # Увеличиваем за участие в социальных функциях
        if UserBehaviorPattern.ACTIVE_CHATTER in profile.patterns:
            base_probability += 0.1

        profile.retention_probability = max(0.0, min(1.0, base_probability))

    async def _update_user_segments(self, profile: UserBehaviorProfile):
        """Обновление сегментов пользователя"""
        segments = []

        # Определяем сегменты на основе оценок
        if profile.engagement_score >= 0.7:
            segments.append(UserSegment.POWER_USER)
        elif profile.engagement_score >= 0.5:
            segments.append(UserSegment.ACTIVE_USER)
        elif profile.engagement_score >= 0.2:
            segments.append(UserSegment.ENGAGED_USER)
        else:
            segments.append(UserSegment.INFREQUENT_USER)

        # Определяем сегменты на основе риска оттока
        if profile.churn_risk_score >= 0.7:
            segments.append(UserSegment.CHURN_RISK)

        # Определяем сегменты на основе активности
        if profile.activity_level == "low" and profile.churn_risk_score < 0.5:
            segments.append(UserSegment.PASSIVE_USER)

        profile.segments = segments

    async def _get_user_activities_since(self, user_id: int, 
                                       since_date: datetime) -> List[UserActivity]:
        """Получение активностей пользователя с определенной даты"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, user_id, activity_type, timestamp, duration, metadata, session_id
                FROM user_activities
                WHERE user_id = $1 AND timestamp >= $2
                ORDER BY timestamp DESC
                """,
                user_id, since_date
            )

        activities = []
        for row in rows:
            activity = UserActivity(
                id=row['id'],
                user_id=row['user_id'],
                activity_type=UserActivityType(row['activity_type']),
                timestamp=row['timestamp'],
                duration=row['duration'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                session_id=row['session_id']
            )
            activities.append(activity)

        return activities

    async def _save_behavior_profile(self, profile: UserBehaviorProfile):
        """Сохранение профиля поведения в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_behavior_profiles (
                    user_id, segments, patterns, preferences, activity_level, peak_usage_times,
                    preferred_features, last_interaction, engagement_score, churn_risk_score,
                    retention_probability, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (user_id) DO UPDATE SET
                    segments = $2, patterns = $3, preferences = $4, activity_level = $5,
                    peak_usage_times = $6, preferred_features = $7,
                    last_interaction = $8, engagement_score = $9, churn_risk_score = $10,
                    retention_probability = $11, updated_at = $13
                """,
                profile.user_id, [s.value for s in profile.segments],
                [p.value for p in profile.patterns], json.dumps(profile.preferences),
                profile.activity_level, profile.peak_usage_times, profile.preferred_features,
                profile.last_interaction, profile.engagement_score, profile.churn_risk_score,
                profile.retention_probability, profile.created_at, profile.updated_at
            )

    async def _update_behavior_profile_in_db(self, profile: UserBehaviorProfile):
        """Обновление профиля поведения в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE user_behavior_profiles SET
                    segments = $2, patterns = $3, preferences = $4, activity_level = $5,
                    peak_usage_times = $6, preferred_features = $7,
                    last_interaction = $8, engagement_score = $9, churn_risk_score = $10,
                    retention_probability = $11, updated_at = $12
                WHERE user_id = $1
                """,
                profile.user_id, [s.value for s in profile.segments],
                [p.value for p in profile.patterns], json.dumps(profile.preferences),
                profile.activity_level, profile.peak_usage_times, profile.preferred_features,
                profile.last_interaction, profile.engagement_score, profile.churn_risk_score,
                profile.retention_probability, profile.updated_at
            )

    async def _cache_behavior_profile(self, profile: UserBehaviorProfile):
        """Кэширование профиля поведения"""
        await redis_client.setex(f"user_behavior_profile:{profile.user_id}", 3600, profile.model_dump_json())

    async def _get_cached_behavior_profile(self, user_id: int) -> Optional[UserBehaviorProfile]:
        """Получение профиля поведения из кэша"""
        cached = await redis_client.get(f"user_behavior_profile:{user_id}")
        if cached:
            return UserBehaviorProfile(**json.loads(cached.decode()))
        return None

    async def get_user_behavior_profile(self, user_id: int) -> Optional[UserBehaviorProfile]:
        """Получение профиля поведения пользователя"""
        # Сначала проверяем кэш
        cached_profile = await self._get_cached_behavior_profile(user_id)
        if cached_profile:
            return cached_profile

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT user_id, segments, patterns, preferences, activity_level, peak_usage_times,
                       preferred_features, last_interaction, engagement_score, churn_risk_score,
                       retention_probability, created_at, updated_at
                FROM user_behavior_profiles WHERE user_id = $1
                """,
                user_id
            )

        if not row:
            return None

        profile = UserBehaviorProfile(
            user_id=row['user_id'],
            segments=[UserSegment(s) for s in row['segments']] if row['segments'] else [],
            patterns=[UserBehaviorPattern(p) for p in row['patterns']] if row['patterns'] else [],
            preferences=json.loads(row['preferences']) if row['preferences'] else {},
            activity_level=row['activity_level'],
            peak_usage_times=row['peak_usage_times'] or [],
            preferred_features=row['preferred_features'] or [],
            last_interaction=row['last_interaction'],
            engagement_score=row['engagement_score'] or 0.0,
            churn_risk_score=row['churn_risk_score'] or 0.0,
            retention_probability=row['retention_probability'] or 0.0,
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

        # Кэшируем профиль
        await self._cache_behavior_profile(profile)

        return profile

    async def analyze_user_behavior(self, user_id: int, 
                                  start_date: datetime, 
                                  end_date: datetime) -> Dict[str, Any]:
        """Анализ поведения пользователя за указанный период"""
        # Получаем активности пользователя за период
        activities = await self._get_user_activities_in_range(user_id, start_date, end_date)

        # Подсчитываем статистику активностей
        activity_stats = self._calculate_activity_statistics(activities)

        # Определяем паттерны поведения за период
        behavior_patterns = await self._detect_behavior_patterns_in_range(activities)

        # Рассчитываем оценки за период
        engagement_score = await self._calculate_period_engagement_score(activities)
        churn_risk_score = await self._calculate_period_churn_risk_score(activities)

        analysis = {
            'user_id': user_id,
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'activity_statistics': activity_stats,
            'behavior_patterns': behavior_patterns,
            'engagement_score': engagement_score,
            'churn_risk_score': churn_risk_score,
            'recommendations': await self._generate_behavior_recommendations(user_id, activity_stats),
            'timestamp': datetime.utcnow().isoformat()
        }

        return analysis

    async def _get_user_activities_in_range(self, user_id: int, 
                                          start_date: datetime, 
                                          end_date: datetime) -> List[UserActivity]:
        """Получение активностей пользователя в диапазоне дат"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, user_id, activity_type, timestamp, duration, metadata, session_id
                FROM user_activities
                WHERE user_id = $1 AND timestamp BETWEEN $2 AND $3
                ORDER BY timestamp DESC
                """,
                user_id, start_date, end_date
            )

        activities = []
        for row in rows:
            activity = UserActivity(
                id=row['id'],
                user_id=row['user_id'],
                activity_type=UserActivityType(row['activity_type']),
                timestamp=row['timestamp'],
                duration=row['duration'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                session_id=row['session_id']
            )
            activities.append(activity)

        return activities

    def _calculate_activity_statistics(self, activities: List[UserActivity]) -> Dict[str, Any]:
        """Расчет статистики активностей"""
        stats = {
            'total_activities': len(activities),
            'activity_types': {},
            'time_distribution': {
                'morning': 0,
                'afternoon': 0,
                'evening': 0,
                'night': 0
            },
            'day_of_week_distribution': [0] * 7,  # Понедельник-Воскресенье
            'average_session_duration': 0.0,
            'peak_activity_hours': []
        }

        # Подсчитываем типы активностей
        for activity in activities:
            activity_type = activity.activity_type.value
            stats['activity_types'][activity_type] = stats['activity_types'].get(activity_type, 0) + 1

            # Распределяем по времени суток
            hour = activity.timestamp.hour
            time_slot = self._get_time_slot(hour)
            stats['time_distribution'][time_slot] += 1

            # Распределяем по дням недели
            weekday = activity.timestamp.weekday()
            stats['day_of_week_distribution'][weekday] += 1

        # Рассчитываем среднюю продолжительность сессии
        durations = [a.duration for a in activities if a.duration]
        if durations:
            stats['average_session_duration'] = sum(durations) / len(durations)

        # Определяем часы пиковой активности
        hour_activity = {}
        for activity in activities:
            hour = activity.timestamp.hour
            hour_activity[hour] = hour_activity.get(hour, 0) + 1

        # Сортируем по активности
        sorted_hours = sorted(hour_activity.items(), key=lambda x: x[1], reverse=True)
        stats['peak_activity_hours'] = [hour for hour, count in sorted_hours[:5]]

        return stats

    async def _detect_behavior_patterns_in_range(self, activities: List[UserActivity]) -> List[UserBehaviorPattern]:
        """Определение паттернов поведения в диапазоне"""
        patterns = []

        # Подсчитываем активности по типам
        activity_counts = {}
        for activity in activities:
            activity_type = activity.activity_type.value
            activity_counts[activity_type] = activity_counts.get(activity_type, 0) + 1

        # Определяем паттерны на основе активностей
        if activity_counts.get('message_sent', 0) > 50:
            patterns.append(UserBehaviorPattern.ACTIVE_CHATTER)
        if activity_counts.get('file_uploaded', 0) > 10:
            patterns.append(UserBehaviorPattern.FILE_SHARER)
        if activity_counts.get('task_created', 0) > 5:
            patterns.append(UserBehaviorPattern.TASK_ORGANIZER)
        if activity_counts.get('game_started', 0) > 10:
            patterns.append(UserBehaviorPattern.GAMER)
        if activity_counts.get('call_initiated', 0) > 5:
            patterns.append(UserBehaviorPattern.CALLER)

        # Определяем временные паттерны
        time_usage = {
            'morning': 0,
            'afternoon': 0,
            'evening': 0,
            'night': 0
        }

        for activity in activities:
            hour = activity.timestamp.hour
            time_slot = self._get_time_slot(hour)
            time_usage[time_slot] += 1

        max_time_slot = max(time_usage, key=time_usage.get)
        usage_percentage = time_usage[max_time_slot] / len(activities) if activities else 0

        if max_time_slot == 'night' and usage_percentage > 0.4:
            patterns.append(UserBehaviorPattern.NIGHT_OWL)
        elif max_time_slot == 'morning' and usage_percentage > 0.4:
            patterns.append(UserBehaviorPattern.MORNING_PERSON)

        return patterns

    async def _calculate_period_engagement_score(self, activities: List[UserActivity]) -> float:
        """Расчет оценки вовлеченности за период"""
        if not activities:
            return 0.0

        # Рассчитываем взвешенную активность
        total_weight = 0
        for activity in activities:
            weight = self.activity_weights.get(activity.activity_type, 0.1)
            total_weight += weight

        # Нормализуем к 0-1 диапазону
        avg_daily_weight = total_weight / len(activities)
        engagement_score = min(avg_daily_weight / 2.0, 1.0)  # Предполагаем, что 2.0 - это высокий уровень

        return engagement_score

    async def _calculate_period_churn_risk_score(self, activities: List[UserActivity]) -> float:
        """Расчет оценки риска оттока за период"""
        if not activities:
            return 1.0  # Высокий риск, если нет активности

        # Получаем последнюю активность
        last_activity = max(activities, key=lambda a: a.timestamp)
        days_since_last = (datetime.utcnow() - last_activity.timestamp).days

        # Рассчитываем риск на основе отсутствия активности
        if days_since_last > 30:
            return 0.8
        elif days_since_last > 14:
            return 0.5
        elif days_since_last > 7:
            return 0.3
        else:
            return 0.1

    async def _generate_behavior_recommendations(self, user_id: int, 
                                               activity_stats: Dict[str, Any]) -> List[Dict[str, str]]:
        """Генерация рекомендаций на основе поведения"""
        recommendations = []

        # Рекомендации для пользователей с низкой активностью
        if activity_stats['total_activities'] < 10:
            recommendations.append({
                'type': 'engagement',
                'message': 'We noticed you\'re not very active. Try exploring our new features!',
                'action': 'show_feature_discovery_tour'
            })

        # Рекомендации для пользователей, которые часто отправляют сообщения
        if activity_stats['activity_types'].get('message_sent', 0) > 30:
            recommendations.append({
                'type': 'productivity',
                'message': 'You\'re an active chatter! Try our advanced chat shortcuts.',
                'action': 'show_advanced_chat_features'
            })

        # Рекомендации для пользователей, которые часто делятся файлами
        if activity_stats['activity_types'].get('file_uploaded', 0) > 5:
            recommendations.append({
                'type': 'productivity',
                'message': 'You share a lot of files! Try our file organization tools.',
                'action': 'show_file_organization_features'
            })

        # Рекомендации для пользователей, которые часто создают задачи
        if activity_stats['activity_types'].get('task_created', 0) > 3:
            recommendations.append({
                'type': 'productivity',
                'message': 'You create many tasks! Try our project templates.',
                'action': 'show_project_templates'
            })

        # Рекомендации для пользователей, которые часто играют
        if activity_stats['activity_types'].get('game_started', 0) > 5:
            recommendations.append({
                'type': 'entertainment',
                'message': 'You play games often! Try our new multiplayer games.',
                'action': 'show_multiplayer_games'
            })

        return recommendations

    async def get_user_segmentation_analysis(self, start_date: datetime, 
                                          end_date: datetime) -> Dict[str, Any]:
        """Получение анализа сегментации пользователей"""
        # Получаем активности всех пользователей за период
        all_activities = await self._get_all_activities_in_range(start_date, end_date)

        # Группируем активности по пользователям
        user_activities = {}
        for activity in all_activities:
            user_id = activity.user_id
            if user_id not in user_activities:
                user_activities[user_id] = []
            user_activities[user_id].append(activity)

        # Создаем профили для каждого пользователя
        user_profiles = []
        for user_id, activities in user_activities.items():
            profile = await self._create_profile_from_activities(user_id, activities)
            user_profiles.append(profile)

        # Кластеризуем пользователей
        clusters = await self._cluster_users(user_profiles)

        # Рассчитываем статистику по сегментам
        segment_stats = self._calculate_segment_statistics(user_profiles)

        analysis = {
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'total_users': len(user_profiles),
            'segment_distribution': segment_stats,
            'clusters': clusters,
            'behavioral_insights': await self._generate_segment_insights(segment_stats),
            'timestamp': datetime.utcnow().isoformat()
        }

        return analysis

    async def _get_all_activities_in_range(self, start_date: datetime, 
                                         end_date: datetime) -> List[UserActivity]:
        """Получение активностей всех пользователей в диапазоне"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, user_id, activity_type, timestamp, duration, metadata, session_id
                FROM user_activities
                WHERE timestamp BETWEEN $1 AND $2
                ORDER BY timestamp DESC
                """,
                start_date, end_date
            )

        activities = []
        for row in rows:
            activity = UserActivity(
                id=row['id'],
                user_id=row['user_id'],
                activity_type=UserActivityType(row['activity_type']),
                timestamp=row['timestamp'],
                duration=row['duration'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                session_id=row['session_id']
            )
            activities.append(activity)

        return activities

    async def _create_profile_from_activities(self, user_id: int, 
                                           activities: List[UserActivity]) -> UserBehaviorProfile:
        """Создание профиля поведения из активностей"""
        # Подсчитываем статистику активностей
        activity_counts = {}
        for activity in activities:
            activity_type = activity.activity_type.value
            activity_counts[activity_type] = activity_counts.get(activity_type, 0) + 1

        # Определяем паттерны
        patterns = []
        if activity_counts.get('message_sent', 0) > 50:
            patterns.append(UserBehaviorPattern.ACTIVE_CHATTER)
        if activity_counts.get('file_uploaded', 0) > 10:
            patterns.append(UserBehaviorPattern.FILE_SHARER)
        if activity_counts.get('task_created', 0) > 5:
            patterns.append(UserBehaviorPattern.TASK_ORGANIZER)
        if activity_counts.get('game_started', 0) > 10:
            patterns.append(UserBehaviorPattern.GAMER)

        # Рассчитываем оценки
        engagement_score = await self._calculate_period_engagement_score(activities)
        churn_risk_score = await self._calculate_period_churn_risk_score(activities)

        # Определяем сегменты
        segments = []
        if engagement_score >= 0.7:
            segments.append(UserSegment.POWER_USER)
        elif engagement_score >= 0.5:
            segments.append(UserSegment.ACTIVE_USER)
        else:
            segments.append(UserSegment.INFREQUENT_USER)

        if churn_risk_score >= 0.7:
            segments.append(UserSegment.CHURN_RISK)

        # Определяем пики использования
        peak_usage_times = await self._analyze_time_usage_patterns(activities)

        profile = UserBehaviorProfile(
            user_id=user_id,
            segments=segments,
            patterns=patterns,
            preferences={},
            activity_level="high" if engagement_score >= 0.7 else "medium" if engagement_score >= 0.4 else "low",
            peak_usage_times=peak_usage_times,
            preferred_features=[],
            last_interaction=max(a.timestamp for a in activities) if activities else None,
            engagement_score=engagement_score,
            churn_risk_score=churn_risk_score,
            retention_probability=1.0 - churn_risk_score,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        return profile

    async def _cluster_users(self, user_profiles: List[UserBehaviorProfile]) -> List[Dict[str, Any]]:
        """Кластеризация пользователей по поведению"""
        if len(user_profiles) < 2:
            return []

        # Подготавливаем данные для кластеризации
        features = []
        user_ids = []
        for profile in user_profiles:
            features.append([
                profile.engagement_score,
                profile.churn_risk_score,
                profile.retention_probability,
                len(profile.patterns),
                len(profile.preferred_features)
            ])
            user_ids.append(profile.user_id)

        # Преобразуем в numpy массив
        feature_matrix = np.array(features)

        # Нормализуем данные
        scaler = StandardScaler()
        normalized_features = scaler.fit_transform(feature_matrix)

        # Применяем K-means кластеризацию
        n_clusters = min(len(user_profiles), 5)  # Не более 5 кластеров
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        cluster_labels = kmeans.fit_predict(normalized_features)

        # Формируем результаты кластеризации
        clusters = []
        for i in range(n_clusters):
            cluster_users = [user_ids[j] for j, label in enumerate(cluster_labels) if label == i]
            cluster_features = normalized_features[cluster_labels == i]
            
            cluster_info = {
                'cluster_id': i,
                'user_count': len(cluster_users),
                'users': cluster_users,
                'centroid': kmeans.cluster_centers_[i].tolist(),
                'characteristics': self._describe_cluster_characteristics(cluster_features)
            }
            clusters.append(cluster_info)

        return clusters

    def _describe_cluster_characteristics(self, cluster_features: np.ndarray) -> Dict[str, float]:
        """Описание характеристик кластера"""
        if cluster_features.size == 0:
            return {}

        avg_engagement = np.mean(cluster_features[:, 0])
        avg_churn_risk = np.mean(cluster_features[:, 1])
        avg_retention = np.mean(cluster_features[:, 2])
        avg_patterns = np.mean(cluster_features[:, 3])
        avg_features = np.mean(cluster_features[:, 4])

        return {
            'avg_engagement_score': float(avg_engagement),
            'avg_churn_risk_score': float(avg_churn_risk),
            'avg_retention_probability': float(avg_retention),
            'avg_behavior_patterns_count': float(avg_patterns),
            'avg_preferred_features_count': float(avg_features)
        }

    def _calculate_segment_statistics(self, user_profiles: List[UserBehaviorProfile]) -> Dict[str, Dict[str, int]]:
        """Расчет статистики по сегментам"""
        segment_stats = {}
        for profile in user_profiles:
            for segment in profile.segments:
                segment_name = segment.value
                if segment_name not in segment_stats:
                    segment_stats[segment_name] = {
                        'count': 0,
                        'total_users': len(user_profiles)
                    }
                segment_stats[segment_name]['count'] += 1

        return segment_stats

    async def _generate_segment_insights(self, segment_stats: Dict[str, Dict[str, int]]) -> List[Dict[str, Any]]:
        """Генерация инсайтов по сегментам"""
        insights = []

        for segment_name, stats in segment_stats.items():
            percentage = (stats['count'] / stats['total_users']) * 100
            insights.append({
                'segment': segment_name,
                'user_count': stats['count'],
                'percentage': round(percentage, 2),
                'characteristics': await self._get_segment_characteristics(segment_name),
                'recommendations': await self._get_segment_recommendations(segment_name)
            })

        return insights

    async def _get_segment_characteristics(self, segment_name: str) -> Dict[str, str]:
        """Получение характеристик сегмента"""
        characteristics = {
            'new_user': {
                'description': 'Recently joined users',
                'behavior': 'Exploring features, learning interface',
                'needs': 'Onboarding, tutorials, guidance'
            },
            'active_user': {
                'description': 'Regularly active users',
                'behavior': 'Consistent engagement with core features',
                'needs': 'Productivity tools, advanced features'
            },
            'passive_user': {
                'description': 'Low activity users',
                'behavior': 'Occasional usage, mostly reading',
                'needs': 'Engagement incentives, simplified interface'
            },
            'power_user': {
                'description': 'Highly engaged users',
                'behavior': 'Extensive use of all features',
                'needs': 'Advanced customization, integrations'
            },
            'churn_risk': {
                'description': 'Users at risk of leaving',
                'behavior': 'Decreased activity, potential issues',
                'needs': 'Retention campaigns, support outreach'
            },
            'engaged_user': {
                'description': 'Moderately engaged users',
                'behavior': 'Regular usage of selected features',
                'needs': 'Feature discovery, engagement programs'
            },
            'infrequent_user': {
                'description': 'Rarely active users',
                'behavior': 'Minimal usage, occasional visits',
                'needs': 'Re-engagement campaigns, value proposition'
            }
        }

        return characteristics.get(segment_name, {
            'description': 'Unknown segment',
            'behavior': 'Undefined behavior pattern',
            'needs': 'General improvements'
        })

    async def _get_segment_recommendations(self, segment_name: str) -> List[str]:
        """Получение рекомендаций для сегмента"""
        recommendations = {
            'new_user': [
                'Provide comprehensive onboarding experience',
                'Show feature highlights and tutorials',
                'Implement welcome campaign with incentives'
            ],
            'active_user': [
                'Introduce advanced productivity features',
                'Offer customization options',
                'Provide power user tools'
            ],
            'passive_user': [
                'Simplify interface and navigation',
                'Send personalized engagement notifications',
                'Highlight relevant content'
            ],
            'power_user': [
                'Offer premium features and integrations',
                'Provide customization and automation tools',
                'Create exclusive community features'
            ],
            'churn_risk': [
                'Implement re-engagement campaigns',
                'Offer special promotions or features',
                'Reach out with personalized support'
            ],
            'engaged_user': [
                'Introduce new features gradually',
                'Provide feature discovery mechanisms',
                'Encourage deeper usage of existing features'
            ],
            'infrequent_user': [
                'Send reactivation notifications',
                'Highlight value proposition',
                'Offer simplified experience'
            ]
        }

        return recommendations.get(segment_name, [
            'General UX improvements',
            'Performance optimizations',
            'Bug fixes and stability improvements'
        ])

    async def _cache_user_activity(self, activity: UserActivity):
        """Кэширование активности пользователя"""
        activity_data = {
            'type': activity.activity_type.value,
            'timestamp': activity.timestamp.isoformat(),
            'duration': activity.duration,
            'metadata': activity.metadata
        }
        
        # Добавляем в список последних активностей
        await redis_client.lpush(f"user_recent_activities:{activity.user_id}", json.dumps(activity_data))
        await redis_client.ltrim(f"user_recent_activities:{activity.user_id}", 0, 99)  # Храним последние 100 активностей

    async def _increment_activity_counters(self, user_id: int, activity_type: UserActivityType):
        """Увеличение счетчиков активностей в Redis"""
        # Увеличиваем общий счетчик
        await redis_client.incr(f"user_activities:{user_id}:total")
        
        # Увеличиваем счетчик по типу активности
        await redis_client.incr(f"user_activities:{user_id}:{activity_type.value}")
        
        # Увеличиваем дневной счетчик
        today = datetime.utcnow().strftime("%Y%m%d")
        await redis_client.incr(f"user_activities:{user_id}:daily:{today}")

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

    async def _increment_views(self, content_id: str):
        """Увеличение счетчика просмотров"""
        await redis_client.incr(f"content_views:{content_id}")
        
        # Обновляем в базе данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE content SET views = views + 1 WHERE id = $1",
                content_id
            )

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
behavior_analysis_service = UserBehaviorAnalysisService()
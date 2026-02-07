# User Engagement and Interaction Enhancement System
# File: services/engagement_service/user_engagement.py

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

class EngagementType(Enum):
    MESSAGE_INTERACTION = "message_interaction"
    FILE_SHARING = "file_sharing"
    TASK_COMPLETION = "task_completion"
    POLL_PARTICIPATION = "poll_participation"
    CALL_PARTICIPATION = "call_participation"
    GAME_PLAYING = "game_playing"
    CONTENT_LIKING = "content_liking"
    CONTENT_SHARING = "content_sharing"
    PROFILE_CUSTOMIZATION = "profile_customization"
    FEATURE_EXPLORATION = "feature_exploration"

class EngagementLevel(Enum):
    NEW_USER = "new_user"
    CASUAL_USER = "casual_user"
    REGULAR_USER = "regular_user"
    ACTIVE_USER = "active_user"
    SUPER_USER = "super_user"

class NotificationPreference(BaseModel):
    user_id: int
    notification_type: str  # 'message', 'mention', 'reaction', etc.
    channels: List[str]  # ['push', 'email', 'in_app']
    enabled: bool = True
    priority: str = "medium"  # 'low', 'medium', 'high'
    mute_until: Optional[datetime] = None

class UserEngagementProfile(BaseModel):
    user_id: int
    engagement_level: EngagementLevel
    total_interactions: int = 0
    weekly_interactions: int = 0
    monthly_interactions: int = 0
    last_interaction: Optional[datetime] = None
    streak_days: int = 0  # Последовательные дни активности
    preferred_features: List[str] = []
    peak_usage_times: List[str] = []  # ['morning', 'afternoon', 'evening', 'night']
    engagement_score: float = 0.0  # 0.0 - 1.0
    retention_probability: float = 0.0  # 0.0 - 1.0
    churn_risk: float = 0.0  # 0.0 - 1.0
    created_at: datetime = None
    updated_at: datetime = None

class UserAchievement(BaseModel):
    id: str
    user_id: int
    achievement_type: str  # 'first_message', 'hundred_messages', 'first_call', etc.
    name: str
    description: str
    points: int
    unlocked_at: datetime = None
    metadata: Optional[Dict] = None

class EngagementRecommendation(BaseModel):
    id: str
    user_id: int
    type: str  # 'feature_suggestion', 'content_recommendation', 'connection_suggestion'
    title: str
    description: str
    action_url: str
    priority: str  # 'low', 'medium', 'high'
    created_at: datetime = None

class UserEngagementService:
    def __init__(self):
        self.engagement_thresholds = {
            'daily_interactions': 5,   # Количество взаимодействий в день для активного пользователя
            'weekly_interactions': 35, # Количество взаимодействий в неделю
            'monthly_interactions': 150, # Количество взаимодействий в месяц
            'streak_days': 7,          # Количество дней подряд для активного пользователя
            'feature_diversity': 5     # Количество разных функций для активного пользователя
        }
        
        self.achievement_definitions = {
            'first_message': {
                'name': 'First Steps',
                'description': 'Send your first message',
                'points': 10,
                'condition': lambda profile: profile.total_interactions >= 1
            },
            'hundred_messages': {
                'name': 'Chatterbox',
                'description': 'Send 100 messages',
                'points': 50,
                'condition': lambda profile: profile.total_interactions >= 100
            },
            'first_call': {
                'name': 'Voice Pioneer',
                'description': 'Make your first voice call',
                'points': 30,
                'condition': lambda profile: 'call_initiation' in profile.preferred_features
            },
            'first_file_share': {
                'name': 'File Sharer',
                'description': 'Share your first file',
                'points': 20,
                'condition': lambda profile: 'file_sharing' in profile.preferred_features
            },
            'week_streak': {
                'name': 'Consistent User',
                'description': 'Be active for 7 consecutive days',
                'points': 100,
                'condition': lambda profile: profile.streak_days >= 7
            },
            'feature_explorer': {
                'name': 'Feature Explorer',
                'description': 'Try 10 different features',
                'points': 75,
                'condition': lambda profile: len(profile.preferred_features) >= 10
            }
        }

    async def track_user_interaction(self, user_id: int, interaction_type: EngagementType,
                                   target_id: Optional[str] = None,
                                   metadata: Optional[Dict] = None) -> bool:
        """Отслеживание взаимодействия пользователя"""
        try:
            # Обновляем профиль вовлеченности пользователя
            await self._update_user_engagement_profile(user_id, interaction_type, metadata)

            # Проверяем, достиг ли пользователь новых достижений
            await self._check_achievements(user_id)

            # Записываем взаимодействие в базу данных
            interaction_id = str(uuid.uuid4())
            timestamp = datetime.utcnow()

            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO user_interactions (
                        id, user_id, interaction_type, target_id, metadata, timestamp
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    interaction_id, user_id, interaction_type.value,
                    target_id, json.dumps(metadata) if metadata else None, timestamp
                )

            # Обновляем кэш
            await self._cache_user_interaction(user_id, interaction_type, timestamp)

            # Увеличиваем счетчики в Redis
            await self._increment_interaction_counters(user_id, interaction_type)

            # Создаем запись активности
            await self._log_activity(user_id, "user_interaction", {
                "interaction_type": interaction_type.value,
                "target_id": target_id
            })

            return True
        except Exception as e:
            logger.error(f"Error tracking user interaction: {e}")
            return False

    async def _update_user_engagement_profile(self, user_id: int, 
                                            interaction_type: EngagementType,
                                            metadata: Optional[Dict] = None):
        """Обновление профиля вовлеченности пользователя"""
        profile = await self.get_user_engagement_profile(user_id)
        if not profile:
            profile = await self._create_default_engagement_profile(user_id)

        # Обновляем общее количество взаимодействий
        profile.total_interactions += 1
        profile.updated_at = datetime.utcnow()

        # Обновляем количество взаимодействий за неделю и месяц
        profile.weekly_interactions = await self._get_weekly_interactions_count(user_id)
        profile.monthly_interactions = await self._get_monthly_interactions_count(user_id)

        # Обновляем время последнего взаимодействия
        profile.last_interaction = datetime.utcnow()

        # Обновляем серию дней активности
        profile.streak_days = await self._update_streak_days(user_id)

        # Обновляем предпочтительные функции
        feature_name = self._get_feature_name_from_interaction(interaction_type)
        if feature_name and feature_name not in profile.preferred_features:
            profile.preferred_features.append(feature_name)

        # Обновляем пики использования
        current_hour = datetime.utcnow().hour
        time_slot = self._get_time_slot(current_hour)
        if time_slot not in profile.peak_usage_times:
            profile.peak_usage_times.append(time_slot)

        # Пересчитываем уровень вовлеченности
        profile.engagement_level = await self._calculate_engagement_level(profile)

        # Пересчитываем оценку вовлеченности
        profile.engagement_score = await self._calculate_engagement_score(profile)

        # Пересчитываем вероятность удержания и риск оттока
        profile.retention_probability = await self._calculate_retention_probability(profile)
        profile.churn_risk = await self._calculate_churn_risk(profile)

        # Сохраняем обновленный профиль
        await self._save_engagement_profile(profile)

        # Обновляем кэш
        await self._cache_engagement_profile(profile)

    async def _create_default_engagement_profile(self, user_id: int) -> UserEngagementProfile:
        """Создание профиля вовлеченности по умолчанию для нового пользователя"""
        profile = UserEngagementProfile(
            user_id=user_id,
            engagement_level=EngagementLevel.NEW_USER,
            total_interactions=0,
            weekly_interactions=0,
            monthly_interactions=0,
            streak_days=0,
            preferred_features=[],
            peak_usage_times=[],
            engagement_score=0.0,
            retention_probability=0.8,  # Новый пользователь имеет высокую вероятность удержания
            churn_risk=0.2,  # Низкий риск оттока для нового пользователя
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем профиль
        await self._save_engagement_profile(profile)

        # Кэшируем профиль
        await self._cache_engagement_profile(profile)

        return profile

    async def get_user_engagement_profile(self, user_id: int) -> Optional[UserEngagementProfile]:
        """Получение профиля вовлеченности пользователя"""
        # Сначала проверяем кэш
        cached_profile = await self._get_cached_engagement_profile(user_id)
        if cached_profile:
            return cached_profile

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT user_id, engagement_level, total_interactions, weekly_interactions,
                       monthly_interactions, last_interaction, streak_days, preferred_features,
                       peak_usage_times, engagement_score, retention_probability, churn_risk,
                       created_at, updated_at
                FROM user_engagement_profiles WHERE user_id = $1
                """,
                user_id
            )

        if not row:
            return None

        profile = UserEngagementProfile(
            user_id=row['user_id'],
            engagement_level=EngagementLevel(row['engagement_level']),
            total_interactions=row['total_interactions'],
            weekly_interactions=row['weekly_interactions'],
            monthly_interactions=row['monthly_interactions'],
            last_interaction=row['last_interaction'],
            streak_days=row['streak_days'],
            preferred_features=row['preferred_features'] or [],
            peak_usage_times=row['peak_usage_times'] or [],
            engagement_score=row['engagement_score'] or 0.0,
            retention_probability=row['retention_probability'] or 0.0,
            churn_risk=row['churn_risk'] or 0.0,
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

        # Кэшируем профиль
        await self._cache_engagement_profile(profile)

        return profile

    def _get_feature_name_from_interaction(self, interaction_type: EngagementType) -> Optional[str]:
        """Получение названия функции из типа взаимодействия"""
        mapping = {
            EngagementType.MESSAGE_INTERACTION: 'messaging',
            EngagementType.FILE_SHARING: 'file_sharing',
            EngagementType.TASK_COMPLETION: 'task_management',
            EngagementType.POLL_PARTICIPATION: 'polls',
            EngagementType.CALL_PARTICIPATION: 'calling',
            EngagementType.GAME_PLAYING: 'gaming',
            EngagementType.CONTENT_LIKING: 'content_interaction',
            EngagementType.CONTENT_SHARING: 'content_sharing',
            EngagementType.PROFILE_CUSTOMIZATION: 'profile_customization',
            EngagementType.FEATURE_EXPLORATION: 'feature_exploration'
        }
        return mapping.get(interaction_type)

    def _get_time_slot(self, hour: int) -> str:
        """Определение временного слота по часу"""
        if 5 <= hour < 12:
            return 'morning'
        elif 12 <= hour < 17:
            return 'afternoon'
        elif 17 <= hour < 22:
            return 'evening'
        else:
            return 'night'

    async def _calculate_engagement_level(self, profile: UserEngagementProfile) -> EngagementLevel:
        """Расчет уровня вовлеченности пользователя"""
        # Определяем уровень на основе различных метрик
        daily_interactions = profile.total_interactions / max(1, (datetime.utcnow() - profile.created_at).days)
        
        if profile.streak_days >= 30 and daily_interactions >= 10 and len(profile.preferred_features) >= 8:
            return EngagementLevel.SUPER_USER
        elif profile.streak_days >= 14 and daily_interactions >= 7 and len(profile.preferred_features) >= 6:
            return EngagementLevel.ACTIVE_USER
        elif profile.streak_days >= 7 and daily_interactions >= 3 and len(profile.preferred_features) >= 3:
            return EngagementLevel.REGULAR_USER
        elif profile.total_interactions >= 10:
            return EngagementLevel.CASUAL_USER
        else:
            return EngagementLevel.NEW_USER

    async def _calculate_engagement_score(self, profile: UserEngagementProfile) -> float:
        """Расчет оценки вовлеченности пользователя"""
        score = 0.0

        # Базовая оценка за количество взаимодействий
        score += min(profile.total_interactions / 1000, 0.3)  # Максимум 0.3 за взаимодействия

        # За серию активности
        score += min(profile.streak_days / 100, 0.2)  # Максимум 0.2 за серию

        # За разнообразие функций
        score += min(len(profile.preferred_features) / 20, 0.2)  # Максимум 0.2 за функции

        # За частоту использования
        if profile.last_interaction:
            days_since_last = (datetime.utcnow() - profile.last_interaction).days
            if days_since_last <= 1:
                score += 0.2
            elif days_since_last <= 3:
                score += 0.1
            elif days_since_last <= 7:
                score += 0.05

        # Ограничиваем максимальное значение
        return min(score, 1.0)

    async def _calculate_retention_probability(self, profile: UserEngagementProfile) -> float:
        """Расчет вероятности удержания пользователя"""
        base_probability = 0.7  # Базовая вероятность

        # Увеличиваем за активность
        if profile.engagement_level in [EngagementLevel.ACTIVE_USER, EngagementLevel.SUPER_USER]:
            base_probability += 0.2
        elif profile.engagement_level == EngagementLevel.REGULAR_USER:
            base_probability += 0.1

        # Увеличиваем за серию активности
        base_probability += min(profile.streak_days * 0.005, 0.15)  # Максимум +0.15 за серию

        # Уменьшаем за отсутствие активности
        if profile.last_interaction:
            days_since_last = (datetime.utcnow() - profile.last_interaction).days
            if days_since_last > 30:
                base_probability -= 0.3
            elif days_since_last > 14:
                base_probability -= 0.2
            elif days_since_last > 7:
                base_probability -= 0.1

        return max(0.0, min(1.0, base_probability))

    async def _calculate_churn_risk(self, profile: UserEngagementProfile) -> float:
        """Расчет риска оттока пользователя"""
        risk = 0.3  # Базовый риск

        # Уменьшаем за высокую вовлеченность
        if profile.engagement_level in [EngagementLevel.ACTIVE_USER, EngagementLevel.SUPER_USER]:
            risk -= 0.2
        elif profile.engagement_level == EngagementLevel.REGULAR_USER:
            risk -= 0.1

        # Уменьшаем за серию активности
        risk -= min(profile.streak_days * 0.005, 0.15)  # Максимум -0.15 за серию

        # Увеличиваем за отсутствие активности
        if profile.last_interaction:
            days_since_last = (datetime.utcnow() - profile.last_interaction).days
            if days_since_last > 30:
                risk += 0.4
            elif days_since_last > 14:
                risk += 0.25
            elif days_since_last > 7:
                risk += 0.15

        return max(0.0, min(1.0, risk))

    async def _get_weekly_interactions_count(self, user_id: int) -> int:
        """Получение количества взаимодействий за неделю"""
        week_ago = datetime.utcnow() - timedelta(weeks=1)
        
        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM user_interactions
                WHERE user_id = $1 AND timestamp >= $2
                """,
                user_id, week_ago
            )

        return count or 0

    async def _get_monthly_interactions_count(self, user_id: int) -> int:
        """Получение количества взаимодействий за месяц"""
        month_ago = datetime.utcnow() - timedelta(days=30)
        
        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM user_interactions
                WHERE user_id = $1 AND timestamp >= $2
                """,
                user_id, month_ago
            )

        return count or 0

    async def _update_streak_days(self, user_id: int) -> int:
        """Обновление серии дней активности"""
        # Получаем даты взаимодействий пользователя
        async with db_pool.acquire() as conn:
            interaction_dates = await conn.fetch(
                """
                SELECT DISTINCT DATE(timestamp) as interaction_date
                FROM user_interactions
                WHERE user_id = $1 AND timestamp >= $2
                ORDER BY interaction_date DESC
                """,
                user_id, datetime.utcnow() - timedelta(days=365)  # За последний год
            )

        dates = [row['interaction_date'] for row in interaction_dates]
        
        if not dates:
            return 0

        # Подсчитываем последовательные дни
        streak = 1
        current_date = datetime.utcnow().date()
        
        for i in range(len(dates) - 1):
            if dates[i] - dates[i + 1] == timedelta(days=1):
                streak += 1
            elif dates[i] - dates[i + 1] > timedelta(days=1):
                break  # Прерываем серию, если был перерыв
        
        return streak

    async def _save_engagement_profile(self, profile: UserEngagementProfile):
        """Сохранение профиля вовлеченности в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_engagement_profiles (
                    user_id, engagement_level, total_interactions, weekly_interactions,
                    monthly_interactions, last_interaction, streak_days, preferred_features,
                    peak_usage_times, engagement_score, retention_probability, churn_risk,
                    created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                ON CONFLICT (user_id) DO UPDATE SET
                    engagement_level = $2, total_interactions = $3, weekly_interactions = $4,
                    monthly_interactions = $5, last_interaction = $6, streak_days = $7,
                    preferred_features = $8, peak_usage_times = $9, engagement_score = $10,
                    retention_probability = $11, churn_risk = $12, updated_at = $14
                """,
                profile.user_id, profile.engagement_level.value, profile.total_interactions,
                profile.weekly_interactions, profile.monthly_interactions, profile.last_interaction,
                profile.streak_days, profile.preferred_features, profile.peak_usage_times,
                profile.engagement_score, profile.retention_probability, profile.churn_risk,
                profile.created_at, profile.updated_at
            )

    async def _cache_engagement_profile(self, profile: UserEngagementProfile):
        """Кэширование профиля вовлеченности"""
        await redis_client.setex(
            f"engagement_profile:{profile.user_id}",
            3600,  # 1 час
            profile.model_dump_json()
        )

    async def _get_cached_engagement_profile(self, user_id: int) -> Optional[UserEngagementProfile]:
        """Получение профиля вовлеченности из кэша"""
        cached = await redis_client.get(f"engagement_profile:{user_id}")
        if cached:
            return UserEngagementProfile(**json.loads(cached.decode()))
        return None

    async def _check_achievements(self, user_id: int):
        """Проверка достижений пользователя"""
        profile = await self.get_user_engagement_profile(user_id)
        if not profile:
            return

        # Получаем уже разблокированные достижения
        unlocked_achievements = await self._get_unlocked_achievements(user_id)

        for achievement_type, definition in self.achievement_definitions.items():
            if achievement_type not in unlocked_achievements:
                if definition['condition'](profile):
                    await self._unlock_achievement(user_id, achievement_type, definition)

    async def _get_unlocked_achievements(self, user_id: int) -> List[str]:
        """Получение уже разблокированных достижений пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT achievement_type FROM user_achievements WHERE user_id = $1",
                user_id
            )

        return [row['achievement_type'] for row in rows]

    async def _unlock_achievement(self, user_id: int, achievement_type: str, 
                                definition: Dict[str, Any]):
        """Разблокировка достижения для пользователя"""
        achievement_id = str(uuid.uuid4())

        achievement = UserAchievement(
            id=achievement_id,
            user_id=user_id,
            achievement_type=achievement_type,
            name=definition['name'],
            description=definition['description'],
            points=definition['points'],
            unlocked_at=datetime.utcnow()
        )

        # Сохраняем достижение в базу данных
        await self._save_achievement(achievement)

        # Уведомляем пользователя о новом достижении
        await self._notify_achievement_unlocked(user_id, achievement)

        # Обновляем профиль вовлеченности
        profile = await self.get_user_engagement_profile(user_id)
        if profile:
            profile.engagement_score += achievement.points / 1000  # Добавляем очки к оценке вовлеченности
            await self._save_engagement_profile(profile)
            await self._cache_engagement_profile(profile)

    async def _save_achievement(self, achievement: UserAchievement):
        """Сохранение достижения в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_achievements (
                    id, user_id, achievement_type, name, description, points, unlocked_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                achievement.id, achievement.user_id, achievement.achievement_type,
                achievement.name, achievement.description, achievement.points,
                achievement.unlocked_at
            )

    async def _notify_achievement_unlocked(self, user_id: int, achievement: UserAchievement):
        """Уведомление пользователя о новом достижении"""
        notification = {
            'type': 'achievement_unlocked',
            'achievement': {
                'id': achievement.id,
                'name': achievement.name,
                'description': achievement.description,
                'points': achievement.points
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        await redis_client.publish(f"user:{user_id}:notifications", json.dumps(notification))

    async def get_engagement_recommendations(self, user_id: int) -> List[EngagementRecommendation]:
        """Получение рекомендаций для повышения вовлеченности"""
        profile = await self.get_user_engagement_profile(user_id)
        if not profile:
            return []

        recommendations = []

        # Рекомендации на основе уровня вовлеченности
        if profile.engagement_level == EngagementLevel.NEW_USER:
            recommendations.extend([
                EngagementRecommendation(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    type="feature_suggestion",
                    title="Try our messaging feature",
                    description="Start a conversation with friends or colleagues",
                    action_url="/chats/new",
                    priority="high",
                    created_at=datetime.utcnow()
                ),
                EngagementRecommendation(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    type="feature_suggestion",
                    title="Customize your profile",
                    description="Add a photo and bio to personalize your account",
                    action_url="/profile/edit",
                    priority="medium",
                    created_at=datetime.utcnow()
                )
            ])
        elif profile.engagement_level == EngagementLevel.CASUAL_USER:
            recommendations.extend([
                EngagementRecommendation(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    type="feature_suggestion",
                    title="Join a group chat",
                    description="Connect with others who share your interests",
                    action_url="/groups/explore",
                    priority="medium",
                    created_at=datetime.utcnow()
                ),
                EngagementRecommendation(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    type="feature_suggestion",
                    title="Try voice calls",
                    description="Connect with friends through voice calls",
                    action_url="/calls/new",
                    priority="medium",
                    created_at=datetime.utcnow()
                )
            ])
        elif profile.engagement_level == EngagementLevel.REGULAR_USER:
            recommendations.extend([
                EngagementRecommendation(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    type="feature_suggestion",
                    title="Create a task",
                    description="Organize your work with our task management feature",
                    action_url="/tasks/create",
                    priority="medium",
                    created_at=datetime.utcnow()
                ),
                EngagementRecommendation(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    type="feature_suggestion",
                    title="Share files",
                    description="Collaborate more effectively by sharing files",
                    action_url="/files/share",
                    priority="medium",
                    created_at=datetime.utcnow()
                )
            ])

        # Рекомендации на основе предпочтений
        if 'messaging' in profile.preferred_features and 'calling' not in profile.preferred_features:
            recommendations.append(
                EngagementRecommendation(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    type="feature_suggestion",
                    title="Try voice/video calls",
                    description="Enhance your communication with voice and video calls",
                    action_url="/calls/new",
                    priority="medium",
                    created_at=datetime.utcnow()
                )
            )

        if 'file_sharing' in profile.preferred_features and 'gaming' not in profile.preferred_features:
            recommendations.append(
                EngagementRecommendation(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    type="feature_suggestion",
                    title="Play games with friends",
                    description="Have fun with our built-in mini-games",
                    action_url="/games",
                    priority="low",
                    created_at=datetime.utcnow()
                )
            )

        # Рекомендации для пользователей с низким уровнем вовлеченности
        if profile.engagement_score < 0.3:
            recommendations.extend([
                EngagementRecommendation(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    type="content_recommendation",
                    title="Check out our tutorials",
                    description="Learn how to get the most out of our platform",
                    action_url="/help/tutorials",
                    priority="high",
                    created_at=datetime.utcnow()
                ),
                EngagementRecommendation(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    type="feature_suggestion",
                    title="Explore more features",
                    description="Discover features you might not have tried yet",
                    action_url="/features/explore",
                    priority="high",
                    created_at=datetime.utcnow()
                )
            ])

        # Рекомендации для пользователей с риском оттока
        if profile.churn_risk > 0.5:
            recommendations.extend([
                EngagementRecommendation(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    type="retention",
                    title="We miss you!",
                    description="Come back and see what's new in our platform",
                    action_url="/dashboard",
                    priority="high",
                    created_at=datetime.utcnow()
                ),
                EngagementRecommendation(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    type="feature_suggestion",
                    title="Try our newest features",
                    description="We've added exciting new features you might enjoy",
                    action_url="/whats-new",
                    priority="high",
                    created_at=datetime.utcnow()
                )
            ])

        return recommendations

    async def _increment_interaction_counters(self, user_id: int, interaction_type: EngagementType):
        """Увеличение счетчиков взаимодействий в Redis"""
        # Увеличиваем общий счетчик
        await redis_client.incr(f"user_interactions:{user_id}:total")
        
        # Увеличиваем счетчик по типу взаимодействия
        await redis_client.incr(f"user_interactions:{user_id}:{interaction_type.value}")
        
        # Увеличиваем дневной счетчик
        today = datetime.utcnow().strftime("%Y%m%d")
        await redis_client.incr(f"user_interactions:{user_id}:daily:{today}")

    async def _cache_user_interaction(self, user_id: int, interaction_type: EngagementType, 
                                   timestamp: datetime):
        """Кэширование взаимодействия пользователя"""
        interaction_data = {
            'type': interaction_type.value,
            'timestamp': timestamp.isoformat()
        }
        
        # Добавляем в список последних взаимодействий
        await redis_client.lpush(f"user_recent_interactions:{user_id}", json.dumps(interaction_data))
        await redis_client.ltrim(f"user_recent_interactions:{user_id}", 0, 49)  # Храним последние 50 взаимодействий

    async def get_user_engagement_insights(self, user_id: int) -> Dict[str, Any]:
        """Получение инсайтов о вовлеченности пользователя"""
        profile = await self.get_user_engagement_profile(user_id)
        if not profile:
            return {}

        # Получаем последние взаимодействия
        recent_interactions = await self._get_recent_user_interactions(user_id, 20)

        # Получаем достижения
        achievements = await self._get_user_achievements(user_id)

        # Получаем рекомендации
        recommendations = await self.get_engagement_recommendations(user_id)

        insights = {
            'profile_summary': {
                'engagement_level': profile.engagement_level.value,
                'engagement_score': profile.engagement_score,
                'retention_probability': profile.retention_probability,
                'churn_risk': profile.churn_risk,
                'streak_days': profile.streak_days,
                'total_interactions': profile.total_interactions,
                'weekly_interactions': profile.weekly_interactions,
                'monthly_interactions': profile.monthly_interactions,
                'last_interaction': profile.last_interaction.isoformat() if profile.last_interaction else None
            },
            'recent_interactions': recent_interactions,
            'achievements': [ach.dict() for ach in achievements],
            'recommendations': [rec.dict() for rec in recommendations],
            'preferred_features': profile.preferred_features,
            'peak_usage_times': profile.peak_usage_times,
            'timestamp': datetime.utcnow().isoformat()
        }

        return insights

    async def _get_recent_user_interactions(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Получение последних взаимодействий пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT interaction_type, target_id, metadata, timestamp
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
                'metadata': json.loads(row['metadata']) if row['metadata'] else {},
                'timestamp': row['timestamp'].isoformat()
            }
            interactions.append(interaction)

        return interactions

    async def _get_user_achievements(self, user_id: int) -> List[UserAchievement]:
        """Получение достижений пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, user_id, achievement_type, name, description, points, unlocked_at
                FROM user_achievements
                WHERE user_id = $1
                ORDER BY unlocked_at DESC
                """,
                user_id
            )

        achievements = []
        for row in rows:
            achievement = UserAchievement(
                id=row['id'],
                user_id=row['user_id'],
                achievement_type=row['achievement_type'],
                name=row['name'],
                description=row['description'],
                points=row['points'],
                unlocked_at=row['unlocked_at']
            )
            achievements.append(achievement)

        return achievements

    async def get_engagement_leaderboard(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Получение таблицы лидеров по вовлеченности"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, engagement_score, total_interactions, streak_days
                FROM user_engagement_profiles
                ORDER BY engagement_score DESC
                LIMIT $1
                """,
                limit
            )

        leaderboard = []
        for i, row in enumerate(rows, 1):
            # Получаем имя пользователя
            user_row = await conn.fetchrow(
                "SELECT username FROM users WHERE id = $1",
                row['user_id']
            )
            
            leaderboard_entry = {
                'rank': i,
                'user_id': row['user_id'],
                'username': user_row['username'] if user_row else f"User {row['user_id']}",
                'engagement_score': row['engagement_score'],
                'total_interactions': row['total_interactions'],
                'streak_days': row['streak_days']
            }
            leaderboard.append(leaderboard_entry)

        return leaderboard

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
user_engagement_service = UserEngagementService()
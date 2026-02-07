# User Experience Enhancement System
# File: services/ux_service/ux_enhancement.py

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

class InteractionType(Enum):
    CHAT_MESSAGE = "chat_message"
    FILE_SHARE = "file_share"
    TASK_ASSIGNMENT = "task_assignment"
    POLL_PARTICIPATION = "poll_participation"
    CALL_INITIATE = "call_initiate"
    GAME_INVITE = "game_invite"
    CALENDAR_EVENT = "calendar_event"
    NOTIFICATION_CLICK = "notification_click"
    UI_ACTION = "ui_action"
    SETTINGS_CHANGE = "settings_change"

class FeedbackType(Enum):
    BUG_REPORT = "bug_report"
    FEATURE_REQUEST = "feature_request"
    USABILITY_FEEDBACK = "usability_feedback"
    PERFORMANCE_ISSUE = "performance_issue"
    DESIGN_SUGGESTION = "design_suggestion"
    GENERAL_FEEDBACK = "general_feedback"

class UserSatisfactionScore(Enum):
    VERY_UNSATISFIED = 1
    UNSATISFIED = 2
    NEUTRAL = 3
    SATISFIED = 4
    VERY_SATISFIED = 5

class UserBehaviorPattern(Enum):
    ACTIVE_CHATTER = "active_chatter"
    PASSIVE_READER = "passive_reader"
    FILE_SHARER = "file_sharer"
    TASK_ORGANIZER = "task_organizer"
    GAMER = "gamer"
    CALLER = "caller"
    CUSTOMIZER = "customizer"

class UserInteraction(BaseModel):
    id: str
    user_id: int
    interaction_type: InteractionType
    target_id: Optional[str] = None  # ID чата, файла, задачи и т.д.
    action_details: Dict[str, Any]  # Дополнительные детали действия
    timestamp: datetime = None
    duration: Optional[float] = None  # Продолжительность взаимодействия в секундах
    satisfaction_score: Optional[UserSatisfactionScore] = None
    feedback: Optional[str] = None

class UserFeedback(BaseModel):
    id: str
    user_id: int
    feedback_type: FeedbackType
    title: str
    description: str
    rating: Optional[int] = None  # 1-5
    is_resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    created_at: datetime = None
    updated_at: datetime = None

class UserBehaviorProfile(BaseModel):
    user_id: int
    patterns: List[UserBehaviorPattern]
    preferences: Dict[str, Any]  # Предпочтения пользователя
    activity_level: str  # 'high', 'medium', 'low'
    peak_usage_times: List[str]  # ['morning', 'afternoon', 'evening', 'night']
    preferred_features: List[str]
    last_interaction: Optional[datetime] = None
    engagement_score: float = 0.0  # 0.0 - 1.0
    churn_risk_score: float = 0.0  # 0.0 - 1.0
    created_at: datetime = None
    updated_at: datetime = None

class UXEnhancementService:
    def __init__(self):
        self.feedback_categories = {
            FeedbackType.BUG_REPORT: ["technical", "ui", "functionality", "performance"],
            FeedbackType.FEATURE_REQUEST: ["chat", "files", "tasks", "calls", "games", "calendar"],
            FeedbackType.USABILITY_FEEDBACK: ["navigation", "interface", "workflow", "accessibility"],
            FeedbackType.PERFORMANCE_ISSUE: ["speed", "responsiveness", "stability", "resource_usage"],
            FeedbackType.DESIGN_SUGGESTION: ["visual", "layout", "color_scheme", "typography"],
            FeedbackType.GENERAL_FEEDBACK: ["general", "experience", "satisfaction"]
        }
        
        self.behavior_detection_rules = {
            UserBehaviorPattern.ACTIVE_CHATTER: {
                "message_threshold": 50,  # сообщений в день
                "chat_participation": 0.7  # 70% активности в чатах
            },
            UserBehaviorPattern.PASSIVE_READER: {
                "message_threshold": 5,
                "read_ratio": 0.9  # 90% сообщений прочитано
            },
            UserBehaviorPattern.FILE_SHARER: {
                "file_share_threshold": 10,  # файлов в неделю
                "media_ratio": 0.6  # 60% медиа файлов
            },
            UserBehaviorPattern.TASK_ORGANIZER: {
                "task_creation_threshold": 5,  # задач в неделю
                "task_assignment_ratio": 0.8  # 80% задач с назначениями
            },
            UserBehaviorPattern.GAMER: {
                "game_interaction_threshold": 20,  # игровых взаимодействий в неделю
                "game_invitation_ratio": 0.3  # 30% игр по приглашениям
            },
            UserBehaviorPattern.CALLER: {
                "call_initiation_threshold": 10,  # инициаций звонков в неделю
                "call_participation_ratio": 0.8  # 80% участия в звонках
            },
            UserBehaviorPattern.CUSTOMIZER: {
                "settings_change_threshold": 15,  # изменений настроек в месяц
                "theme_change_frequency": 0.2  # 20% изменений темы
            }
        }

    async def track_user_interaction(self, user_id: int, interaction_type: InteractionType,
                                   target_id: Optional[str] = None,
                                   action_details: Optional[Dict] = None,
                                   duration: Optional[float] = None,
                                   satisfaction_score: Optional[UserSatisfactionScore] = None,
                                   feedback: Optional[str] = None) -> bool:
        """Отслеживание взаимодействия пользователя"""
        try:
            interaction_id = str(uuid.uuid4())
            timestamp = datetime.utcnow()

            interaction = UserInteraction(
                id=interaction_id,
                user_id=user_id,
                interaction_type=interaction_type,
                target_id=target_id,
                action_details=action_details or {},
                timestamp=timestamp,
                duration=duration,
                satisfaction_score=satisfaction_score,
                feedback=feedback
            )

            # Сохраняем взаимодействие в базу данных
            await self._save_user_interaction(interaction)

            # Обновляем профиль поведения пользователя
            await self._update_user_behavior_profile(user_id, interaction)

            # Проверяем, не нужно ли предложить улучшения UX
            await self._check_ux_improvements_needed(user_id, interaction)

            # Кэшируем взаимодействие
            await self._cache_user_interaction(interaction)

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

    async def _save_user_interaction(self, interaction: UserInteraction):
        """Сохранение взаимодействия пользователя в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_interactions (
                    id, user_id, interaction_type, target_id, action_details,
                    timestamp, duration, satisfaction_score, feedback
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                interaction.id, interaction.user_id, interaction.interaction_type.value,
                interaction.target_id, json.dumps(interaction.action_details),
                interaction.timestamp, interaction.duration,
                interaction.satisfaction_score.value if interaction.satisfaction_score else None,
                interaction.feedback
            )

    async def _update_user_behavior_profile(self, user_id: int, interaction: UserInteraction):
        """Обновление профиля поведения пользователя"""
        profile = await self.get_user_behavior_profile(user_id)
        if not profile:
            profile = await self._create_default_behavior_profile(user_id)

        # Обновляем время последнего взаимодействия
        profile.last_interaction = datetime.utcnow()

        # Обновляем уровень активности
        await self._update_activity_level(profile)

        # Обновляем предпочтительные функции
        feature_name = self._get_feature_name_from_interaction(interaction.interaction_type)
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

        # Обновляем в базе данных
        await self._save_behavior_profile(profile)

        # Обновляем кэш
        await self._cache_behavior_profile(profile)

    async def _create_default_behavior_profile(self, user_id: int) -> UserBehaviorProfile:
        """Создание профиля поведения по умолчанию для нового пользователя"""
        profile = UserBehaviorProfile(
            user_id=user_id,
            patterns=[],
            preferences={},
            activity_level="low",
            peak_usage_times=[],
            preferred_features=[],
            last_interaction=datetime.utcnow(),
            engagement_score=0.0,
            churn_risk_score=0.0,
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
        # Получаем количество взаимодействий за последние 7 дней
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_interactions = await self._get_user_interactions_since(
            profile.user_id, week_ago
        )

        interaction_count = len(recent_interactions)

        if interaction_count > 100:
            profile.activity_level = "high"
        elif interaction_count > 30:
            profile.activity_level = "medium"
        else:
            profile.activity_level = "low"

    def _get_feature_name_from_interaction(self, interaction_type: InteractionType) -> Optional[str]:
        """Получение названия функции из типа взаимодействия"""
        mapping = {
            InteractionType.CHAT_MESSAGE: "messaging",
            InteractionType.FILE_SHARE: "file_sharing",
            InteractionType.TASK_ASSIGNMENT: "task_management",
            InteractionType.POLL_PARTICIPATION: "polls",
            InteractionType.CALL_INITIATE: "calling",
            InteractionType.GAME_INVITE: "gaming",
            InteractionType.CALENDAR_EVENT: "calendar",
            InteractionType.NOTIFICATION_CLICK: "notifications",
            InteractionType.UI_ACTION: "interface",
            InteractionType.SETTINGS_CHANGE: "settings"
        }
        return mapping.get(interaction_type)

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
        # Получаем историю взаимодействий за последние 30 дней
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        interactions = await self._get_user_interactions_since(
            profile.user_id, thirty_days_ago
        )

        # Подсчитываем различные типы взаимодействий
        interaction_counts = {}
        for interaction in interactions:
            interaction_type = interaction.interaction_type.value
            interaction_counts[interaction_type] = interaction_counts.get(interaction_type, 0) + 1

        # Определяем паттерны на основе пороговых значений
        for pattern, rules in self.behavior_detection_rules.items():
            if await self._matches_behavior_pattern(interaction_counts, rules):
                if pattern not in profile.patterns:
                    profile.patterns.append(pattern)

    async def _matches_behavior_pattern(self, interaction_counts: Dict[str, int], 
                                      rules: Dict[str, Any]) -> bool:
        """Проверка соответствия взаимодействий паттерну поведения"""
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

        profile.churn_risk_score = max(0.0, min(1.0, risk_score))

    async def _get_user_interactions_since(self, user_id: int, 
                                         since_date: datetime) -> List[UserInteraction]:
        """Получение взаимодействий пользователя с определенной даты"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, user_id, interaction_type, target_id, action_details,
                       timestamp, duration, satisfaction_score, feedback
                FROM user_interactions
                WHERE user_id = $1 AND timestamp >= $2
                ORDER BY timestamp DESC
                """,
                user_id, since_date
            )

        interactions = []
        for row in rows:
            interaction = UserInteraction(
                id=row['id'],
                user_id=row['user_id'],
                interaction_type=InteractionType(row['interaction_type']),
                target_id=row['target_id'],
                action_details=json.loads(row['action_details']) if row['action_details'] else {},
                timestamp=row['timestamp'],
                duration=row['duration'],
                satisfaction_score=UserSatisfactionScore(row['satisfaction_score']) if row['satisfaction_score'] else None,
                feedback=row['feedback']
            )
            interactions.append(interaction)

        return interactions

    async def _save_behavior_profile(self, profile: UserBehaviorProfile):
        """Сохранение профиля поведения в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_behavior_profiles (
                    user_id, patterns, preferences, activity_level, peak_usage_times,
                    preferred_features, last_interaction, engagement_score, churn_risk_score,
                    created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (user_id) DO UPDATE SET
                    patterns = $2, preferences = $3, activity_level = $4,
                    peak_usage_times = $5, preferred_features = $6,
                    last_interaction = $7, engagement_score = $8, churn_risk_score = $9,
                    updated_at = $11
                """,
                profile.user_id, [p.value for p in profile.patterns],
                json.dumps(profile.preferences), profile.activity_level,
                profile.peak_usage_times, profile.preferred_features,
                profile.last_interaction, profile.engagement_score,
                profile.churn_risk_score, profile.created_at, profile.updated_at
            )

    async def _cache_behavior_profile(self, profile: UserBehaviorProfile):
        """Кэширование профиля поведения"""
        await redis_client.setex(
            f"user_behavior_profile:{profile.user_id}",
            3600,  # 1 час
            profile.model_dump_json()
        )

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
                SELECT user_id, patterns, preferences, activity_level, peak_usage_times,
                       preferred_features, last_interaction, engagement_score, churn_risk_score,
                       created_at, updated_at
                FROM user_behavior_profiles WHERE user_id = $1
                """,
                user_id
            )

        if not row:
            return None

        profile = UserBehaviorProfile(
            user_id=row['user_id'],
            patterns=[UserBehaviorPattern(p) for p in row['patterns']] if row['patterns'] else [],
            preferences=json.loads(row['preferences']) if row['preferences'] else {},
            activity_level=row['activity_level'],
            peak_usage_times=row['peak_usage_times'] or [],
            preferred_features=row['preferred_features'] or [],
            last_interaction=row['last_interaction'],
            engagement_score=row['engagement_score'] or 0.0,
            churn_risk_score=row['churn_risk_score'] or 0.0,
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

        # Кэшируем профиль
        await self._cache_behavior_profile(profile)

        return profile

    async def _check_ux_improvements_needed(self, user_id: int, interaction: UserInteraction):
        """Проверка необходимости улучшений UX на основе взаимодействия"""
        profile = await self.get_user_behavior_profile(user_id)
        if not profile:
            return

        # Проверяем, есть ли у пользователя проблемы с использованием функций
        if interaction.satisfaction_score and interaction.satisfaction_score.value <= 2:
            # Низкая удовлетворенность - предлагаем улучшения
            await self._suggest_ux_improvements(user_id, interaction, profile)

        # Проверяем, не сталкивается ли пользователь с трудностями
        if interaction.duration and interaction.duration > 30:  # Если действие занимает более 30 секунд
            # Возможно, пользователь испытывает трудности - предлагаем помощь
            await self._suggest_usability_help(user_id, interaction)

    async def _suggest_ux_improvements(self, user_id: int, interaction: UserInteraction,
                                    profile: UserBehaviorProfile):
        """Предложение улучшений UX пользователю"""
        suggestions = []

        # В зависимости от типа взаимодействия и профиля пользователя
        if interaction.interaction_type == InteractionType.UI_ACTION:
            if 'navigation' in interaction.action_details.get('path', ''):
                suggestions.append({
                    'type': 'navigation_simplification',
                    'message': 'We noticed you had trouble navigating. Would you like us to simplify the menu structure?',
                    'action': 'show_simplified_menu'
                })

        elif interaction.interaction_type == InteractionType.SETTINGS_CHANGE:
            if interaction.action_details.get('setting_changed') == 'theme':
                suggestions.append({
                    'type': 'theme_customization',
                    'message': 'We noticed you frequently change themes. Would you like to try our new automatic theme switching?',
                    'action': 'enable_auto_theme'
                })

        # Отправляем предложения пользователю
        if suggestions:
            await self._send_ux_suggestions_to_user(user_id, suggestions)

    async def _suggest_usability_help(self, user_id: int, interaction: UserInteraction):
        """Предложение помощи в использовании функций"""
        help_suggestions = []

        if interaction.interaction_type == InteractionType.TASK_ASSIGNMENT:
            help_suggestions.append({
                'type': 'task_tutorial',
                'message': 'Need help assigning tasks? Watch our quick tutorial.',
                'action': 'show_task_assignment_tutorial'
            })

        elif interaction.interaction_type == InteractionType.CALL_INITIATE:
            help_suggestions.append({
                'type': 'call_tutorial',
                'message': 'Having trouble with calls? Check out our calling guide.',
                'action': 'show_call_guide'
            })

        # Отправляем предложения помощи пользователю
        if help_suggestions:
            await self._send_help_suggestions_to_user(user_id, help_suggestions)

    async def _send_ux_suggestions_to_user(self, user_id: int, suggestions: List[Dict[str, Any]]):
        """Отправка предложений UX пользователю"""
        notification = {
            'type': 'ux_suggestions',
            'suggestions': suggestions,
            'timestamp': datetime.utcnow().isoformat()
        }

        await redis_client.publish(f"user:{user_id}:ux_suggestions", json.dumps(notification))

    async def _send_help_suggestions_to_user(self, user_id: int, suggestions: List[Dict[str, Any]]):
        """Отправка предложений помощи пользователю"""
        notification = {
            'type': 'help_suggestions',
            'suggestions': suggestions,
            'timestamp': datetime.utcnow().isoformat()
        }

        await redis_client.publish(f"user:{user_id}:help_suggestions", json.dumps(notification))

    async def submit_user_feedback(self, user_id: int, feedback_type: FeedbackType,
                                 title: str, description: str, rating: Optional[int] = None) -> Optional[str]:
        """Отправка пользовательского отзыва"""
        feedback_id = str(uuid.uuid4())

        feedback = UserFeedback(
            id=feedback_id,
            user_id=user_id,
            feedback_type=feedback_type,
            title=title,
            description=description,
            rating=rating,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем отзыв в базу данных
        await self._save_user_feedback(feedback)

        # Проверяем, не указывает ли отзыв на проблему с UX
        await self._analyze_feedback_for_ux_issues(feedback)

        # Уведомляем команду поддержки
        await self._notify_support_team(feedback)

        # Создаем запись активности
        await self._log_activity(user_id, "feedback_submitted", {
            "feedback_type": feedback_type.value,
            "title": title,
            "rating": rating
        })

        return feedback_id

    async def _save_user_feedback(self, feedback: UserFeedback):
        """Сохранение отзыва пользователя в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_feedback (
                    id, user_id, feedback_type, title, description, rating,
                    is_resolved, resolved_at, resolution_notes, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                feedback.id, feedback.user_id, feedback.feedback_type.value,
                feedback.title, feedback.description, feedback.rating,
                feedback.is_resolved, feedback.resolved_at, feedback.resolution_notes,
                feedback.created_at, feedback.updated_at
            )

    async def _analyze_feedback_for_ux_issues(self, feedback: UserFeedback):
        """Анализ отзыва на предмет проблем с UX"""
        # Проверяем, содержит ли отзыв информацию о проблемах с UX
        feedback_text = f"{feedback.title} {feedback.description}".lower()
        
        ux_keywords = [
            "difficult", "confusing", "complicated", "not intuitive", "hard to use",
            "interface", "navigation", "layout", "design", "slow", "laggy", "bug",
            "doesn't work", "broken", "glitch", "error", "problem", "issue"
        ]
        
        if any(keyword in feedback_text for keyword in ux_keywords):
            # Это потенциальная проблема с UX
            await self._log_ux_issue(feedback)

    async def _log_ux_issue(self, feedback: UserFeedback):
        """Логирование проблемы с UX"""
        issue_id = str(uuid.uuid4())
        
        ux_issue = {
            'id': issue_id,
            'feedback_id': feedback.id,
            'user_id': feedback.user_id,
            'type': 'ux_issue',
            'description': feedback.description,
            'reported_at': datetime.utcnow().isoformat()
        }
        
        # Сохраняем в Redis для быстрого доступа
        await redis_client.lpush("ux_issues", json.dumps(ux_issue))
        await redis_client.ltrim("ux_issues", 0, 999)  # Храним последние 1000 проблем

    async def _notify_support_team(self, feedback: UserFeedback):
        """Уведомление команды поддержки об отзыве"""
        notification = {
            'type': 'new_feedback',
            'feedback': {
                'id': feedback.id,
                'user_id': feedback.user_id,
                'type': feedback.feedback_type.value,
                'title': feedback.title,
                'description': feedback.description,
                'rating': feedback.rating
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем в канал поддержки
        await redis_client.publish("support_notifications", json.dumps(notification))

    async def get_personalized_features(self, user_id: int) -> Dict[str, Any]:
        """Получение персонализированных функций для пользователя"""
        profile = await self.get_user_behavior_profile(user_id)
        if not profile:
            return {}

        # Возвращаем рекомендации на основе профиля поведения
        recommendations = {
            'recommended_features': [],
            'interface_customizations': [],
            'productivity_tools': [],
            'engagement_boosters': []
        }

        # Рекомендуем функции на основе паттернов поведения
        if UserBehaviorPattern.ACTIVE_CHATTER in profile.patterns:
            recommendations['recommended_features'].extend([
                'advanced_chat_shortcuts',
                'message_templates',
                'conversation_threads'
            ])

        if UserBehaviorPattern.FILE_SHARER in profile.patterns:
            recommendations['recommended_features'].extend([
                'bulk_file_upload',
                'file_organization_tools',
                'cloud_storage_integration'
            ])

        if UserBehaviorPattern.TASK_ORGANIZER in profile.patterns:
            recommendations['recommended_features'].extend([
                'task_automation',
                'project_templates',
                'team_collaboration_tools'
            ])

        if UserBehaviorPattern.GAMER in profile.patterns:
            recommendations['recommended_features'].extend([
                'game_invitation_system',
                'achievement_tracking',
                'leaderboards'
            ])

        # Рекомендуем настройки интерфейса
        if profile.activity_level == "high":
            recommendations['interface_customizations'].append('compact_mode')
        
        if 'morning' in profile.peak_usage_times:
            recommendations['interface_customizations'].append('light_theme_morning')

        # Рекомендуем инструменты продуктивности
        if UserBehaviorPattern.TASK_ORGANIZER in profile.patterns:
            recommendations['productivity_tools'].extend([
                'smart_scheduling',
                'deadline_reminders',
                'progress_tracking'
            ])

        # Рекомендуем инструменты для повышения вовлеченности
        if profile.engagement_score < 0.5:
            recommendations['engagement_boosters'].extend([
                'daily_challenges',
                'feature_discovery_tours',
                'personalized_notifications'
            ])

        return recommendations

    async def _cache_user_interaction(self, interaction: UserInteraction):
        """Кэширование взаимодействия пользователя"""
        interaction_data = {
            'type': interaction.interaction_type.value,
            'target_id': interaction.target_id,
            'timestamp': interaction.timestamp.isoformat(),
            'duration': interaction.duration,
            'satisfaction_score': interaction.satisfaction_score.value if interaction.satisfaction_score else None
        }
        
        # Добавляем в список последних взаимодействий
        await redis_client.lpush(f"user_recent_interactions:{interaction.user_id}", json.dumps(interaction_data))
        await redis_client.ltrim(f"user_recent_interactions:{interaction.user_id}", 0, 49)  # Храним последние 50 взаимодействий

    async def _increment_interaction_counters(self, user_id: int, interaction_type: InteractionType):
        """Увеличение счетчиков взаимодействий в Redis"""
        # Увеличиваем общий счетчик
        await redis_client.incr(f"user_interactions:{user_id}:total")
        
        # Увеличиваем счетчик по типу взаимодействия
        await redis_client.incr(f"user_interactions:{user_id}:{interaction_type.value}")
        
        # Увеличиваем дневной счетчик
        today = datetime.utcnow().strftime("%Y%m%d")
        await redis_client.incr(f"user_interactions:{user_id}:daily:{today}")

    async def get_user_experience_insights(self, user_id: int) -> Dict[str, Any]:
        """Получение инсайтов о пользовательском опыте"""
        profile = await self.get_user_behavior_profile(user_id)
        if not profile:
            return {}

        # Получаем последние взаимодействия
        recent_interactions = await self._get_recent_user_interactions(user_id, 20)

        # Получаем отзывы пользователя
        user_feedback = await self._get_user_feedback(user_id)

        # Получаем рекомендации
        recommendations = await self.get_personalized_features(user_id)

        insights = {
            'profile_summary': {
                'behavior_patterns': [p.value for p in profile.patterns],
                'activity_level': profile.activity_level,
                'engagement_score': profile.engagement_score,
                'churn_risk_score': profile.churn_risk_score,
                'preferred_features': profile.preferred_features,
                'peak_usage_times': profile.peak_usage_times,
                'last_interaction': profile.last_interaction.isoformat() if profile.last_interaction else None
            },
            'recent_interactions': recent_interactions,
            'user_feedback': [fb.dict() for fb in user_feedback],
            'recommendations': recommendations,
            'ux_improvement_opportunities': await self._identify_ux_improvement_opportunities(profile),
            'timestamp': datetime.utcnow().isoformat()
        }

        return insights

    async def _get_recent_user_interactions(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
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

    async def _get_user_feedback(self, user_id: int) -> List[UserFeedback]:
        """Получение отзывов пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, user_id, feedback_type, title, description, rating,
                       is_resolved, resolved_at, resolution_notes, created_at, updated_at
                FROM user_feedback
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT 20
                """,
                user_id
            )

        feedback_list = []
        for row in rows:
            feedback = UserFeedback(
                id=row['id'],
                user_id=row['user_id'],
                feedback_type=FeedbackType(row['feedback_type']),
                title=row['title'],
                description=row['description'],
                rating=row['rating'],
                is_resolved=row['is_resolved'],
                resolved_at=row['resolved_at'],
                resolution_notes=row['resolution_notes'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            feedback_list.append(feedback)

        return feedback_list

    async def _identify_ux_improvement_opportunities(self, profile: UserBehaviorProfile) -> List[Dict[str, str]]:
        """Идентификация возможностей для улучшения UX"""
        opportunities = []

        # Возможности для пользователей с низкой вовлеченностью
        if profile.engagement_score < 0.3:
            opportunities.append({
                'area': 'engagement',
                'opportunity': 'Provide onboarding tutorials and feature discovery',
                'potential_impact': 'Increased user retention'
            })

        # Возможности для пользователей с высоким риском оттока
        if profile.churn_risk_score > 0.6:
            opportunities.append({
                'area': 'retention',
                'opportunity': 'Implement re-engagement campaigns and loyalty programs',
                'potential_impact': 'Reduced churn rate'
            })

        # Возможности для пользователей с определенными паттернами
        if UserBehaviorPattern.PASSIVE_READER in profile.patterns:
            opportunities.append({
                'area': 'interaction',
                'opportunity': 'Provide easier ways to participate in conversations',
                'potential_impact': 'Increased user participation'
            })

        if UserBehaviorPattern.CUSTOMIZER in profile.patterns:
            opportunities.append({
                'area': 'personalization',
                'opportunity': 'Offer more customization options',
                'potential_impact': 'Higher user satisfaction'
            })

        return opportunities

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
ux_enhancement_service = UXEnhancementService()
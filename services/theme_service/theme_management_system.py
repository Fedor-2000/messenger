# Theme Management System
# File: services/theme_service/theme_management_system.py

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

class ThemeType(Enum):
    LIGHT = "light"
    DARK = "dark"
    BLACK = "black"
    AUTO = "auto"  # Автоматически по времени суток
    CUSTOM = "custom"

class ThemeColor(Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    BACKGROUND = "background"
    SURFACE = "surface"
    TEXT_PRIMARY = "text_primary"
    TEXT_SECONDARY = "text_secondary"
    TEXT_TERTIARY = "text_tertiary"
    ACCENT = "accent"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    INFO = "info"

class Theme(BaseModel):
    id: str
    name: str
    type: ThemeType
    colors: Dict[ThemeColor, str]  # {'primary': '#007AFF', 'background': '#FFFFFF', ...}
    font_family: str = "Roboto, Arial, sans-serif"
    font_size: str = "medium"  # 'small', 'medium', 'large'
    spacing: str = "medium"  # 'compact', 'medium', 'spacious'
    corner_radius: int = 8  # Радиус скругления углов
    shadow_intensity: str = "medium"  # 'low', 'medium', 'high'
    animation_speed: str = "normal"  # 'slow', 'normal', 'fast'
    is_default: bool = False
    is_public: bool = True  # Может ли тема использоваться другими пользователями
    creator_id: Optional[int] = None  # ID создателя для пользовательских тем
    created_at: datetime = None
    updated_at: datetime = None

class UserThemePreference(BaseModel):
    user_id: int
    theme_id: str
    applied_at: datetime = None
    auto_switch_enabled: bool = False  # Автоматическое переключение по времени суток
    morning_theme_id: Optional[str] = None  # Тема для утра
    evening_theme_id: Optional[str] = None  # Тема для вечера
    updated_at: datetime = None

class ThemeManagementService:
    def __init__(self):
        self.default_themes = {
            "light": Theme(
                id="theme_light_default",
                name="Light Theme",
                type=ThemeType.LIGHT,
                colors={
                    ThemeColor.PRIMARY.value: "#007AFF",
                    ThemeColor.SECONDARY.value: "#5856D6",
                    ThemeColor.BACKGROUND.value: "#FFFFFF",
                    ThemeColor.SURFACE.value: "#F2F2F7",
                    ThemeColor.TEXT_PRIMARY.value: "#000000",
                    ThemeColor.TEXT_SECONDARY.value: "#8E8E93",
                    ThemeColor.TEXT_TERTIARY.value: "#C7C7CC",
                    ThemeColor.ACCENT.value: "#FF9500",
                    ThemeColor.SUCCESS.value: "#34C759",
                    ThemeColor.WARNING.value: "#FFCC00",
                    ThemeColor.ERROR.value: "#FF3B30",
                    ThemeColor.INFO.value: "#5AC8FA"
                },
                font_family="Roboto, Arial, sans-serif",
                font_size="medium",
                spacing="medium",
                corner_radius=8,
                shadow_intensity="medium",
                animation_speed="normal",
                is_default=True,
                is_public=True,
                created_at=datetime.utcnow()
            ),
            "dark": Theme(
                id="theme_dark_default",
                name="Dark Theme",
                type=ThemeType.DARK,
                colors={
                    ThemeColor.PRIMARY.value: "#0A84FF",
                    ThemeColor.SECONDARY.value: "#B586FF",
                    ThemeColor.BACKGROUND.value: "#000000",
                    ThemeColor.SURFACE.value: "#1C1C1E",
                    ThemeColor.TEXT_PRIMARY.value: "#FFFFFF",
                    ThemeColor.TEXT_SECONDARY.value: "#AEAEB2",
                    ThemeColor.TEXT_TERTIARY.value: "#48484A",
                    ThemeColor.ACCENT.value: "#FFCC00",
                    ThemeColor.SUCCESS.value: "#30D158",
                    ThemeColor.WARNING.value: "#FFD60A",
                    ThemeColor.ERROR.value: "#FF453A",
                    ThemeColor.INFO.value: "#64D2FF"
                },
                font_family="Roboto, Arial, sans-serif",
                font_size="medium",
                spacing="medium",
                corner_radius=8,
                shadow_intensity="medium",
                animation_speed="normal",
                is_default=True,
                is_public=True,
                created_at=datetime.utcnow()
            ),
            "black": Theme(
                id="theme_black_default",
                name="Black Theme",
                type=ThemeType.BLACK,
                colors={
                    ThemeColor.PRIMARY.value: "#0A84FF",
                    ThemeColor.SECONDARY.value: "#B586FF",
                    ThemeColor.BACKGROUND.value: "#000000",
                    ThemeColor.SURFACE.value: "#000000",
                    ThemeColor.TEXT_PRIMARY.value: "#FFFFFF",
                    ThemeColor.TEXT_SECONDARY.value: "#AEAEB2",
                    ThemeColor.TEXT_TERTIARY.value: "#48484A",
                    ThemeColor.ACCENT.value: "#FFCC00",
                    ThemeColor.SUCCESS.value: "#30D158",
                    ThemeColor.WARNING.value: "#FFD60A",
                    ThemeColor.ERROR.value: "#FF453A",
                    ThemeColor.INFO.value: "#64D2FF"
                },
                font_family="Roboto, Arial, sans-serif",
                font_size="medium",
                spacing="medium",
                corner_radius=0,
                shadow_intensity="low",
                animation_speed="fast",
                is_default=True,
                is_public=True,
                created_at=datetime.utcnow()
            )
        }

    async def initialize_default_themes(self):
        """Инициализация тем по умолчанию"""
        for theme in self.default_themes.values():
            await self._save_theme_to_db(theme)

    async def create_theme(self, name: str, theme_type: ThemeType, colors: Dict[str, str],
                          font_family: str = "Roboto, Arial, sans-serif",
                          font_size: str = "medium", spacing: str = "medium",
                          corner_radius: int = 8, shadow_intensity: str = "medium",
                          animation_speed: str = "normal", is_public: bool = True,
                          creator_id: Optional[int] = None) -> Optional[str]:
        """Создание новой темы"""
        theme_id = str(uuid.uuid4())

        theme = Theme(
            id=theme_id,
            name=name,
            type=theme_type,
            colors=colors,
            font_family=font_family,
            font_size=font_size,
            spacing=spacing,
            corner_radius=corner_radius,
            shadow_intensity=shadow_intensity,
            animation_speed=animation_speed,
            is_default=False,
            is_public=is_public,
            creator_id=creator_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем тему в базу данных
        await self._save_theme_to_db(theme)

        # Добавляем в кэш
        await self._cache_theme(theme)

        # Создаем запись активности
        await self._log_activity("theme_created", {
            "theme_id": theme_id,
            "theme_name": name,
            "creator_id": creator_id
        })

        return theme_id

    async def _save_theme_to_db(self, theme: Theme):
        """Сохранение темы в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO themes (
                    id, name, type, colors, font_family, font_size, spacing,
                    corner_radius, shadow_intensity, animation_speed, is_default,
                    is_public, creator_id, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                """,
                theme.id, theme.name, theme.type.value, json.dumps(theme.colors),
                theme.font_family, theme.font_size, theme.spacing,
                theme.corner_radius, theme.shadow_intensity, theme.animation_speed,
                theme.is_default, theme.is_public, theme.creator_id,
                theme.created_at, theme.updated_at
            )

    async def get_theme(self, theme_id: str) -> Optional[Theme]:
        """Получение темы по ID"""
        # Сначала проверяем кэш
        cached_theme = await self._get_cached_theme(theme_id)
        if cached_theme:
            return cached_theme

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, type, colors, font_family, font_size, spacing,
                       corner_radius, shadow_intensity, animation_speed, is_default,
                       is_public, creator_id, created_at, updated_at
                FROM themes WHERE id = $1
                """,
                theme_id
            )

        if not row:
            return None

        theme = Theme(
            id=row['id'],
            name=row['name'],
            type=ThemeType(row['type']),
            colors=json.loads(row['colors']) if row['colors'] else {},
            font_family=row['font_family'],
            font_size=row['font_size'],
            spacing=row['spacing'],
            corner_radius=row['corner_radius'],
            shadow_intensity=row['shadow_intensity'],
            animation_speed=row['animation_speed'],
            is_default=row['is_default'],
            is_public=row['is_public'],
            creator_id=row['creator_id'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

        # Кэшируем тему
        await self._cache_theme(theme)

        return theme

    async def get_user_theme(self, user_id: int) -> Optional[Theme]:
        """Получение темы пользователя"""
        # Получаем предпочтения пользователя
        user_pref = await self._get_user_theme_preference(user_id)
        if not user_pref:
            # Возвращаем тему по умолчанию
            return self.default_themes["light"]

        # Если включено автоматическое переключение темы
        if user_pref.auto_switch_enabled:
            current_hour = datetime.utcnow().hour
            if 6 <= current_hour < 18:  # Утро/день
                theme_id = user_pref.morning_theme_id or user_pref.theme_id
            else:  # Вечер/ночь
                theme_id = user_pref.evening_theme_id or user_pref.theme_id
        else:
            theme_id = user_pref.theme_id

        return await self.get_theme(theme_id)

    async def set_user_theme(self, user_id: int, theme_id: str,
                           auto_switch_enabled: bool = False,
                           morning_theme_id: Optional[str] = None,
                           evening_theme_id: Optional[str] = None) -> bool:
        """Установка темы для пользователя"""
        # Проверяем, существует ли тема
        theme = await self.get_theme(theme_id)
        if not theme:
            return False

        # Проверяем права доступа к теме
        if not theme.is_public and theme.creator_id != user_id:
            return False

        user_pref = UserThemePreference(
            user_id=user_id,
            theme_id=theme_id,
            applied_at=datetime.utcnow(),
            auto_switch_enabled=auto_switch_enabled,
            morning_theme_id=morning_theme_id,
            evening_theme_id=evening_theme_id,
            updated_at=datetime.utcnow()
        )

        # Сохраняем предпочтения в базу данных
        await self._save_user_theme_preference(user_pref)

        # Обновляем кэш
        await self._cache_user_theme_preference(user_pref)

        # Уведомляем клиента об изменении темы
        await self._notify_theme_changed(user_id, theme)

        # Создаем запись активности
        await self._log_activity("user_theme_set", {
            "user_id": user_id,
            "theme_id": theme_id,
            "auto_switch_enabled": auto_switch_enabled
        })

        return True

    async def _save_user_theme_preference(self, preference: UserThemePreference):
        """Сохранение предпочтений темы пользователя в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_theme_preferences (
                    user_id, theme_id, applied_at, auto_switch_enabled, morning_theme_id, evening_theme_id, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (user_id) DO UPDATE SET
                    theme_id = $2, auto_switch_enabled = $4, morning_theme_id = $5,
                    evening_theme_id = $6, updated_at = $7
                """,
                preference.user_id, preference.theme_id, preference.applied_at,
                preference.auto_switch_enabled, preference.morning_theme_id,
                preference.evening_theme_id, preference.updated_at
            )

    async def _get_user_theme_preference(self, user_id: int) -> Optional[UserThemePreference]:
        """Получение предпочтений темы пользователя"""
        # Сначала проверяем кэш
        cached_pref = await self._get_cached_user_theme_preference(user_id)
        if cached_pref:
            return cached_pref

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT user_id, theme_id, applied_at, auto_switch_enabled, morning_theme_id, evening_theme_id, updated_at
                FROM user_theme_preferences WHERE user_id = $1
                """,
                user_id
            )

        if not row:
            return None

        preference = UserThemePreference(
            user_id=row['user_id'],
            theme_id=row['theme_id'],
            applied_at=row['applied_at'],
            auto_switch_enabled=row['auto_switch_enabled'],
            morning_theme_id=row['morning_theme_id'],
            evening_theme_id=row['evening_theme_id'],
            updated_at=row['updated_at']
        )

        # Кэшируем предпочтения
        await self._cache_user_theme_preference(preference)

        return preference

    async def _cache_theme(self, theme: Theme):
        """Кэширование темы"""
        await redis_client.setex(f"theme:{theme.id}", 3600, theme.model_dump_json())

    async def _get_cached_theme(self, theme_id: str) -> Optional[Theme]:
        """Получение темы из кэша"""
        cached = await redis_client.get(f"theme:{theme_id}")
        if cached:
            return Theme(**json.loads(cached.decode()))
        return None

    async def _cache_user_theme_preference(self, preference: UserThemePreference):
        """Кэширование предпочтений темы пользователя"""
        await redis_client.setex(f"user_theme_pref:{preference.user_id}", 1800, preference.model_dump_json())

    async def _get_cached_user_theme_preference(self, user_id: int) -> Optional[UserThemePreference]:
        """Получение предпочтений темы пользователя из кэша"""
        cached = await redis_client.get(f"user_theme_pref:{user_id}")
        if cached:
            return UserThemePreference(**json.loads(cached.decode()))
        return None

    async def _notify_theme_changed(self, user_id: int, theme: Theme):
        """Уведомление клиента об изменении темы"""
        notification = {
            'type': 'theme_changed',
            'theme': {
                'id': theme.id,
                'name': theme.name,
                'type': theme.type.value,
                'colors': theme.colors,
                'font_family': theme.font_family,
                'font_size': theme.font_size,
                'spacing': theme.spacing,
                'corner_radius': theme.corner_radius,
                'shadow_intensity': theme.shadow_intensity,
                'animation_speed': theme.animation_speed
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        await redis_client.publish(f"user:{user_id}:theme_updates", json.dumps(notification))

    async def get_available_themes(self, user_id: Optional[int] = None) -> List[Theme]:
        """Получение доступных тем"""
        # Сначала получаем публичные темы
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, type, colors, font_family, font_size, spacing,
                       corner_radius, shadow_intensity, animation_speed, is_default,
                       is_public, creator_id, created_at, updated_at
                FROM themes
                WHERE is_public = true
                ORDER BY created_at DESC
                """
            )

        themes = []
        for row in rows:
            theme = Theme(
                id=row['id'],
                name=row['name'],
                type=ThemeType(row['type']),
                colors=json.loads(row['colors']) if row['colors'] else {},
                font_family=row['font_family'],
                font_size=row['font_size'],
                spacing=row['spacing'],
                corner_radius=row['corner_radius'],
                shadow_intensity=row['shadow_intensity'],
                animation_speed=row['animation_speed'],
                is_default=row['is_default'],
                is_public=row['is_public'],
                creator_id=row['creator_id'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            themes.append(theme)

        # Добавляем пользовательские темы, если указан user_id
        if user_id:
            user_themes = await self._get_user_created_themes(user_id)
            themes.extend(user_themes)

        return themes

    async def _get_user_created_themes(self, user_id: int) -> List[Theme]:
        """Получение тем, созданных пользователем"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, type, colors, font_family, font_size, spacing,
                       corner_radius, shadow_intensity, animation_speed, is_default,
                       is_public, creator_id, created_at, updated_at
                FROM themes
                WHERE creator_id = $1
                ORDER BY created_at DESC
                """,
                user_id
            )

        themes = []
        for row in rows:
            theme = Theme(
                id=row['id'],
                name=row['name'],
                type=ThemeType(row['type']),
                colors=json.loads(row['colors']) if row['colors'] else {},
                font_family=row['font_family'],
                font_size=row['font_size'],
                spacing=row['spacing'],
                corner_radius=row['corner_radius'],
                shadow_intensity=row['shadow_intensity'],
                animation_speed=row['animation_speed'],
                is_default=row['is_default'],
                is_public=row['is_public'],
                creator_id=row['creator_id'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            themes.append(theme)

        return themes

    async def create_custom_theme_from_template(self, user_id: int, name: str,
                                              base_theme_id: str,
                                              custom_colors: Optional[Dict[str, str]] = None,
                                              custom_font_family: Optional[str] = None,
                                              custom_font_size: Optional[str] = None,
                                              custom_spacing: Optional[str] = None,
                                              custom_corner_radius: Optional[int] = None,
                                              custom_shadow_intensity: Optional[str] = None,
                                              custom_animation_speed: Optional[str] = None) -> Optional[str]:
        """Создание пользовательской темы на основе шаблона"""
        base_theme = await self.get_theme(base_theme_id)
        if not base_theme:
            return None

        # Создаем новую тему на основе базовой
        new_theme_id = str(uuid.uuid4())
        
        custom_theme = Theme(
            id=new_theme_id,
            name=name,
            type=ThemeType.CUSTOM,
            colors=custom_colors or base_theme.colors,
            font_family=custom_font_family or base_theme.font_family,
            font_size=custom_font_size or base_theme.font_size,
            spacing=custom_spacing or base_theme.spacing,
            corner_radius=custom_corner_radius or base_theme.corner_radius,
            shadow_intensity=custom_shadow_intensity or base_theme.shadow_intensity,
            animation_speed=custom_animation_speed or base_theme.animation_speed,
            is_default=False,
            is_public=False,  # Пользовательские темы по умолчанию приватные
            creator_id=user_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем тему в базу данных
        await self._save_theme_to_db(custom_theme)

        # Добавляем в кэш
        await self._cache_theme(custom_theme)

        # Создаем запись активности
        await self._log_activity("custom_theme_created", {
            "theme_id": new_theme_id,
            "theme_name": name,
            "base_theme_id": base_theme_id,
            "creator_id": user_id
        })

        return new_theme_id

    async def share_theme(self, theme_id: str, creator_id: int, 
                         target_users: List[int]) -> bool:
        """Поделиться темой с другими пользователями"""
        theme = await self.get_theme(theme_id)
        if not theme or theme.creator_id != creator_id:
            return False

        # Проверяем, может ли пользователь делиться этой темой
        if not theme.is_public and theme.creator_id != creator_id:
            return False

        # Делаем тему публичной, если она была приватной
        if not theme.is_public:
            theme.is_public = True
            await self._update_theme_in_db(theme)
            await self._cache_theme(theme)

        # Уведомляем пользователей о доступной теме
        for target_user_id in target_users:
            await self._notify_theme_shared(target_user_id, theme)

        # Создаем запись активности
        await self._log_activity("theme_shared", {
            "theme_id": theme_id,
            "sharer_id": creator_id,
            "recipient_count": len(target_users)
        })

        return True

    async def _notify_theme_shared(self, user_id: int, theme: Theme):
        """Уведомление пользователя о доступной теме"""
        notification = {
            'type': 'theme_shared',
            'theme': {
                'id': theme.id,
                'name': theme.name,
                'type': theme.type.value,
                'creator_id': theme.creator_id
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        await redis_client.publish(f"user:{user_id}:theme_notifications", json.dumps(notification))

    async def _update_theme_in_db(self, theme: Theme):
        """Обновление темы в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE themes SET
                    name = $2, type = $3, colors = $4, font_family = $5, font_size = $6,
                    spacing = $7, corner_radius = $8, shadow_intensity = $9, animation_speed = $10,
                    is_public = $11, updated_at = $12
                WHERE id = $1
                """,
                theme.id, theme.name, theme.type.value, json.dumps(theme.colors),
                theme.font_family, theme.font_size, theme.spacing,
                theme.corner_radius, theme.shadow_intensity, theme.animation_speed,
                theme.is_public, theme.updated_at
            )

    async def get_theme_statistics(self, theme_id: str) -> Dict[str, Any]:
        """Получение статистики по теме"""
        async with db_pool.acquire() as conn:
            # Общая статистика
            total_users = await conn.fetchval(
                "SELECT COUNT(*) FROM user_theme_preferences WHERE theme_id = $1",
                theme_id
            )
            
            # Статистика по времени использования
            usage_stats = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total_users,
                    AVG(EXTRACT(EPOCH FROM (NOW() - applied_at))/3600/24) as avg_days_since_application,
                    MIN(applied_at) as first_application,
                    MAX(applied_at) as last_application
                FROM user_theme_preferences 
                WHERE theme_id = $1
                """,
                theme_id
            )

        return {
            "theme_id": theme_id,
            "total_users_using": usage_stats['total_users'] or 0,
            "avg_days_since_application": usage_stats['avg_days_since_application'] or 0,
            "first_application": usage_stats['first_application'].isoformat() if usage_stats['first_application'] else None,
            "last_application": usage_stats['last_application'].isoformat() if usage_stats['last_application'] else None,
            "timestamp": datetime.utcnow().isoformat()
        }

    async def get_user_theme_preferences(self, user_id: int) -> Optional[UserThemePreference]:
        """Получение предпочтений темы пользователя"""
        return await self._get_cached_user_theme_preference(user_id)

    async def get_popular_themes(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение популярных тем"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT t.id, t.name, t.type, t.colors, t.created_at, 
                       COUNT(utp.user_id) as usage_count
                FROM themes t
                LEFT JOIN user_theme_preferences utp ON t.id = utp.theme_id
                WHERE t.is_public = true
                GROUP BY t.id, t.name, t.type, t.colors, t.created_at
                ORDER BY usage_count DESC
                LIMIT $1
                """,
                limit
            )

        popular_themes = []
        for row in rows:
            theme_info = {
                'id': row['id'],
                'name': row['name'],
                'type': row['type'],
                'usage_count': row['usage_count'],
                'created_at': row['created_at'].isoformat()
            }
            popular_themes.append(theme_info)

        return popular_themes

    async def _log_activity(self, action: str, details: Dict[str, Any]):
        """Логирование активности пользователя"""
        activity_id = str(uuid.uuid4())
        activity = {
            'id': activity_id,
            'action': action,
            'details': details,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Сохраняем в Redis для быстрого доступа
        await redis_client.lpush("theme_activities", json.dumps(activity))
        await redis_client.ltrim("theme_activities", 0, 999)  # Храним последние 1000 активностей

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
theme_management_service = ThemeManagementService()
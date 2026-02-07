# Enhanced UI/UX System
# File: services/ui_ux_service/enhanced_ui_ux.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid

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

class NotificationType(Enum):
    MESSAGE = "message"
    MENTION = "mention"
    REACTION = "reaction"
    CALL = "call"
    TASK = "task"
    SYSTEM = "system"
    SECURITY = "security"

class NotificationPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class NotificationChannel(Enum):
    PUSH = "push"
    EMAIL = "email"
    SMS = "sms"
    IN_APP = "in_app"
    DESKTOP = "desktop"

class UIComponent(Enum):
    CHAT_INTERFACE = "chat_interface"
    CONTACT_LIST = "contact_list"
    SETTINGS_PANEL = "settings_panel"
    NOTIFICATION_CENTER = "notification_center"
    FILE_MANAGER = "file_manager"
    TASK_BOARD = "task_board"
    CALENDAR_VIEW = "calendar_view"
    CALL_INTERFACE = "call_interface"
    GAME_INTERFACE = "game_interface"

class UserInterfaceSetting(BaseModel):
    user_id: int
    component: UIComponent
    settings: Dict[str, Any]  # Настройки компонента
    updated_at: datetime = None

class UserNotificationPreference(BaseModel):
    user_id: int
    notification_type: NotificationType
    channels: List[NotificationChannel]
    priority: NotificationPriority
    enabled: bool = True
    mute_until: Optional[datetime] = None
    custom_sound: Optional[str] = None
    custom_vibration: Optional[str] = None
    updated_at: datetime = None

class Theme(BaseModel):
    id: str
    name: str
    type: ThemeType
    primary_color: str
    secondary_color: str
    background_color: str
    text_color: str
    accent_color: str
    created_at: datetime = None
    updated_at: datetime = None

class UserTheme(BaseModel):
    user_id: int
    theme_id: str
    applied_at: datetime = None

class EnhancedUIUXService:
    def __init__(self):
        self.default_themes = {
            "light": Theme(
                id="theme_light",
                name="Light Theme",
                type=ThemeType.LIGHT,
                primary_color="#007AFF",
                secondary_color="#5856D6",
                background_color="#FFFFFF",
                text_color="#000000",
                accent_color="#FF9500",
                created_at=datetime.utcnow()
            ),
            "dark": Theme(
                id="theme_dark",
                name="Dark Theme",
                type=ThemeType.DARK,
                primary_color="#0A84FF",
                secondary_color="#B586FF",
                background_color="#000000",
                text_color="#FFFFFF",
                accent_color="#FFCC00",
                created_at=datetime.utcnow()
            ),
            "black": Theme(
                id="theme_black",
                name="Black Theme",
                type=ThemeType.BLACK,
                primary_color="#0A84FF",
                secondary_color="#B586FF",
                background_color="#000000",
                text_color="#FFFFFF",
                accent_color="#FFCC00",
                created_at=datetime.utcnow()
            )
        }
        self.component_defaults = {
            UIComponent.CHAT_INTERFACE: {
                "font_size": "medium",
                "message_bubbles": True,
                "compact_mode": False,
                "show_avatars": True,
                "show_timestamps": True,
                "auto_expand_images": True,
                "show_typing_indicators": True
            },
            UIComponent.CONTACT_LIST: {
                "show_presence": True,
                "group_by_status": False,
                "show_last_seen": True,
                "show_avatar": True,
                "compact_view": False
            },
            UIComponent.SETTINGS_PANEL: {
                "layout": "vertical",
                "show_advanced": False,
                "auto_save": True
            },
            UIComponent.NOTIFICATION_CENTER: {
                "group_notifications": True,
                "show_preview": True,
                "auto_clear": False,
                "max_visible": 10
            },
            UIComponent.FILE_MANAGER: {
                "view_mode": "grid",
                "show_thumbnails": True,
                "auto_preview": True,
                "sort_order": "date_desc"
            },
            UIComponent.TASK_BOARD: {
                "view_mode": "kanban",
                "show_assignees": True,
                "show_due_dates": True,
                "auto_refresh": True
            },
            UIComponent.CALENDAR_VIEW: {
                "default_view": "month",
                "show_week_numbers": True,
                "work_week_only": False,
                "show_task_overlays": True
            },
            UIComponent.CALL_INTERFACE: {
                "show_participants_list": True,
                "show_participant_names": True,
                "mirror_my_video": False,
                "auto_focus_video": True
            },
            UIComponent.GAME_INTERFACE: {
                "show_scores": True,
                "show_timer": True,
                "auto_hint": False,
                "sound_effects": True
            }
        }

    async def initialize_default_themes(self):
        """Инициализация тем по умолчанию"""
        for theme in self.default_themes.values():
            await self._save_theme_to_db(theme)

    async def _save_theme_to_db(self, theme: Theme):
        """Сохранение темы в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO themes (
                    id, name, type, primary_color, secondary_color,
                    background_color, text_color, accent_color, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (id) DO UPDATE SET
                    name = $2, type = $3, primary_color = $4, secondary_color = $5,
                    background_color = $6, text_color = $7, accent_color = $8, updated_at = $10
                """,
                theme.id, theme.name, theme.type.value, theme.primary_color,
                theme.secondary_color, theme.background_color, theme.text_color,
                theme.accent_color, theme.created_at, theme.updated_at
            )

    async def set_user_theme(self, user_id: int, theme_id: str) -> bool:
        """Установка темы для пользователя"""
        # Проверяем, существует ли тема
        theme = await self.get_theme(theme_id)
        if not theme:
            return False

        user_theme = UserTheme(
            user_id=user_id,
            theme_id=theme_id,
            applied_at=datetime.utcnow()
        )

        # Сохраняем в базу данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_themes (user_id, theme_id, applied_at)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id) DO UPDATE SET
                    theme_id = $2, applied_at = $3
                """,
                user_theme.user_id, user_theme.theme_id, user_theme.applied_at
            )

        # Обновляем кэш
        await self._cache_user_theme(user_id, theme_id)

        # Уведомляем клиента об изменении темы
        await self._notify_theme_changed(user_id, theme)

        # Создаем запись активности
        await self._log_activity(user_id, "theme_changed", {
            "theme_id": theme_id,
            "theme_name": theme.name
        })

        return True

    async def get_user_theme(self, user_id: int) -> Optional[Theme]:
        """Получение темы пользователя"""
        # Сначала проверяем кэш
        cached_theme_id = await self._get_cached_user_theme(user_id)
        if cached_theme_id:
            return await self.get_theme(cached_theme_id)

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT theme_id FROM user_themes WHERE user_id = $1",
                user_id
            )

        if not row:
            # Возвращаем тему по умолчанию
            return self.default_themes["light"]

        theme_id = row['theme_id']
        theme = await self.get_theme(theme_id)

        # Кэшируем результат
        if theme:
            await self._cache_user_theme(user_id, theme.id)

        return theme

    async def get_theme(self, theme_id: str) -> Optional[Theme]:
        """Получение темы по ID"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, type, primary_color, secondary_color,
                       background_color, text_color, accent_color, created_at, updated_at
                FROM themes WHERE id = $1
                """,
                theme_id
            )

        if not row:
            return None

        return Theme(
            id=row['id'],
            name=row['name'],
            type=ThemeType(row['type']),
            primary_color=row['primary_color'],
            secondary_color=row['secondary_color'],
            background_color=row['background_color'],
            text_color=row['text_color'],
            accent_color=row['accent_color'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

    async def update_component_settings(self, user_id: int, component: UIComponent,
                                      settings: Dict[str, Any]) -> bool:
        """Обновление настроек компонента интерфейса"""
        user_setting = UserInterfaceSetting(
            user_id=user_id,
            component=component,
            settings=settings,
            updated_at=datetime.utcnow()
        )

        # Сохраняем в базу данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ui_component_settings (user_id, component, settings, updated_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, component) DO UPDATE SET
                    settings = $3, updated_at = $4
                """,
                user_setting.user_id, user_setting.component.value,
                json.dumps(user_setting.settings), user_setting.updated_at
            )

        # Обновляем кэш
        await self._cache_component_settings(user_id, component, settings)

        # Уведомляем клиента об изменении настроек
        await self._notify_component_settings_changed(user_id, component, settings)

        # Создаем запись активности
        await self._log_activity(user_id, "component_settings_updated", {
            "component": component.value,
            "settings_keys": list(settings.keys())
        })

        return True

    async def get_component_settings(self, user_id: int, 
                                   component: UIComponent) -> Dict[str, Any]:
        """Получение настроек компонента интерфейса"""
        # Сначала проверяем кэш
        cached_settings = await self._get_cached_component_settings(user_id, component)
        if cached_settings:
            return cached_settings

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT settings FROM ui_component_settings
                WHERE user_id = $1 AND component = $2
                """,
                user_id, component.value
            )

        if not row or not row['settings']:
            # Возвращаем настройки по умолчанию
            default_settings = self.component_defaults.get(component, {})
            return default_settings

        settings = json.loads(row['settings'])

        # Кэшируем результат
        await self._cache_component_settings(user_id, component, settings)

        return settings

    async def set_notification_preferences(self, user_id: int,
                                         notification_type: NotificationType,
                                         channels: List[NotificationChannel],
                                         priority: NotificationPriority,
                                         enabled: bool = True,
                                         custom_sound: Optional[str] = None,
                                         custom_vibration: Optional[str] = None) -> bool:
        """Установка настроек уведомлений"""
        preferences = UserNotificationPreference(
            user_id=user_id,
            notification_type=notification_type,
            channels=channels,
            priority=priority,
            enabled=enabled,
            custom_sound=custom_sound,
            custom_vibration=custom_vibration,
            updated_at=datetime.utcnow()
        )

        # Сохраняем в базу данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO notification_preferences (
                    user_id, notification_type, channels, priority, enabled,
                    custom_sound, custom_vibration, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (user_id, notification_type) DO UPDATE SET
                    channels = $3, priority = $4, enabled = $5,
                    custom_sound = $6, custom_vibration = $7, updated_at = $8
                """,
                preferences.user_id, preferences.notification_type.value,
                [ch.value for ch in preferences.channels], preferences.priority.value,
                preferences.enabled, preferences.custom_sound, preferences.custom_vibration,
                preferences.updated_at
            )

        # Обновляем кэш
        await self._cache_notification_preferences(user_id, notification_type, preferences)

        # Создаем запись активности
        await self._log_activity(user_id, "notification_preferences_updated", {
            "notification_type": notification_type.value,
            "channels": [ch.value for ch in channels],
            "priority": priority.value,
            "enabled": enabled
        })

        return True

    async def get_notification_preferences(self, user_id: int,
                                         notification_type: NotificationType) -> Optional[UserNotificationPreference]:
        """Получение настроек уведомлений"""
        # Сначала проверяем кэш
        cached_prefs = await self._get_cached_notification_preferences(user_id, notification_type)
        if cached_prefs:
            return cached_prefs

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT notification_type, channels, priority, enabled,
                       custom_sound, custom_vibration, updated_at
                FROM notification_preferences
                WHERE user_id = $1 AND notification_type = $2
                """,
                user_id, notification_type.value
            )

        if not row:
            # Возвращаем настройки по умолчанию
            default_prefs = UserNotificationPreference(
                user_id=user_id,
                notification_type=notification_type,
                channels=[NotificationChannel.PUSH, NotificationChannel.IN_APP],
                priority=NotificationPriority.MEDIUM,
                enabled=True,
                updated_at=datetime.utcnow()
            )
            return default_prefs

        preferences = UserNotificationPreference(
            user_id=user_id,
            notification_type=NotificationType(row['notification_type']),
            channels=[NotificationChannel(ch) for ch in row['channels']],
            priority=NotificationPriority(row['priority']),
            enabled=row['enabled'],
            custom_sound=row['custom_sound'],
            custom_vibration=row['custom_vibration'],
            updated_at=row['updated_at']
        )

        # Кэшируем результат
        await self._cache_notification_preferences(user_id, notification_type, preferences)

        return preferences

    async def get_all_notification_preferences(self, user_id: int) -> List[UserNotificationPreference]:
        """Получение всех настроек уведомлений пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT notification_type, channels, priority, enabled,
                       custom_sound, custom_vibration, updated_at
                FROM notification_preferences
                WHERE user_id = $1
                """,
                user_id
            )

        preferences = []
        for row in rows:
            pref = UserNotificationPreference(
                user_id=user_id,
                notification_type=NotificationType(row['notification_type']),
                channels=[NotificationChannel(ch) for ch in row['channels']],
                priority=NotificationPriority(row['priority']),
                enabled=row['enabled'],
                custom_sound=row['custom_sound'],
                custom_vibration=row['custom_vibration'],
                updated_at=row['updated_at']
            )
            preferences.append(pref)

        # Если нет настроек для некоторых типов, добавляем значения по умолчанию
        existing_types = {pref.notification_type for pref in preferences}
        for notification_type in NotificationType:
            if notification_type not in existing_types:
                default_pref = UserNotificationPreference(
                    user_id=user_id,
                    notification_type=notification_type,
                    channels=[NotificationChannel.PUSH, NotificationChannel.IN_APP],
                    priority=NotificationPriority.MEDIUM,
                    enabled=True,
                    updated_at=datetime.utcnow()
                )
                preferences.append(default_pref)

        return preferences

    async def mute_notifications(self, user_id: int, notification_type: NotificationType,
                               duration_minutes: int) -> bool:
        """Временное отключение уведомлений"""
        mute_until = datetime.utcnow() + timedelta(minutes=duration_minutes)

        async with db_pool.acquire() as conn:
            result = await conn.execute(
                """
                INSERT INTO notification_preferences (
                    user_id, notification_type, channels, priority, enabled, mute_until, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (user_id, notification_type) DO UPDATE SET
                    enabled = $5, mute_until = $6, updated_at = $7
                """,
                user_id, notification_type.value, 
                ['push', 'in_app'], 'medium', False, mute_until, datetime.utcnow()
            )

        # Обновляем кэш
        await self._invalidate_notification_preferences_cache(user_id, notification_type)

        # Создаем запись активности
        await self._log_activity(user_id, "notifications_muted", {
            "notification_type": notification_type.value,
            "duration_minutes": duration_minutes,
            "mute_until": mute_until.isoformat()
        })

        return True

    async def unmute_notifications(self, user_id: int, 
                                 notification_type: Optional[NotificationType] = None) -> bool:
        """Включение уведомлений"""
        if notification_type:
            # Включаем конкретный тип уведомлений
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE notification_preferences
                    SET enabled = true, mute_until = NULL, updated_at = $3
                    WHERE user_id = $1 AND notification_type = $2
                    """,
                    user_id, notification_type.value, datetime.utcnow()
                )

            # Обновляем кэш
            await self._invalidate_notification_preferences_cache(user_id, notification_type)
        else:
            # Включаем все уведомления пользователя
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE notification_preferences
                    SET enabled = true, mute_until = NULL, updated_at = $2
                    WHERE user_id = $1
                    """,
                    user_id, datetime.utcnow()
                )

            # Очищаем весь кэш уведомлений пользователя
            await self._invalidate_all_notification_preferences_cache(user_id)

        # Создаем запись активности
        await self._log_activity(user_id, "notifications_unmuted", {
            "notification_type": notification_type.value if notification_type else "all"
        })

        return True

    async def _cache_user_theme(self, user_id: int, theme_id: str):
        """Кэширование темы пользователя"""
        await redis_client.setex(f"user_theme:{user_id}", 3600, theme_id)

    async def _get_cached_user_theme(self, user_id: int) -> Optional[str]:
        """Получение темы пользователя из кэша"""
        cached = await redis_client.get(f"user_theme:{user_id}")
        return cached.decode() if cached else None

    async def _cache_component_settings(self, user_id: int, component: UIComponent, 
                                      settings: Dict[str, Any]):
        """Кэширование настроек компонента"""
        cache_key = f"component_settings:{user_id}:{component.value}"
        await redis_client.setex(cache_key, 1800, json.dumps(settings))

    async def _get_cached_component_settings(self, user_id: int, 
                                           component: UIComponent) -> Optional[Dict[str, Any]]:
        """Получение настроек компонента из кэша"""
        cache_key = f"component_settings:{user_id}:{component.value}"
        cached = await redis_client.get(cache_key)
        if cached:
            return json.loads(cached.decode())
        return None

    async def _cache_notification_preferences(self, user_id: int, 
                                            notification_type: NotificationType,
                                            preferences: UserNotificationPreference):
        """Кэширование настроек уведомлений"""
        cache_key = f"notification_prefs:{user_id}:{notification_type.value}"
        await redis_client.setex(cache_key, 1800, preferences.model_dump_json())

    async def _get_cached_notification_preferences(self, user_id: int, 
                                                 notification_type: NotificationType) -> Optional[UserNotificationPreference]:
        """Получение настроек уведомлений из кэша"""
        cache_key = f"notification_prefs:{user_id}:{notification_type.value}"
        cached = await redis_client.get(cache_key)
        if cached:
            return UserNotificationPreference(**json.loads(cached.decode()))
        return None

    async def _invalidate_notification_preferences_cache(self, user_id: int, 
                                                       notification_type: NotificationType):
        """Очистка кэша настроек уведомлений"""
        cache_key = f"notification_prefs:{user_id}:{notification_type.value}"
        await redis_client.delete(cache_key)

    async def _invalidate_all_notification_preferences_cache(self, user_id: int):
        """Очистка всего кэша настроек уведомлений пользователя"""
        # Используем шаблон для поиска всех ключей уведомлений пользователя
        pattern = f"notification_prefs:{user_id}:*"
        keys = await redis_client.keys(pattern)
        if keys:
            await redis_client.delete(*keys)

    async def _notify_theme_changed(self, user_id: int, theme: Theme):
        """Уведомление клиента об изменении темы"""
        notification = {
            'type': 'theme_changed',
            'theme': {
                'id': theme.id,
                'name': theme.name,
                'type': theme.type.value,
                'colors': {
                    'primary': theme.primary_color,
                    'secondary': theme.secondary_color,
                    'background': theme.background_color,
                    'text': theme.text_color,
                    'accent': theme.accent_color
                }
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем через WebSocket или Redis
        await redis_client.publish(f"user:{user_id}:ui_updates", json.dumps(notification))

    async def _notify_component_settings_changed(self, user_id: int, component: UIComponent,
                                               settings: Dict[str, Any]):
        """Уведомление клиента об изменении настроек компонента"""
        notification = {
            'type': 'component_settings_changed',
            'component': component.value,
            'settings': settings,
            'timestamp': datetime.utcnow().isoformat()
        }

        await redis_client.publish(f"user:{user_id}:ui_updates", json.dumps(notification))

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

    async def get_user_interface_settings(self, user_id: int) -> Dict[str, Any]:
        """Получение всех настроек интерфейса пользователя"""
        settings = {}

        # Получаем тему пользователя
        theme = await self.get_user_theme(user_id)
        settings['theme'] = theme.dict() if theme else self.default_themes["light"].dict()

        # Получаем настройки компонентов
        for component in UIComponent:
            component_settings = await self.get_component_settings(user_id, component)
            settings[component.value] = component_settings

        # Получаем настройки уведомлений
        notification_preferences = await self.get_all_notification_preferences(user_id)
        settings['notification_preferences'] = [
            pref.dict() for pref in notification_preferences
        ]

        return settings

    async def reset_component_settings(self, user_id: int, component: UIComponent) -> bool:
        """Сброс настроек компонента к значениям по умолчанию"""
        default_settings = self.component_defaults.get(component, {})
        
        return await self.update_component_settings(user_id, component, default_settings)

    async def reset_all_settings(self, user_id: int) -> bool:
        """Сброс всех настроек интерфейса к значениям по умолчанию"""
        # Сбрасываем тему
        await self.set_user_theme(user_id, "theme_light")

        # Сбрасываем настройки компонентов
        for component in UIComponent:
            await self.reset_component_settings(user_id, component)

        # Сбрасываем настройки уведомлений
        for notification_type in NotificationType:
            await self.set_notification_preferences(
                user_id, notification_type,
                [NotificationChannel.PUSH, NotificationChannel.IN_APP],
                NotificationPriority.MEDIUM
            )

        # Создаем запись активности
        await self._log_activity(user_id, "all_settings_reset", {})

        return True

    async def export_user_settings(self, user_id: int) -> Dict[str, Any]:
        """Экспорт настроек пользователя"""
        settings = await self.get_user_interface_settings(user_id)
        
        export_data = {
            'user_id': user_id,
            'exported_at': datetime.utcnow().isoformat(),
            'settings': settings
        }

        return export_data

    async def import_user_settings(self, user_id: int, settings_data: Dict[str, Any]) -> bool:
        """Импорт настроек пользователя"""
        try:
            # Устанавливаем тему
            if 'theme' in settings_data:
                theme_data = settings_data['theme']
                await self.set_user_theme(user_id, theme_data['id'])

            # Устанавливаем настройки компонентов
            for component_name, component_settings in settings_data.get('settings', {}).items():
                try:
                    component = UIComponent(component_name)
                    if isinstance(component_settings, dict):
                        await self.update_component_settings(user_id, component, component_settings)
                except ValueError:
                    # Неизвестный компонент
                    continue

            # Устанавливаем настройки уведомлений
            for pref_data in settings_data.get('notification_preferences', []):
                try:
                    notification_type = NotificationType(pref_data['notification_type'])
                    channels = [NotificationChannel(ch) for ch in pref_data['channels']]
                    priority = NotificationPriority(pref_data['priority'])
                    
                    await self.set_notification_preferences(
                        user_id, notification_type, channels, priority,
                        pref_data.get('enabled', True),
                        pref_data.get('custom_sound'),
                        pref_data.get('custom_vibration')
                    )
                except (ValueError, KeyError):
                    # Некорректные данные
                    continue

            # Создаем запись активности
            await self._log_activity(user_id, "settings_imported", {
                "components_count": len(settings_data.get('settings', {})),
                "notification_types_count": len(settings_data.get('notification_preferences', []))
            })

            return True
        except Exception as e:
            logger.error(f"Error importing user settings: {e}")
            return False

    async def get_themes_list(self) -> List[Theme]:
        """Получение списка всех доступных тем"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, type, primary_color, secondary_color,
                       background_color, text_color, accent_color, created_at, updated_at
                FROM themes
                ORDER BY created_at DESC
                """
            )

        themes = []
        for row in rows:
            theme = Theme(
                id=row['id'],
                name=row['name'],
                type=ThemeType(row['type']),
                primary_color=row['primary_color'],
                secondary_color=row['secondary_color'],
                background_color=row['background_color'],
                text_color=row['text_color'],
                accent_color=row['accent_color'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            themes.append(theme)

        return themes

    async def create_custom_theme(self, user_id: int, name: str, theme_data: Dict[str, str]) -> Optional[str]:
        """Создание пользовательской темы"""
        theme_id = f"custom_{user_id}_{uuid.uuid4().hex[:8]}"
        
        theme = Theme(
            id=theme_id,
            name=name,
            type=ThemeType.AUTO,  # Пользовательская тема
            primary_color=theme_data.get('primary_color', '#007AFF'),
            secondary_color=theme_data.get('secondary_color', '#5856D6'),
            background_color=theme_data.get('background_color', '#FFFFFF'),
            text_color=theme_data.get('text_color', '#000000'),
            accent_color=theme_data.get('accent_color', '#FF9500'),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем тему в базу данных
        await self._save_theme_to_db(theme)

        # Применяем тему для пользователя
        await self.set_user_theme(user_id, theme_id)

        # Создаем запись активности
        await self._log_activity(user_id, "custom_theme_created", {
            "theme_id": theme_id,
            "theme_name": name
        })

        return theme_id

    async def update_notification_preferences_batch(self, user_id: int,
                                                  preferences: List[Dict[str, Any]]) -> bool:
        """Обновление нескольких настроек уведомлений за раз"""
        try:
            async with db_pool.acquire() as conn:
                for pref_data in preferences:
                    notification_type = NotificationType(pref_data['type'])
                    channels = [NotificationChannel(ch) for ch in pref_data['channels']]
                    priority = NotificationPriority(pref_data['priority'])
                    enabled = pref_data.get('enabled', True)
                    
                    await conn.execute(
                        """
                        INSERT INTO notification_preferences (
                            user_id, notification_type, channels, priority, enabled, updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (user_id, notification_type) DO UPDATE SET
                            channels = $3, priority = $4, enabled = $5, updated_at = $6
                        """,
                        user_id, notification_type.value, [ch.value for ch in channels],
                        priority.value, enabled, datetime.utcnow()
                    )

            # Очищаем кэш
            await self._invalidate_all_notification_preferences_cache(user_id)

            # Создаем запись активности
            await self._log_activity(user_id, "notification_preferences_batch_updated", {
                "preferences_count": len(preferences)
            })

            return True
        except Exception as e:
            logger.error(f"Error updating notification preferences in batch: {e}")
            return False

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
enhanced_ui_ux_service = EnhancedUIUXService()
# Enhanced Notifications and Reminders System
# File: services/notification_service/enhanced_notifications.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum
import uuid

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class NotificationType(Enum):
    MESSAGE = "message"
    TASK_ASSIGNMENT = "task_assignment"
    TASK_UPDATE = "task_update"
    TASK_COMPLETION = "task_completion"
    POLL_RESULT = "poll_result"
    POLL_REMINDER = "poll_reminder"
    EVENT_REMINDER = "event_reminder"
    SYSTEM = "system"
    SECURITY = "security"
    MENTION = "mention"
    REACTION = "reaction"
    FILE_SHARED = "file_shared"
    CALL_INVITE = "call_invite"
    GAME_INVITE = "game_invite"
    AI_ASSISTANT = "ai_assistant"

class NotificationPriority(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

class NotificationStatus(Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"

class ReminderType(Enum):
    TIME_BASED = "time_based"
    EVENT_BASED = "event_based"
    LOCATION_BASED = "location_based"
    RECURRING = "recurring"

class Notification(BaseModel):
    id: str
    user_id: int
    type: NotificationType
    title: str
    body: str
    priority: NotificationPriority
    status: NotificationStatus
    data: Optional[Dict] = None  # Дополнительные данные
    scheduled_time: Optional[datetime] = None  # Для отложенных уведомлений
    expires_at: Optional[datetime] = None  # Время истечения
    created_at: datetime = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    channel_preferences: Optional[Dict] = None  # {'email': True, 'push': True, 'sms': False}

class Reminder(BaseModel):
    id: str
    user_id: int
    title: str
    description: str
    reminder_type: ReminderType
    trigger_time: Optional[datetime] = None  # Для time-based
    trigger_event: Optional[str] = None  # Для event-based
    location_coordinates: Optional[Dict] = None  # Для location-based
    recurring_pattern: Optional[str] = None  # Для recurring
    recurring_end: Optional[datetime] = None  # Для recurring
    notification_template: str  # Шаблон уведомления
    created_at: datetime = None
    updated_at: datetime = None
    is_active: bool = True

class NotificationPreference(BaseModel):
    user_id: int
    notification_type: NotificationType
    channels: List[str]  # ['email', 'push', 'sms', 'in_app']
    enabled: bool = True
    mute_until: Optional[datetime] = None  # Время до которого уведомления приглушены

class EnhancedNotificationService:
    def __init__(self):
        self.push_service = None
        self.email_service = None
        self.sms_service = None
        self.scheduler = NotificationScheduler()

    async def send_notification(self, user_id: int, title: str, body: str,
                               notification_type: NotificationType,
                               priority: NotificationPriority = NotificationPriority.NORMAL,
                               data: Optional[Dict] = None,
                               scheduled_time: Optional[datetime] = None,
                               expires_at: Optional[datetime] = None,
                               channels: Optional[List[str]] = None) -> Optional[str]:
        """Отправка уведомления пользователю"""
        notification_id = str(uuid.uuid4())

        # Проверяем предпочтения пользователя
        if not await self._should_notify_user(user_id, notification_type):
            return None

        # Создаем уведомление
        notification = Notification(
            id=notification_id,
            user_id=user_id,
            type=notification_type,
            title=title,
            body=body,
            priority=priority,
            status=NotificationStatus.PENDING,
            data=data,
            scheduled_time=scheduled_time,
            expires_at=expires_at,
            created_at=datetime.utcnow()
        )

        # Определяем каналы доставки
        if channels is None:
            channels = await self._get_user_channels(user_id, notification_type)
        notification.channel_preferences = {ch: True for ch in channels}

        # Если уведомление отложенное, планируем его
        if scheduled_time and scheduled_time > datetime.utcnow():
            await self.scheduler.schedule_notification(notification)
            return notification_id

        # Отправляем уведомление
        success = await self._deliver_notification(notification)

        if success:
            notification.status = NotificationStatus.SENT
            notification.sent_at = datetime.utcnow()
        else:
            notification.status = NotificationStatus.FAILED

        # Сохраняем уведомление в базу данных
        await self._save_notification(notification)

        # Добавляем в кэш
        await self._cache_notification(notification)

        return notification_id if success else None

    async def _should_notify_user(self, user_id: int, notification_type: NotificationType) -> bool:
        """Проверка, должен ли пользователь получать уведомления"""
        # Проверяем общие настройки уведомлений пользователя
        user_prefs = await self._get_user_notification_preferences(user_id)
        
        # Проверяем, не приглушены ли уведомления
        for pref in user_prefs:
            if pref.notification_type == notification_type:
                if not pref.enabled:
                    return False
                if pref.mute_until and datetime.utcnow() < pref.mute_until:
                    return False
                break
        else:
            # Если нет специфических настроек, проверяем общие
            if not any(p.notification_type == NotificationType.SYSTEM for p in user_prefs):
                return False

        return True

    async def _get_user_channels(self, user_id: int, notification_type: NotificationType) -> List[str]:
        """Получение предпочтительных каналов доставки уведомлений"""
        user_prefs = await self._get_user_notification_preferences(user_id)
        
        for pref in user_prefs:
            if pref.notification_type == notification_type:
                return pref.channels
        else:
            # Возвращаем каналы по умолчанию
            return ['push', 'in_app']

    async def _deliver_notification(self, notification: Notification) -> bool:
        """Доставка уведомления через все указанные каналы"""
        success = True
        
        # Доставка через push-уведомления
        if notification.channel_preferences.get('push', False):
            push_success = await self._send_push_notification(notification)
            success = success and push_success

        # Доставка через email
        if notification.channel_preferences.get('email', False):
            email_success = await self._send_email_notification(notification)
            success = success and email_success

        # Доставка через SMS
        if notification.channel_preferences.get('sms', False):
            sms_success = await self._send_sms_notification(notification)
            success = success and sms_success

        # Доставка через in-app
        if notification.channel_preferences.get('in_app', False):
            in_app_success = await self._send_in_app_notification(notification)
            success = success and in_app_success

        return success

    async def _send_push_notification(self, notification: Notification) -> bool:
        """Отправка push-уведомления"""
        try:
            # Получаем токены устройства пользователя
            device_tokens = await self._get_user_device_tokens(notification.user_id)
            
            if not device_tokens:
                return False

            # В реальном приложении здесь будет код для отправки через FCM/APNs
            # Для примера просто логируем
            for token in device_tokens:
                logger.info(f"Sending push notification to {token}: {notification.title}")
            
            return True
        except Exception as e:
            logger.error(f"Error sending push notification: {e}")
            return False

    async def _send_email_notification(self, notification: Notification) -> bool:
        """Отправка email-уведомления"""
        try:
            # Используем централизованную функцию отправки email с сервера
            from ..main import send_email_notification as server_send_email
            return await server_send_email(notification.user_id, notification.title, notification.body)
        except Exception as e:
            logger.error(f"Error sending email notification to user {notification.user_id}: {e}")
            return False

    async def _send_sms_notification(self, notification: Notification) -> bool:
        """Отправка SMS-уведомления"""
        try:
            # Используем централизованную функцию отправки SMS с сервера
            from ..main import send_sms_notification as server_send_sms
            sms_text = f"{notification.title[:50]} - {notification.body[:100]}"
            return await server_send_sms(notification.user_id, sms_text)
        except Exception as e:
            logger.error(f"Error sending SMS notification to user {notification.user_id}: {e}")
            return False

    async def _send_in_app_notification(self, notification: Notification) -> bool:
        """Отправка in-app уведомления"""
        try:
            # Отправляем через Redis канал
            notification_data = {
                'type': 'in_app_notification',
                'notification': notification.dict(),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            await redis_client.publish(f"user:{notification.user_id}:notifications", 
                                     json.dumps(notification_data))
            
            return True
        except Exception as e:
            logger.error(f"Error sending in-app notification: {e}")
            return False

    async def _save_notification(self, notification: Notification):
        """Сохранение уведомления в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO notifications (
                    id, user_id, type, title, body, priority, status,
                    data, scheduled_time, expires_at, created_at, sent_at,
                    delivered_at, read_at, channel_preferences
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                """,
                notification.id, notification.user_id, notification.type.value,
                notification.title, notification.body, notification.priority.value,
                notification.status.value, json.dumps(notification.data) if notification.data else None,
                notification.scheduled_time, notification.expires_at,
                notification.created_at, notification.sent_at,
                notification.delivered_at, notification.read_at,
                json.dumps(notification.channel_preferences) if notification.channel_preferences else None
            )

    async def _cache_notification(self, notification: Notification):
        """Кэширование уведомления"""
        await redis_client.setex(f"notification:{notification.id}", 300, 
                                notification.model_dump_json())

    async def create_reminder(self, user_id: int, title: str, description: str,
                             reminder_type: ReminderType,
                             trigger_time: Optional[datetime] = None,
                             trigger_event: Optional[str] = None,
                             location_coordinates: Optional[Dict] = None,
                             recurring_pattern: Optional[str] = None,
                             recurring_end: Optional[datetime] = None,
                             notification_template: str = "") -> Optional[str]:
        """Создание напоминания"""
        reminder_id = str(uuid.uuid4())

        reminder = Reminder(
            id=reminder_id,
            user_id=user_id,
            title=title,
            description=description,
            reminder_type=reminder_type,
            trigger_time=trigger_time,
            trigger_event=trigger_event,
            location_coordinates=location_coordinates,
            recurring_pattern=recurring_pattern,
            recurring_end=recurring_end,
            notification_template=notification_template,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем напоминание в базу данных
        await self._save_reminder(reminder)

        # Добавляем в кэш
        await self._cache_reminder(reminder)

        # Планируем напоминание
        await self.scheduler.schedule_reminder(reminder)

        return reminder_id

    async def _save_reminder(self, reminder: Reminder):
        """Сохранение напоминания в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO reminders (
                    id, user_id, title, description, reminder_type,
                    trigger_time, trigger_event, location_coordinates,
                    recurring_pattern, recurring_end, notification_template,
                    created_at, updated_at, is_active
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                """,
                reminder.id, reminder.user_id, reminder.title, reminder.description,
                reminder.reminder_type.value, reminder.trigger_time, reminder.trigger_event,
                json.dumps(reminder.location_coordinates) if reminder.location_coordinates else None,
                reminder.recurring_pattern, reminder.recurring_end,
                reminder.notification_template, reminder.created_at, reminder.updated_at,
                reminder.is_active
            )

    async def _cache_reminder(self, reminder: Reminder):
        """Кэширование напоминания"""
        await redis_client.setex(f"reminder:{reminder.id}", 300, 
                                reminder.model_dump_json())

    async def get_user_notifications(self, user_id: int, 
                                   status: Optional[NotificationStatus] = None,
                                   notification_type: Optional[NotificationType] = None,
                                   limit: int = 50, offset: int = 0,
                                   unread_only: bool = False) -> List[Notification]:
        """Получение уведомлений пользователя"""
        conditions = ["user_id = $1"]
        params = [user_id]
        param_idx = 2

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        if notification_type:
            conditions.append(f"type = ${param_idx}")
            params.append(notification_type.value)
            param_idx += 1

        if unread_only:
            conditions.append("read_at IS NULL")
        
        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT id, user_id, type, title, body, priority, status,
                   data, scheduled_time, expires_at, created_at, sent_at,
                   delivered_at, read_at, channel_preferences
            FROM notifications
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        notifications = []
        for row in rows:
            notification = Notification(
                id=row['id'],
                user_id=row['user_id'],
                type=NotificationType(row['type']),
                title=row['title'],
                body=row['body'],
                priority=NotificationPriority(row['priority']),
                status=NotificationStatus(row['status']),
                data=json.loads(row['data']) if row['data'] else None,
                scheduled_time=row['scheduled_time'],
                expires_at=row['expires_at'],
                created_at=row['created_at'],
                sent_at=row['sent_at'],
                delivered_at=row['delivered_at'],
                read_at=row['read_at'],
                channel_preferences=json.loads(row['channel_preferences']) if row['channel_preferences'] else None
            )
            notifications.append(notification)

        return notifications

    async def get_user_reminders(self, user_id: int, 
                               reminder_type: Optional[ReminderType] = None,
                               is_active: bool = True,
                               limit: int = 50, offset: int = 0) -> List[Reminder]:
        """Получение напоминаний пользователя"""
        conditions = ["user_id = $1"]
        params = [user_id]
        param_idx = 2

        if reminder_type:
            conditions.append(f"reminder_type = ${param_idx}")
            params.append(reminder_type.value)
            param_idx += 1

        if is_active is not None:
            conditions.append(f"is_active = ${param_idx}")
            params.append(is_active)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT id, user_id, title, description, reminder_type,
                   trigger_time, trigger_event, location_coordinates,
                   recurring_pattern, recurring_end, notification_template,
                   created_at, updated_at, is_active
            FROM reminders
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        reminders = []
        for row in rows:
            reminder = Reminder(
                id=row['id'],
                user_id=row['user_id'],
                title=row['title'],
                description=row['description'],
                reminder_type=ReminderType(row['reminder_type']),
                trigger_time=row['trigger_time'],
                trigger_event=row['trigger_event'],
                location_coordinates=json.loads(row['location_coordinates']) if row['location_coordinates'] else None,
                recurring_pattern=row['recurring_pattern'],
                recurring_end=row['recurring_end'],
                notification_template=row['notification_template'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                is_active=row['is_active']
            )
            reminders.append(reminder)

        return reminders

    async def mark_notification_as_read(self, notification_id: str, user_id: int) -> bool:
        """Отметка уведомления как прочитанного"""
        notification = await self._get_cached_notification(notification_id)
        if not notification:
            notification = await self._get_notification_from_db(notification_id)
            if not notification:
                return False

        # Проверяем, принадлежит ли уведомление пользователю
        if notification.user_id != user_id:
            return False

        # Обновляем статус
        notification.status = NotificationStatus.READ
        notification.read_at = datetime.utcnow()
        notification.updated_at = datetime.utcnow()

        # Сохраняем в базу данных
        await self._update_notification_in_db(notification)

        # Обновляем кэш
        await self._cache_notification(notification)

        # Уведомляем о прочтении
        await self._notify_notification_read(notification)

        return True

    async def _update_notification_in_db(self, notification: Notification):
        """Обновление уведомления в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE notifications SET
                    status = $2, read_at = $3, updated_at = $4
                WHERE id = $1
                """,
                notification.id, notification.status.value, 
                notification.read_at, notification.updated_at
            )

    async def _notify_notification_read(self, notification: Notification):
        """Уведомление о прочтении уведомления"""
        # Обновляем счетчики уведомлений пользователя
        await self._update_user_notification_stats(notification.user_id, 'read')

        # Отправляем событие в систему аналитики
        await self._log_notification_event(notification.id, 'read', notification.user_id)

        # Уменьшаем счетчик непрочитанных уведомлений в Redis
        unread_counter_key = f"user:{notification.user_id}:unread_notifications"
        await redis_client.decr(unread_counter_key)

        # Публикуем событие о прочтении уведомления
        event_data = {
            'event_type': 'notification_read',
            'notification_id': notification.id,
            'user_id': notification.user_id,
            'timestamp': datetime.utcnow().isoformat()
        }
        await redis_client.publish('notification_events', json.dumps(event_data))

        logger.info(f"Notification {notification.id} marked as read by user {notification.user_id}")

    async def _update_user_notification_stats(self, user_id: int, action: str):
        """Обновление статистики уведомлений пользователя"""
        stats_key = f"user:{user_id}:notification_stats"

        # Получаем текущую статистику
        current_stats = await redis_client.hgetall(stats_key)
        if not current_stats:
            current_stats = {}

        # Обновляем соответствующий счетчик
        counter_field = f"{action}_count"
        current_value = int(current_stats.get(counter_field, 0))
        await redis_client.hincrby(stats_key, counter_field, 1)

        # Обновляем время последнего действия
        await redis_client.hset(stats_key, 'last_action_time', datetime.utcnow().isoformat())

    async def _log_notification_event(self, notification_id: str, event_type: str, user_id: int):
        """Логирование события уведомления"""
        event_log = {
            'notification_id': notification_id,
            'event_type': event_type,
            'user_id': user_id,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Сохраняем в Redis для быстрого доступа
        event_key = f"notification_events:{notification_id}"
        await redis_client.lpush(event_key, json.dumps(event_log))
        await redis_client.expire(event_key, 86400 * 7)  # Храним 7 дней

        # Также сохраняем в базу данных для долгосрочного хранения
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO notification_events (
                    notification_id, event_type, user_id, timestamp
                ) VALUES ($1, $2, $3, $4)
                """,
                notification_id, event_type, user_id, datetime.utcnow()
            )

    async def _get_notification_from_db(self, notification_id: str) -> Optional[Notification]:
        """Получение уведомления из базы данных"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, user_id, type, title, body, priority, status,
                       data, scheduled_time, expires_at, created_at, sent_at,
                       delivered_at, read_at, channel_preferences
                FROM notifications WHERE id = $1
                """,
                notification_id
            )

        if not row:
            return None

        return Notification(
            id=row['id'],
            user_id=row['user_id'],
            type=NotificationType(row['type']),
            title=row['title'],
            body=row['body'],
            priority=NotificationPriority(row['priority']),
            status=NotificationStatus(row['status']),
            data=json.loads(row['data']) if row['data'] else None,
            scheduled_time=row['scheduled_time'],
            expires_at=row['expires_at'],
            created_at=row['created_at'],
            sent_at=row['sent_at'],
            delivered_at=row['delivered_at'],
            read_at=row['read_at'],
            channel_preferences=json.loads(row['channel_preferences']) if row['channel_preferences'] else None
        )

    async def _get_cached_notification(self, notification_id: str) -> Optional[Notification]:
        """Получение уведомления из кэша"""
        cached = await redis_client.get(f"notification:{notification_id}")
        if cached:
            return Notification(**json.loads(cached))
        return None

    async def _get_user_notification_preferences(self, user_id: int) -> List[NotificationPreference]:
        """Получение предпочтений уведомлений пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, notification_type, channels, enabled, mute_until
                FROM notification_preferences WHERE user_id = $1
                """,
                user_id
            )

        preferences = []
        for row in rows:
            pref = NotificationPreference(
                user_id=row['user_id'],
                notification_type=NotificationType(row['notification_type']),
                channels=json.loads(row['channels']) if row['channels'] else [],
                enabled=row['enabled'],
                mute_until=row['mute_until']
            )
            preferences.append(pref)

        return preferences

    async def _get_user_device_tokens(self, user_id: int) -> List[str]:
        """Получение токенов устройств пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT token FROM device_tokens WHERE user_id = $1 AND active = true
                """,
                user_id
            )

        return [row['token'] for row in rows]

    async def _get_user_email(self, user_id: int) -> Optional[str]:
        """Получение email пользователя"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT email FROM users WHERE id = $1
                """,
                user_id
            )

        return row['email'] if row and row['email'] else None

    async def _get_user_phone(self, user_id: int) -> Optional[str]:
        """Получение телефона пользователя"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT phone FROM users WHERE id = $1
                """,
                user_id
            )

        return row['phone'] if row and row['phone'] else None

    async def set_notification_preference(self, user_id: int, notification_type: NotificationType,
                                        channels: List[str], enabled: bool = True) -> bool:
        """Установка предпочтений уведомлений пользователя"""
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO notification_preferences (
                        user_id, notification_type, channels, enabled, created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (user_id, notification_type) 
                    DO UPDATE SET channels = $3, enabled = $4, updated_at = $6
                    """,
                    user_id, notification_type.value, json.dumps(channels), 
                    enabled, datetime.utcnow(), datetime.utcnow()
                )

            return True
        except Exception as e:
            logger.error(f"Error setting notification preference: {e}")
            return False

    async def mute_notifications(self, user_id: int, notification_type: NotificationType,
                               duration_minutes: int) -> bool:
        """Приглушение уведомлений на определенное время"""
        mute_until = datetime.utcnow() + timedelta(minutes=duration_minutes)

        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO notification_preferences (
                        user_id, notification_type, channels, enabled, mute_until, created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (user_id, notification_type) 
                    DO UPDATE SET mute_until = $5, updated_at = $7
                    """,
                    user_id, notification_type.value, "[]", True, 
                    mute_until, datetime.utcnow(), datetime.utcnow()
                )

            return True
        except Exception as e:
            logger.error(f"Error muting notifications: {e}")
            return False

    async def get_unread_count(self, user_id: int) -> int:
        """Получение количества непрочитанных уведомлений"""
        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM notifications 
                WHERE user_id = $1 AND read_at IS NULL AND status != 'failed'
                """,
                user_id
            )

        return count or 0

    async def bulk_send_notifications(self, notifications_data: List[Dict]) -> List[str]:
        """Массовая отправка уведомлений"""
        sent_ids = []

        for data in notifications_data:
            notification_id = await self.send_notification(**data)
            if notification_id:
                sent_ids.append(notification_id)

        return sent_ids

class NotificationScheduler:
    """Планировщик уведомлений и напоминаний"""
    
    def __init__(self):
        self.scheduled_notifications = {}
        self.scheduled_reminders = {}

    async def schedule_notification(self, notification: Notification):
        """Планирование отложенного уведомления"""
        if not notification.scheduled_time:
            return

        delay = (notification.scheduled_time - datetime.utcnow()).total_seconds()
        if delay <= 0:
            # Если время уже прошло, отправляем немедленно
            await self._execute_notification(notification)
            return

        # Сохраняем в Redis для планирования
        await redis_client.setex(
            f"scheduled_notification:{notification.id}",
            int(delay),
            notification.model_dump_json()
        )

        # Добавляем в очередь планировщика
        await redis_client.zadd(
            "notification_scheduler_queue",
            {notification.id: notification.scheduled_time.timestamp()}
        )

    async def schedule_reminder(self, reminder: Reminder):
        """Планирование напоминания"""
        if reminder.reminder_type == ReminderType.TIME_BASED and reminder.trigger_time:
            delay = (reminder.trigger_time - datetime.utcnow()).total_seconds()
            if delay > 0:
                # Сохраняем в Redis для планирования
                await redis_client.setex(
                    f"scheduled_reminder:{reminder.id}",
                    int(delay),
                    reminder.model_dump_json()
                )

                # Добавляем в очередь планировщика
                await redis_client.zadd(
                    "reminder_scheduler_queue",
                    {reminder.id: reminder.trigger_time.timestamp()}
                )
        elif reminder.reminder_type == ReminderType.EVENT_BASED:
            # Для event-based напоминаний регистрируем слушатель события
            await self._register_event_listener(reminder)
        elif reminder.reminder_type == ReminderType.RECURRING:
            # Для recurring напоминаний планируем первое срабатывание
            await self._schedule_recurring_reminder(reminder)

    async def _execute_notification(self, notification: Notification):
        """Выполнение запланированного уведомления"""
        success = await enhanced_notification_service._deliver_notification(notification)
        
        if success:
            notification.status = NotificationStatus.SENT
            notification.sent_at = datetime.utcnow()
        else:
            notification.status = NotificationStatus.FAILED

        # Сохраняем результат
        await enhanced_notification_service._save_notification(notification)

    async def _register_event_listener(self, reminder: Reminder):
        """Регистрация слушателя события для напоминания"""
        # В реальном приложении здесь будет регистрация слушателя
        # для определенного события
        event_key = f"event_listener:{reminder.trigger_event}:{reminder.user_id}"
        await redis_client.setex(
            event_key,
            7 * 24 * 60 * 60,  # 7 дней
            reminder.model_dump_json()
        )

    async def _schedule_recurring_reminder(self, reminder: Reminder):
        """Планирование повторяющегося напоминания"""
        # Вычисляем следующее время срабатывания
        next_trigger = self._calculate_next_occurrence(reminder)
        if next_trigger:
            # Обновляем время срабатывания
            reminder.trigger_time = next_trigger
            
            # Планируем следующее срабатывание
            await self.schedule_reminder(reminder)

    def _calculate_next_occurrence(self, reminder: Reminder) -> Optional[datetime]:
        """Вычисление следующего срабатывания повторяющегося напоминания"""
        if not reminder.trigger_time or not reminder.recurring_pattern:
            return None

        current_time = reminder.trigger_time
        pattern = reminder.recurring_pattern.lower()

        if pattern == "daily":
            return current_time + timedelta(days=1)
        elif pattern == "weekly":
            return current_time + timedelta(weeks=1)
        elif pattern == "monthly":
            # Простая реализация - добавляем 30 дней
            return current_time + timedelta(days=30)
        elif pattern == "yearly":
            return current_time + timedelta(days=365)
        else:
            # Для сложных паттернов (например, "every monday") 
            # потребуется более сложная логика
            return None

# Глобальный экземпляр для использования в приложении
enhanced_notification_service = EnhancedNotificationService()
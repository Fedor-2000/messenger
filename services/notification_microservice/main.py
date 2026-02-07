# Notification Microservice
# File: services/notification_microservice/main.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid

import asyncpg
import redis.asyncio as redis
from aiohttp import web
import aiohttp
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class NotificationType(Enum):
    MESSAGE = "message"
    MENTION = "mention"
    REACTION = "reaction"
    COMMENT = "comment"
    SHARE = "share"
    TASK_ASSIGNMENT = "task_assignment"
    TASK_UPDATE = "task_update"
    TASK_COMPLETION = "task_completion"
    FILE_UPLOADED = "file_uploaded"
    FILE_PROCESSED = "file_processed"
    CALL_INVITE = "call_invite"
    CALL_MISSED = "call_missed"
    POLL_RESULT = "poll_result"
    SYSTEM = "system"
    SECURITY = "security"
    SUBSCRIPTION = "subscription"
    GAME_INVITE = "game_invite"
    GAME_RESULT = "game_result"
    CALENDAR_EVENT = "calendar_event"
    CALENDAR_REMINDER = "calendar_reminder"

class NotificationPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class NotificationStatus(Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"

class NotificationChannel(Enum):
    PUSH = "push"
    EMAIL = "email"
    SMS = "sms"
    IN_APP = "in_app"
    WEBHOOK = "webhook"

class Notification(BaseModel):
    id: str
    user_id: int
    type: NotificationType
    title: str
    content: str
    priority: NotificationPriority
    status: NotificationStatus
    data: Optional[Dict[str, Any]] = None  # Дополнительные данные
    channels: List[NotificationChannel]  # Каналы доставки
    scheduled_time: Optional[datetime] = None  # Для отложенных уведомлений
    expires_at: Optional[datetime] = None  # Время истечения
    created_at: datetime = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    metadata: Optional[Dict] = None

class NotificationPreference(BaseModel):
    user_id: int
    notification_type: NotificationType
    channels: List[NotificationChannel]
    enabled: bool = True
    mute_until: Optional[datetime] = None  # Время до которого уведомления приглушены
    custom_settings: Optional[Dict[str, Any]] = None  # Пользовательские настройки

class NotificationTemplate(BaseModel):
    id: str
    name: str
    type: NotificationType
    title_template: str  # Шаблон заголовка с переменными
    content_template: str  # Шаблон содержания с переменными
    default_channels: List[NotificationChannel]
    default_priority: NotificationPriority
    variables: List[str]  # Переменные, используемые в шаблоне
    is_active: bool = True
    created_at: datetime = None
    updated_at: datetime = None

class NotificationService:
    def __init__(self):
        self.default_templates = {
            NotificationType.MESSAGE: NotificationTemplate(
                id="template_message",
                name="New Message Template",
                type=NotificationType.MESSAGE,
                title_template="New message from {sender_name}",
                content_template="{sender_name} sent you a message: {message_preview}",
                default_channels=[NotificationChannel.PUSH, NotificationChannel.IN_APP],
                default_priority=NotificationPriority.MEDIUM,
                variables=["sender_name", "message_preview"],
                created_at=datetime.utcnow()
            ),
            NotificationType.MENTION: NotificationTemplate(
                id="template_mention",
                name="Mention Template",
                type=NotificationType.MENTION,
                title_template="You were mentioned in {chat_name}",
                content_template="{sender_name} mentioned you in {chat_name}: {message_preview}",
                default_channels=[NotificationChannel.PUSH, NotificationChannel.IN_APP],
                default_priority=NotificationPriority.HIGH,
                variables=["sender_name", "chat_name", "message_preview"],
                created_at=datetime.utcnow()
            ),
            NotificationType.TASK_ASSIGNMENT: NotificationTemplate(
                id="template_task_assignment",
                name="Task Assignment Template",
                type=NotificationType.TASK_ASSIGNMENT,
                title_template="New task assigned: {task_title}",
                content_template="You have been assigned a new task: {task_title} by {assigner_name}",
                default_channels=[NotificationChannel.PUSH, NotificationChannel.EMAIL],
                default_priority=NotificationPriority.HIGH,
                variables=["task_title", "assigner_name"],
                created_at=datetime.utcnow()
            ),
            NotificationType.CALL_INVITE: NotificationTemplate(
                id="template_call_invite",
                name="Call Invite Template",
                type=NotificationType.CALL_INVITE,
                title_template="Call invitation from {caller_name}",
                content_template="{caller_name} is inviting you to a {call_type} call",
                default_channels=[NotificationChannel.PUSH, NotificationChannel.IN_APP],
                default_priority=NotificationPriority.URGENT,
                variables=["caller_name", "call_type"],
                created_at=datetime.utcnow()
            )
        }
        
        self.push_service = None
        self.email_service = None
        self.sms_service = None
        self.webhook_service = None

    async def initialize_services(self):
        """Инициализация сервисов уведомлений"""
        # Здесь будет инициализация push, email, sms сервисов
        import logging
        logging.info("Initializing notification services...")
        return True

    async def send_notification(self, user_id: int, notification_type: NotificationType,
                               title: str, content: str,
                               channels: List[NotificationChannel],
                               priority: NotificationPriority = NotificationPriority.MEDIUM,
                               data: Optional[Dict] = None,
                               scheduled_time: Optional[datetime] = None,
                               expires_at: Optional[datetime] = None,
                               metadata: Optional[Dict] = None) -> Optional[str]:
        """Отправка уведомления пользователю"""
        notification_id = str(uuid.uuid4())

        notification = Notification(
            id=notification_id,
            user_id=user_id,
            type=notification_type,
            title=title,
            content=content,
            priority=priority,
            status=NotificationStatus.PENDING,
            data=data or {},
            channels=channels,
            scheduled_time=scheduled_time,
            expires_at=expires_at,
            created_at=datetime.utcnow(),
            metadata=metadata or {}
        )

        # Проверяем, должен ли пользователь получать это уведомление
        if not await self._should_notify_user(user_id, notification_type):
            return None

        # Если уведомление должно быть отправлено немедленно
        if not scheduled_time:
            success = await self._deliver_notification(notification)
            if success:
                notification.status = NotificationStatus.SENT
                notification.sent_at = datetime.utcnow()
            else:
                notification.status = NotificationStatus.FAILED
        else:
            # Иначе планируем отправку
            await self._schedule_notification(notification)

        # Сохраняем уведомление в базу данных
        await self._save_notification(notification)

        # Добавляем в кэш
        await self._cache_notification(notification)

        # Создаем запись активности
        await self._log_activity(user_id, "notification_sent", {
            "notification_id": notification_id,
            "type": notification_type.value,
            "channels": [ch.value for ch in channels]
        })

        return notification_id

    async def _deliver_notification(self, notification: Notification) -> bool:
        """Доставка уведомления пользователю"""
        success_count = 0

        for channel in notification.channels:
            try:
                if channel == NotificationChannel.PUSH:
                    success = await self._send_push_notification(notification)
                elif channel == NotificationChannel.EMAIL:
                    success = await self._send_email_notification(notification)
                elif channel == NotificationChannel.SMS:
                    success = await self._send_sms_notification(notification)
                elif channel == NotificationChannel.IN_APP:
                    success = await self._send_in_app_notification(notification)
                elif channel == NotificationChannel.WEBHOOK:
                    success = await self._send_webhook_notification(notification)
                else:
                    success = False

                if success:
                    success_count += 1

            except Exception as e:
                logger.error(f"Error sending notification via {channel}: {e}")

        # Обновляем статус уведомления
        if success_count > 0:
            notification.status = NotificationStatus.SENT
            notification.sent_at = datetime.utcnow()
        else:
            notification.status = NotificationStatus.FAILED

        # Обновляем в базе данных
        await self._update_notification_status(notification)

        return success_count > 0

    async def _send_push_notification(self, notification: Notification) -> bool:
        """Отправка push-уведомления"""
        try:
            # Получаем токены устройства пользователя
            device_tokens = await self._get_user_device_tokens(notification.user_id)
            
            if not device_tokens:
                return False

            # В реальной системе здесь будет отправка через FCM/APNs
            # Для упрощения логируем
            for token in device_tokens:
                logger.info(f"Sending push notification to {token}: {notification.title}")

            return True
        except Exception as e:
            logger.error(f"Error sending push notification: {e}")
            return False

    async def _send_email_notification(self, notification: Notification) -> bool:
        """Отправка email-уведомления"""
        try:
            # Получаем email пользователя
            user_email = await self._get_user_email(notification.user_id)
            if not user_email:
                return False

            # В реальной системе здесь будет отправка через email-сервис
            logger.info(f"Sending email notification to {user_email}: {notification.title}")

            return True
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
            return False

    async def _send_sms_notification(self, notification: Notification) -> bool:
        """Отправка SMS-уведомления"""
        try:
            # Получаем телефон пользователя
            user_phone = await self._get_user_phone(notification.user_id)
            if not user_phone:
                return False

            # В реальной системе здесь будет отправка через SMS-сервис
            logger.info(f"Sending SMS notification to {user_phone}: {notification.title}")

            return True
        except Exception as e:
            logger.error(f"Error sending SMS notification: {e}")
            return False

    async def _send_in_app_notification(self, notification: Notification) -> bool:
        """Отправка in-app уведомления"""
        try:
            # Отправляем через WebSocket или Redis
            notification_data = {
                'type': 'in_app_notification',
                'notification': {
                    'id': notification.id,
                    'title': notification.title,
                    'content': notification.content,
                    'type': notification.type.value,
                    'priority': notification.priority.value,
                    'timestamp': notification.created_at.isoformat(),
                    'data': notification.data
                }
            }

            await redis_client.publish(f"user:{notification.user_id}:notifications", json.dumps(notification_data))
            return True
        except Exception as e:
            logger.error(f"Error sending in-app notification: {e}")
            return False

    async def _send_webhook_notification(self, notification: Notification) -> bool:
        """Отправка webhook-уведомления"""
        try:
            # Получаем URL вебхука пользователя
            webhook_url = await self._get_user_webhook_url(notification.user_id)
            if not webhook_url:
                return False

            # Подготавливаем данные для отправки
            payload = {
                'notification_id': notification.id,
                'user_id': notification.user_id,
                'type': notification.type.value,
                'title': notification.title,
                'content': notification.content,
                'priority': notification.priority.value,
                'data': notification.data,
                'timestamp': notification.created_at.isoformat()
            }

            # Отправляем через HTTP
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    return response.status == 200

        except Exception as e:
            logger.error(f"Error sending webhook notification: {e}")
            return False

    async def _get_user_device_tokens(self, user_id: int) -> List[str]:
        """Получение токенов устройств пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT token FROM user_device_tokens WHERE user_id = $1 AND active = true",
                user_id
            )

        return [row['token'] for row in rows]

    async def _get_user_email(self, user_id: int) -> Optional[str]:
        """Получение email пользователя"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT email FROM users WHERE id = $1",
                user_id
            )

        return row['email'] if row and row['email'] else None

    async def _get_user_phone(self, user_id: int) -> Optional[str]:
        """Получение телефона пользователя"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT phone FROM users WHERE id = $1",
                user_id
            )

        return row['phone'] if row and row['phone'] else None

    async def _get_user_webhook_url(self, user_id: int) -> Optional[str]:
        """Получение URL вебхука пользователя"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT webhook_url FROM user_settings WHERE user_id = $1",
                user_id
            )

        return row['webhook_url'] if row and row['webhook_url'] else None

    async def _schedule_notification(self, notification: Notification):
        """Планирование отправки уведомления"""
        if not notification.scheduled_time:
            return

        # Добавляем в очередь планировщика
        await redis_client.zadd(
            "scheduled_notifications",
            {notification.id: notification.scheduled_time.timestamp()}
        )

    async def _save_notification(self, notification: Notification):
        """Сохранение уведомления в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO notifications (
                    id, user_id, type, title, content, priority, status,
                    data, channels, scheduled_time, expires_at, created_at,
                    sent_at, delivered_at, read_at, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                """,
                notification.id, notification.user_id, notification.type.value,
                notification.title, notification.content, notification.priority.value,
                notification.status.value, json.dumps(notification.data) if notification.data else None,
                [ch.value for ch in notification.channels], notification.scheduled_time,
                notification.expires_at, notification.created_at, notification.sent_at,
                notification.delivered_at, notification.read_at,
                json.dumps(notification.metadata) if notification.metadata else None
            )

    async def _update_notification_status(self, notification: Notification):
        """Обновление статуса уведомления"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE notifications SET
                    status = $2, sent_at = $3, delivered_at = $4, read_at = $5, updated_at = $6
                WHERE id = $1
                """,
                notification.id, notification.status.value, notification.sent_at,
                notification.delivered_at, notification.read_at, datetime.utcnow()
            )

    async def _cache_notification(self, notification: Notification):
        """Кэширование уведомления"""
        await redis_client.setex(f"notification:{notification.id}", 300, notification.model_dump_json())

    async def _get_cached_notification(self, notification_id: str) -> Optional[Notification]:
        """Получение уведомления из кэша"""
        cached = await redis_client.get(f"notification:{notification_id}")
        if cached:
            return Notification(**json.loads(cached.decode()))
        return None

    async def get_user_notifications(self, user_id: int, 
                                   notification_type: Optional[NotificationType] = None,
                                   status: Optional[NotificationStatus] = None,
                                   limit: int = 50, offset: int = 0) -> List[Notification]:
        """Получение уведомлений пользователя"""
        conditions = ["user_id = $1"]
        params = [user_id]
        param_idx = 2

        if notification_type:
            conditions.append(f"type = ${param_idx}")
            params.append(notification_type.value)
            param_idx += 1

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, user_id, type, title, content, priority, status,
                   data, channels, scheduled_time, expires_at, created_at,
                   sent_at, delivered_at, read_at, metadata
            FROM notifications
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        notifications = []
        for row in rows:
            notification = Notification(
                id=row['id'],
                user_id=row['user_id'],
                type=NotificationType(row['type']),
                title=row['title'],
                content=row['content'],
                priority=NotificationPriority(row['priority']),
                status=NotificationStatus(row['status']),
                data=json.loads(row['data']) if row['data'] else None,
                channels=[NotificationChannel(ch) for ch in row['channels']],
                scheduled_time=row['scheduled_time'],
                expires_at=row['expires_at'],
                created_at=row['created_at'],
                sent_at=row['sent_at'],
                delivered_at=row['delivered_at'],
                read_at=row['read_at'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None
            )
            notifications.append(notification)

        return notifications

    async def mark_notification_as_read(self, notification_id: str, user_id: int) -> bool:
        """Отметка уведомления как прочитанного"""
        notification = await self._get_cached_notification(notification_id)
        if not notification:
            # Получаем из базы данных
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT id, user_id FROM notifications WHERE id = $1",
                    notification_id
                )
            
            if not row or row['user_id'] != user_id:
                return False
            
            notification = Notification(id=row['id'], user_id=row['user_id'])
        elif notification.user_id != user_id:
            return False

        # Обновляем статус в базе данных
        async with db_pool.acquire() as conn:
            result = await conn.fetchval(
                """
                UPDATE notifications SET status = $1, read_at = $2
                WHERE id = $3 AND user_id = $4
                RETURNING id
                """,
                NotificationStatus.READ.value, datetime.utcnow(), notification_id, user_id
            )

        if result:
            # Обновляем в кэше
            await self._update_cached_notification_status(notification_id, NotificationStatus.READ)
            
            # Уменьшаем счетчик непрочитанных уведомлений
            await self._decrement_unread_count(user_id)
            
            return True

        return False

    async def _update_cached_notification_status(self, notification_id: str, status: NotificationStatus):
        """Обновление статуса уведомления в кэше"""
        cached = await self._get_cached_notification(notification_id)
        if cached:
            cached.status = status
            cached.read_at = datetime.utcnow() if status == NotificationStatus.READ else None
            await redis_client.setex(f"notification:{notification_id}", 300, 
                                   cached.model_dump_json())

    async def _decrement_unread_count(self, user_id: int):
        """Уменьшение счетчика непрочитанных уведомлений"""
        await redis_client.decr(f"unread_notifications_count:{user_id}")

    async def get_unread_count(self, user_id: int) -> int:
        """Получение количества непрочитанных уведомлений"""
        # Сначала проверяем кэш
        cached_count = await redis_client.get(f"unread_notifications_count:{user_id}")
        if cached_count is not None:
            return int(cached_count)

        # Если в кэше нет, получаем из базы данных
        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM notifications
                WHERE user_id = $1 AND status != $2
                """,
                user_id, NotificationStatus.READ.value
            )

        count = count or 0

        # Кэшируем результат на 5 минут
        await redis_client.setex(f"unread_notifications_count:{user_id}", 300, count)

        return count

    async def set_notification_preferences(self, user_id: int, notification_type: NotificationType,
                                         channels: List[NotificationChannel], enabled: bool = True,
                                         mute_until: Optional[datetime] = None,
                                         custom_settings: Optional[Dict] = None) -> bool:
        """Установка настроек уведомлений для пользователя"""
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO notification_preferences (
                        user_id, notification_type, channels, enabled, mute_until, custom_settings, created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (user_id, notification_type)
                    DO UPDATE SET
                        channels = $3, enabled = $4, mute_until = $5, custom_settings = $6, updated_at = $8
                    """,
                    user_id, notification_type.value, [ch.value for ch in channels],
                    enabled, mute_until, json.dumps(custom_settings) if custom_settings else None,
                    datetime.utcnow(), datetime.utcnow()
                )

            # Удаляем из кэша, чтобы обновить при следующем запросе
            await redis_client.delete(f"notification_preferences:{user_id}")

            return True
        except Exception as e:
            logger.error(f"Error setting notification preferences: {e}")
            return False

    async def get_notification_preferences(self, user_id: int, 
                                         notification_type: Optional[NotificationType] = None) -> List[NotificationPreference]:
        """Получение настроек уведомлений пользователя"""
        # Сначала проверяем кэш
        cache_key = f"notification_preferences:{user_id}"
        if notification_type:
            cache_key += f":{notification_type.value}"
        
        cached = await redis_client.get(cache_key)
        if cached:
            return [NotificationPreference(**item) for item in json.loads(cached)]

        conditions = ["user_id = $1"]
        params = [user_id]
        param_idx = 2

        if notification_type:
            conditions.append(f"notification_type = ${param_idx}")
            params.append(notification_type.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT user_id, notification_type, channels, enabled, mute_until, custom_settings
            FROM notification_preferences
            WHERE {where_clause}
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        preferences = []
        for row in rows:
            pref = NotificationPreference(
                user_id=row['user_id'],
                notification_type=NotificationType(row['notification_type']),
                channels=[NotificationChannel(ch) for ch in row['channels']],
                enabled=row['enabled'],
                mute_until=row['mute_until'],
                custom_settings=json.loads(row['custom_settings']) if row['custom_settings'] else None
            )
            preferences.append(pref)

        # Кэшируем результат
        await redis_client.setex(cache_key, 600, json.dumps([p.dict() for p in preferences]))

        return preferences

    async def _should_notify_user(self, user_id: int, notification_type: NotificationType) -> bool:
        """Проверка, должен ли пользователь получать уведомление"""
        # Получаем настройки уведомлений пользователя
        user_prefs = await self.get_notification_preferences(user_id)

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

    async def _process_scheduled_notifications(self):
        """Обработка запланированных уведомлений"""
        current_time = datetime.utcnow().timestamp()
        
        # Получаем все уведомления, время которых наступило
        scheduled_ids = await redis_client.zrangebyscore(
            "scheduled_notifications", 0, current_time
        )

        for notification_id in scheduled_ids:
            # Получаем уведомление из базы данных
            notification = await self._get_cached_notification(notification_id)
            if not notification:
                async with db_pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT * FROM notifications WHERE id = $1",
                        notification_id
                    )
                
                if not row:
                    continue
                
                notification = Notification(
                    id=row['id'],
                    user_id=row['user_id'],
                    type=NotificationType(row['type']),
                    title=row['title'],
                    content=row['content'],
                    priority=NotificationPriority(row['priority']),
                    status=NotificationStatus(row['status']),
                    data=json.loads(row['data']) if row['data'] else None,
                    channels=[NotificationChannel(ch) for ch in row['channels']],
                    scheduled_time=row['scheduled_time'],
                    expires_at=row['expires_at'],
                    created_at=row['created_at'],
                    sent_at=row['sent_at'],
                    delivered_at=row['delivered_at'],
                    read_at=row['read_at'],
                    metadata=json.loads(row['metadata']) if row['metadata'] else None
                )

            # Отправляем уведомление
            await self._deliver_notification(notification)

            # Удаляем из очереди
            await redis_client.zrem("scheduled_notifications", notification_id)

    async def bulk_send_notifications(self, notifications_data: List[Dict]) -> List[str]:
        """Массовая отправка уведомлений"""
        sent_ids = []

        for data in notifications_data:
            notification_id = await self.send_notification(**data)
            if notification_id:
                sent_ids.append(notification_id)

        return sent_ids

    async def create_notification_template(self, name: str, notification_type: NotificationType,
                                         title_template: str, content_template: str,
                                         default_channels: List[NotificationChannel],
                                         default_priority: NotificationPriority,
                                         variables: List[str]) -> Optional[str]:
        """Создание шаблона уведомления"""
        template_id = str(uuid.uuid4())

        template = NotificationTemplate(
            id=template_id,
            name=name,
            type=notification_type,
            title_template=title_template,
            content_template=content_template,
            default_channels=default_channels,
            default_priority=default_priority,
            variables=variables,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем шаблон в базу данных
        await self._save_notification_template(template)

        # Добавляем в кэш
        await self._cache_notification_template(template)

        return template_id

    async def _save_notification_template(self, template: NotificationTemplate):
        """Сохранение шаблона уведомления в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO notification_templates (
                    id, name, type, title_template, content_template, default_channels,
                    default_priority, variables, is_active, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                template.id, template.name, template.type.value,
                template.title_template, template.content_template,
                [ch.value for ch in template.default_channels],
                template.default_priority.value, template.variables,
                template.is_active, template.created_at, template.updated_at
            )

    async def _cache_notification_template(self, template: NotificationTemplate):
        """Кэширование шаблона уведомления"""
        await redis_client.setex(f"notification_template:{template.id}", 3600, template.model_dump_json())

    async def _get_cached_notification_template(self, template_id: str) -> Optional[NotificationTemplate]:
        """Получение шаблона уведомления из кэша"""
        cached = await redis_client.get(f"notification_template:{template_id}")
        if cached:
            return NotificationTemplate(**json.loads(cached.decode()))
        return None

    async def get_notification_template(self, template_id: str) -> Optional[NotificationTemplate]:
        """Получение шаблона уведомления"""
        # Сначала проверяем кэш
        cached_template = await self._get_cached_notification_template(template_id)
        if cached_template:
            return cached_template

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, type, title_template, content_template, default_channels,
                       default_priority, variables, is_active, created_at, updated_at
                FROM notification_templates WHERE id = $1
                """,
                template_id
            )

        if not row:
            return None

        template = NotificationTemplate(
            id=row['id'],
            name=row['name'],
            type=NotificationType(row['type']),
            title_template=row['title_template'],
            content_template=row['content_template'],
            default_channels=[NotificationChannel(ch) for ch in row['default_channels']],
            default_priority=NotificationPriority(row['default_priority']),
            variables=row['variables'] or [],
            is_active=row['is_active'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

        # Кэшируем шаблон
        await self._cache_notification_template(template)

        return template

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
notification_service = NotificationService()
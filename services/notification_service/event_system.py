# Notification and Event System
# File: services/notification_service/event_system.py

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import uuid
import aiohttp
from pydantic import BaseModel

import asyncpg
import redis.asyncio as redis

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
    metadata: Optional[Dict[str, Any]] = None

class Event(BaseModel):
    id: str
    type: str
    source: str  # Источник события (например, 'chat_service', 'file_service')
    actor_id: Optional[int] = None  # ID пользователя, вызвавшего событие
    target_id: Optional[str] = None  # ID объекта, к которому относится событие
    target_type: Optional[str] = None  # Тип объекта ('user', 'chat', 'message', etc.)
    data: Dict[str, Any]  # Дополнительные данные события
    created_at: datetime = None

class Subscription(BaseModel):
    id: str
    user_id: int
    event_type: str
    notification_types: List[NotificationType]
    channels: List[NotificationChannel]
    filters: Optional[Dict[str, Any]] = None  # Фильтры для событий
    is_active: bool = True
    created_at: datetime = None
    updated_at: datetime = None

class NotificationPreferences(BaseModel):
    user_id: int
    notification_type: NotificationType
    channels: List[NotificationChannel]
    enabled: bool = True
    mute_until: Optional[datetime] = None  # Время до которого уведомления приглушены
    custom_settings: Optional[Dict[str, Any]] = None  # Пользовательские настройки

class EventSystem:
    def __init__(self):
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.notification_templates: Dict[str, str] = {}
        self.push_service = None
        self.email_service = None
        self.sms_service = None
        self.webhook_service = None

    async def initialize_services(self):
        """Инициализация сервисов уведомлений"""
        # Инициализация push-уведомлений (Firebase Cloud Messaging)
        try:
            from aiohttp import ClientSession
            self.push_service = ClientSession()
            logger.info("Push notification service initialized")
        except ImportError:
            logger.warning("Push notification service could not be initialized")
            self.push_service = None

        # Инициализация email-уведомлений
        try:
            import aiosmtplib
            self.email_service = aiosmtplib.SMTP()
            logger.info("Email notification service initialized")
        except ImportError:
            logger.warning("Email notification service could not be initialized")
            self.email_service = None

        # Инициализация SMS-уведомлений
        try:
            # В реальном приложении здесь будет инициализация SMS-провайдера
            # Например, Twilio или другого сервиса
            # Определяем провайдера SMS-услуг на основе конфигурации
            sms_provider = os.getenv('SMS_PROVIDER', 'twilio')
            self.sms_service = {
                'initialized': True,
                'provider': sms_provider,
                'configured': self._is_sms_provider_configured(sms_provider)
            }
            logger.info("SMS notification service initialized")
        except Exception as e:
            logger.warning(f"SMS notification service could not be initialized: {e}")

    def _is_sms_provider_configured(self, provider: str) -> bool:
        """Проверка, настроен ли провайдер SMS-услуг"""
        if provider == 'twilio':
            return all([
                os.getenv('TWILIO_ACCOUNT_SID'),
                os.getenv('TWILIO_AUTH_TOKEN'),
                os.getenv('TWILIO_PHONE_NUMBER')
            ])
        elif provider == 'aws_sns':
            return all([
                os.getenv('AWS_ACCESS_KEY_ID'),
                os.getenv('AWS_SECRET_ACCESS_KEY')
            ])
        elif provider == 'fake':
            return True  # Для тестирования всегда доступен
        else:
            return False

        # Инициализация webhook-уведомлений
        try:
            self.webhook_service = ClientSession()
            logger.info("Webhook notification service initialized")
        except Exception as e:
            logger.warning(f"Webhook notification service could not be initialized: {e}")
            self.webhook_service = None

        # Инициализация внутренних очередей и каналов
        await self._setup_notification_queues()
        await self._setup_broadcast_channels()

        logger.info("All notification services initialized")

    async def _setup_notification_queues(self):
        """Настройка очередей уведомлений"""
        # Создаем очереди для разных типов уведомлений
        queues = [
            'urgent_notifications',
            'standard_notifications',
            'bulk_notifications',
            'scheduled_notifications'
        ]

        for queue in queues:
            # В Redis создаем очередь с помощью списка
            # Это позволит обрабатывать уведомления в порядке очереди
            await redis_client.exists(f"queue:{queue}")

        logger.info("Notification queues setup completed")

    async def _setup_broadcast_channels(self):
        """Настройка широковещательных каналов"""
        # Подготавливаем каналы для вещания уведомлений
        channels = [
            'system_alerts',
            'maintenance_notices',
            'security_updates'
        ]

        for channel in channels:
            # Помечаем канал как активный
            await redis_client.setex(f"channel:{channel}:active", 86400, "true")

        logger.info("Broadcast channels setup completed")

    async def subscribe_to_event(self, user_id: int, event_type: str,
                                notification_types: List[NotificationType],
                                channels: List[NotificationChannel],
                                filters: Optional[Dict] = None) -> str:
        """Подписка пользователя на событие"""
        subscription_id = str(uuid.uuid4())

        subscription = Subscription(
            id=subscription_id,
            user_id=user_id,
            event_type=event_type,
            notification_types=notification_types,
            channels=channels,
            filters=filters,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем подписку в базу данных
        await self._save_subscription(subscription)

        # Добавляем в кэш
        await self._cache_subscription(subscription)

        return subscription_id

    async def unsubscribe_from_event(self, subscription_id: str, user_id: int) -> bool:
        """Отписка от события"""
        subscription = await self._get_subscription(subscription_id)
        if not subscription or subscription.user_id != user_id:
            return False

        # Удаляем из базы данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM event_subscriptions WHERE id = $1",
                subscription_id
            )

        # Удаляем из кэша
        await self._uncache_subscription(subscription_id)

        return True

    async def emit_event(self, event_type: str, source: str, actor_id: Optional[int] = None,
                        target_id: Optional[str] = None, target_type: Optional[str] = None,
                        data: Optional[Dict] = None) -> str:
        """Генерация события"""
        event_id = str(uuid.uuid4())

        event = Event(
            id=event_id,
            type=event_type,
            source=source,
            actor_id=actor_id,
            target_id=target_id,
            target_type=target_type,
            data=data or {},
            created_at=datetime.utcnow()
        )

        # Сохраняем событие в базу данных
        await self._save_event(event)

        # Проверяем подписки и отправляем уведомления
        await self._process_event_subscriptions(event)

        # Вызываем зарегистрированные обработчики событий
        await self._emit_to_handlers(event)

        # Публикуем событие в Redis для других сервисов
        await self._publish_event_to_redis(event)

        return event_id

    async def _save_event(self, event: Event):
        """Сохранение события в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO events (
                    id, type, source, actor_id, target_id, target_type, data, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                event.id, event.type, event.source, event.actor_id,
                event.target_id, event.target_type,
                json.dumps(event.data), event.created_at
            )

    async def _process_event_subscriptions(self, event: Event):
        """Обработка подписок на событие"""
        # Получаем все подписки на этот тип события
        subscriptions = await self._get_subscriptions_for_event(event.type)

        for subscription in subscriptions:
            # Проверяем фильтры
            if not await self._passes_filters(event, subscription.filters):
                continue

            # Проверяем права доступа
            if not await self._can_receive_notification(subscription.user_id, event):
                continue

            # Создаем уведомления для всех типов уведомлений в подписке
            for notification_type in subscription.notification_types:
                notification_id = await self._create_notification(
                    user_id=subscription.user_id,
                    notification_type=notification_type,
                    event=event,
                    channels=subscription.channels
                )

    async def _create_notification(self, user_id: int, notification_type: NotificationType,
                                  event: Event, channels: List[NotificationChannel]) -> Optional[str]:
        """Создание уведомления на основе события"""
        # Генерируем заголовок и содержание уведомления на основе шаблона
        title, content = await self._generate_notification_content(notification_type, event)

        notification_id = str(uuid.uuid4())

        notification = Notification(
            id=notification_id,
            user_id=user_id,
            type=notification_type,
            title=title,
            content=content,
            priority=self._determine_priority(notification_type),
            status=NotificationStatus.PENDING,
            channels=channels,
            data=event.data,
            created_at=datetime.utcnow()
        )

        # Проверяем, должен ли пользователь получать это уведомление
        if not await self._should_notify_user(user_id, notification_type):
            return None

        # Если уведомление должно быть отправлено немедленно
        if not await self._requires_delay(notification, user_id):
            await self._send_notification(notification)
        else:
            # Иначе планируем отправку
            await self._schedule_notification(notification)

        # Сохраняем уведомление в базу данных
        await self._save_notification(notification)

        # Добавляем в кэш
        await self._cache_notification(notification)

        return notification_id

    async def _send_notification(self, notification: Notification):
        """Отправка уведомления пользователю"""
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

    async def _send_push_notification(self, notification: Notification) -> bool:
        """Отправка push-уведомления"""
        try:
            # Получаем токены устройства пользователя
            device_tokens = await self._get_user_device_tokens(notification.user_id)
            
            if not device_tokens:
                return False

            # В реальной системе здесь будет вызов сервиса push-уведомлений (Firebase, APNs и т.д.)
            # Для примера используем условную реализацию
            for token in device_tokens:
                # Отправляем уведомление через push-сервис
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
            channel = f"user:{notification.user_id}:notifications"
            notification_data = {
                'id': notification.id,
                'type': notification.type.value,
                'title': notification.title,
                'content': notification.content,
                'priority': notification.priority.value,
                'data': notification.data,
                'timestamp': notification.created_at.isoformat()
            }

            await redis_client.publish(channel, json.dumps(notification_data))
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

    def _determine_priority(self, notification_type: NotificationType) -> NotificationPriority:
        """Определение приоритета уведомления"""
        priority_mapping = {
            NotificationType.CALL_INVITE: NotificationPriority.URGENT,
            NotificationType.CALL_MISSED: NotificationPriority.HIGH,
            NotificationType.MENTION: NotificationPriority.HIGH,
            NotificationType.TASK_ASSIGNMENT: NotificationPriority.HIGH,
            NotificationType.SECURITY: NotificationPriority.URGENT,
            NotificationType.SYSTEM: NotificationPriority.MEDIUM,
            NotificationType.MESSAGE: NotificationPriority.MEDIUM,
            NotificationType.REACTION: NotificationPriority.LOW,
            NotificationType.COMMENT: NotificationPriority.LOW
        }

        return priority_mapping.get(notification_type, NotificationPriority.MEDIUM)

    async def _should_notify_user(self, user_id: int, notification_type: NotificationType) -> bool:
        """Проверка, должен ли пользователь получать уведомление"""
        # Проверяем общие настройки уведомлений пользователя
        user_prefs = await self._get_user_notification_preferences(user_id)

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

    async def _requires_delay(self, event: Event, user_id: int) -> bool:
        """Проверка, требуется ли задержка уведомления (например, для дайджестов)"""
        # В реальной системе здесь будет проверка настройки пользователя
        # о получении дайджестов вместо мгновенных уведомлений
        return False

    async def _passes_filters(self, event: Event, filters: Optional[Dict]) -> bool:
        """Проверка, проходит ли событие фильтры подписки"""
        if not filters:
            return True

        # Простая реализация фильтрации
        for key, expected_value in filters.items():
            actual_value = event.data.get(key)
            if actual_value != expected_value:
                return False

        return True

    async def _can_receive_notification(self, user_id: int, event: Event) -> bool:
        """Проверка, может ли пользователь получать уведомление о событии"""
        # В реальной системе здесь будет проверка прав доступа
        # Например, проверка, состоит ли пользователь в чате, если событие связано с чатом
        return True

    async def _generate_notification_content(self, notification_type: NotificationType, 
                                           event: Event) -> tuple[str, str]:
        """Генерация содержания уведомления"""
        # Получаем шаблон уведомления
        template = self._get_notification_template(notification_type)

        # Заменяем переменные в шаблоне данными из события
        title = template['title']
        content = template['content']

        # Пример замены переменных (в реальной системе будет более сложная логика)
        if '{actor}' in title or '{actor}' in content:
            actor_name = await self._get_user_display_name(event.actor_id) if event.actor_id else 'Someone'
            title = title.replace('{actor}', actor_name)
            content = content.replace('{actor}', actor_name)

        if '{target}' in title or '{target}' in content:
            target_name = event.data.get('target_name', 'something')
            title = title.replace('{target}', target_name)
            content = content.replace('{target}', target_name)

        return title, content

    def _get_notification_template(self, notification_type: NotificationType) -> Dict[str, str]:
        """Получение шаблона уведомления"""
        templates = {
            NotificationType.MESSAGE: {
                'title': 'New Message',
                'content': '{actor} sent you a message'
            },
            NotificationType.MENTION: {
                'title': 'You were mentioned',
                'content': '{actor} mentioned you in {target}'
            },
            NotificationType.REACTION: {
                'title': 'New Reaction',
                'content': '{actor} reacted to your message'
            },
            NotificationType.CALL_INVITE: {
                'title': 'Call Invitation',
                'content': '{actor} invited you to a call'
            },
            NotificationType.TASK_ASSIGNMENT: {
                'title': 'New Task Assigned',
                'content': '{actor} assigned a task to you: {target}'
            },
            NotificationType.POLL_RESULT: {
                'title': 'Poll Results',
                'content': 'Results are available for the poll you participated in'
            }
        }

        return templates.get(notification_type, {
            'title': 'Notification',
            'content': 'You have a new notification'
        })

    async def _get_user_display_name(self, user_id: int) -> str:
        """Получение отображаемого имени пользователя"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT username, display_name FROM users WHERE id = $1",
                user_id
            )

        if row:
            return row['display_name'] or row['username']
        return f"User {user_id}"

    async def _save_notification(self, notification: Notification):
        """Сохранение уведомления в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO notifications (
                    id, user_id, type, title, content, priority, status,
                    data, channels, scheduled_time, expires_at, created_at,
                    sent_at, delivered_at, read_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                """,
                notification.id, notification.user_id, notification.type.value,
                notification.title, notification.content, notification.priority.value,
                notification.status.value, json.dumps(notification.data) if notification.data else None,
                [ch.value for ch in notification.channels], notification.scheduled_time,
                notification.expires_at, notification.created_at, notification.sent_at,
                notification.delivered_at, notification.read_at
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

    async def _save_subscription(self, subscription: Subscription):
        """Сохранение подписки в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO event_subscriptions (
                    id, user_id, event_type, notification_types, channels, filters, is_active, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                subscription.id, subscription.user_id, subscription.event_type,
                [nt.value for nt in subscription.notification_types],
                [ch.value for ch in subscription.channels],
                json.dumps(subscription.filters) if subscription.filters else None,
                subscription.is_active, subscription.created_at, subscription.updated_at
            )

    async def _get_subscriptions_for_event(self, event_type: str) -> List[Subscription]:
        """Получение подписок для типа события"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, user_id, event_type, notification_types, channels, filters,
                       is_active, created_at, updated_at
                FROM event_subscriptions
                WHERE event_type = $1 AND is_active = true
                """,
                event_type
            )

        subscriptions = []
        for row in rows:
            subscription = Subscription(
                id=row['id'],
                user_id=row['user_id'],
                event_type=row['event_type'],
                notification_types=[NotificationType(nt) for nt in row['notification_types']],
                channels=[NotificationChannel(ch) for ch in row['channels']],
                filters=json.loads(row['filters']) if row['filters'] else None,
                is_active=row['is_active'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            subscriptions.append(subscription)

        return subscriptions

    async def _get_subscription(self, subscription_id: str) -> Optional[Subscription]:
        """Получение подписки по ID"""
        # Сначала проверяем кэш
        cached = await self._get_cached_subscription(subscription_id)
        if cached:
            return cached

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, user_id, event_type, notification_types, channels, filters,
                       is_active, created_at, updated_at
                FROM event_subscriptions
                WHERE id = $1
                """,
                subscription_id
            )

        if not row:
            return None

        subscription = Subscription(
            id=row['id'],
            user_id=row['user_id'],
            event_type=row['event_type'],
            notification_types=[NotificationType(nt) for nt in row['notification_types']],
            channels=[NotificationChannel(ch) for ch in row['channels']],
            filters=json.loads(row['filters']) if row['filters'] else None,
            is_active=row['is_active'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

        # Кэшируем
        await self._cache_subscription(subscription)

        return subscription

    async def _get_cached_subscription(self, subscription_id: str) -> Optional[Subscription]:
        """Получение подписки из кэша"""
        cached = await redis_client.get(f"subscription:{subscription_id}")
        if cached:
            return Subscription(**json.loads(cached))
        return None

    async def _cache_subscription(self, subscription: Subscription):
        """Кэширование подписки"""
        await redis_client.setex(f"subscription:{subscription.id}", 300, 
                                subscription.model_dump_json())

    async def _uncache_subscription(self, subscription_id: str):
        """Удаление подписки из кэша"""
        await redis_client.delete(f"subscription:{subscription_id}")

    async def _get_user_notification_preferences(self, user_id: int) -> List[NotificationPreferences]:
        """Получение настроек уведомлений пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, notification_type, channels, enabled, mute_until, custom_settings
                FROM notification_preferences
                WHERE user_id = $1
                """,
                user_id
            )

        preferences = []
        for row in rows:
            pref = NotificationPreferences(
                user_id=row['user_id'],
                notification_type=NotificationType(row['notification_type']),
                channels=[NotificationChannel(ch) for ch in row['channels']],
                enabled=row['enabled'],
                mute_until=row['mute_until'],
                custom_settings=json.loads(row['custom_settings']) if row['custom_settings'] else None
            )
            preferences.append(pref)

        return preferences

    async def _publish_event_to_redis(self, event: Event):
        """Публикация события в Redis для других сервисов"""
        channel = f"events:{event.type}"
        await redis_client.publish(channel, event.model_dump_json())

    async def _emit_to_handlers(self, event: Event):
        """Вызов зарегистрированных обработчиков событий"""
        handlers = self.event_handlers.get(event.type, [])
        for handler in handlers:
            try:
                # Вызываем обработчик асинхронно
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Error in event handler for {event.type}: {e}")

    def register_event_handler(self, event_type: str, handler: Callable):
        """Регистрация обработчика события"""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)

    def unregister_event_handler(self, event_type: str, handler: Callable):
        """Отмена регистрации обработчика события"""
        if event_type in self.event_handlers:
            self.event_handlers[event_type].remove(handler)

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
                   sent_at, delivered_at, read_at
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
                read_at=row['read_at']
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

    async def _get_cached_notification(self, notification_id: str) -> Optional[Notification]:
        """Получение уведомления из кэша"""
        cached = await redis_client.get(f"notification:{notification_id}")
        if cached:
            return Notification(**json.loads(cached))
        return None

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
                                         notification_type: Optional[NotificationType] = None) -> List[NotificationPreferences]:
        """Получение настроек уведомлений пользователя"""
        # Сначала проверяем кэш
        cache_key = f"notification_preferences:{user_id}"
        if notification_type:
            cache_key += f":{notification_type.value}"
        
        cached = await redis_client.get(cache_key)
        if cached:
            return [NotificationPreferences(**item) for item in json.loads(cached)]

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
            pref = NotificationPreferences(
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

    async def schedule_notification(self, user_id: int, notification_type: NotificationType,
                                  title: str, content: str, scheduled_time: datetime,
                                  channels: List[NotificationChannel],
                                  data: Optional[Dict] = None) -> Optional[str]:
        """Планирование отложенного уведомления"""
        notification_id = str(uuid.uuid4())

        notification = Notification(
            id=notification_id,
            user_id=user_id,
            type=notification_type,
            title=title,
            content=content,
            priority=self._determine_priority(notification_type),
            status=NotificationStatus.PENDING,
            channels=channels,
            scheduled_time=scheduled_time,
            data=data or {},
            created_at=datetime.utcnow()
        )

        # Сохраняем уведомление
        await self._save_notification(notification)

        # Добавляем в очередь планировщика
        await self._schedule_notification_delivery(notification)

        return notification_id

    async def _schedule_notification_delivery(self, notification: Notification):
        """Планирование доставки уведомления"""
        if not notification.scheduled_time:
            return

        # Добавляем в очередь Redis с тайм-штампом
        await redis_client.zadd(
            "scheduled_notifications",
            {notification.id: notification.scheduled_time.timestamp()}
        )

    async def process_scheduled_notifications(self):
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
                    read_at=row['read_at']
                )

            # Отправляем уведомление
            await self._send_notification(notification)

            # Удаляем из очереди
            await redis_client.zrem("scheduled_notifications", notification_id)

    async def bulk_send_notifications(self, notifications_data: List[Dict]) -> List[str]:
        """Массовая отправка уведомлений"""
        sent_ids = []

        for data in notifications_data:
            notification_id = await self.create_notification(**data)
            if notification_id:
                sent_ids.append(notification_id)

        return sent_ids

    async def create_notification(self, user_id: int, notification_type: NotificationType,
                                title: str, content: str,
                                channels: List[NotificationChannel],
                                priority: Optional[NotificationPriority] = None,
                                data: Optional[Dict] = None,
                                scheduled_time: Optional[datetime] = None) -> Optional[str]:
        """Создание и отправка уведомления"""
        notification_id = str(uuid.uuid4())

        notification = Notification(
            id=notification_id,
            user_id=user_id,
            type=notification_type,
            title=title,
            content=content,
            priority=priority or self._determine_priority(notification_type),
            status=NotificationStatus.PENDING,
            channels=channels,
            data=data or {},
            scheduled_time=scheduled_time,
            created_at=datetime.utcnow()
        )

        # Проверяем, должен ли пользователь получать это уведомление
        if not await self._should_notify_user(user_id, notification_type):
            return None

        # Если уведомление должно быть отправлено немедленно
        if not scheduled_time:
            await self._send_notification(notification)
        else:
            # Иначе планируем отправку
            await self._schedule_notification_delivery(notification)

        # Сохраняем уведомление
        await self._save_notification(notification)

        # Добавляем в кэш
        await self._cache_notification(notification)

        return notification_id

    async def _cache_notification(self, notification: Notification):
        """Кэширование уведомления"""
        await redis_client.setex(f"notification:{notification.id}", 300, 
                                notification.model_dump_json())

    async def mute_notifications(self, user_id: int, notification_type: NotificationType,
                               duration_minutes: int) -> bool:
        """Временное отключение уведомлений определенного типа"""
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
                    user_id, notification_type.value, [], False, mute_until,
                    datetime.utcnow(), datetime.utcnow()
                )

            # Удаляем из кэша, чтобы обновить при следующем запросе
            await redis_client.delete(f"notification_preferences:{user_id}")

            return True
        except Exception as e:
            logger.error(f"Error muting notifications: {e}")
            return False

    async def unmute_notifications(self, user_id: int, notification_type: NotificationType) -> bool:
        """Включение уведомлений определенного типа"""
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE notification_preferences
                    SET enabled = true, mute_until = NULL, updated_at = $3
                    WHERE user_id = $1 AND notification_type = $2
                    """,
                    user_id, notification_type.value, datetime.utcnow()
                )

            # Удаляем из кэша, чтобы обновить при следующем запросе
            await redis_client.delete(f"notification_preferences:{user_id}")

            return True
        except Exception as e:
            logger.error(f"Error unmuting notifications: {e}")
            return False

    async def get_user_events(self, user_id: int, event_types: Optional[List[str]] = None,
                            limit: int = 50, offset: int = 0) -> List[Event]:
        """Получение событий для пользователя"""
        conditions = ["(actor_id = $1 OR target_id = $1)"]
        params = [str(user_id)]
        param_idx = 2

        if event_types:
            conditions.append(f"type = ANY(${'$'.join([str(i) for i in range(param_idx, param_idx + len(event_types))])})")
            params.extend(event_types)
            param_idx += len(event_types)

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, type, source, actor_id, target_id, target_type, data, created_at
            FROM events
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        events = []
        for row in rows:
            event = Event(
                id=row['id'],
                type=row['type'],
                source=row['source'],
                actor_id=row['actor_id'],
                target_id=row['target_id'],
                target_type=row['target_type'],
                data=json.loads(row['data']) if row['data'] else {},
                created_at=row['created_at']
            )
            events.append(event)

        return events

    async def get_events_by_target(self, target_id: str, target_type: str,
                                 event_types: Optional[List[str]] = None,
                                 limit: int = 50, offset: int = 0) -> List[Event]:
        """Получение событий для определенного объекта"""
        conditions = ["target_id = $1 AND target_type = $2"]
        params = [target_id, target_type]
        param_idx = 3

        if event_types:
            conditions.append(f"type = ANY(${'$'.join([str(i) for i in range(param_idx, param_idx + len(event_types))])})")
            params.extend(event_types)
            param_idx += len(event_types)

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, type, source, actor_id, target_id, target_type, data, created_at
            FROM events
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        events = []
        for row in rows:
            event = Event(
                id=row['id'],
                type=row['type'],
                source=row['source'],
                actor_id=row['actor_id'],
                target_id=row['target_id'],
                target_type=row['target_type'],
                data=json.loads(row['data']) if row['data'] else {},
                created_at=row['created_at']
            )
            events.append(event)

        return events

# Глобальный экземпляр для использования в приложении
event_system = EventSystem()
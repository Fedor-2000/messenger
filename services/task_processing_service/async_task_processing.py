# Asynchronous Task Processing System
# File: services/task_processing_service/async_task_processing.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import uuid
import time
from dataclasses import dataclass

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel
import aio_pika
from aio_pika import connect_robust, Message, ExchangeType
import aioredis

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class TaskPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"

class TaskType(Enum):
    MESSAGE_DELIVERY = "message_delivery"
    FILE_PROCESSING = "file_processing"
    NOTIFICATION_SENDING = "notification_sending"
    EMAIL_SENDING = "email_sending"
    SMS_SENDING = "sms_sending"
    PUSH_NOTIFICATION = "push_notification"
    DATA_SYNC = "data_sync"
    REPORT_GENERATION = "report_generation"
    BACKUP_CREATION = "backup_creation"
    CONTENT_MODERATION = "content_moderation"
    MEDIA_PROCESSING = "media_processing"
    ANALYTICS_CALCULATION = "analytics_calculation"
    USER_IMPORT = "user_import"
    USER_EXPORT = "user_export"
    CUSTOM_TASK = "custom_task"

class Task(BaseModel):
    id: str
    type: TaskType
    priority: TaskPriority
    status: TaskStatus
    payload: Dict[str, Any]  # Данные для выполнения задачи
    created_at: datetime = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    timeout: Optional[int] = None  # В секундах
    callback_url: Optional[str] = None  # URL для обратного вызова
    metadata: Optional[Dict[str, Any]] = None

class TaskQueueConfig(BaseModel):
    queue_name: str
    exchange_name: str
    routing_key: str
    durable: bool = True
    max_priority: int = 4  # 0-4 для RabbitMQ

class AsyncTaskProcessor:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.queues = {}
        self.task_handlers = {}
        self.active_tasks = {}
        self.retry_delay = 5  # секунд
        self.max_retry_delay = 300  # 5 минут
        self.task_timeout = 300  # 5 минут по умолчанию
        self.prefetch_count = 10  # количество задач для предварительной выборки

        # Регистрируем обработчики задач по умолчанию
        self._register_default_task_handlers()

    async def initialize(self):
        """Инициализация системы асинхронной обработки задач"""
        # Подключаемся к RabbitMQ
        try:
            self.connection = await connect_robust("amqp://messenger:your-secure-password@rabbitmq:5672/")
            self.channel = await self.connection.channel()
            
            # Устанавливаем prefetch count для равномерного распределения задач
            await self.channel.set_qos(prefetch_count=self.prefetch_count)
            
            # Создаем очереди для различных типов задач
            await self._setup_task_queues()
            
            logger.info("Async task processor initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing async task processor: {e}")
            raise

    async def _setup_task_queues(self):
        """Настройка очередей задач"""
        queue_configs = [
            TaskQueueConfig(
                queue_name="message_delivery_queue",
                exchange_name="task_exchange",
                routing_key="message_delivery",
                max_priority=4
            ),
            TaskQueueConfig(
                queue_name="file_processing_queue",
                exchange_name="task_exchange",
                routing_key="file_processing",
                max_priority=4
            ),
            TaskQueueConfig(
                queue_name="notification_queue",
                exchange_name="task_exchange",
                routing_key="notification",
                max_priority=4
            ),
            TaskQueueConfig(
                queue_name="email_queue",
                exchange_name="task_exchange",
                routing_key="email",
                max_priority=3
            ),
            TaskQueueConfig(
                queue_name="media_processing_queue",
                exchange_name="task_exchange",
                routing_key="media_processing",
                max_priority=3
            ),
            TaskQueueConfig(
                queue_name="analytics_queue",
                exchange_name="task_exchange",
                routing_key="analytics",
                max_priority=2
            ),
            TaskQueueConfig(
                queue_name="system_queue",
                exchange_name="task_exchange",
                routing_key="system",
                max_priority=4
            )
        ]

        for config in queue_configs:
            # Создаем exchange
            exchange = await self.channel.declare_exchange(
                config.exchange_name, ExchangeType.TOPIC, durable=config.durable
            )
            
            # Создаем очередь
            queue = await self.channel.declare_queue(
                config.queue_name,
                durable=config.durable,
                arguments={"x-max-priority": config.max_priority} if config.max_priority else None
            )
            
            # Привязываем очередь к exchange
            await queue.bind(exchange, routing_key=config.routing_key)
            
            self.queues[config.queue_name] = {
                'exchange': exchange,
                'queue': queue,
                'routing_key': config.routing_key
            }

    def _register_default_task_handlers(self):
        """Регистрация обработчиков задач по умолчанию"""
        self.task_handlers = {
            TaskType.MESSAGE_DELIVERY: self._handle_message_delivery_task,
            TaskType.FILE_PROCESSING: self._handle_file_processing_task,
            TaskType.NOTIFICATION_SENDING: self._handle_notification_task,
            TaskType.EMAIL_SENDING: self._handle_email_task,
            TaskType.SMS_SENDING: self._handle_sms_task,
            TaskType.PUSH_NOTIFICATION: self._handle_push_notification_task,
            TaskType.DATA_SYNC: self._handle_data_sync_task,
            TaskType.REPORT_GENERATION: self._handle_report_generation_task,
            TaskType.BACKUP_CREATION: self._handle_backup_task,
            TaskType.CONTENT_MODERATION: self._handle_content_moderation_task,
            TaskType.MEDIA_PROCESSING: self._handle_media_processing_task,
            TaskType.ANALYTICS_CALCULATION: self._handle_analytics_task,
            TaskType.USER_IMPORT: self._handle_user_import_task,
            TaskType.USER_EXPORT: self._handle_user_export_task
        }

    async def submit_task(self, task_type: TaskType, payload: Dict[str, Any],
                         priority: TaskPriority = TaskPriority.MEDIUM,
                         max_retries: int = 3, timeout: Optional[int] = None,
                         callback_url: Optional[str] = None,
                         metadata: Optional[Dict] = None) -> Optional[str]:
        """Отправка задачи в очередь"""
        task_id = str(uuid.uuid4())

        task = Task(
            id=task_id,
            type=task_type,
            priority=priority,
            status=TaskStatus.PENDING,
            payload=payload,
            created_at=datetime.utcnow(),
            max_retries=max_retries,
            timeout=timeout,
            callback_url=callback_url,
            metadata=metadata or {}
        )

        # Сохраняем задачу в базу данных
        await self._save_task_to_db(task)

        # Отправляем задачу в очередь
        await self._enqueue_task(task)

        # Добавляем в кэш
        await self._cache_task(task)

        logger.info(f"Task {task_id} of type {task_type.value} submitted to queue")

        # Создаем запись активности
        await self._log_activity("task_submitted", {
            "task_id": task_id,
            "task_type": task_type.value,
            "priority": priority.value
        })

        return task_id

    async def _save_task_to_db(self, task: Task):
        """Сохранение задачи в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO async_tasks (
                    id, type, priority, status, payload, created_at, started_at,
                    completed_at, error_message, retry_count, max_retries, timeout,
                    callback_url, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                """,
                task.id, task.type.value, task.priority.value, task.status.value,
                json.dumps(task.payload), task.created_at, task.started_at,
                task.completed_at, task.error_message, task.retry_count,
                task.max_retries, task.timeout, task.callback_url,
                json.dumps(task.metadata) if task.metadata else None
            )

    async def _enqueue_task(self, task: Task):
        """Добавление задачи в очередь сообщений"""
        queue_name = self._get_queue_name_for_task_type(task.type)
        
        if queue_name not in self.queues:
            logger.error(f"No queue found for task type: {task.type.value}")
            return

        # Преобразуем приоритет в число для RabbitMQ
        priority_num = self._priority_to_number(task.priority)

        # Создаем сообщение
        message_body = json.dumps({
            'task_id': task.id,
            'task_type': task.type.value,
            'payload': task.payload,
            'priority': priority_num,
            'created_at': task.created_at.isoformat(),
            'timeout': task.timeout
        })

        message = Message(
            message_body.encode(),
            priority=priority_num,
            delivery_mode=2,  #.persistent
            expiration=task.timeout * 1000 if task.timeout else None
        )

        # Отправляем в очередь
        exchange = self.queues[queue_name]['exchange']
        routing_key = self.queues[queue_name]['routing_key']
        
        await exchange.publish(message, routing_key=routing_key)

    def _get_queue_name_for_task_type(self, task_type: TaskType) -> str:
        """Получение имени очереди для типа задачи"""
        queue_mapping = {
            TaskType.MESSAGE_DELIVERY: "message_delivery_queue",
            TaskType.FILE_PROCESSING: "file_processing_queue",
            TaskType.NOTIFICATION_SENDING: "notification_queue",
            TaskType.EMAIL_SENDING: "email_queue",
            TaskType.SMS_SENDING: "notification_queue",
            TaskType.PUSH_NOTIFICATION: "notification_queue",
            TaskType.DATA_SYNC: "system_queue",
            TaskType.REPORT_GENERATION: "system_queue",
            TaskType.BACKUP_CREATION: "system_queue",
            TaskType.CONTENT_MODERATION: "system_queue",
            TaskType.MEDIA_PROCESSING: "media_processing_queue",
            TaskType.ANALYTICS_CALCULATION: "analytics_queue",
            TaskType.USER_IMPORT: "system_queue",
            TaskType.USER_EXPORT: "system_queue"
        }
        return queue_mapping.get(task_type, "system_queue")

    def _priority_to_number(self, priority: TaskPriority) -> int:
        """Преобразование приоритета в число для RabbitMQ"""
        priority_mapping = {
            TaskPriority.LOW: 0,
            TaskPriority.MEDIUM: 1,
            TaskPriority.HIGH: 2,
            TaskPriority.URGENT: 3
        }
        return priority_mapping.get(priority, 1)  # по умолчанию MEDIUM

    async def process_next_task(self) -> bool:
        """Обработка следующей задачи из очереди"""
        # В реальной системе это будет асинхронный обработчик, подписанный на очередь
        # Для упрощения возвращаем False, так как обработка будет происходить через подписку
        return False

    async def _handle_message_delivery_task(self, task: Task) -> bool:
        """Обработка задачи доставки сообщения"""
        try:
            payload = task.payload
            message_id = payload.get('message_id')
            target_users = payload.get('target_users', [])
            content = payload.get('content', '')

            # В реальной системе здесь будет доставка сообщения пользователям
            # через WebSocket, push-уведомления или другие каналы
            logger.info(f"Delivering message {message_id} to {len(target_users)} users")

            # Симуляция обработки
            await asyncio.sleep(0.1)

            # В реальной системе здесь будет фактическая доставка сообщения
            # и проверка статуса доставки

            return True
        except Exception as e:
            logger.error(f"Error handling message delivery task: {e}")
            return False

    async def _handle_file_processing_task(self, task: Task) -> bool:
        """Обработка задачи обработки файла"""
        try:
            payload = task.payload
            file_id = payload.get('file_id')
            operation = payload.get('operation')  # 'thumbnail', 'transcode', 'scan', etc.
            params = payload.get('params', {})

            logger.info(f"Processing file {file_id} with operation {operation}")

            # В зависимости от операции выполняем соответствующую обработку
            if operation == 'thumbnail':
                # Создание миниатюры
                await self._create_thumbnail(file_id, params)
            elif operation == 'transcode':
                # Перекодировка видео/аудио
                await self._transcode_media(file_id, params)
            elif operation == 'scan':
                # Сканирование на вирусы
                await self._scan_file_for_viruses(file_id)
            elif operation == 'ocr':
                # OCR обработка
                await self._perform_ocr(file_id)
            else:
                logger.warning(f"Unknown file operation: {operation}")
                return False

            return True
        except Exception as e:
            logger.error(f"Error handling file processing task: {e}")
            return False

    async def _handle_notification_task(self, task: Task) -> bool:
        """Обработка задачи отправки уведомления"""
        try:
            payload = task.payload
            user_id = payload.get('user_id')
            notification_type = payload.get('type')
            title = payload.get('title')
            content = payload.get('content')
            channels = payload.get('channels', ['push'])

            logger.info(f"Sending notification to user {user_id}, type: {notification_type}")

            # В реальной системе здесь будет отправка уведомления через
            # соответствующие каналы (push, email, in-app, etc.)

            # Симуляция обработки
            await asyncio.sleep(0.05)

            return True
        except Exception as e:
            logger.error(f"Error handling notification task: {e}")
            return False

    async def _handle_email_task(self, task: Task) -> bool:
        """Обработка задачи отправки email"""
        try:
            payload = task.payload
            recipient_email = payload.get('recipient_email')
            subject = payload.get('subject')
            body = payload.get('body')
            user_id = payload.get('user_id')  # Если есть ID пользователя вместо email

            if not (recipient_email or user_id) or not subject:
                logger.error(f"Missing required fields for email task {task.id}")
                return False

            # Если указан user_id, получаем email из базы данных
            if user_id:
                # Импортируем функцию из основного серверного файла
                import sys
                import os
                # Добавляем путь к основному серверному модулю
                sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
                from server.app.main import send_email_notification as server_send_email
                return await server_send_email(user_id, subject, body or '')
            elif recipient_email:
                # Если указан email напрямую, нужно найти соответствующего пользователя
                # или создать специальную функцию для отправки по email
                # Для этого случая создадим временную функцию отправки по email напрямую
                success = await self._send_direct_email(recipient_email, subject, body or '')
                return success
            else:
                return False

        except Exception as e:
            logger.error(f"Error handling email task {task.id}: {e}")
            return False

    async def _send_direct_email(self, recipient_email: str, subject: str, body: str) -> bool:
        """Отправка email напрямую по email адресу"""
        try:
            # Создаем HTML-шаблон уведомления
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; }}
                    .container {{ max-width: 600px; margin: 0 auto; background-color: #f9f9f9; padding: 20px; border-radius: 8px; }}
                    .header {{ background-color: #4CAF50; color: white; padding: 15px; text-align: center; border-radius: 6px 6px 0 0; }}
                    .content {{ padding: 20px; background-color: white; border-radius: 0 0 6px 6px; }}
                    .footer {{ margin-top: 20px; font-size: 12px; color: #777; text-align: center; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>Уведомление от Messenger</h2>
                    </div>
                    <div class="content">
                        <h3>{subject}</h3>
                        <p>{body}</p>
                        <p><em>Это автоматическое уведомление. Пожалуйста, не отвечайте на него.</em></p>
                    </div>
                    <div class="footer">
                        <p>© {datetime.now().year} Messenger. Все права защищены.</p>
                        <p>Вы получили это письмо, потому что подписаны на уведомления от Messenger.</p>
                        <p><a href="https://messenger.local/preferences">Изменить настройки уведомлений</a></p>
                    </div>
                </div>
            </body>
            </html>
            """

            # Подготовка сообщения
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            import aiosmtplib

            msg = MIMEMultipart()
            msg['From'] = os.getenv('EMAIL_FROM', 'noreply@messenger.com')
            msg['To'] = recipient_email
            msg['Subject'] = subject
            msg.attach(MIMEText(html_content, 'html'))

            # Отправка через SMTP
            smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_user = os.getenv('SMTP_USER')
            smtp_password = os.getenv('SMTP_PASSWORD')
            smtp_use_tls = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'

            if not smtp_user or not smtp_password:
                logger.error("SMTP credentials not configured")
                return False

            # Попытка подключения с повторными попытками
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    async with aiosmtplib.SMTP(hostname=smtp_host, port=smtp_port, use_tls=smtp_use_tls) as server:
                        await server.login(smtp_user, smtp_password)
                        await server.send_message(msg)

                    logger.info(f"Direct email sent successfully to {recipient_email}")
                    return True

                except Exception as smtp_error:
                    logger.warning(f"Attempt {attempt + 1} failed to send direct email to {recipient_email}: {smtp_error}")
                    if attempt == max_retries - 1:  # Последняя попытка
                        logger.error(f"Failed to send direct email to {recipient_email}: {smtp_error}")
                        return False
                    await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка

        except Exception as e:
            logger.error(f"Error sending direct email to {recipient_email}: {e}")
            return False

    async def _handle_sms_task(self, task: Task) -> bool:
        """Обработка задачи отправки SMS"""
        try:
            payload = task.payload
            recipient_phone = payload.get('recipient_phone')
            message = payload.get('message')
            user_id = payload.get('user_id')  # Если есть ID пользователя вместо номера

            if not (recipient_phone or user_id) or not message:
                logger.error(f"Missing required fields for SMS task {task.id}")
                return False

            # Если указан user_id, отправляем SMS пользователю через серверную функцию
            if user_id:
                import sys
                import os
                # Добавляем путь к основному серверному модулю
                sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
                from server.app.main import send_sms_notification as server_send_sms
                return await server_send_sms(user_id, message)
            elif recipient_phone:
                # Если указан номер напрямую, отправляем SMS напрямую
                success = await self._send_direct_sms(recipient_phone, message)
                return success
            else:
                return False

        except Exception as e:
            logger.error(f"Error handling SMS task {task.id}: {e}")
            return False

    async def _send_direct_sms(self, recipient_phone: str, message: str) -> bool:
        """Отправка SMS напрямую по номеру телефона"""
        try:
            # Нормализуем номер телефона
            normalized_phone = self._normalize_phone_number(recipient_phone)
            if not normalized_phone:
                logger.warning(f"Invalid phone number format: {recipient_phone}")
                return False

            # Подготовка текста SMS с ограничением длины
            sms_text = message[:160]  # Ограничение для SMS

            # Определяем провайдера SMS-услуг
            sms_provider = os.getenv('SMS_PROVIDER', 'twilio').lower()

            success = False
            if sms_provider == 'twilio':
                success = await self._send_sms_via_twilio(normalized_phone, sms_text)
            elif sms_provider == 'aws_sns':
                success = await self._send_sms_via_aws_sns(normalized_phone, sms_text)
            elif sms_provider == 'fake':  # Для тестирования
                # Используем серверную функцию для тестовой отправки
                # Импортируем функцию из основного серверного файла
                import sys
                import os
                sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
                from server.app.main import _send_sms_fake as server_send_sms_fake
                success = await server_send_sms_fake(normalized_phone, sms_text)
            else:
                logger.warning(f"Unknown SMS provider: {sms_provider}. Using fake provider.")
                # Используем серверную функцию для тестовой отправки
                import sys
                import os
                sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
                from server.app.main import _send_sms_fake as server_send_sms_fake
                success = await server_send_sms_fake(normalized_phone, sms_text)

            if success:
                logger.info(f"Direct SMS sent successfully to {normalized_phone}")
                return True
            else:
                logger.error(f"Failed to send direct SMS to {normalized_phone}")
                return False

        except Exception as e:
            logger.error(f"Error sending direct SMS to {recipient_phone}: {e}")
            return False

    async def _handle_push_notification_task(self, task: Task) -> bool:
        """Обработка задачи отправки push-уведомления"""
        try:
            payload = task.payload
            device_tokens = payload.get('device_tokens', [])
            title = payload.get('title')
            body = payload.get('body')
            data = payload.get('data', {})

            logger.info(f"Sending push notification to {len(device_tokens)} devices")

            # В реальной системе здесь будет отправка через FCM/APNs
            # Симуляция обработки
            await asyncio.sleep(0.1)

            return True
        except Exception as e:
            logger.error(f"Error handling push notification task: {e}")
            return False

    async def _handle_data_sync_task(self, task: Task) -> bool:
        """Обработка задачи синхронизации данных"""
        try:
            payload = task.payload
            source = payload.get('source')
            target = payload.get('target')
            entities = payload.get('entities', [])

            logger.info(f"Synchronizing data from {source} to {target}, entities: {entities}")

            # В реальной системе здесь будет синхронизация данных между источниками
            # Симуляция обработки
            await asyncio.sleep(0.5)

            return True
        except Exception as e:
            logger.error(f"Error handling data sync task: {e}")
            return False

    async def _handle_report_generation_task(self, task: Task) -> bool:
        """Обработка задачи генерации отчета"""
        try:
            payload = task.payload
            report_type = payload.get('report_type')
            filters = payload.get('filters', {})
            user_id = payload.get('user_id')

            logger.info(f"Generating {report_type} report for user {user_id}")

            # В реальной системе здесь будет генерация отчета
            # Симуляция обработки
            await asyncio.sleep(1.0)

            return True
        except Exception as e:
            logger.error(f"Error handling report generation task: {e}")
            return False

    async def _handle_backup_task(self, task: Task) -> bool:
        """Обработка задачи создания резервной копии"""
        try:
            payload = task.payload
            backup_type = payload.get('backup_type', 'full')
            destination = payload.get('destination', 'local')

            logger.info(f"Creating {backup_type} backup to {destination}")

            # В реальной системе здесь будет создание резервной копии
            # Симуляция обработки
            await asyncio.sleep(2.0)

            return True
        except Exception as e:
            logger.error(f"Error handling backup task: {e}")
            return False

    async def _handle_content_moderation_task(self, task: Task) -> bool:
        """Обработка задачи модерации контента"""
        try:
            payload = task.payload
            content_id = payload.get('content_id')
            content_type = payload.get('content_type')

            logger.info(f"Moderating content {content_id} of type {content_type}")

            # В реальной системе здесь будет модерация контента
            # Симуляция обработки
            await asyncio.sleep(0.3)

            return True
        except Exception as e:
            logger.error(f"Error handling content moderation task: {e}")
            return False

    async def _handle_media_processing_task(self, task: Task) -> bool:
        """Обработка задачи обработки медиа"""
        try:
            payload = task.payload
            file_id = payload.get('file_id')
            operations = payload.get('operations', [])

            logger.info(f"Processing media {file_id} with operations: {operations}")

            # В реальной системе здесь будет обработка медиа-файла
            # Симуляция обработки
            await asyncio.sleep(1.5)

            return True
        except Exception as e:
            logger.error(f"Error handling media processing task: {e}")
            return False

    async def _handle_analytics_task(self, task: Task) -> bool:
        """Обработка задачи аналитики"""
        try:
            payload = task.payload
            analytics_type = payload.get('analytics_type')
            filters = payload.get('filters', {})

            logger.info(f"Calculating {analytics_type} analytics")

            # В реальной системе здесь будет вычисление аналитики
            # Симуляция обработки
            await asyncio.sleep(0.8)

            return True
        except Exception as e:
            logger.error(f"Error handling analytics task: {e}")
            return False

    async def _handle_user_import_task(self, task: Task) -> bool:
        """Обработка задачи импорта пользователей"""
        try:
            payload = task.payload
            source = payload.get('source')
            data = payload.get('data', [])

            logger.info(f"Importing {len(data)} users from {source}")

            # В реальной системе здесь будет импорт пользователей
            # Симуляция обработки
            await asyncio.sleep(1.0)

            return True
        except Exception as e:
            logger.error(f"Error handling user import task: {e}")
            return False

    async def _handle_user_export_task(self, task: Task) -> bool:
        """Обработка задачи экспорта пользователей"""
        try:
            payload = task.payload
            user_ids = payload.get('user_ids', [])
            format = payload.get('format', 'json')

            logger.info(f"Exporting {len(user_ids)} users in {format} format")

            # В реальной системе здесь будет экспорт пользователей
            # Симуляция обработки
            await asyncio.sleep(0.5)

            return True
        except Exception as e:
            logger.error(f"Error handling user export task: {e}")
            return False

    async def _create_thumbnail(self, file_id: str, params: Dict[str, Any]):
        """Создание миниатюры файла"""
        # В реальной системе здесь будет создание миниатюры
        import logging
        logging.info(f"Creating thumbnail for file {file_id}")
        return True

    async def _transcode_media(self, file_id: str, params: Dict[str, Any]):
        """Перекодировка медиа-файла"""
        # В реальной системе здесь будет перекодировка
        import logging
        logging.info(f"Transcoding media file {file_id}")
        return True

    async def _scan_file_for_viruses(self, file_id: str):
        """Сканирование файла на вирусы"""
        # В реальной системе здесь будет сканирование через антивирус
        import logging
        logging.info(f"Scanning file {file_id} for viruses")
        return True

    async def _perform_ocr(self, file_id: str):
        """Выполнение OCR обработки"""
        # В реальной системе здесь будет OCR обработка изображения
        import logging
        logging.info(f"Performing OCR on file {file_id}")
        return True

    async def _update_task_status(self, task_id: str, status: TaskStatus, 
                                error_message: Optional[str] = None):
        """Обновление статуса задачи"""
        # Обновляем в базе данных
        async with db_pool.acquire() as conn:
            if status == TaskStatus.IN_PROGRESS:
                await conn.execute(
                    "UPDATE async_tasks SET status = $2, started_at = $3 WHERE id = $1",
                    task_id, status.value, datetime.utcnow()
                )
            elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                completion_time = datetime.utcnow()
                await conn.execute(
                    """
                    UPDATE async_tasks SET 
                        status = $2, completed_at = $3, error_message = $4, updated_at = $5
                    WHERE id = $1
                    """,
                    task_id, status.value, completion_time, error_message, completion_time
                )

        # Обновляем в кэше
        await self._update_cached_task_status(task_id, status, error_message)

        # Если задача завершена, удаляем из активных
        if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]

    async def _update_cached_task_status(self, task_id: str, status: TaskStatus, 
                                       error_message: Optional[str] = None):
        """Обновление статуса задачи в кэше"""
        cached_task = await self._get_cached_task(task_id)
        if cached_task:
            cached_task.status = status
            if error_message:
                cached_task.error_message = error_message
            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                cached_task.completed_at = datetime.utcnow()
            
            await self._cache_task(cached_task)

    async def _cache_task(self, task: Task):
        """Кэширование задачи"""
        await redis_client.setex(f"task:{task.id}", 3600, task.model_dump_json())

    async def _get_cached_task(self, task_id: str) -> Optional[Task]:
        """Получение задачи из кэша"""
        cached = await redis_client.get(f"task:{task_id}")
        if cached:
            return Task(**json.loads(cached.decode()))
        return None

    async def get_task_status(self, task_id: str) -> Optional[Task]:
        """Получение статуса задачи"""
        # Сначала проверяем кэш
        cached_task = await self._get_cached_task(task_id)
        if cached_task:
            return cached_task

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, type, priority, status, payload, created_at, started_at,
                       completed_at, error_message, retry_count, max_retries, timeout,
                       callback_url, metadata
                FROM async_tasks WHERE id = $1
                """,
                task_id
            )

        if not row:
            return None

        task = Task(
            id=row['id'],
            type=TaskType(row['type']),
            priority=TaskPriority(row['priority']),
            status=TaskStatus(row['status']),
            payload=json.loads(row['payload']) if row['payload'] else {},
            created_at=row['created_at'],
            started_at=row['started_at'],
            completed_at=row['completed_at'],
            error_message=row['error_message'],
            retry_count=row['retry_count'],
            max_retries=row['max_retries'],
            timeout=row['timeout'],
            callback_url=row['callback_url'],
            metadata=json.loads(row['metadata']) if row['metadata'] else None
        )

        # Кэшируем задачу
        await self._cache_task(task)

        return task

    async def cancel_task(self, task_id: str) -> bool:
        """Отмена задачи"""
        task = await self.get_task_status(task_id)
        if not task or task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            return False

        # Обновляем статус в базе данных
        await self._update_task_status(task_id, TaskStatus.CANCELLED)

        # Удаляем из кэша
        await redis_client.delete(f"task:{task_id}")

        # Если задача активна, пытаемся отменить
        if task_id in self.active_tasks:
            future = self.active_tasks[task_id]
            if not future.done():
                future.cancel()

        logger.info(f"Task {task_id} cancelled")

        # Создаем запись активности
        await self._log_activity("task_cancelled", {
            "task_id": task_id,
            "task_type": task.type.value
        })

        return True

    async def retry_failed_task(self, task_id: str) -> bool:
        """Повторная попытка выполнения неудачной задачи"""
        task = await self.get_task_status(task_id)
        if not task or task.status != TaskStatus.FAILED:
            return False

        if task.retry_count >= task.max_retries:
            logger.warning(f"Max retries reached for task {task_id}")
            return False

        # Обновляем счетчик попыток
        new_retry_count = task.retry_count + 1
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE async_tasks SET retry_count = $2, status = $3 WHERE id = $1",
                task_id, new_retry_count, TaskStatus.PENDING.value
            )

        # Обновляем в кэше
        task.retry_count = new_retry_count
        task.status = TaskStatus.PENDING
        await self._cache_task(task)

        # Повторно отправляем задачу в очередь
        await self._enqueue_task(task)

        logger.info(f"Task {task_id} retried (attempt {new_retry_count})")

        # Создаем запись активности
        await self._log_activity("task_retried", {
            "task_id": task_id,
            "task_type": task.type.value,
            "retry_count": new_retry_count
        })

        return True

    async def get_user_tasks(self, user_id: int, status: Optional[TaskStatus] = None,
                           task_type: Optional[TaskType] = None,
                           limit: int = 50, offset: int = 0) -> List[Task]:
        """Получение задач пользователя"""
        conditions = ["EXISTS (SELECT 1 FROM jsonb_array_elements(payload->'user_ids') elem WHERE elem::text::integer = $1)"]
        params = [user_id]
        param_idx = 2

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        if task_type:
            conditions.append(f"type = ${param_idx}")
            params.append(task_type.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, type, priority, status, payload, created_at, started_at,
                   completed_at, error_message, retry_count, max_retries, timeout,
                   callback_url, metadata
            FROM async_tasks
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        tasks = []
        for row in rows:
            task = Task(
                id=row['id'],
                type=TaskType(row['type']),
                priority=TaskPriority(row['priority']),
                status=TaskStatus(row['status']),
                payload=json.loads(row['payload']) if row['payload'] else {},
                created_at=row['created_at'],
                started_at=row['started_at'],
                completed_at=row['completed_at'],
                error_message=row['error_message'],
                retry_count=row['retry_count'],
                max_retries=row['max_retries'],
                timeout=row['timeout'],
                callback_url=row['callback_url'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None
            )
            tasks.append(task)

        return tasks

    async def get_system_tasks(self, status: Optional[TaskStatus] = None,
                             task_type: Optional[TaskType] = None,
                             limit: int = 50, offset: int = 0) -> List[Task]:
        """Получение системных задач"""
        conditions = []
        params = []
        param_idx = 1

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        if task_type:
            conditions.append(f"type = ${param_idx}")
            params.append(task_type.value)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        sql_query = f"""
            SELECT id, type, priority, status, payload, created_at, started_at,
                   completed_at, error_message, retry_count, max_retries, timeout,
                   callback_url, metadata
            FROM async_tasks
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        tasks = []
        for row in rows:
            task = Task(
                id=row['id'],
                type=TaskType(row['type']),
                priority=TaskPriority(row['priority']),
                status=TaskStatus(row['status']),
                payload=json.loads(row['payload']) if row['payload'] else {},
                created_at=row['created_at'],
                started_at=row['started_at'],
                completed_at=row['completed_at'],
                error_message=row['error_message'],
                retry_count=row['retry_count'],
                max_retries=row['max_retries'],
                timeout=row['timeout'],
                callback_url=row['callback_url'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None
            )
            tasks.append(task)

        return tasks

    async def _log_activity(self, action: str, details: Dict[str, Any]):
        """Логирование активности"""
        activity_id = str(uuid.uuid4())
        activity = {
            'id': activity_id,
            'action': action,
            'details': details,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Сохраняем в Redis для быстрого доступа
        await redis_client.lpush("system_activities", json.dumps(activity))
        await redis_client.ltrim("system_activities", 0, 999)  # Храним последние 1000 активностей

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
async_task_processor = AsyncTaskProcessor()
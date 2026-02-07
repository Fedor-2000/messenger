# Task Processing Service with Message Queues
# File: services/task_processor/main.py

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Callable

import aio_pika
from aio_pika import connect_robust, IncomingMessage, ExchangeType
import asyncpg
import redis.asyncio as redis

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
class Config:
    RABBITMQ_URL = os.getenv('RABBITMQ_URL', 'amqp://messenger:secure_password@rabbitmq:5672/')
    DB_URL = os.getenv('DB_URL', 'postgresql://messenger:password@db:5432/messenger')
    REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379')

config = Config()

# Глобальные переменные
db_pool = None
redis_client = None
connection = None
channel = None

class TaskProcessor:
    def __init__(self):
        self.task_handlers = {}
        self.setup_handlers()

    def setup_handlers(self):
        """Настройка обработчиков задач"""
        self.task_handlers = {
            'send_message': self.handle_send_message,
            'process_file': self.handle_process_file,
            'send_notification': self.handle_send_notification,
            'generate_report': self.handle_generate_report,
            'backup_data': self.handle_backup_data,
            'update_user_stats': self.handle_update_user_stats,
            'process_media': self.handle_process_media,
            'sync_external_service': self.handle_sync_external_service,
        }

    async def handle_send_message(self, task_data: Dict[str, Any]) -> bool:
        """Обработка задачи отправки сообщения"""
        try:
            chat_id = task_data.get('chat_id')
            sender_id = task_data.get('sender_id')
            content = task_data.get('content')
            message_type = task_data.get('message_type', 'text')
            
            # Сохраняем сообщение в базе данных
            async with db_pool.acquire() as conn:
                await conn.execute(
                    '''
                    INSERT INTO messages (chat_id, sender_id, content, message_type, timestamp)
                    VALUES ($1, $2, $3, $4, $5)
                    ''',
                    chat_id, sender_id, content, message_type, datetime.utcnow()
                )
            
            # Отправляем сообщение через Redis
            message_data = {
                'type': 'new_message',
                'chat_id': chat_id,
                'sender_id': sender_id,
                'content': content,
                'message_type': message_type,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            await redis_client.publish(f"chat:{chat_id}", json.dumps(message_data))
            
            logger.info(f"Message sent to chat {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Error handling send_message task: {e}")
            return False

    async def handle_process_file(self, task_data: Dict[str, Any]) -> bool:
        """Обработка задачи обработки файла"""
        try:
            file_id = task_data.get('file_id')
            file_path = task_data.get('file_path')
            operation = task_data.get('operation')  # resize, compress, convert, etc.
            
            # В реальном приложении здесь будет обработка файла
            # В зависимости от типа операции
            if operation == 'resize':
                width = task_data.get('width')
                height = task_data.get('height')
                # Обработка изменения размера
                logger.info(f"Resizing file {file_id} to {width}x{height}")
            elif operation == 'compress':
                quality = task_data.get('quality', 80)
                # Обработка сжатия
                logger.info(f"Compressing file {file_id} with quality {quality}")
            elif operation == 'convert':
                target_format = task_data.get('format')
                # Обработка конвертации
                logger.info(f"Converting file {file_id} to {target_format}")
            
            # Обновляем статус файла в базе данных
            async with db_pool.acquire() as conn:
                await conn.execute(
                    '''
                    UPDATE files SET processed = true, processed_at = $1
                    WHERE id = $2
                    ''',
                    datetime.utcnow(), file_id
                )
            
            logger.info(f"File {file_id} processed")
            return True
        except Exception as e:
            logger.error(f"Error handling process_file task: {e}")
            return False

    async def handle_send_notification(self, task_data: Dict[str, Any]) -> bool:
        """Обработка задачи отправки уведомления"""
        try:
            user_id = task_data.get('user_id')
            title = task_data.get('title')
            body = task_data.get('body')
            notification_type = task_data.get('type', 'info')
            
            # Отправляем уведомление через notification service
            # В реальном приложении здесь будет вызов notification service
            notification_data = {
                'user_id': user_id,
                'title': title,
                'body': body,
                'type': notification_type,
                'sent_at': datetime.utcnow().isoformat()
            }
            
            # Сохраняем уведомление в базу данных
            async with db_pool.acquire() as conn:
                await conn.execute(
                    '''
                    INSERT INTO notifications (user_id, title, body, type, sent, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ''',
                    user_id, title, body, notification_type, True, datetime.utcnow()
                )
            
            # Отправляем через Redis
            await redis_client.publish(f"user:{user_id}:notifications", json.dumps(notification_data))
            
            logger.info(f"Notification sent to user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error handling send_notification task: {e}")
            return False

    async def handle_generate_report(self, task_data: Dict[str, Any]) -> bool:
        """Обработка задачи генерации отчета"""
        try:
            report_type = task_data.get('report_type')
            user_id = task_data.get('user_id')
            filters = task_data.get('filters', {})
            
            # Генерируем отчет
            report_data = await self.generate_report(report_type, user_id, filters)
            
            # Сохраняем отчет в базу данных или файловую систему
            report_id = f"report_{user_id}_{datetime.utcnow().timestamp()}"
            
            async with db_pool.acquire() as conn:
                await conn.execute(
                    '''
                    INSERT INTO reports (id, user_id, type, data, generated_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ''',
                    report_id, user_id, report_type, json.dumps(report_data), datetime.utcnow()
                )
            
            # Отправляем уведомление пользователю о готовности отчета
            notification_task = {
                'user_id': user_id,
                'title': 'Отчет готов',
                'body': f'Ваш {report_type} отчет готов для просмотра',
                'type': 'info'
            }
            
            await self.publish_task('send_notification', notification_task)
            
            logger.info(f"Report {report_id} generated for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error handling generate_report task: {e}")
            return False

    async def generate_report(self, report_type: str, user_id: int, filters: Dict) -> Dict:
        """Генерация отчета"""
        # В реальном приложении здесь будет сложная логика генерации отчета
        # В зависимости от типа отчета
        if report_type == 'user_activity':
            # Получаем данные об активности пользователя
            async with db_pool.acquire() as conn:
                activity_data = await conn.fetch(
                    '''
                    SELECT COUNT(*) as message_count, 
                           MAX(timestamp) as last_message_time
                    FROM messages 
                    WHERE sender_id = $1
                    ''',
                    user_id
                )
            
            return {
                'user_id': user_id,
                'report_type': report_type,
                'generated_at': datetime.utcnow().isoformat(),
                'data': dict(activity_data[0]) if activity_data else {}
            }
        elif report_type == 'chat_statistics':
            # Получаем статистику чата
            chat_id = filters.get('chat_id')
            # Логика получения статистики чата
            return {
                'chat_id': chat_id,
                'report_type': report_type,
                'generated_at': datetime.utcnow().isoformat(),
                'data': await self._generate_chat_statistics(chat_id, start_date, end_date)
            }
        
        return {}

    async def handle_backup_data(self, task_data: Dict[str, Any]) -> bool:
        """Обработка задачи резервного копирования данных"""
        try:
            backup_type = task_data.get('backup_type', 'full')  # full, incremental, differential
            destination = task_data.get('destination', 'cloud')
            
            # Выполняем резервное копирование
            backup_id = f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            
            # В реальном приложении здесь будет логика резервного копирования
            # В зависимости от типа и места назначения
            if backup_type == 'full':
                logger.info(f"Starting full backup {backup_id}")
            elif backup_type == 'incremental':
                logger.info(f"Starting incremental backup {backup_id}")
            
            # Обновляем статус резервного копирования
            async with db_pool.acquire() as conn:
                await conn.execute(
                    '''
                    INSERT INTO backups (id, type, destination, status, started_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ''',
                    backup_id, backup_type, destination, 'completed', datetime.utcnow()
                )
            
            logger.info(f"Backup {backup_id} completed")
            return True
        except Exception as e:
            logger.error(f"Error handling backup_data task: {e}")
            # Обновляем статус как неудачный
            backup_id = f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_failed"
            async with db_pool.acquire() as conn:
                await conn.execute(
                    '''
                    INSERT INTO backups (id, type, destination, status, started_at, error_message)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ''',
                    backup_id, backup_type, destination, 'failed', datetime.utcnow(), str(e)
                )
            return False

    async def handle_update_user_stats(self, task_data: Dict[str, Any]) -> bool:
        """Обработка задачи обновления статистики пользователя"""
        try:
            user_id = task_data.get('user_id')
            
            # Обновляем статистику пользователя
            async with db_pool.acquire() as conn:
                # Получаем количество сообщений пользователя
                message_count = await conn.fetchval(
                    '''
                    SELECT COUNT(*) FROM messages WHERE sender_id = $1
                    ''',
                    user_id
                )
                
                # Получаем последнее время активности
                last_activity = await conn.fetchval(
                    '''
                    SELECT MAX(timestamp) FROM messages WHERE sender_id = $1
                    ''',
                    user_id
                )
                
                # Обновляем статистику в таблице пользователей
                await conn.execute(
                    '''
                    UPDATE users SET 
                        message_count = $1, 
                        last_activity = $2 
                    WHERE id = $3
                    ''',
                    message_count, last_activity, user_id
                )
            
            logger.info(f"User stats updated for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error handling update_user_stats task: {e}")
            return False

    async def handle_process_media(self, task_data: Dict[str, Any]) -> bool:
        """Обработка задачи обработки медиа-файла"""
        try:
            file_id = task_data.get('file_id')
            operations = task_data.get('operations', [])  # список операций для выполнения
            
            # Выполняем операции над медиа-файлом
            for operation in operations:
                op_type = operation.get('type')
                params = operation.get('params', {})
                
                if op_type == 'transcode':
                    # Перекодирование видео/аудио
                    quality = params.get('quality', 'medium')
                    format = params.get('format', 'mp4')
                    logger.info(f"Transcoding file {file_id} to {format} with {quality} quality")
                elif op_type == 'extract_thumbnail':
                    # Извлечение миниатюры
                    size = params.get('size', '128x128')
                    logger.info(f"Extracting thumbnail {size} from file {file_id}")
                elif op_type == 'watermark':
                    # Добавление водяного знака
                    position = params.get('position', 'bottom-right')
                    logger.info(f"Adding watermark at {position} to file {file_id}")
            
            # Обновляем статус файла
            async with db_pool.acquire() as conn:
                await conn.execute(
                    '''
                    UPDATE files SET 
                        media_processed = true, 
                        media_processed_at = $1 
                    WHERE id = $2
                    ''',
                    datetime.utcnow(), file_id
                )
            
            logger.info(f"Media processing completed for file {file_id}")
            return True
        except Exception as e:
            logger.error(f"Error handling process_media task: {e}")
            return False

    async def handle_sync_external_service(self, task_data: Dict[str, Any]) -> bool:
        """Обработка задачи синхронизации с внешним сервисом"""
        try:
            service_name = task_data.get('service_name')
            sync_type = task_data.get('sync_type')  # full, delta, webhook
            filters = task_data.get('filters', {})
            
            # В реальном приложении здесь будет синхронизация с внешним сервисом
            # Например, с календарем, задачами, файловым хранилищем и т.д.
            if service_name == 'calendar':
                logger.info(f"Synchronizing calendar data ({sync_type})")
            elif service_name == 'task_manager':
                logger.info(f"Synchronizing task manager data ({sync_type})")
            elif service_name == 'cloud_storage':
                logger.info(f"Synchronizing cloud storage data ({sync_type})")
            
            # Обновляем статус синхронизации
            sync_id = f"sync_{service_name}_{datetime.utcnow().timestamp()}"
            async with db_pool.acquire() as conn:
                await conn.execute(
                    '''
                    INSERT INTO sync_operations (id, service_name, type, status, started_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ''',
                    sync_id, service_name, sync_type, 'completed', datetime.utcnow()
                )
            
            logger.info(f"Sync operation {sync_id} completed for {service_name}")
            return True
        except Exception as e:
            logger.error(f"Error handling sync_external_service task: {e}")
            return False

    async def process_message(self, message: IncomingMessage):
        """Обработка сообщения из очереди"""
        async with message.process():
            try:
                task_data = json.loads(message.body.decode())
                task_type = task_data.get('task_type')
                
                logger.info(f"Processing task: {task_type}")
                
                if task_type in self.task_handlers:
                    success = await self.task_handlers[task_type](task_data)
                    
                    if success:
                        logger.info(f"Task {task_type} completed successfully")
                    else:
                        logger.error(f"Task {task_type} failed")
                        # Помечаем сообщение как необработанное для повторной попытки
                        if message.delivery_tag:
                            await message.nack(requeue=True)
                else:
                    logger.error(f"Unknown task type: {task_type}")
                    # Отправляем в очередь ошибок
                    await self.publish_to_error_queue(task_type, task_data, "Unknown task type")
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                # Помечаем сообщение как необработанное для повторной попытки
                if message.delivery_tag:
                    await message.nack(requeue=True)

    async def publish_task(self, task_type: str, task_data: Dict[str, Any]) -> bool:
        """Публикация задачи в очередь"""
        try:
            # Добавляем тип задачи к данным
            task_data['task_type'] = task_type
            task_data['created_at'] = datetime.utcnow().isoformat()
            
            # Публикуем в очередь
            exchange = await channel.declare_exchange('tasks', ExchangeType.TOPIC, durable=True)
            queue = await channel.declare_queue(task_type, durable=True)
            await queue.bind(exchange, routing_key=task_type)
            
            await exchange.publish(
                aio_pika.Message(
                    json.dumps(task_data).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                ),
                routing_key=task_type
            )
            
            logger.info(f"Task {task_type} published to queue")
            return True
        except Exception as e:
            logger.error(f"Error publishing task: {e}")
            return False

    async def publish_to_error_queue(self, task_type: str, task_data: Dict[str, Any], error: str):
        """Публикация задачи в очередь ошибок"""
        error_data = {
            'original_task_type': task_type,
            'original_task_data': task_data,
            'error': error,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        try:
            exchange = await channel.declare_exchange('errors', ExchangeType.TOPIC, durable=True)
            error_queue = await channel.declare_queue('error_tasks', durable=True)
            await error_queue.bind(exchange, routing_key='error')
            
            await exchange.publish(
                aio_pika.Message(
                    json.dumps(error_data).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                ),
                routing_key='error'
            )
            
            logger.error(f"Task moved to error queue: {error}")
        except Exception as e:
            logger.error(f"Error publishing to error queue: {e}")

    async def setup_queues(self):
        """Настройка очередей"""
        # Объявляем обменник
        exchange = await channel.declare_exchange('tasks', ExchangeType.TOPIC, durable=True)
        
        # Объявляем очереди для различных типов задач
        queues = [
            'send_message', 'process_file', 'send_notification', 
            'generate_report', 'backup_data', 'update_user_stats',
            'process_media', 'sync_external_service'
        ]
        
        for queue_name in queues:
            queue = await channel.declare_queue(queue_name, durable=True)
            await queue.bind(exchange, routing_key=queue_name)
        
        # Очередь для ошибок
        error_exchange = await channel.declare_exchange('errors', ExchangeType.TOPIC, durable=True)
        error_queue = await channel.declare_queue('error_tasks', durable=True)
        await error_queue.bind(error_exchange, routing_key='error')
        
        logger.info("Queues setup completed")

# Инициализация процессора задач
task_processor = TaskProcessor()

async def consume_tasks():
    """Потребление задач из очередей"""
    await task_processor.setup_queues()
    
    # Подписываемся на все очереди задач
    queues = [
        'send_message', 'process_file', 'send_notification', 
        'generate_report', 'backup_data', 'update_user_stats',
        'process_media', 'sync_external_service'
    ]
    
    for queue_name in queues:
        queue = await channel.declare_queue(queue_name, durable=True)
        await queue.consume(task_processor.process_message)
    
    logger.info("Started consuming tasks from queues")
    
    # Держим соединение открытым
    await asyncio.Future()

async def init_db():
    """Инициализация базы данных"""
    global db_pool
    db_pool = await asyncpg.create_pool(config.DB_URL, min_size=5, max_size=20)

async def init_redis():
    """Инициализация Redis"""
    global redis_client
    redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)

async def init_rabbitmq():
    """Инициализация RabbitMQ"""
    global connection, channel
    connection = await connect_robust(config.RABBITMQ_URL)
    channel = await connection.channel()
    
    # Устанавливаем prefetch count для равномерного распределения задач
    await channel.set_qos(prefetch_count=10)

async def main():
    """Основная функция запуска"""
    await init_db()
    await init_redis()
    await init_rabbitmq()
    
    # Запускаем потребление задач
    await consume_tasks()

if __name__ == '__main__':
    asyncio.run(main())
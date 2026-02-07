# Notification Service
# File: services/notification_service/main.py

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
from aiohttp import web
import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
class Config:
    DB_URL = os.getenv('DB_URL', 'postgresql://messenger:password@db:5432/messenger')
    REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379')
    FCM_SERVER_KEY = os.getenv('FCM_SERVER_KEY', '')  # Firebase Cloud Messaging
    APNS_CERT_PATH = os.getenv('APNS_CERT_PATH', '')  # Apple Push Notification Service

config = Config()

# Глобальные переменные
db_pool = None
redis_client = None

class Notification(BaseModel):
    user_id: int
    title: str
    body: str
    type: str = 'info'  # info, warning, error, success
    data: Optional[Dict] = None
    scheduled_time: Optional[datetime] = None

class NotificationService:
    def __init__(self):
        self.db_pool = None
        self.redis_client = None
        self.push_service = None

    async def send_push_notification(self, user_id: int, title: str, body: str, notification_type: str = 'info', data: Dict = None) -> bool:
        """Отправка push-уведомления пользователю"""
        # Получаем токены устройства пользователя
        device_tokens = await self.get_user_device_tokens(user_id)
        
        success_count = 0
        
        for token in device_tokens:
            # Определяем тип устройства по токену
            if self.is_fcm_token(token):
                # Отправка через Firebase Cloud Messaging
                sent = await self.send_fcm_notification(token, title, body, notification_type, data)
                if sent:
                    success_count += 1
            elif self.is_apns_token(token):
                # Отправка через Apple Push Notification Service
                sent = await self.send_apns_notification(token, title, body, notification_type, data)
                if sent:
                    success_count += 1
        
        # Сохраняем уведомление в базу данных
        await self.save_notification(user_id, title, body, notification_type, data, success_count > 0)
        
        return success_count > 0

    async def send_fcm_notification(self, token: str, title: str, body: str, notification_type: str, data: Dict) -> bool:
        """Отправка уведомления через Firebase Cloud Messaging"""
        if not config.FCM_SERVER_KEY:
            logger.warning("FCM server key not configured")
            return False
        
        headers = {
            'Authorization': f'key={config.FCM_SERVER_KEY}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'to': token,
            'notification': {
                'title': title,
                'body': body,
                'icon': 'ic_notification',
                'sound': 'default'
            },
            'data': data or {},
            'priority': 'high'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post('https://fcm.googleapis.com/fcm/send', headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        logger.info(f"FCM notification sent successfully to {token}")
                        return True
                    else:
                        logger.error(f"FCM notification failed: {resp.status}, {await resp.text()}")
                        return False
        except Exception as e:
            logger.error(f"Error sending FCM notification: {e}")
            return False

    async def send_apns_notification(self, token: str, title: str, body: str, notification_type: str, data: Dict) -> bool:
        """Отправка уведомления через Apple Push Notification Service"""
        if not config.APNS_CERT_PATH:
            logger.warning("APNS certificate not configured")
            return False
        
        # Реализуем полноценную отправку через APNS
        try:
            import asyncio
            from aiosmtplib import SMTP
            import jwt
            import time

            # Генерируем JWT токен для аутентификации с APNs
            private_key = config.APNS_PRIVATE_KEY
            team_id = config.APNS_TEAM_ID
            key_id = config.APNS_KEY_ID

            if not all([private_key, team_id, key_id]):
                logger.error("APNS credentials not configured")
                return False

            # Создаем JWT токен
            token = jwt.encode({
                'iss': team_id,
                'iat': int(time.time())
            }, private_key, algorithm='ES256', headers={'kid': key_id})

            # Формируем заголовки запроса
            headers = {
                'apns-expiration': str(int(time.time()) + 3600),  # 1 hour
                'apns-priority': '10',
                'apns-topic': config.APP_BUNDLE_ID,
                'authorization': f'bearer {token}'
            }

            # Формируем тело уведомления
            notification_payload = {
                'aps': {
                    'alert': {
                        'title': notification.title,
                        'body': notification.body
                    },
                    'badge': 1,
                    'sound': 'default'
                }
            }

            if notification.data:
                notification_payload.update(notification.data)

            # Отправляем запрос к APNs
            apns_url = f"https://api.push.apple.com/3/device/{token}"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    apns_url,
                    json=notification_payload,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        logger.info(f"APNS notification sent successfully to {token}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"APNS error {response.status}: {error_text}")
                        return False

        except Exception as e:
            logger.error(f"Error sending APNS notification to {token}: {e}")
            return False

    def is_fcm_token(self, token: str) -> bool:
        """Проверка, является ли токен FCM токеном"""
        # FCM токены обычно длинные строки
        return len(token) > 100 and token.startswith(('e', 'c', 'd'))

    def is_apns_token(self, token: str) -> bool:
        """Проверка, является ли токен APNS токеном"""
        # APNS токены обычно являются hex строками длиной 64 символа
        return len(token) == 64 and all(c in '0123456789abcdefABCDEF' for c in token)

    async def get_user_device_tokens(self, user_id: int) -> List[str]:
        """Получение токенов устройств пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT token FROM device_tokens WHERE user_id = $1 AND active = true
                ''',
                user_id
            )
        
        return [row['token'] for row in rows]

    async def save_notification(self, user_id: int, title: str, body: str, notification_type: str, data: Dict, sent: bool):
        """Сохранение уведомления в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO notifications (
                    user_id, title, body, type, data, sent, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ''',
                user_id, title, body, notification_type, json.dumps(data) if data else None, sent, datetime.utcnow()
            )

    async def schedule_notification(self, user_id: int, title: str, body: str, scheduled_time: datetime, notification_type: str = 'info', data: Dict = None) -> str:
        """Планирование уведомления"""
        notification_id = f"notification_{user_id}_{scheduled_time.timestamp()}"
        
        notification_data = {
            'id': notification_id,
            'user_id': user_id,
            'title': title,
            'body': body,
            'type': notification_type,
            'data': data,
            'scheduled_time': scheduled_time.isoformat(),
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Сохраняем запланированное уведомление в Redis
        await redis_client.setex(
            f"scheduled_notification:{notification_id}",
            int((scheduled_time - datetime.utcnow()).total_seconds()),
            json.dumps(notification_data)
        )
        
        # Добавляем в очередь планировщика
        await redis_client.zadd(
            "notification_scheduler_queue",
            {notification_id: scheduled_time.timestamp()}
        )
        
        return notification_id

    async def send_email_notification(self, user_id: int, subject: str, body: str) -> bool:
        """Отправка email уведомления"""
        # Используем централизованную функцию отправки email с сервера
        from ..main import send_email_notification as server_send_email
        success = await server_send_email(user_id, subject, body)

        if success:
            # Сохраняем в базу данных
            await self.save_notification(user_id, subject, body, 'email', {'email': await self.get_user_email(user_id)}, True)

        return success

    async def get_user_email(self, user_id: int) -> Optional[str]:
        """Получение email пользователя"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                SELECT email FROM users WHERE id = $1
                ''',
                user_id
            )
        
        return row['email'] if row and row['email'] else None

    async def mark_as_read(self, notification_id: str, user_id: int) -> bool:
        """Отметка уведомления как прочитанного"""
        async with db_pool.acquire() as conn:
            result = await conn.execute(
                '''
                UPDATE notifications SET read_at = $1 WHERE id = $2 AND user_id = $3
                ''',
                datetime.utcnow(), notification_id, user_id
            )
        
        return result != "UPDATE 0"

    async def get_user_notifications(self, user_id: int, limit: int = 50, offset: int = 0, unread_only: bool = False) -> List[Dict]:
        """Получение уведомлений пользователя"""
        query = '''
                SELECT id, title, body, type, data, sent, created_at, read_at
                FROM notifications
                WHERE user_id = $1
                '''
        
        params = [user_id]
        param_idx = 2
        
        if unread_only:
            query += f" AND read_at IS NULL"
        
        query += " ORDER BY created_at DESC LIMIT $" + str(param_idx) + " OFFSET $" + str(param_idx + 1)
        params.extend([limit, offset])
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        notifications = []
        for row in rows:
            notifications.append({
                'id': row['id'],
                'title': row['title'],
                'body': row['body'],
                'type': row['type'],
                'data': json.loads(row['data']) if row['data'] else {},
                'sent': row['sent'],
                'created_at': row['created_at'].isoformat(),
                'read_at': row['read_at'].isoformat() if row['read_at'] else None
            })
        
        return notifications

# Инициализация сервиса
notification_service = NotificationService()

async def send_push_handler(request):
    """Обработчик отправки push-уведомления"""
    data = await request.json()
    user_id = data.get('user_id')
    title = data.get('title')
    body = data.get('body')
    notification_type = data.get('type', 'info')
    notification_data = data.get('data')
    
    if not all([user_id, title, body]):
        return web.json_response({'error': 'Missing required fields'}, status=400)
    
    success = await notification_service.send_push_notification(
        user_id, title, body, notification_type, notification_data
    )
    
    if success:
        return web.json_response({'status': 'sent'})
    else:
        return web.json_response({'error': 'Failed to send notification'}, status=500)

async def schedule_handler(request):
    """Обработчик планирования уведомления"""
    data = await request.json()
    user_id = data.get('user_id')
    title = data.get('title')
    body = data.get('body')
    scheduled_time_str = data.get('scheduled_time')
    notification_type = data.get('type', 'info')
    notification_data = data.get('data')
    
    if not all([user_id, title, body, scheduled_time_str]):
        return web.json_response({'error': 'Missing required fields'}, status=400)
    
    try:
        scheduled_time = datetime.fromisoformat(scheduled_time_str.replace('Z', '+00:00'))
    except ValueError:
        return web.json_response({'error': 'Invalid date format'}, status=400)
    
    notification_id = await notification_service.schedule_notification(
        user_id, title, body, scheduled_time, notification_type, notification_data
    )
    
    return web.json_response({'notification_id': notification_id})

async def send_email_handler(request):
    """Обработчик отправки email-уведомления"""
    data = await request.json()
    user_id = data.get('user_id')
    subject = data.get('subject')
    body = data.get('body')
    
    if not all([user_id, subject, body]):
        return web.json_response({'error': 'Missing required fields'}, status=400)
    
    success = await notification_service.send_email_notification(user_id, subject, body)
    
    if success:
        return web.json_response({'status': 'sent'})
    else:
        return web.json_response({'error': 'Failed to send email'}, status=500)

async def get_user_notifications_handler(request):
    """Обработчик получения уведомлений пользователя"""
    user_id = int(request.match_info['user_id'])
    limit = int(request.query.get('limit', 50))
    offset = int(request.query.get('offset', 0))
    unread_only = request.query.get('unread_only', 'false').lower() == 'true'
    
    notifications = await notification_service.get_user_notifications(
        user_id, limit, offset, unread_only
    )
    
    return web.json_response({'notifications': notifications})

async def mark_as_read_handler(request):
    """Обработчик отметки уведомления как прочитанного"""
    notification_id = request.match_info['notification_id']
    data = await request.json()
    user_id = data.get('user_id')
    
    if not user_id:
        return web.json_response({'error': 'Missing user_id'}, status=400)
    
    success = await notification_service.mark_as_read(notification_id, user_id)
    
    if success:
        return web.json_response({'status': 'marked_as_read'})
    else:
        return web.json_response({'error': 'Failed to mark as read'}, status=400)

async def health_check(request):
    """Проверка состояния сервиса"""
    return web.json_response({'status': 'healthy'})

async def init_app():
    """Инициализация приложения"""
    app = web.Application()
    
    # Маршруты
    app.router.add_post('/push', send_push_handler)
    app.router.add_post('/schedule', schedule_handler)
    app.router.add_post('/email', send_email_handler)
    app.router.add_get('/users/{user_id}/notifications', get_user_notifications_handler)
    app.router.add_post('/notifications/{notification_id}/read', mark_as_read_handler)
    app.router.add_get('/health', health_check)
    
    return app

async def init_db():
    """Инициализация базы данных"""
    global db_pool
    db_pool = await asyncpg.create_pool(config.DB_URL, min_size=5, max_size=20)

async def init_redis():
    """Инициализация Redis"""
    global redis_client
    redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)

async def main():
    """Основная функция запуска"""
    await init_db()
    await init_redis()
    
    app = await init_app()
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', 8003)
    await site.start()
    
    logger.info("Notification Service запущен на порту 8003")
    
    # Бесконечный цикл
    await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())
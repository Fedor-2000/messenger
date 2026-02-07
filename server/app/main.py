import asyncio
import json
import logging
import os
import ssl
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, Set

import aiohttp
import asyncpg
import redis.asyncio as redis
from aiohttp import web
from aiohttp.web_middlewares import normalize_path_middleware
import jwt
import bcrypt
import base64
import hashlib
from pydantic import BaseModel
from cryptography.fernet import Fernet
import time
from collections import defaultdict, deque

# Метрики для мониторинга
import prometheus_client
from prometheus_client import Counter, Histogram, Gauge

# Импорт дополнительных компонентов
from .webrtc.signaling import webrtc_signaling_manager
from .games.minigames import game_manager
from .tasks.task_manager import task_manager
from .analytics.chat_analytics import chat_analytics_manager
from .calendar.calendar_integration import calendar_integration
from .advanced_auth import advanced_auth_manager
from .advanced_encryption import advanced_encryption
from .advanced_security import session_security

# Настройка логгирования
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
class Config:
    DB_URL = os.getenv('DATABASE_URL', 'postgresql://messenger:your-secure-password@db:5432/messenger')
    REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379')
    JWT_SECRET = os.getenv('JWT_SECRET', 'your-super-secret-jwt-key-change-it')
    MESSAGE_ENCRYPTION_KEY = os.getenv('MESSAGE_ENCRYPTION_KEY', 'your-message-encryption-key')
    TCP_HOST = os.getenv('TCP_HOST', '0.0.0.0')
    TCP_PORT = int(os.getenv('TCP_PORT', '8888'))
    HTTP_HOST = os.getenv('HTTP_HOST', '0.0.0.0')
    HTTP_PORT = int(os.getenv('HTTP_PORT', '8080'))
    SSL_CERT = os.getenv('SSL_CERT_PATH', '')
    SSL_KEY = os.getenv('SSL_KEY_PATH', '')

# Инициализация глобальных объектов
config = Config()
db_pool = None
redis_client = None

# Определение метрик Prometheus
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint']
)

ACTIVE_CONNECTIONS = Gauge(
    'active_connections',
    'Number of active WebSocket connections'
)

MESSAGES_SENT = Counter(
    'messages_sent_total',
    'Total number of messages sent',
    ['chat_type']
)

USERS_ONLINE = Gauge(
    'users_online',
    'Number of online users'
)

DATABASE_CONNECTIONS = Gauge(
    'database_connections',
    'Number of active database connections'
)

CACHE_HITS = Counter(
    'cache_hits_total',
    'Total number of cache hits'
)

CACHE_MISSES = Counter(
    'cache_misses_total',
    'Total number of cache misses'
)

# Импорт дополнительных компонентов
from .webrtc.signaling import webrtc_signaling_manager
from .games.minigames import game_manager
from .tasks.task_manager import task_manager
from .analytics.chat_analytics import chat_analytics_manager
from .calendar.calendar_integration import calendar_integration
from .advanced_auth import advanced_auth_manager
from .advanced_encryption import advanced_encryption
from .advanced_security import session_security

class TokenData(BaseModel):
    username: str

class SecurityManager:
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    
    @staticmethod
    def create_access_token(data: dict, expires_delta: timedelta = None):
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=30)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, config.JWT_SECRET, algorithm="HS256")
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str) -> TokenData:
        try:
            payload = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
            username: str = payload.get("sub")
            if username is None:
                return None
            token_data = TokenData(username=username)
            return token_data
        except jwt.exceptions.ExpiredSignatureError:
            return None
        except jwt.exceptions.JWTError:
            return None

class MessageEncryption:
    def __init__(self):
        key = config.MESSAGE_ENCRYPTION_KEY
        self.key = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
        self.cipher_suite = Fernet(self.key)
    
    def encrypt_message(self, message: str) -> str:
        encrypted_bytes = self.cipher_suite.encrypt(message.encode())
        return base64.b64encode(encrypted_bytes).decode()
    
    def decrypt_message(self, encrypted_message: str) -> str:
        encrypted_bytes = base64.b64decode(encrypted_message.encode())
        decrypted_bytes = self.cipher_suite.decrypt(encrypted_bytes)
        return decrypted_bytes.decode()

class RateLimiter:
    def __init__(self, max_requests: int = 10, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests: Dict[str, deque] = defaultdict(deque)
    
    def is_allowed(self, identifier: str) -> bool:
        current_time = time.time()
        
        # Удаляем старые запросы за пределами временного окна
        while (self.requests[identifier] and 
               current_time - self.requests[identifier][0] > self.time_window):
            self.requests[identifier].popleft()
        
        # Проверяем лимит
        if len(self.requests[identifier]) >= self.max_requests:
            return False
        
        # Добавляем новый запрос
        self.requests[identifier].append(current_time)
        return True

class ChatManager:
    def __init__(self, db_pool, redis_client):
        self.db_pool = db_pool
        self.redis = redis_client
        self.private_rooms = {}  # user_id -> [recipient_id]
        self.group_rooms = {}    # room_id -> [user_ids]
    
    async def create_private_chat(self, user1_id: int, user2_id: int):
        # Создание уникального ID для приватного чата
        chat_id = f"private_{min(user1_id, user2_id)}_{max(user1_id, user2_id)}"
        
        # Сохранение в базе данных
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO chats (id, type, participants) 
                VALUES ($1, 'private', ARRAY[$2, $3])
                ON CONFLICT (id) DO NOTHING
                ''',
                chat_id, user1_id, user2_id
            )
        
        return chat_id
    
    async def create_group_chat(self, creator_id: int, name: str, participants: list):
        # Создание группового чата
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                INSERT INTO chats (type, name, creator_id, participants) 
                VALUES ('group', $1, $2, $3) 
                RETURNING id
                ''',
                name, creator_id, participants
            )
            return row['id']
    
    async def send_private_message(self, sender_id: int, recipient_id: int, content: str):
        # Проверка, существует ли приватный чат
        chat_id = f"private_{min(sender_id, recipient_id)}_{max(sender_id, recipient_id)}"
        
        # Сохранение сообщения в базе
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO messages (chat_id, sender_id, content, message_type) 
                VALUES ($1, $2, $3, 'private')
                ''',
                chat_id, sender_id, content
            )
        
        # Отправка через Redis
        message_data = {
            'type': 'private_message',
            'chat_id': chat_id,
            'sender_id': sender_id,
            'content': content,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await self.redis.publish(f"chat:{chat_id}", json.dumps(message_data))
    
    async def send_group_message(self, chat_id: str, sender_id: int, content: str):
        # Сохранение сообщения в базе
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO messages (chat_id, sender_id, content, message_type) 
                VALUES ($1, $2, $3, 'group')
                ''',
                chat_id, sender_id, content
            )
        
        # Отправка через Redis
        message_data = {
            'type': 'group_message',
            'chat_id': chat_id,
            'sender_id': sender_id,
            'content': content,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await self.redis.publish(f"chat:{chat_id}", json.dumps(message_data))

class MessageBroker:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.local_connections: Dict[str, Set] = {
            'tcp': set(),
            'websocket': set()
        }

    async def publish_message(self, room: str, message: dict):
        """Публикация сообщения в Redis (для масштабирования)"""
        await self.redis.publish(f'room:{room}', json.dumps(message))

    async def subscribe_to_room(self, room: str, callback):
        """Подписка на сообщения из комнаты"""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(f'room:{room}')

        async for message in pubsub.listen():
            if message['type'] == 'message':
                await callback(json.loads(message['data']))

@asynccontextmanager
async def lifespan(app):
    """Управление жизненным циклом приложения"""
    global db_pool, redis_client

    # Инициализация подключений
    logger.info("Инициализация базы данных...")
    db_pool = await asyncpg.create_pool(config.DB_URL, min_size=5, max_size=20)

    logger.info("Инициализация Redis...")
    redis_client = redis.from_url(config.REDIS_URL, decode_responses=True, password=os.getenv('REDIS_PASSWORD'))

    # Инициализация дополнительных компонентов
    logger.info("Инициализация WebRTC сигнализации...")
    webrtc_signaling_manager.redis = redis_client
    webrtc_signaling_manager.db_pool = db_pool

    logger.info("Инициализация игрового менеджера...")
    game_manager.redis = redis_client
    game_manager.db_pool = db_pool

    logger.info("Инициализация менеджера задач...")
    task_manager.redis = redis_client
    task_manager.db_pool = db_pool

    logger.info("Инициализация аналитики чатов...")
    chat_analytics_manager.redis = redis_client
    chat_analytics_manager.db_pool = db_pool

    logger.info("Инициализация интеграции с календарем...")
    calendar_integration.redis = redis_client
    calendar_integration.db_pool = db_pool

    logger.info("Инициализация улучшенной аутентификации...")
    advanced_auth_manager.db_pool = db_pool
    advanced_auth_manager.redis = redis_client
    advanced_auth_manager.jwt_secret = config.JWT_SECRET
    # Генерация ключа шифрования из конфигурации
    from cryptography.fernet import Fernet
    import base64
    import hashlib
    key = base64.urlsafe_b64encode(hashlib.sha256(config.MESSAGE_ENCRYPTION_KEY.encode()).digest())
    advanced_auth_manager.encryption_key = key

    logger.info("Инициализация улучшенного шифрования...")
    advanced_encryption.master_key = hashlib.sha256(config.MESSAGE_ENCRYPTION_KEY.encode()).digest()[:32]

    logger.info("Инициализация безопасности сессий...")
    session_security.redis = redis_client

    # Создание таблиц при необходимости
    async with db_pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255),
                created_at TIMESTAMP DEFAULT NOW(),
                avatar VARCHAR(255) DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS chats (
                id VARCHAR(100) PRIMARY KEY,
                type VARCHAR(20) NOT NULL,
                name VARCHAR(100),
                creator_id INTEGER REFERENCES users(id),
                participants INTEGER[],
                created_at TIMESTAMP DEFAULT NOW(),
                last_message TEXT,
                last_activity TIMESTAMP DEFAULT NOW(),
                unread_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                chat_id VARCHAR(100) REFERENCES chats(id),
                sender_id INTEGER REFERENCES users(id),
                content TEXT NOT NULL,
                message_type VARCHAR(20) DEFAULT 'text',
                timestamp TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS files (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                stored_name VARCHAR(255) NOT NULL,
                uploader_id INTEGER REFERENCES users(id),
                size BIGINT,
                mime_type VARCHAR(100),
                uploaded_at TIMESTAMP DEFAULT NOW()
            );

            -- Таблицы для WebRTC
            CREATE TABLE IF NOT EXISTS call_sessions (
                session_id VARCHAR(100) PRIMARY KEY,
                caller_id INTEGER REFERENCES users(id),
                callee_id INTEGER REFERENCES users(id),
                media_types TEXT[],
                started_at TIMESTAMP DEFAULT NOW(),
                ended_at TIMESTAMP,
                status VARCHAR(20) DEFAULT 'initiated'
            );

            -- Таблицы для задач
            CREATE TABLE IF NOT EXISTS tasks (
                id VARCHAR(100) PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                assignee_id INTEGER REFERENCES users(id),
                creator_id INTEGER REFERENCES users(id),
                due_date TIMESTAMP,
                priority VARCHAR(20) DEFAULT 'medium',
                status VARCHAR(20) DEFAULT 'pending',
                task_type VARCHAR(20) DEFAULT 'personal',
                chat_id VARCHAR(100),
                group_id VARCHAR(100),
                project_id VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP,
                estimated_hours DECIMAL(5,2),
                actual_hours DECIMAL(5,2),
                tags TEXT[],
                attachments JSONB,
                subtasks TEXT[],
                parent_task VARCHAR(100)
            );

            -- Таблицы для календаря
            CREATE TABLE IF NOT EXISTS calendar_events (
                id VARCHAR(100) PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP NOT NULL,
                timezone VARCHAR(50) DEFAULT 'UTC',
                creator_id INTEGER REFERENCES users(id),
                event_type VARCHAR(20) DEFAULT 'custom',
                privacy VARCHAR(20) DEFAULT 'private',
                location VARCHAR(255),
                recurrence_pattern VARCHAR(20),
                recurrence_end TIMESTAMP,
                reminder_minutes INTEGER DEFAULT 15,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                chat_id VARCHAR(100)
            );

            CREATE TABLE IF NOT EXISTS event_attendees (
                event_id VARCHAR(100) REFERENCES calendar_events(id),
                user_id INTEGER REFERENCES users(id),
                status VARCHAR(20) DEFAULT 'pending',
                PRIMARY KEY (event_id, user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
            CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        ''')

    yield

    # Очистка при завершении
    logger.info("Завершение работы...")
    await db_pool.close()
    await redis_client.close()

# Создаем приложение с lifespan
app = web.Application(middlewares=[normalize_path_middleware()])
app['config'] = config
app['db'] = db_pool
app['redis'] = redis_client

# Инициализация менеджеров
security_manager = SecurityManager()
encryption = MessageEncryption()
rate_limiter = RateLimiter()
chat_manager = ChatManager(db_pool, redis_client) if db_pool and redis_client else None

# Обработчики запросов
async def metrics_handler(request):
    """Endpoint для метрик Prometheus"""
    from aiohttp.web_response import Response
    output = prometheus_client.generate_latest(prometheus_client.REGISTRY)
    return Response(body=output, content_type='text/plain')

async def websocket_handler(request):
    """Обработчик WebSocket соединений"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    logger.info(f'[WS] Новое подключение')
    
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    message = json.loads(msg.data)
                    logger.debug(f'[WS] Получено: {message}')
                    
                    # Проверка рейт-лимита
                    client_ip = request.remote
                    if not rate_limiter.is_allowed(client_ip):
                        await ws.send_str(json.dumps({
                            'type': 'rate_limit_exceeded',
                            'message': 'Rate limit exceeded. Please slow down.'
                        }))
                        continue
                    
                    # Обработка сообщений
                    msg_type = message.get('type')
                    
                    if msg_type == 'auth':
                        username = message.get('username')
                        password = message.get('password')
                        tfa_code = message.get('tfa_code')  # Двухфакторный код (если включен)

                        # Используем улучшенную аутентификацию
                        auth_result = await advanced_auth_manager.authenticate_user(
                            username, password, tfa_code
                        )

                        if auth_result:
                            # Получаем IP-адрес клиента
                            client_ip = request.remote or request.headers.get('X-Forwarded-For', '').split(',')[0].strip()

                            # Создаем защищенную сессию
                            device_fingerprint = message.get('device_fingerprint', f"{request.headers.get('User-Agent', '')}{client_ip}")
                            session_id = await session_security.create_secure_session(
                                auth_result['user_id'],
                                device_fingerprint,
                                client_ip,
                                request.headers.get('User-Agent', '')
                            )

                            if session_id:
                                response = {
                                    'type': 'auth_success',
                                    'access_token': auth_result['access_token'],
                                    'refresh_token': auth_result['refresh_token'],
                                    'user_id': auth_result['user_id'],
                                    'username': auth_result['username'],
                                    'expires_in': auth_result['expires_in'],
                                    'session_id': session_id
                                }

                                # Отправляем последние сообщения новому пользователю
                                recent_msgs = await get_recent_messages('general', 50)
                                for msg_data in recent_msgs:
                                    await ws.send_str(json.dumps({
                                        'type': 'history_message',
                                        'user': msg_data['user'],
                                        'text': msg_data['text'],
                                        'timestamp': msg_data['timestamp']
                                    }))
                            else:
                                response = {
                                    'type': 'auth_error',
                                    'message': 'Account temporarily locked due to suspicious activity'
                                }
                        else:
                            # Проверяем рейт-лимит для аутентификации
                            client_ip = request.remote or request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
                            is_rate_limited = await session_security.is_rate_limited(
                                client_ip, 'login_attempts'
                            )

                            if is_rate_limited:
                                response = {
                                    'type': 'auth_error',
                                    'message': 'Too many failed login attempts. Please try again later.'
                                }
                            else:
                                response = {
                                    'type': 'auth_error',
                                    'message': 'Invalid credentials or 2FA code'
                                }

                        await ws.send_str(json.dumps(response))
                    
                    elif msg_type == 'message':
                        token = message.get('token')

                        # Используем улучшенную проверку токена
                        token_payload = await advanced_auth_manager.verify_token(token)

                        if not token_payload or token_payload['token_type'] != 'access':
                            await ws.send_str(json.dumps({
                                'type': 'auth_error',
                                'message': 'Invalid or expired token'
                            }))
                            continue

                        # Проверяем рейт-лимит для отправки сообщений
                        client_ip = request.remote or request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
                        is_rate_limited = await session_security.is_rate_limited(
                            client_ip, 'message_sending'
                        )

                        if is_rate_limited:
                            await ws.send_str(json.dumps({
                                'type': 'rate_limit_exceeded',
                                'message': 'Too many messages sent. Please slow down.'
                            }))
                            continue

                        # Получаем ID пользователя из токена
                        user_id = token_payload['user_id']

                        # Получаем имя пользователя из базы данных
                        async with db_pool.acquire() as conn:
                            user_record = await conn.fetchrow(
                                "SELECT username FROM users WHERE id = $1",
                                user_id
                            )

                        if not user_record:
                            await ws.send_str(json.dumps({
                                'type': 'auth_error',
                                'message': 'User not found'
                            }))
                            continue

                        username = user_record['username']

                        # Сохраняем сообщение в базу данных
                        content = message.get('text')

                        # Используем улучшенное шифрование
                        encrypted_data = advanced_encryption.encrypt_message(content)
                        encrypted_content = json.dumps(encrypted_data)

                        async with db_pool.acquire() as conn:
                            await conn.execute(
                                '''
                                INSERT INTO messages (chat_id, sender_id, content, message_type)
                                VALUES ($1, $2, $3, $4)
                                ''',
                                'general', user_id, encrypted_content, 'text'
                            )

                        # Рассылка сообщения всем
                        broadcast_msg = {
                            'type': 'new_message',
                            'user': username,
                            'text': content,  # Отправляем расшифрованное сообщение
                            'timestamp': datetime.utcnow().isoformat()
                        }

                        # Отправка через Redis для широковещательной рассылки
                        await redis_client.publish('room:general', json.dumps(broadcast_msg))
                        
                except json.JSONDecodeError:
                    logger.error("Ошибка парсинга JSON")
                except Exception as e:
                    logger.error(f"Ошибка обработки сообщения: {e}")
                    await ws.send_str(json.dumps({
                        'type': 'error',
                        'message': 'Internal server error'
                    }))

            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f'[WS] Ошибка: {ws.exception()}')

    finally:
        logger.info(f'[WS] Подключение закрыто')

    return ws

async def get_recent_messages(room: str, limit: int = 50):
    """Получение последних сообщений из базы данных"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            '''
            SELECT m.sender_id, u.username, m.content, m.timestamp
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.chat_id = $1
            ORDER BY m.timestamp DESC
            LIMIT $2
            ''',
            room, limit
        )

        messages = []
        for row in reversed(rows):  # Обратный порядок (новые внизу)
            # Расшифровка сообщения
            try:
                # Проверяем, является ли контент JSON (новый формат шифрования)
                import json
                encrypted_data = json.loads(row['content'])
                if isinstance(encrypted_data, dict) and 'ciphertext' in encrypted_data:
                    # Это новое зашифрованное сообщение
                    decrypted_content = advanced_encryption.decrypt_message(encrypted_data)
                else:
                    # Это старое зашифрованное сообщение
                    decrypted_content = encryption.decrypt_message(row['content'])
            except json.JSONDecodeError:
                # Это может быть незашифрованное сообщение или старый формат
                try:
                    decrypted_content = encryption.decrypt_message(row['content'])
                except:
                    decrypted_content = row['content']  # Если не удается расшифровать

            messages.append({
                'user': row['username'],
                'text': decrypted_content,
                'timestamp': row['timestamp'].isoformat()
            })

        return messages

async def rest_api_handler(request):
    """Обработчик REST запросов"""
    if request.content_type != 'application/json':
        return web.json_response({'error': 'Требуется JSON'}, status=400)
    
    data = await request.json()
    action = request.match_info['action']

    if action == 'login':
        username = data.get('username')
        password = data.get('password')
        tfa_code = data.get('tfa_code')  # Двухфакторный код (если включен)

        # Проверяем рейт-лимит для аутентификации
        client_ip = request.remote or request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
        is_rate_limited = await session_security.is_rate_limited(
            client_ip, 'login_attempts'
        )

        if is_rate_limited:
            return web.json_response({
                'success': False,
                'error': 'Too many failed login attempts. Please try again later.'
            }, status=429)  # Too Many Requests

        # Используем улучшенную аутентификацию
        auth_result = await advanced_auth_manager.authenticate_user(
            username, password, tfa_code
        )

        if auth_result:
            # Создаем защищенную сессию
            device_fingerprint = data.get('device_fingerprint', f"{request.headers.get('User-Agent', '')}{client_ip}")
            session_id = await session_security.create_secure_session(
                auth_result['user_id'],
                device_fingerprint,
                client_ip,
                request.headers.get('User-Agent', '')
            )

            if session_id:
                return web.json_response({
                    'success': True,
                    'access_token': auth_result['access_token'],
                    'refresh_token': auth_result['refresh_token'],
                    'session_id': session_id,
                    'user': {
                        'id': auth_result['user_id'],
                        'username': auth_result['username']
                    }
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': 'Account temporarily locked due to suspicious activity'
                }, status=403)
        else:
            return web.json_response({
                'success': False,
                'error': 'Invalid credentials or 2FA code'
            }, status=401)
    
    elif action == 'register':
        username = data.get('username')
        password = data.get('password')
        
        # Хеширование пароля
        password_hash = security_manager.get_password_hash(password)
        
        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    '''
                    INSERT INTO users (username, password_hash) 
                    VALUES ($1, $2) 
                    RETURNING id, username
                    ''',
                    username, password_hash
                )
                
                return web.json_response({
                    'success': True,
                    'user': {
                        'id': row['id'],
                        'username': row['username']
                    }
                })
        except asyncpg.UniqueViolationError:
            return web.json_response({
                'success': False,
                'error': 'Username already exists'
            }, status=400)
    
    elif action == 'send':
        token = data.get('token')

        # Используем улучшенную проверку токена
        token_payload = await advanced_auth_manager.verify_token(token)

        if not token_payload or token_payload['token_type'] != 'access':
            return web.json_response({
                'error': 'Invalid or expired token'
            }, status=401)

        # Проверяем рейт-лимит для отправки сообщений
        client_ip = request.remote or request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
        is_rate_limited = await session_security.is_rate_limited(
            client_ip, 'message_sending'
        )

        if is_rate_limited:
            return web.json_response({
                'error': 'Too many messages sent. Please slow down.',
                'retry_after': 60  # Указываем, когда можно снова пробовать
            }, status=429)

        # Получаем ID пользователя из токена
        user_id = token_payload['user_id']

        # Получаем имя пользователя из базы данных
        async with db_pool.acquire() as conn:
            user_record = await conn.fetchrow(
                "SELECT username FROM users WHERE id = $1",
                user_id
            )

        if not user_record:
            return web.json_response({
                'error': 'User not found'
            }, status=404)

        username = user_record['username']

        content = data.get('content')

        # Используем улучшенное шифрование
        encrypted_data = advanced_encryption.encrypt_message(content)
        encrypted_content = json.dumps(encrypted_data)

        async with db_pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO messages (chat_id, sender_id, content, message_type)
                VALUES ($1, $2, $3, $4)
                ''',
                'general', user_id, encrypted_content, 'text'
            )

        # Рассылка сообщения всем
        broadcast_msg = {
            'type': 'new_message',
            'user': username,
            'text': content,  # Отправляем расшифрованное сообщение
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправка через Redis для широковещательной рассылки
        await redis_client.publish('room:general', json.dumps(broadcast_msg))

        return web.json_response({
            'status': 'ok',
            'timestamp': datetime.utcnow().isoformat()
        })
    
    elif action == 'history':
        limit = int(request.query.get('limit', 50))
        history = await get_recent_messages('general', limit)
        return web.json_response({'history': history})
    
    else:
        return web.json_response({'error': 'Неизвестный API метод'}, status=404)

async def init_app():
    """Инициализация aiohttp приложения"""
    app = web.Application()
    app.router.add_get('/ws', websocket_handler)
    app.router.add_post('/api/{action}', rest_api_handler)
    
    # Статичные файлы для web клиента
    app.router.add_static('/', './static/')
    
    return app

async def handle_tcp_client(reader, writer):
    """Обработчик TCP-соединений для нативных клиентов"""
    addr = writer.get_extra_info('peername')
    logger.info(f'[TCP] Новое подключение: {addr}')

    try:
        while True:
            # Чтение данных (ожидаем JSON с переводом строки)
            data = await reader.readuntil(b'\n')
            message = json.loads(data.decode().strip())

            logger.debug(f'[TCP] Получено: {message}')

            # Проверка рейт-лимита
            client_ip = addr[0]
            if not rate_limiter.is_allowed(client_ip):
                response = {
                    'type': 'rate_limit_exceeded',
                    'message': 'Rate limit exceeded. Please slow down.'
                }
                writer.write((json.dumps(response) + '\n').encode())
                await writer.drain()
                continue

            # Обработка команды
            msg_type = message.get('type')
            
            if msg_type == 'auth':
                username = message.get('username')
                password = message.get('password')
                tfa_code = message.get('tfa_code')  # Двухфакторный код (если включен)

                # Используем улучшенную аутентификацию
                auth_result = await advanced_auth_manager.authenticate_user(
                    username, password, tfa_code
                )

                if auth_result:
                    # Создаем защищенную сессию
                    client_ip = addr[0]
                    device_fingerprint = message.get('device_fingerprint', f"C++_client_{client_ip}")
                    session_id = await session_security.create_secure_session(
                        auth_result['user_id'],
                        device_fingerprint,
                        client_ip,
                        "C++ Client"
                    )

                    if session_id:
                        response = {
                            'type': 'auth_success',
                            'access_token': auth_result['access_token'],
                            'refresh_token': auth_result['refresh_token'],
                            'user_id': auth_result['user_id'],
                            'username': auth_result['username'],
                            'expires_in': auth_result['expires_in'],
                            'session_id': session_id
                        }
                    else:
                        response = {
                            'type': 'auth_error',
                            'message': 'Account temporarily locked due to suspicious activity'
                        }
                else:
                    # Проверяем рейт-лимит для аутентификации
                    client_ip = addr[0]
                    is_rate_limited = await session_security.is_rate_limited(
                        client_ip, 'login_attempts'
                    )

                    if is_rate_limited:
                        response = {
                            'type': 'auth_error',
                            'message': 'Too many failed login attempts. Please try again later.'
                        }
                    else:
                        response = {
                            'type': 'auth_error',
                            'message': 'Invalid credentials or 2FA code'
                        }

                writer.write((json.dumps(response) + '\n').encode())
                await writer.drain()

            elif msg_type == 'message':
                token = message.get('token')

                # Используем улучшенную проверку токена
                token_payload = await advanced_auth_manager.verify_token(token)

                if not token_payload or token_payload['token_type'] != 'access':
                    response = {
                        'type': 'auth_error',
                        'message': 'Invalid or expired token'
                    }
                    writer.write((json.dumps(response) + '\n').encode())
                    await writer.drain()
                    continue

                # Проверяем рейт-лимит для отправки сообщений
                client_ip = addr[0]
                is_rate_limited = await session_security.is_rate_limited(
                    client_ip, 'message_sending'
                )

                if is_rate_limited:
                    response = {
                        'type': 'rate_limit_exceeded',
                        'message': 'Too many messages sent. Please slow down.'
                    }
                    writer.write((json.dumps(response) + '\n').encode())
                    await writer.drain()
                    continue

                # Получаем ID пользователя из токена
                user_id = token_payload['user_id']

                # Получаем имя пользователя из базы данных
                async with db_pool.acquire() as conn:
                    user_record = await conn.fetchrow(
                        "SELECT username FROM users WHERE id = $1",
                        user_id
                    )

                if not user_record:
                    response = {
                        'type': 'auth_error',
                        'message': 'User not found'
                    }
                    writer.write((json.dumps(response) + '\n').encode())
                    await writer.drain()
                    continue

                username = user_record['username']

                # Сохраняем сообщение в базу данных
                content = message.get('text')

                # Используем улучшенное шифрование
                encrypted_data = advanced_encryption.encrypt_message(content)
                encrypted_content = json.dumps(encrypted_data)

                async with db_pool.acquire() as conn:
                    await conn.execute(
                        '''
                        INSERT INTO messages (chat_id, sender_id, content, message_type)
                        VALUES ($1, $2, $3, $4)
                        ''',
                        'general', user_id, encrypted_content, 'text'
                    )

                # Рассылка сообщения всем
                broadcast_msg = {
                    'type': 'new_message',
                    'user': username,
                    'text': content,  # Отправляем расшифрованное сообщение
                    'timestamp': datetime.utcnow().isoformat()
                }

                # Отправка через Redis для широковещательной рассылки
                await redis_client.publish('room:general', json.dumps(broadcast_msg))

    except (asyncio.IncompleteReadError, ConnectionError, json.JSONDecodeError):
        logger.info(f'[TCP] Клиент отключился: {addr}')
    finally:
        writer.close()

# --- Обработчики уведомлений ---
async def send_email_notification(user_id: int, subject: str, body: str) -> bool:
    """Отправка email-уведомления пользователю"""
    try:
        # Получаем email пользователя из базы данных
        async with db_pool.acquire() as conn:
            user_record = await conn.fetchrow(
                "SELECT email FROM users WHERE id = $1",
                user_id
            )

        if not user_record or not user_record['email']:
            logger.warning(f"No email address found for user {user_id}")
            return False

        user_email = user_record['email']

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
        msg = MIMEMultipart()
        msg['From'] = os.getenv('EMAIL_FROM', 'noreply@messenger.com')
        msg['To'] = user_email
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
        import aiosmtplib
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with aiosmtplib.SMTP(hostname=smtp_host, port=smtp_port, use_tls=smtp_use_tls) as server:
                    await server.login(smtp_user, smtp_password)
                    await server.send_message(msg)

                logger.info(f"Email notification sent successfully to {user_email}")
                return True

            except Exception as smtp_error:
                logger.warning(f"Attempt {attempt + 1} failed to send email to {user_email}: {smtp_error}")
                if attempt == max_retries - 1:  # Последняя попытка
                    logger.error(f"Failed to send email notification to {user_email}: {smtp_error}")
                    return False
                await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка

    except Exception as e:
        logger.error(f"Error sending email notification to user {user_id}: {e}")
        return False

async def send_sms_notification(user_id: int, message: str) -> bool:
    """Отправка SMS-уведомления пользователю"""
    try:
        # Получаем телефон пользователя из базы данных
        async with db_pool.acquire() as conn:
            user_record = await conn.fetchrow(
                "SELECT phone FROM users WHERE id = $1",
                user_id
            )

        if not user_record or not user_record['phone']:
            logger.warning(f"No phone number found for user {user_id}")
            return False

        user_phone = user_record['phone']

        # Нормализуем номер телефона
        normalized_phone = _normalize_phone_number(user_phone)
        if not normalized_phone:
            logger.warning(f"Invalid phone number format for user {user_id}: {user_phone}")
            return False

        # Подготовка текста SMS с ограничением длины
        sms_text = message[:160]  # Ограничение для SMS

        # Определяем провайдера SMS-услуг
        sms_provider = os.getenv('SMS_PROVIDER', 'twilio').lower()

        success = False
        if sms_provider == 'twilio':
            success = await _send_sms_via_twilio(normalized_phone, sms_text)
        elif sms_provider == 'aws_sns':
            success = await _send_sms_via_aws_sns(normalized_phone, sms_text)
        elif sms_provider == 'fake':  # Для тестирования
            success = await _send_sms_fake(normalized_phone, sms_text)
        else:
            logger.warning(f"Unknown SMS provider: {sms_provider}. Using fake provider.")
            success = await _send_sms_fake(normalized_phone, sms_text)

        if success:
            logger.info(f"SMS notification sent successfully to {normalized_phone}")
            return True
        else:
            logger.error(f"Failed to send SMS notification to {normalized_phone}")
            return False

    except Exception as e:
        logger.error(f"Error sending SMS notification to user {user_id}: {e}")
        return False

def _normalize_phone_number(phone_number: str) -> str:
    """Нормализация номера телефона"""
    import re

    if not phone_number:
        return None

    # Удаляем все нецифровые символы
    digits_only = re.sub(r'\D', '', phone_number)

    # Проверяем длину и формат
    if len(digits_only) == 10:  # США/Канада без кода страны
        return '+1' + digits_only
    elif len(digits_only) == 11 and digits_only.startswith('1'):  # США/Канада с кодом страны
        return '+' + digits_only
    elif len(digits_only) == 11 and digits_only.startswith('7'):  # Россия
        return '+' + digits_only
    elif len(digits_only) >= 10:  # Другие международные форматы
        if not phone_number.startswith('+'):
            # Предполагаем, что это международный формат без +
            return '+' + digits_only
        else:
            return '+' + digits_only.lstrip('+')
    else:
        logger.warning(f"Invalid phone number format: {phone_number}")
        return None

async def _send_sms_via_twilio(phone_number: str, message: str) -> bool:
    """Отправка SMS через Twilio"""
    try:
        import aiohttp
        twilio_account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        twilio_auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        twilio_phone_number = os.getenv('TWILIO_PHONE_NUMBER')

        if not all([twilio_account_sid, twilio_auth_token, twilio_phone_number]):
            logger.error("Twilio credentials not configured")
            return False

        # Используем aiohttp для асинхронного вызова Twilio API
        twilio_url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_account_sid}/Messages.json"

        data = {
            'To': phone_number,
            'From': twilio_phone_number,
            'Body': message
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                twilio_url,
                data=data,
                auth=aiohttp.BasicAuth(twilio_account_sid, twilio_auth_token)
            ) as response:
                if response.status == 201:
                    result = await response.json()
                    logger.info(f"Twilio SMS sent successfully, SID: {result.get('sid', 'unknown')}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Twilio API error: {response.status}, {error_text}")
                    return False

    except Exception as e:
        logger.error(f"Error sending SMS via Twilio: {e}")
        return False

async def _send_sms_via_aws_sns(phone_number: str, message: str) -> bool:
    """Отправка SMS через AWS SNS"""
    try:
        aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_region = os.getenv('AWS_REGION', 'us-east-1')

        if not all([aws_access_key_id, aws_secret_access_key]):
            logger.error("AWS credentials not configured")
            return False

        # Формируем URL для AWS SNS
        sns_url = f"https://sns.{aws_region}.amazonaws.com/"

        # Подготовка данных для SNS
        data = {
            'Action': 'Publish',
            'Message': message,
            'PhoneNumber': phone_number,
            'Version': '2010-03-31'
        }

        # Реализуем полноценную интеграцию с AWS SNS
        import boto3
        from botocore.exceptions import ClientError

        # Создаем клиент SNS
        sns_client = boto3.client(
            'sns',
            region_name=aws_region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )

        try:
            # Отправляем SMS через SNS
            response = sns_client.publish(
                PhoneNumber=phone_number,
                Message=message,
                MessageAttributes={
                    'AWS.SNS.SMS.SMSType': {
                        'DataType': 'String',
                        'StringValue': 'Transactional'  # или 'Promotional'
                    }
                }
            )

            logger.info(f"AWS SNS SMS sent successfully to {phone_number}, MessageId: {response.get('MessageId')}")
            return True

        except ClientError as e:
            logger.error(f"Error sending SMS via AWS SNS: {e}")
            return False

    except Exception as e:
        logger.error(f"Error sending SMS via AWS SNS: {e}")
        return False

async def _send_sms_fake(phone_number: str, message: str) -> bool:
    """Фиктивная отправка SMS для тестирования - сохраняет в базу данных для отладки"""
    try:
        # Сохраняем SMS в базу данных для тестирования и отладки
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sms_test_log (phone_number, message, sent_at, status)
                VALUES ($1, $2, $3, $4)
                """,
                phone_number, message, datetime.utcnow(), 'sent'
            )

        logger.info(f"Test SMS logged to database for {phone_number}: {message}")
        return True

    except Exception as e:
        logger.error(f"Error logging test SMS for {phone_number}: {e}")
        # Даже при ошибке в базе данных, считаем, что тестовая отправка прошла успешно
        # чтобы не нарушать логику при тестировании
        return True

async def start_tcp_server():
    """Запуск TCP-сервера"""
    server = await asyncio.start_server(
        handle_tcp_client,
        config.TCP_HOST,
        config.TCP_PORT
    )
    logger.info(f'[TCP] Сервер запущен на {config.TCP_HOST}:{config.TCP_PORT}')
    async with server:
        await server.serve_forever()

async def main():
    """Главная функция запуска"""
    # Инициализация приложения
    app_instance = await init_app()
    
    # Запуск TCP и HTTP серверов параллельно
    await asyncio.gather(
        start_tcp_server(),
        web._run_app(app_instance, host=config.HTTP_HOST, port=config.HTTP_PORT)
    )

if __name__ == '__main__':
    logger.info("Запуск гибридного мессенджер-сервера...")
    logger.info(f'TCP порт: {config.TCP_PORT} (для C++ клиентов)')
    logger.info(f'HTTP порт: {config.HTTP_PORT} (для web клиентов)')
    logger.info(f'WebSocket: ws://{config.HTTP_HOST}:{config.HTTP_PORT}/ws')
    logger.info(f'REST API: http://{config.HTTP_HOST}:{config.HTTP_PORT}/api/send')
    
    # Загружаем переменные окружения
    from dotenv import load_dotenv
    load_dotenv()
    
    asyncio.run(main())
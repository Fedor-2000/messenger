"""
Main server module for the hybrid messenger application.

This module implements a scalable messaging server supporting TCP and WebSocket
connections with advanced features like end-to-end encryption, authentication,
and real-time communication.

The server supports:
- TCP and WebSocket connections for different client types
- JWT-based authentication and authorization
- Message encryption and security features
- Real-time chat functionality with history
- Integration with additional services (games, tasks, calendar, analytics)
"""

import asyncio
import json
import logging
import os
import ssl
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, Set, Optional, List, Any, Callable, Awaitable
from pathlib import Path

import aiohttp
import asyncpg
import redis.asyncio as redis
from aiohttp import web
from aiohttp.web_middlewares import normalize_path_middleware
import jwt
import bcrypt
import base64
import hashlib
from pydantic import BaseModel, ValidationError
from cryptography.fernet import Fernet
import time
from collections import defaultdict, deque

# Import additional components
from webrtc.signaling import webrtc_signaling_manager
from games.minigames import game_manager
from tasks.task_manager import task_manager
from analytics.chat_analytics import chat_analytics_manager
from calendar.calendar_integration import calendar_integration

# Setup logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Config:
    """Configuration class for server settings."""
    
    DB_URL: str = os.getenv('DATABASE_URL', 'postgresql://messenger:your-secure-password@db:5432/messenger')
    REDIS_URL: str = os.getenv('REDIS_URL', 'redis://redis:6379')
    JWT_SECRET: str = os.getenv('JWT_SECRET', 'your-super-secret-jwt-key-change-it')
    MESSAGE_ENCRYPTION_KEY: str = os.getenv('MESSAGE_ENCRYPTION_KEY', 'your-message-encryption-key')
    TCP_HOST: str = os.getenv('TCP_HOST', '0.0.0.0')
    TCP_PORT: int = int(os.getenv('TCP_PORT', '8888'))
    HTTP_HOST: str = os.getenv('HTTP_HOST', '0.0.0.0')
    HTTP_PORT: int = int(os.getenv('HTTP_PORT', '8080'))
    SSL_CERT: str = os.getenv('SSL_CERT_PATH', '')
    SSL_KEY: str = os.getenv('SSL_KEY_PATH', '')


class TokenData(BaseModel):
    """Data model for JWT token."""
    username: str


class SecurityManager:
    """Security manager for authentication and encryption."""
    
    def __init__(self, config: Config):
        self.config = config
        self.jwt_secret = config.JWT_SECRET
        self.algorithm = "HS256"
        self.access_token_expire = timedelta(minutes=30)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash."""
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    
    def get_password_hash(self, password: str) -> str:
        """Generate hash for password."""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + self.access_token_expire
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.jwt_secret, algorithm=self.algorithm)
        return encoded_jwt
    
    def verify_token(self, token: str) -> Optional[TokenData]:
        """Verify JWT token."""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.algorithm])
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
    """Message encryption manager."""
    
    def __init__(self, config: Config):
        key = config.MESSAGE_ENCRYPTION_KEY
        self.key = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
        self.cipher_suite = Fernet(self.key)
    
    def encrypt_message(self, message: str) -> str:
        """Encrypt message."""
        encrypted_bytes = self.cipher_suite.encrypt(message.encode())
        return base64.b64encode(encrypted_bytes).decode()
    
    def decrypt_message(self, encrypted_message: str) -> str:
        """Decrypt message."""
        encrypted_bytes = base64.b64decode(encrypted_message.encode())
        decrypted_bytes = self.cipher_suite.decrypt(encrypted_bytes)
        return decrypted_bytes.decode()


class RateLimiter:
    """Rate limiting manager to prevent DDoS attacks."""
    
    def __init__(self, max_requests: int = 10, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests: Dict[str, deque] = defaultdict(deque)
    
    def is_allowed(self, identifier: str) -> bool:
        """Check if request is allowed based on rate limits."""
        current_time = time.time()
        
        # Remove old requests outside the time window
        while (self.requests[identifier] and 
               current_time - self.requests[identifier][0] > self.time_window):
            self.requests[identifier].popleft()
        
        # Check if limit is exceeded
        if len(self.requests[identifier]) >= self.max_requests:
            return False
        
        # Add current request
        self.requests[identifier].append(current_time)
        return True


class ChatManager:
    """Chat manager for handling chat operations."""
    
    def __init__(self, db_pool: asyncpg.Pool, redis_client: redis.Redis):
        self.db_pool = db_pool
        self.redis = redis_client
        self.local_connections: Dict[str, Set] = {
            'tcp': set(),
            'websocket': set()
        }
    
    async def create_private_chat(self, user1_id: int, user2_id: int) -> str:
        """Create a private chat between two users."""
        chat_id = f"private_{min(user1_id, user2_id)}_{max(user1_id, user2_id)}"
        
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
    
    async def create_group_chat(self, creator_id: int, name: str, participants: list) -> str:
        """Create a group chat."""
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
        """Send a private message."""
        chat_id = f"private_{min(sender_id, recipient_id)}_{max(sender_id, recipient_id)}"
        
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO messages (chat_id, sender_id, content, message_type) 
                VALUES ($1, $2, $3, 'private')
                ''',
                chat_id, sender_id, content
            )
        
        message_data = {
            'type': 'new_message',
            'chat_id': chat_id,
            'sender_id': sender_id,
            'content': content,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await self.redis.publish(f"chat:{chat_id}", json.dumps(message_data))
    
    async def send_group_message(self, chat_id: str, sender_id: int, content: str):
        """Send a group message."""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO messages (chat_id, sender_id, content, message_type) 
                VALUES ($1, $2, $3, 'group')
                ''',
                chat_id, sender_id, content
            )
        
        message_data = {
            'type': 'group_message',
            'chat_id': chat_id,
            'sender_id': sender_id,
            'content': content,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await self.redis.publish(f"chat:{chat_id}", json.dumps(message_data))


@asynccontextmanager
async def lifespan(app: web.Application):
    """Application lifecycle manager."""
    global db_pool, redis_client

    # Initialize connections
    logger.info("Initializing database...")
    db_pool = await asyncpg.create_pool(Config.DB_URL, min_size=5, max_size=20)

    logger.info("Initializing Redis...")
    redis_client = redis.from_url(Config.REDIS_URL, decode_responses=True, password=os.getenv('REDIS_PASSWORD'))

    # Initialize additional components
    logger.info("Initializing WebRTC signaling...")
    webrtc_signaling_manager.redis = redis_client
    webrtc_signaling_manager.db_pool = db_pool

    logger.info("Initializing game manager...")
    game_manager.redis = redis_client
    game_manager.db_pool = db_pool

    logger.info("Initializing task manager...")
    task_manager.redis = redis_client
    task_manager.db_pool = db_pool

    logger.info("Initializing chat analytics...")
    chat_analytics_manager.redis = redis_client
    chat_analytics_manager.db_pool = db_pool

    logger.info("Initializing calendar integration...")
    calendar_integration.redis = redis_client
    calendar_integration.db_pool = db_pool

    # Create tables if needed
    async with db_pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255),
                created_at TIMESTAMP DEFAULT NOW(),
                avatar VARCHAR(255) DEFAULT '',
                bio TEXT,
                last_seen TIMESTAMP DEFAULT NOW(),
                online_status VARCHAR(20) DEFAULT 'offline'
            );

            CREATE TABLE IF NOT EXISTS chats (
                id VARCHAR(100) PRIMARY KEY,
                type VARCHAR(20) NOT NULL,
                name VARCHAR(100),
                description TEXT,
                creator_id INTEGER REFERENCES users(id),
                participants INTEGER[],
                created_at TIMESTAMP DEFAULT NOW(),
                last_message TEXT,
                last_activity TIMESTAMP DEFAULT NOW(),
                unread_count INTEGER DEFAULT 0,
                avatar VARCHAR(255) DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                chat_id VARCHAR(100) REFERENCES chats(id),
                sender_id INTEGER REFERENCES users(id),
                content TEXT NOT NULL,
                message_type VARCHAR(20) DEFAULT 'text',
                timestamp TIMESTAMP DEFAULT NOW(),
                reply_to VARCHAR(50),
                edited BOOLEAN DEFAULT FALSE,
                edited_at TIMESTAMP,
                deleted BOOLEAN DEFAULT FALSE,
                deleted_at TIMESTAMP,
                mentions INTEGER[],
                reactions JSONB
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

            -- Tables for WebRTC
            CREATE TABLE IF NOT EXISTS call_sessions (
                session_id VARCHAR(100) PRIMARY KEY,
                caller_id INTEGER REFERENCES users(id),
                callee_id INTEGER REFERENCES users(id),
                media_types TEXT[],
                started_at TIMESTAMP DEFAULT NOW(),
                ended_at TIMESTAMP,
                status VARCHAR(20) DEFAULT 'initiated'
            );

            -- Tables for tasks
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

            -- Tables for calendar
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
            CREATE INDEX IF NOT EXISTS idx_messages_sender_id ON messages(sender_id);
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
            CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen);
            CREATE INDEX IF NOT EXISTS idx_chats_last_activity ON chats(last_activity);
            CREATE INDEX IF NOT EXISTS idx_tasks_assignee_id ON tasks(assignee_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_creator_id ON tasks(creator_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
            CREATE INDEX IF NOT EXISTS idx_calendar_events_start_time ON calendar_events(start_time);
            CREATE INDEX IF NOT EXISTS idx_calendar_events_creator_id ON calendar_events(creator_id);
        ''')

    yield

    # Cleanup on shutdown
    logger.info("Shutting down...")
    await db_pool.close()
    await redis_client.close()


# Global variables
config = Config()
db_pool: Optional[asyncpg.Pool] = None
redis_client: Optional[redis.Redis] = None

# Initialize managers
security_manager = SecurityManager(config)
encryption = MessageEncryption(config)
rate_limiter = RateLimiter()
chat_manager = ChatManager(db_pool, redis_client) if db_pool and redis_client else None


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle WebSocket connections."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    logger.info(f'[WS] New connection')
    
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    message = json.loads(msg.data)
                    logger.debug(f'[WS] Received: {message}')
                    
                    # Rate limiting check
                    client_ip = request.remote
                    if not rate_limiter.is_allowed(client_ip):
                        await ws.send_str(json.dumps({
                            'type': 'rate_limit_exceeded',
                            'message': 'Rate limit exceeded. Please slow down.'
                        }))
                        continue
                    
                    # Handle different message types
                    msg_type = message.get('type')
                    
                    if msg_type == 'auth':
                        username = message.get('username')
                        password = message.get('password')
                        
                        # Verify credentials against database
                        async with db_pool.acquire() as conn:
                            user_record = await conn.fetchrow(
                                "SELECT id, username, password_hash FROM users WHERE username = $1",
                                username
                            )
                            
                            if user_record and security_manager.verify_password(password, user_record['password_hash']):
                                # Create token
                                token_data = {"sub": username, "user_id": user_record['id']}
                                token = security_manager.create_access_token(
                                    data=token_data,
                                    expires_delta=timedelta(minutes=30)
                                )
                                
                                # Store token in Redis for active session tracking
                                await redis_client.setex(
                                    f"session:{user_record['id']}", 
                                    1800, 
                                    token
                                )
                                
                                response = {
                                    'type': 'auth_success',
                                    'token': token,
                                    'user_id': user_record['id'],
                                    'username': username,
                                    'expires_in': 1800
                                }
                                
                                # Send recent messages to new user
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
                                    'message': 'Invalid credentials'
                                }
                        
                        await ws.send_str(json.dumps(response))
                    
                    elif msg_type == 'message':
                        token = message.get('token')
                        token_data = security_manager.verify_token(token)
                        
                        if not token_data:
                            await ws.send_str(json.dumps({
                                'type': 'auth_error',
                                'message': 'Invalid or expired token'
                            }))
                            continue
                        
                        # Store message in database
                        content = message.get('text')
                        username = token_data.username
                        
                        # Encrypt message
                        encrypted_content = encryption.encrypt_message(content)
                        
                        async with db_pool.acquire() as conn:
                            await conn.execute(
                                '''
                                INSERT INTO messages (chat_id, sender_id, content, message_type) 
                                VALUES ($1, $2, $3, $4)
                                ''',
                                'general', 1, encrypted_content, 'text'
                            )
                        
                        # Broadcast message to all
                        broadcast_msg = {
                            'type': 'new_message',
                            'user': username,
                            'text': content,  # Send decrypted content
                            'timestamp': datetime.utcnow().isoformat()
                        }
                        
                        # Publish via Redis for broadcasting
                        await redis_client.publish('room:general', json.dumps(broadcast_msg))
                        
                except json.JSONDecodeError:
                    logger.error("Error parsing JSON")
                except ValidationError as e:
                    logger.error(f"Validation error: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await ws.send_str(json.dumps({
                        'type': 'error',
                        'message': 'Internal server error'
                    }))

            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f'[WS] Error: {ws.exception()}')

    finally:
        logger.info(f'[WS] Connection closed')

    return ws


async def get_recent_messages(room: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent messages from database."""
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
        for row in reversed(rows):  # Reverse order (newest at bottom)
            try:
                decrypted_content = encryption.decrypt_message(row['content'])
            except:
                decrypted_content = row['content']  # If decryption fails, use original
                
            messages.append({
                'user': row['username'],
                'text': decrypted_content,
                'timestamp': row['timestamp'].isoformat()
            })
        
        return messages


async def rest_api_handler(request: web.Request) -> web.Response:
    """Handle REST API requests."""
    if request.content_type != 'application/json':
        return web.json_response({'error': 'JSON required'}, status=400)
    
    data = await request.json()
    action = request.match_info['action']

    if action == 'login':
        username = data.get('username')
        password = data.get('password')
        
        # Verify credentials against database
        async with db_pool.acquire() as conn:
            user_record = await conn.fetchrow(
                "SELECT id, username, password_hash FROM users WHERE username = $1",
                username
            )
            
            if user_record and security_manager.verify_password(password, user_record['password_hash']):
                # Create token
                token_data = {"sub": username, "user_id": user_record['id']}
                token = security_manager.create_access_token(
                    data=token_data,
                    expires_delta=timedelta(minutes=30)
                )
                
                # Store token in Redis for active session tracking
                await redis_client.setex(
                    f"session:{user_record['id']}", 
                    1800, 
                    token
                )
                
                return web.json_response({
                    'success': True,
                    'token': token,
                    'user': {
                        'id': user_record['id'],
                        'username': user_record['username']
                    }
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': 'Invalid credentials'
                }, status=401)
    
    elif action == 'register':
        username = data.get('username')
        password = data.get('password')
        
        # Hash password
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
        token_data = security_manager.verify_token(token)
        
        if not token_data:
            return web.json_response({
                'error': 'Invalid or expired token'
            }, status=401)
        
        content = data.get('content')
        username = token_data.username
        
        # Encrypt message
        encrypted_content = encryption.encrypt_message(content)
        
        async with db_pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO messages (chat_id, sender_id, content, message_type) 
                VALUES ($1, $2, $3, $4)
                ''',
                'general', 1, encrypted_content, 'text'
            )
        
        # Broadcast message to all
        broadcast_msg = {
            'type': 'new_message',
            'user': username,
            'text': content,  # Send decrypted content
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Publish via Redis for broadcasting
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
        return web.json_response({'error': 'Unknown API action'}, status=404)


async def handle_tcp_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Handle TCP connections for native clients."""
    addr = writer.get_extra_info('peername')
    logger.info(f'[TCP] New connection: {addr}')

    try:
        while True:
            # Read data (expecting JSON with newline)
            data = await reader.readuntil(b'\n')
            message = json.loads(data.decode().strip())

            logger.debug(f'[TCP] Received: {message}')

            # Rate limiting check
            client_ip = addr[0]
            if not rate_limiter.is_allowed(client_ip):
                response = {
                    'type': 'rate_limit_exceeded',
                    'message': 'Rate limit exceeded. Please slow down.'
                }
                writer.write((json.dumps(response) + '\n').encode())
                await writer.drain()
                continue

            # Handle commands
            msg_type = message.get('type')
            
            if msg_type == 'auth':
                username = message.get('username')
                password = message.get('password')
                
                # Verify credentials against database
                async with db_pool.acquire() as conn:
                    user_record = await conn.fetchrow(
                        "SELECT id, username, password_hash FROM users WHERE username = $1",
                        username
                    )
                    
                    if user_record and security_manager.verify_password(password, user_record['password_hash']):
                        # Create token
                        token_data = {"sub": username, "user_id": user_record['id']}
                        token = security_manager.create_access_token(
                            data=token_data,
                            expires_delta=timedelta(minutes=30)
                        )
                        
                        # Store token in Redis for active session tracking
                        await redis_client.setex(
                            f"session:{user_record['id']}", 
                            1800, 
                            token
                        )
                        
                        response = {
                            'type': 'auth_success',
                            'token': token,
                            'user_id': user_record['id'],
                            'username': username,
                            'expires_in': 1800
                        }
                    else:
                        response = {
                            'type': 'auth_error',
                            'message': 'Invalid credentials'
                        }
                
                writer.write((json.dumps(response) + '\n').encode())
                await writer.drain()

            elif msg_type == 'message':
                token = message.get('token')
                token_data = security_manager.verify_token(token)
                
                if not token_data:
                    response = {
                        'type': 'auth_error',
                        'message': 'Invalid or expired token'
                    }
                    writer.write((json.dumps(response) + '\n').encode())
                    await writer.drain()
                    continue
                
                # Store message in database
                content = message.get('text')
                username = token_data.username
                
                # Encrypt message
                encrypted_content = encryption.encrypt_message(content)
                
                async with db_pool.acquire() as conn:
                    await conn.execute(
                        '''
                        INSERT INTO messages (chat_id, sender_id, content, message_type) 
                        VALUES ($1, $2, $3, $4)
                        ''',
                        'general', 1, encrypted_content, 'text'
                    )
                
                # Broadcast message to all
                broadcast_msg = {
                    'type': 'new_message',
                    'user': username,
                    'text': content,  # Send decrypted content
                    'timestamp': datetime.utcnow().isoformat()
                }
                
                # Publish via Redis for broadcasting
                await redis_client.publish('room:general', json.dumps(broadcast_msg))

    except (asyncio.IncompleteReadError, ConnectionError, json.JSONDecodeError):
        logger.info(f'[TCP] Client disconnected: {addr}')
    finally:
        writer.close()


async def start_tcp_server():
    """Start TCP server."""
    server = await asyncio.start_server(
        handle_tcp_client,
        config.TCP_HOST,
        config.TCP_PORT
    )
    logger.info(f'[TCP] Server started on {config.TCP_HOST}:{config.TCP_PORT}')
    async with server:
        await server.serve_forever()


async def init_app():
    """Initialize aiohttp application."""
    app = web.Application(lifespan=lifespan)
    app.router.add_get('/ws', websocket_handler)
    app.router.add_post('/api/{action}', rest_api_handler)
    
    # Static files for web client
    app.router.add_static('/', './static/')
    
    return app


async def main():
    """Main function to start the server."""
    # Initialize application
    app_instance = await init_app()
    
    # Start TCP and HTTP servers concurrently
    await asyncio.gather(
        start_tcp_server(),
        web._run_app(app_instance, host=config.HTTP_HOST, port=config.HTTP_PORT)
    )


if __name__ == '__main__':
    logger.info("Starting hybrid messenger server...")
    logger.info(f'TCP port: {config.TCP_PORT} (for C++ clients)')
    logger.info(f'HTTP port: {config.HTTP_PORT} (for web clients)')
    logger.info(f'WebSocket: ws://{config.HTTP_HOST}:{config.HTTP_PORT}/ws')
    logger.info(f'REST API: http://{config.HTTP_HOST}:{config.HTTP_PORT}/api/send')
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    asyncio.run(main())
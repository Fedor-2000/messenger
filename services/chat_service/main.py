# Chat Service
# File: services/chat_service/main.py

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

config = Config()

# Глобальные переменные
db_pool = None
redis_client = None

class Message(BaseModel):
    chat_id: str
    sender_id: int
    content: str
    message_type: str = 'text'
    timestamp: datetime = None

class ChatService:
    def __init__(self):
        self.db_pool = None
        self.redis_client = None
        self.active_chats = {}

    async def create_private_chat(self, user1_id: int, user2_id: int) -> str:
        """Создание приватного чата"""
        chat_id = f"private_{min(user1_id, user2_id)}_{max(user1_id, user2_id)}"
        
        async with db_pool.acquire() as conn:
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
        """Создание группового чата"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                INSERT INTO chats (type, name, creator_id, participants)
                VALUES ('group', $1, $2, $3)
                RETURNING id
                ''',
                name, creator_id, participants
            )
            return row['id']

    async def send_message(self, message: Message) -> bool:
        """Отправка сообщения"""
        if not message.timestamp:
            message.timestamp = datetime.utcnow()
        
        # Сохранение сообщения в базе
        async with db_pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO messages (chat_id, sender_id, content, message_type, timestamp)
                VALUES ($1, $2, $3, $4, $5)
                ''',
                message.chat_id, message.sender_id, message.content, 
                message.message_type, message.timestamp
            )

        # Отправка через Redis
        message_data = {
            'type': 'new_message',
            'chat_id': message.chat_id,
            'sender_id': message.sender_id,
            'content': message.content,
            'message_type': message.message_type,
            'timestamp': message.timestamp.isoformat()
        }

        await redis_client.publish(f"chat:{message.chat_id}", json.dumps(message_data))
        return True

    async def get_chat_history(self, chat_id: str, limit: int = 50, offset: int = 0) -> List[Dict]:
        """Получение истории чата"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT m.sender_id, u.username, m.content, m.message_type, m.timestamp
                FROM messages m
                JOIN users u ON m.sender_id = u.id
                WHERE m.chat_id = $1
                ORDER BY m.timestamp DESC
                LIMIT $2 OFFSET $3
                ''',
                chat_id, limit, offset
            )

        messages = []
        for row in reversed(rows):  # Обратный порядок (новые внизу)
            messages.append({
                'sender_id': row['sender_id'],
                'username': row['username'],
                'content': row['content'],
                'message_type': row['message_type'],
                'timestamp': row['timestamp'].isoformat()
            })

        return messages

    async def get_user_chats(self, user_id: int) -> List[Dict]:
        """Получение чатов пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT id, type, name, creator_id, participants, last_message, last_activity, unread_count
                FROM chats
                WHERE $1 = ANY(participants)
                ORDER BY last_activity DESC
                ''',
                user_id
            )

        chats = []
        for row in rows:
            chats.append({
                'id': row['id'],
                'type': row['type'],
                'name': row['name'],
                'creator_id': row['creator_id'],
                'participants': row['participants'],
                'last_message': row['last_message'],
                'last_activity': row['last_activity'].isoformat() if row['last_activity'] else None,
                'unread_count': row['unread_count']
            })

        return chats

    async def create_poll(self, chat_id: str, question: str, options: List[str], creator_id: int) -> str:
        """Создание голосования/опроса"""
        poll_id = f"poll_{chat_id}_{datetime.utcnow().timestamp()}"
        
        poll_data = {
            'id': poll_id,
            'question': question,
            'options': {str(i): {'text': opt, 'votes': 0} for i, opt in enumerate(options)},
            'creator_id': creator_id,
            'chat_id': chat_id,
            'created_at': datetime.utcnow().isoformat(),
            'closed': False
        }
        
        # Сохраняем голосование в Redis
        await redis_client.setex(f"poll:{poll_id}", 7*24*60*60, json.dumps(poll_data))  # 7 дней
        
        # Отправляем сообщение о голосовании в чат
        poll_message = {
            'type': 'poll',
            'poll_id': poll_id,
            'question': question,
            'options': options,
            'creator_id': creator_id,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await redis_client.publish(f"chat:{chat_id}", json.dumps(poll_message))
        
        return poll_id

    async def vote_poll(self, poll_id: str, option_index: str, voter_id: int) -> bool:
        """Голосование в опросе"""
        poll_data_json = await redis_client.get(f"poll:{poll_id}")
        if not poll_data_json:
            return False
        
        poll_data = json.loads(poll_data_json)
        
        if poll_data['closed']:
            return False
        
        # Проверяем, не голосовал ли уже пользователь
        voter_key = f"poll:{poll_id}:voter:{voter_id}"
        if await redis_client.exists(voter_key):
            return False  # Пользователь уже голосовал
        
        # Добавляем голос
        if option_index in poll_data['options']:
            poll_data['options'][option_index]['votes'] += 1
            
            # Сохраняем обновленные данные
            await redis_client.setex(f"poll:{poll_id}", 7*24*60*60, json.dumps(poll_data))
            
            # Отмечаем, что пользователь проголосовал
            await redis_client.setex(voter_key, 7*24*60*60, "1")
            
            # Отправляем обновление в чат
            vote_update = {
                'type': 'poll_vote_update',
                'poll_id': poll_id,
                'option_index': option_index,
                'new_votes': poll_data['options'][option_index]['votes'],
                'timestamp': datetime.utcnow().isoformat()
            }
            
            await redis_client.publish(f"chat:{poll_data['chat_id']}", json.dumps(vote_update))
            
            return True
        
        return False

# Инициализация сервиса
chat_service = ChatService()

async def create_chat_handler(request):
    """Обработчик создания чата"""
    data = await request.json()
    chat_type = data.get('type')
    
    if chat_type == 'private':
        user1_id = data.get('user1_id')
        user2_id = data.get('user2_id')
        chat_id = await chat_service.create_private_chat(user1_id, user2_id)
        return web.json_response({'chat_id': chat_id})
    elif chat_type == 'group':
        creator_id = data.get('creator_id')
        name = data.get('name')
        participants = data.get('participants', [])
        chat_id = await chat_service.create_group_chat(creator_id, name, participants)
        return web.json_response({'chat_id': chat_id})
    else:
        return web.json_response({'error': 'Invalid chat type'}, status=400)

async def send_message_handler(request):
    """Обработчик отправки сообщения"""
    data = await request.json()
    
    try:
        message = Message(**data)
        success = await chat_service.send_message(message)
        
        if success:
            return web.json_response({'status': 'sent'})
        else:
            return web.json_response({'error': 'Failed to send message'}, status=500)
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return web.json_response({'error': 'Invalid message format'}, status=400)

async def get_history_handler(request):
    """Обработчик получения истории чата"""
    chat_id = request.match_info['chat_id']
    limit = int(request.query.get('limit', 50))
    offset = int(request.query.get('offset', 0))
    
    history = await chat_service.get_chat_history(chat_id, limit, offset)
    return web.json_response({'messages': history})

async def get_user_chats_handler(request):
    """Обработчик получения чатов пользователя"""
    user_id = int(request.match_info['user_id'])
    
    chats = await chat_service.get_user_chats(user_id)
    return web.json_response({'chats': chats})

async def create_poll_handler(request):
    """Обработчик создания голосования"""
    data = await request.json()
    chat_id = data.get('chat_id')
    question = data.get('question')
    options = data.get('options', [])
    creator_id = data.get('creator_id')
    
    if not all([chat_id, question, options, creator_id]):
        return web.json_response({'error': 'Missing required fields'}, status=400)
    
    poll_id = await chat_service.create_poll(chat_id, question, options, creator_id)
    return web.json_response({'poll_id': poll_id})

async def vote_poll_handler(request):
    """Обработчик голосования"""
    poll_id = request.match_info['poll_id']
    data = await request.json()
    option_index = data.get('option_index')
    voter_id = data.get('voter_id')
    
    if not all([option_index, voter_id]):
        return web.json_response({'error': 'Missing required fields'}, status=400)
    
    success = await chat_service.vote_poll(poll_id, str(option_index), voter_id)
    
    if success:
        return web.json_response({'status': 'voted'})
    else:
        return web.json_response({'error': 'Vote failed'}, status=400)

async def health_check(request):
    """Проверка состояния сервиса"""
    return web.json_response({'status': 'healthy'})

async def init_app():
    """Инициализация приложения"""
    app = web.Application()
    
    # Маршруты
    app.router.add_post('/chats', create_chat_handler)
    app.router.add_post('/messages', send_message_handler)
    app.router.add_get('/chats/{chat_id}/history', get_history_handler)
    app.router.add_get('/users/{user_id}/chats', get_user_chats_handler)
    app.router.add_post('/polls', create_poll_handler)
    app.router.add_post('/polls/{poll_id}/vote', vote_poll_handler)
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
    
    site = web.TCPSite(runner, '0.0.0.0', 8001)
    await site.start()
    
    logger.info("Chat Service запущен на порту 8001")
    
    # Бесконечный цикл
    await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())
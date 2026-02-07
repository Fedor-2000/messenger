# Polls and Surveys Implementation
# File: services/chat_service/polls.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class PollOption(BaseModel):
    id: str
    text: str
    votes: int = 0

class Poll(BaseModel):
    id: str
    question: str
    options: List[PollOption]
    creator_id: int
    chat_id: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_multiple_choice: bool = False
    is_anonymous: bool = False
    total_votes: int = 0

class PollService:
    def __init__(self):
        self.active_polls = {}
        self.poll_results_cache = {}

    async def create_poll(self, question: str, options: List[str], creator_id: int, 
                         chat_id: str, expires_in: int = None, is_multiple_choice: bool = False, 
                         is_anonymous: bool = False) -> Optional[str]:
        """Создание голосования/опроса"""
        poll_id = f"poll_{chat_id}_{datetime.utcnow().timestamp()}"
        
        # Создаем опции голосования
        poll_options = [PollOption(id=str(i), text=opt, votes=0) for i, opt in enumerate(options)]
        
        # Создаем объект голосования
        poll = Poll(
            id=poll_id,
            question=question,
            options=poll_options,
            creator_id=creator_id,
            chat_id=chat_id,
            created_at=datetime.utcnow(),
            is_multiple_choice=is_multiple_choice,
            is_anonymous=is_anonymous
        )
        
        # Устанавливаем время истечения, если указано
        if expires_in:
            poll.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        # Сохраняем голосование в Redis
        await redis_client.setex(f"poll:{poll_id}", 7*24*60*60, poll.model_dump_json())  # 7 дней
        
        # Добавляем голосование в список голосований чата
        await redis_client.sadd(f"chat_polls:{chat_id}", poll_id)
        
        # Отправляем сообщение о голосовании в чат
        poll_message = {
            'type': 'poll',
            'poll_id': poll_id,
            'question': question,
            'options': [{'id': opt.id, 'text': opt.text} for opt in poll_options],
            'creator_id': creator_id,
            'created_at': poll.created_at.isoformat(),
            'is_multiple_choice': is_multiple_choice,
            'is_anonymous': is_anonymous,
            'expires_at': poll.expires_at.isoformat() if poll.expires_at else None
        }
        
        await redis_client.publish(f"chat:{chat_id}", json.dumps(poll_message))
        
        # Сохраняем информацию о голосовании в базе данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO polls (
                    id, question, options, creator_id, chat_id, created_at, expires_at, 
                    is_multiple_choice, is_anonymous
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ''',
                poll_id, question, json.dumps([opt.dict() for opt in poll_options]), 
                creator_id, chat_id, poll.created_at, poll.expires_at, 
                is_multiple_choice, is_anonymous
            )
        
        logger.info(f"Poll {poll_id} created in chat {chat_id}")
        return poll_id

    async def vote_poll(self, poll_id: str, option_ids: List[str], voter_id: int) -> bool:
        """Голосование в опросе"""
        poll_data_json = await redis_client.get(f"poll:{poll_id}")
        if not poll_data_json:
            return False
        
        poll_data = json.loads(poll_data_json)
        poll = Poll(**poll_data)
        
        # Проверяем, истекло ли голосование
        if poll.expires_at and datetime.utcnow() > poll.expires_at:
            return False
        
        # Проверяем, не голосовал ли уже пользователь (для одиночного выбора)
        if not poll.is_multiple_choice:
            voter_key = f"poll:{poll_id}:voter:{voter_id}"
            if await redis_client.exists(voter_key):
                return False  # Пользователь уже голосовал
        
        # Проверяем, что указанные опции существуют
        valid_option_ids = {opt.id for opt in poll.options}
        if not all(opt_id in valid_option_ids for opt_id in option_ids):
            return False
        
        # Обновляем голоса
        for option_id in option_ids:
            for option in poll.options:
                if option.id == option_id:
                    option.votes += 1
                    poll.total_votes += 1
                    break
        
        # Обновляем данные в Redis
        await redis_client.setex(f"poll:{poll_id}", 7*24*60*60, poll.model_dump_json())
        
        # Отмечаем, что пользователь проголосовал (для одиночного выбора)
        if not poll.is_multiple_choice:
            await redis_client.setex(voter_key, 7*24*60*60, "1")
        
        # Если голосование анонимное, не раскрываем информацию о голосующем
        vote_update = {
            'type': 'poll_vote_update',
            'poll_id': poll_id,
            'option_ids': option_ids,
            'new_total_votes': poll.total_votes,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if not poll.is_anonymous:
            vote_update['voter_id'] = voter_id
        
        await redis_client.publish(f"chat:{poll.chat_id}", json.dumps(vote_update))
        
        # Обновляем информацию в базе данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                '''
                UPDATE polls SET 
                    options = $1, 
                    total_votes = $2 
                WHERE id = $3
                ''',
                json.dumps([opt.dict() for opt in poll.options]), 
                poll.total_votes, 
                poll_id
            )
        
        logger.info(f"User {voter_id} voted in poll {poll_id}")
        return True

    async def get_poll_results(self, poll_id: str) -> Optional[Dict]:
        """Получение результатов голосования"""
        poll_data_json = await redis_client.get(f"poll:{poll_id}")
        if not poll_data_json:
            return None
        
        poll_data = json.loads(poll_data_json)
        poll = Poll(**poll_data)
        
        return {
            'id': poll.id,
            'question': poll.question,
            'options': [{'id': opt.id, 'text': opt.text, 'votes': opt.votes} for opt in poll.options],
            'creator_id': poll.creator_id,
            'chat_id': poll.chat_id,
            'created_at': poll.created_at.isoformat(),
            'expires_at': poll.expires_at.isoformat() if poll.expires_at else None,
            'is_multiple_choice': poll.is_multiple_choice,
            'is_anonymous': poll.is_anonymous,
            'total_votes': poll.total_votes
        }

    async def close_poll(self, poll_id: str, closer_id: int) -> bool:
        """Закрытие голосования (только создателем или администратором)"""
        poll_data_json = await redis_client.get(f"poll:{poll_id}")
        if not poll_data_json:
            return False
        
        poll_data = json.loads(poll_data_json)
        poll = Poll(**poll_data)
        
        # Проверяем права на закрытие (создатель или администратор)
        if poll.creator_id != closer_id and not await self.is_admin(closer_id, poll.chat_id):
            return False
        
        # Помечаем голосование как закрытое (удаляем из Redis)
        await redis_client.delete(f"poll:{poll_id}")
        
        # Отправляем уведомление о закрытии голосования
        close_message = {
            'type': 'poll_closed',
            'poll_id': poll_id,
            'closer_id': closer_id,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await redis_client.publish(f"chat:{poll.chat_id}", json.dumps(close_message))
        
        # Обновляем статус в базе данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                '''
                UPDATE polls SET closed_at = $1 WHERE id = $2
                ''',
                datetime.utcnow(), poll_id
            )
        
        logger.info(f"Poll {poll_id} closed by user {closer_id}")
        return True

    async def get_active_polls(self, chat_id: str) -> List[Dict]:
        """Получение активных голосований в чате"""
        poll_ids = await redis_client.smembers(f"chat_polls:{chat_id}")
        active_polls = []
        
        for poll_id in poll_ids:
            poll_data_json = await redis_client.get(f"poll:{poll_id}")
            if poll_id and poll_data_json:
                poll_data = json.loads(poll_data_json)
                poll = Poll(**poll_data)
                
                # Проверяем, не истекло ли голосование
                if not poll.expires_at or datetime.utcnow() < poll.expires_at:
                    active_polls.append({
                        'id': poll.id,
                        'question': poll.question,
                        'options_count': len(poll.options),
                        'creator_id': poll.creator_id,
                        'created_at': poll.created_at.isoformat(),
                        'expires_at': poll.expires_at.isoformat() if poll.expires_at else None,
                        'is_multiple_choice': poll.is_multiple_choice,
                        'is_anonymous': poll.is_anonymous,
                        'total_votes': poll.total_votes
                    })
        
        return active_polls

    async def is_admin(self, user_id: int, chat_id: str) -> bool:
        """Проверка, является ли пользователь администратором чата"""
        # В реальном приложении здесь будет проверка прав пользователя в чате
        # Пока возвращаем False для всех пользователей
        return False

# Глобальный экземпляр сервиса голосований
poll_service = PollService()

# Функции для использования в других частях приложения

async def create_poll_handler(question: str, options: List[str], creator_id: int, 
                            chat_id: str, expires_in: int = None, 
                            is_multiple_choice: bool = False, 
                            is_anonymous: bool = False) -> Optional[str]:
    """Обработчик создания голосования"""
    return await poll_service.create_poll(
        question, options, creator_id, chat_id, expires_in, 
        is_multiple_choice, is_anonymous
    )

async def vote_poll_handler(poll_id: str, option_ids: List[str], voter_id: int) -> bool:
    """Обработчик голосования"""
    return await poll_service.vote_poll(poll_id, option_ids, voter_id)

async def get_poll_results_handler(poll_id: str) -> Optional[Dict]:
    """Обработчик получения результатов голосования"""
    return await poll_service.get_poll_results(poll_id)

async def close_poll_handler(poll_id: str, closer_id: int) -> bool:
    """Обработчик закрытия голосования"""
    return await poll_service.close_poll(poll_id, closer_id)

async def get_active_polls_handler(chat_id: str) -> List[Dict]:
    """Обработчик получения активных голосований"""
    return await poll_service.get_active_polls(chat_id)
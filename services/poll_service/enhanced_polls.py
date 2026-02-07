# Enhanced Polls and Voting System
# File: services/poll_service/enhanced_polls.py

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

class PollType(Enum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    RANKING = "ranking"
    RATING = "rating"  # Оценка по шкале (например, 1-5)
    BOOLEAN = "boolean"  # Да/Нет
    TEXT_RESPONSE = "text_response"  # Текстовый ответ

class PollVisibility(Enum):
    PUBLIC = "public"
    PARTICIPANTS_ONLY = "participants_only"
    ADMIN_ONLY = "admin_only"

class PollStatus(Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"
    ARCHIVED = "archived"

class PollOption(BaseModel):
    id: str
    text: str
    votes: int = 0
    rank: Optional[int] = None  # Для ранжирования
    rating: Optional[int] = None  # Для оценок
    text_response: Optional[str] = None  # Для текстовых ответов

class Poll(BaseModel):
    id: str
    title: str
    description: str
    creator_id: int
    chat_id: Optional[str] = None
    group_id: Optional[str] = None
    type: PollType
    visibility: PollVisibility
    status: PollStatus
    options: List[PollOption]
    allow_change_vote: bool = False
    allow_multiple_votes: bool = False
    max_choices: Optional[int] = None  # Для multiple choice
    min_rating: int = 1  # Для рейтинга
    max_rating: int = 5  # Для рейтинга
    start_date: datetime
    end_date: Optional[datetime] = None
    created_at: datetime = None
    updated_at: datetime = None
    total_votes: int = 0
    unique_voters: int = 0
    tags: List[str] = []
    attachments: List[Dict] = []  # [{'id': 'file_id', 'name': 'file_name'}]
    results_visible: bool = True  # Показывать результаты во время голосования
    anonymous: bool = False  # Анонимное голосование
    require_authentication: bool = True  # Требовать аутентификацию для голосования

class Vote(BaseModel):
    id: str
    poll_id: str
    user_id: int
    option_ids: List[str]  # Для multiple choice
    ratings: Optional[Dict[str, int]] = None  # Для рейтинга {'option_id': rating}
    text_responses: Optional[Dict[str, str]] = None  # Для текстовых ответов {'option_id': response}
    created_at: datetime = None
    updated_at: datetime = None

class PollResult(BaseModel):
    poll_id: str
    option_results: List[Dict]  # [{'option_id': '...', 'votes': 0, 'percentage': 0.0}]
    total_votes: int
    unique_voters: int
    timestamp: datetime = None

class EnhancedPollService:
    def __init__(self):
        self.db_pool = None
        self.redis_client = None
        self.active_polls = {}

    async def create_poll(self, title: str, description: str, creator_id: int,
                         options: List[str], poll_type: PollType,
                         chat_id: Optional[str] = None,
                         group_id: Optional[str] = None,
                         visibility: PollVisibility = PollVisibility.PUBLIC,
                         allow_change_vote: bool = False,
                         allow_multiple_votes: bool = False,
                         max_choices: Optional[int] = None,
                         min_rating: int = 1,
                         max_rating: int = 5,
                         start_date: Optional[datetime] = None,
                         end_date: Optional[datetime] = None,
                         results_visible: bool = True,
                         anonymous: bool = False,
                         require_authentication: bool = True,
                         tags: Optional[List[str]] = None) -> Optional[Poll]:
        """Создание нового опроса/голосования"""
        poll_id = str(uuid.uuid4())

        # Создаем опции голосования
        poll_options = [PollOption(id=str(uuid.uuid4()), text=opt) for opt in options]

        # Устанавливаем дату начала, если не указана
        if not start_date:
            start_date = datetime.utcnow()

        poll = Poll(
            id=poll_id,
            title=title,
            description=description,
            creator_id=creator_id,
            chat_id=chat_id,
            group_id=group_id,
            type=poll_type,
            visibility=visibility,
            status=PollStatus.ACTIVE if start_date <= datetime.utcnow() else PollStatus.DRAFT,
            options=poll_options,
            allow_change_vote=allow_change_vote,
            allow_multiple_votes=allow_multiple_votes,
            max_choices=max_choices,
            min_rating=min_rating,
            max_rating=max_rating,
            start_date=start_date,
            end_date=end_date,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            total_votes=0,
            unique_voters=0,
            tags=tags or [],
            attachments=[],
            results_visible=results_visible,
            anonymous=anonymous,
            require_authentication=require_authentication
        )

        # Сохраняем опрос в базу данных
        await self._save_poll_to_db(poll)

        # Добавляем в кэш
        await self._cache_poll(poll)

        # Уведомляем заинтересованные стороны
        await self._notify_poll_created(poll)

        # Создаем запись активности
        await self._log_activity(poll.id, creator_id, "created", {
            "title": poll.title,
            "type": poll.type.value,
            "options_count": len(poll.options)
        })

        return poll

    async def _save_poll_to_db(self, poll: Poll):
        """Сохранение опроса в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO polls (
                    id, title, description, creator_id, chat_id, group_id,
                    type, visibility, status, options, allow_change_vote,
                    allow_multiple_votes, max_choices, min_rating, max_rating,
                    start_date, end_date, created_at, updated_at, total_votes,
                    unique_voters, tags, attachments, results_visible,
                    anonymous, require_authentication
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                         $13, $14, $15, $16, $17, $18, $19, $20, $21, $22,
                         $23, $24, $25, $26)
                """,
                poll.id, poll.title, poll.description, poll.creator_id,
                poll.chat_id, poll.group_id, poll.type.value, 
                poll.visibility.value, poll.status.value,
                json.dumps([opt.dict() for opt in poll.options]),
                poll.allow_change_vote, poll.allow_multiple_votes,
                poll.max_choices, poll.min_rating, poll.max_rating,
                poll.start_date, poll.end_date, poll.created_at,
                poll.updated_at, poll.total_votes, poll.unique_voters,
                poll.tags, json.dumps(poll.attachments), poll.results_visible,
                poll.anonymous, poll.require_authentication
            )

    async def get_poll(self, poll_id: str) -> Optional[Poll]:
        """Получение опроса по ID"""
        # Сначала проверяем кэш
        cached_poll = await self._get_cached_poll(poll_id)
        if cached_poll:
            return cached_poll

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, title, description, creator_id, chat_id, group_id,
                       type, visibility, status, options, allow_change_vote,
                       allow_multiple_votes, max_choices, min_rating, max_rating,
                       start_date, end_date, created_at, updated_at, total_votes,
                       unique_voters, tags, attachments, results_visible,
                       anonymous, require_authentication
                FROM polls WHERE id = $1
                """,
                poll_id
            )

        if not row:
            return None

        poll = Poll(
            id=row['id'],
            title=row['title'],
            description=row['description'],
            creator_id=row['creator_id'],
            chat_id=row['chat_id'],
            group_id=row['group_id'],
            type=PollType(row['type']),
            visibility=PollVisibility(row['visibility']),
            status=PollStatus(row['status']),
            options=[PollOption(**opt) for opt in json.loads(row['options'])],
            allow_change_vote=row['allow_change_vote'],
            allow_multiple_votes=row['allow_multiple_votes'],
            max_choices=row['max_choices'],
            min_rating=row['min_rating'],
            max_rating=row['max_rating'],
            start_date=row['start_date'],
            end_date=row['end_date'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            total_votes=row['total_votes'],
            unique_voters=row['unique_voters'],
            tags=row['tags'] or [],
            attachments=json.loads(row['attachments']) if row['attachments'] else [],
            results_visible=row['results_visible'],
            anonymous=row['anonymous'],
            require_authentication=row['require_authentication']
        )

        # Кэшируем опрос
        await self._cache_poll(poll)

        return poll

    async def vote_poll(self, poll_id: str, user_id: int, option_ids: List[str],
                       ratings: Optional[Dict[str, int]] = None,
                       text_responses: Optional[Dict[str, str]] = None) -> bool:
        """Голосование в опросе"""
        poll = await self.get_poll(poll_id)
        if not poll:
            return False

        # Проверяем, активен ли опрос
        if poll.status != PollStatus.ACTIVE:
            return False

        # Проверяем, истекло ли время голосования
        if poll.end_date and datetime.utcnow() > poll.end_date:
            await self.close_poll(poll_id, poll.creator_id)
            return False

        # Проверяем права на голосование
        if poll.require_authentication and not await self._is_authenticated(user_id):
            return False

        # Проверяем ограничения типа опроса
        if not await self._validate_vote_constraints(poll, user_id, option_ids, ratings, text_responses):
            return False

        # Проверяем, голосовал ли пользователь ранее
        previous_vote = await self._get_user_vote(poll_id, user_id)
        if previous_vote and not poll.allow_change_vote:
            return False

        vote_id = str(uuid.uuid4())
        vote = Vote(
            id=vote_id,
            poll_id=poll_id,
            user_id=user_id,
            option_ids=option_ids,
            ratings=ratings,
            text_responses=text_responses,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Обновляем результаты опроса
        await self._update_poll_results(poll, vote, previous_vote)

        # Сохраняем голос в базу данных
        await self._save_vote_to_db(vote)

        # Если это изменение голоса, удаляем старый голос
        if previous_vote:
            await self._remove_previous_vote(poll, previous_vote)

        # Уведомляем заинтересованные стороны
        await self._notify_vote_cast(poll, vote)

        # Создаем запись активности
        await self._log_activity(poll_id, user_id, "voted", {
            "option_ids": option_ids,
            "ratings": ratings,
            "text_responses_count": len(text_responses) if text_responses else 0
        })

        return True

    async def _validate_vote_constraints(self, poll: Poll, user_id: int, 
                                       option_ids: List[str],
                                       ratings: Optional[Dict[str, int]],
                                       text_responses: Optional[Dict[str, str]]) -> bool:
        """Проверка ограничений голосования"""
        # Проверяем тип опроса
        if poll.type == PollType.SINGLE_CHOICE and len(option_ids) != 1:
            return False
        elif poll.type == PollType.BOOLEAN and len(option_ids) != 1:
            return False
        elif poll.type == PollType.MULTIPLE_CHOICE:
            if poll.max_choices and len(option_ids) > poll.max_choices:
                return False
        elif poll.type == PollType.RANKING:
            # Для ранжирования должны быть выбраны все опции
            if set(option_ids) != set(opt.id for opt in poll.options):
                return False
        elif poll.type == PollType.RATING:
            # Проверяем, что рейтинги в пределах допустимого диапазона
            if ratings:
                for rating in ratings.values():
                    if rating < poll.min_rating or rating > poll.max_rating:
                        return False
        elif poll.type == PollType.TEXT_RESPONSE:
            # Для текстовых ответов должны быть предоставлены ответы
            if not text_responses or not all(opt_id in text_responses for opt_id in option_ids):
                return False

        # Проверяем, что все выбранные опции существуют
        poll_option_ids = {opt.id for opt in poll.options}
        if not set(option_ids).issubset(poll_option_ids):
            return False

        return True

    async def _update_poll_results(self, poll: Poll, vote: Vote, previous_vote: Optional[Vote] = None):
        """Обновление результатов опроса"""
        # Если это изменение голоса, сначала уменьшаем старые результаты
        if previous_vote:
            await self._adjust_results(poll, previous_vote, decrement=True)

        # Увеличиваем результаты для новых голосов
        await self._adjust_results(poll, vote, decrement=False)

        # Обновляем статистику
        poll.total_votes += 1
        if not previous_vote:
            poll.unique_voters += 1
        poll.updated_at = datetime.utcnow()

        # Сохраняем обновленный опрос
        await self._update_poll_in_db(poll)

        # Обновляем кэш
        await self._cache_poll(poll)

    async def _adjust_results(self, poll: Poll, vote: Vote, decrement: bool = False):
        """Корректировка результатов опроса"""
        multiplier = -1 if decrement else 1

        for option_id in vote.option_ids:
            for option in poll.options:
                if option.id == option_id:
                    option.votes += multiplier
                    break

        # Для рейтинга
        if vote.ratings:
            for option_id, rating in vote.ratings.items():
                for option in poll.options:
                    if option.id == option_id:
                        if option.rating is None:
                            option.rating = 0
                        option.rating += multiplier * rating
                        break

        # Для текстовых ответов
        if vote.text_responses:
            for option_id, response in vote.text_responses.items():
                for option in poll.options:
                    if option.id == option_id:
                        if option.text_response is None:
                            option.text_response = ""
                        # Для текстовых ответов мы сохраняем только последний ответ
                        option.text_response = response
                        break

    async def _save_vote_to_db(self, vote: Vote):
        """Сохранение голоса в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO poll_votes (
                    id, poll_id, user_id, option_ids, ratings, text_responses,
                    created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                vote.id, vote.poll_id, vote.user_id, vote.option_ids,
                json.dumps(vote.ratings) if vote.ratings else None,
                json.dumps(vote.text_responses) if vote.text_responses else None,
                vote.created_at, vote.updated_at
            )

    async def _get_user_vote(self, poll_id: str, user_id: int) -> Optional[Vote]:
        """Получение голоса пользователя в опросе"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, poll_id, user_id, option_ids, ratings, text_responses,
                       created_at, updated_at
                FROM poll_votes WHERE poll_id = $1 AND user_id = $2
                """,
                poll_id, user_id
            )

        if not row:
            return None

        return Vote(
            id=row['id'],
            poll_id=row['poll_id'],
            user_id=row['user_id'],
            option_ids=row['option_ids'],
            ratings=json.loads(row['ratings']) if row['ratings'] else None,
            text_responses=json.loads(row['text_responses']) if row['text_responses'] else None,
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

    async def _remove_previous_vote(self, poll: Poll, previous_vote: Vote):
        """Удаление предыдущего голоса при изменении"""
        await self._adjust_results(poll, previous_vote, decrement=True)

        # Удаляем из базы данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM poll_votes WHERE id = $1",
                previous_vote.id
            )

    async def get_poll_results(self, poll_id: str, user_id: int) -> Optional[PollResult]:
        """Получение результатов опроса"""
        poll = await self.get_poll(poll_id)
        if not poll:
            return None

        # Проверяем права на просмотр результатов
        if not await self._can_view_results(poll, user_id):
            return None

        # Формируем результаты
        option_results = []
        for option in poll.options:
            percentage = (option.votes / poll.total_votes * 100) if poll.total_votes > 0 else 0
            option_results.append({
                'option_id': option.id,
                'text': option.text,
                'votes': option.votes,
                'percentage': round(percentage, 2),
                'rating': option.rating,
                'text_response': option.text_response
            })

        result = PollResult(
            poll_id=poll_id,
            option_results=option_results,
            total_votes=poll.total_votes,
            unique_voters=poll.unique_voters,
            timestamp=datetime.utcnow()
        )

        return result

    async def _can_view_results(self, poll: Poll, user_id: int) -> bool:
        """Проверка прав на просмотр результатов"""
        if poll.results_visible:
            if poll.visibility == PollVisibility.PUBLIC:
                return True
            elif poll.visibility == PollVisibility.PARTICIPANTS_ONLY:
                # Проверяем, участвовал ли пользователь в голосовании
                return await self._has_user_voted(poll.id, user_id)
            elif poll.visibility == PollVisibility.ADMIN_ONLY:
                # Только создатель или администратор
                return poll.creator_id == user_id or await self._is_admin(user_id)
        else:
            # Результаты не видны до окончания голосования
            return poll.end_date and datetime.utcnow() > poll.end_date

    async def _has_user_voted(self, poll_id: str, user_id: int) -> bool:
        """Проверка, голосовал ли пользователь"""
        vote = await self._get_user_vote(poll_id, user_id)
        return vote is not None

    async def close_poll(self, poll_id: str, closer_id: int) -> bool:
        """Закрытие опроса"""
        poll = await self.get_poll(poll_id)
        if not poll:
            return False

        # Проверяем права на закрытие (создатель или администратор)
        if poll.creator_id != closer_id and not await self._is_admin(closer_id):
            return False

        # Обновляем статус
        poll.status = PollStatus.CLOSED
        poll.updated_at = datetime.utcnow()

        # Сохраняем в базу данных
        await self._update_poll_in_db(poll)

        # Обновляем кэш
        await self._cache_poll(poll)

        # Уведомляем заинтересованные стороны
        await self._notify_poll_closed(poll)

        # Создаем запись активности
        await self._log_activity(poll_id, closer_id, "closed", {})

        return True

    async def _update_poll_in_db(self, poll: Poll):
        """Обновление опроса в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE polls SET
                    status = $2, total_votes = $3, unique_voters = $4,
                    updated_at = $5
                WHERE id = $1
                """,
                poll.id, poll.status.value, poll.total_votes, 
                poll.unique_voters, poll.updated_at
            )

    async def get_active_polls(self, chat_id: Optional[str] = None, 
                              group_id: Optional[str] = None,
                              limit: int = 50, offset: int = 0) -> List[Poll]:
        """Получение активных опросов"""
        conditions = ["status = 'active'"]
        params = []
        param_idx = 1

        if chat_id:
            conditions.append(f"chat_id = ${param_idx}")
            params.append(chat_id)
            param_idx += 1
        if group_id:
            conditions.append(f"group_id = ${param_idx}")
            params.append(group_id)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT id, title, description, creator_id, chat_id, group_id,
                   type, visibility, status, options, allow_change_vote,
                   allow_multiple_votes, max_choices, min_rating, max_rating,
                   start_date, end_date, created_at, updated_at, total_votes,
                   unique_voters, tags, attachments, results_visible,
                   anonymous, require_authentication
            FROM polls
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        polls = []
        for row in rows:
            poll = Poll(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                creator_id=row['creator_id'],
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                type=PollType(row['type']),
                visibility=PollVisibility(row['visibility']),
                status=PollStatus(row['status']),
                options=[PollOption(**opt) for opt in json.loads(row['options'])],
                allow_change_vote=row['allow_change_vote'],
                allow_multiple_votes=row['allow_multiple_votes'],
                max_choices=row['max_choices'],
                min_rating=row['min_rating'],
                max_rating=row['max_rating'],
                start_date=row['start_date'],
                end_date=row['end_date'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                total_votes=row['total_votes'],
                unique_voters=row['unique_voters'],
                tags=row['tags'] or [],
                attachments=json.loads(row['attachments']) if row['attachments'] else [],
                results_visible=row['results_visible'],
                anonymous=row['anonymous'],
                require_authentication=row['require_authentication']
            )
            polls.append(poll)

        return polls

    async def get_user_polls(self, user_id: int, status: Optional[PollStatus] = None,
                           limit: int = 50, offset: int = 0) -> List[Poll]:
        """Получение опросов пользователя"""
        conditions = ["creator_id = $1"]
        params = [user_id]
        param_idx = 2

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT id, title, description, creator_id, chat_id, group_id,
                   type, visibility, status, options, allow_change_vote,
                   allow_multiple_votes, max_choices, min_rating, max_rating,
                   start_date, end_date, created_at, updated_at, total_votes,
                   unique_voters, tags, attachments, results_visible,
                   anonymous, require_authentication
            FROM polls
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        polls = []
        for row in rows:
            poll = Poll(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                creator_id=row['creator_id'],
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                type=PollType(row['type']),
                visibility=PollVisibility(row['visibility']),
                status=PollStatus(row['status']),
                options=[PollOption(**opt) for opt in json.loads(row['options'])],
                allow_change_vote=row['allow_change_vote'],
                allow_multiple_votes=row['allow_multiple_votes'],
                max_choices=row['max_choices'],
                min_rating=row['min_rating'],
                max_rating=row['max_rating'],
                start_date=row['start_date'],
                end_date=row['end_date'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                total_votes=row['total_votes'],
                unique_voters=row['unique_voters'],
                tags=row['tags'] or [],
                attachments=json.loads(row['attachments']) if row['attachments'] else [],
                results_visible=row['results_visible'],
                anonymous=row['anonymous'],
                require_authentication=row['require_authentication']
            )
            polls.append(poll)

        return polls

    async def add_attachment_to_poll(self, poll_id: str, attachment: Dict, user_id: int) -> bool:
        """Добавление вложения к опросу"""
        poll = await self.get_poll(poll_id)
        if not poll:
            return False

        # Проверяем права на добавление вложения
        if poll.creator_id != user_id and not await self._is_admin(user_id):
            return False

        # Добавляем вложение
        poll.attachments.append(attachment)
        poll.updated_at = datetime.utcnow()

        # Сохраняем в базу данных
        await self._update_poll_in_db(poll)

        # Обновляем кэш
        await self._cache_poll(poll)

        # Создаем запись активности
        await self._log_activity(poll_id, user_id, "attachment_added", {
            "attachment_id": attachment['id'],
            "attachment_name": attachment['name']
        })

        return True

    async def _is_authenticated(self, user_id: int) -> bool:
        """Проверка аутентификации пользователя"""
        # В реальном приложении здесь будет проверка сессии пользователя
        return user_id is not None and user_id > 0

    async def _is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        # В реальном приложении здесь будет проверка прав пользователя
        return False

    async def _cache_poll(self, poll: Poll):
        """Кэширование опроса"""
        await redis_client.setex(f"poll:{poll.id}", 300, poll.model_dump_json())

    async def _get_cached_poll(self, poll_id: str) -> Optional[Poll]:
        """Получение опроса из кэша"""
        cached = await redis_client.get(f"poll:{poll_id}")
        if cached:
            return Poll(**json.loads(cached))
        return None

    async def _log_activity(self, poll_id: str, user_id: int, action: str, details: Dict):
        """Логирование активности по опросу"""
        activity_id = str(uuid.uuid4())
        activity = {
            'id': activity_id,
            'poll_id': poll_id,
            'user_id': user_id,
            'action': action,
            'details': details,
            'created_at': datetime.utcnow().isoformat()
        }

        # Сохраняем активность в базу данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO poll_activities (id, poll_id, user_id, action, details, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                activity_id, poll_id, user_id, action, 
                json.dumps(details), activity['created_at']
            )

    async def _notify_poll_created(self, poll: Poll):
        """Уведомление о создании опроса"""
        notification = {
            'type': 'poll_created',
            'poll': self._poll_to_dict(poll),
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем в чат, если опрос связан с чатом
        if poll.chat_id:
            await self._send_notification_to_chat(poll.chat_id, notification)

    async def _notify_vote_cast(self, poll: Poll, vote: Vote):
        """Уведомление о голосовании"""
        notification = {
            'type': 'vote_cast',
            'poll_id': poll.id,
            'user_id': vote.user_id if not poll.anonymous else None,
            'option_ids': vote.option_ids,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем в чат
        if poll.chat_id:
            await self._send_notification_to_chat(poll.chat_id, notification)

        # Если результаты видны, отправляем обновленные результаты
        if poll.results_visible:
            results = await self.get_poll_results(poll.id, poll.creator_id)
            if results:
                results_notification = {
                    'type': 'poll_results_updated',
                    'poll_id': poll.id,
                    'results': results.dict(),
                    'timestamp': datetime.utcnow().isoformat()
                }
                await self._send_notification_to_chat(poll.chat_id, results_notification)

    async def _notify_poll_closed(self, poll: Poll):
        """Уведомление о закрытии опроса"""
        notification = {
            'type': 'poll_closed',
            'poll_id': poll.id,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем в чат
        if poll.chat_id:
            await self._send_notification_to_chat(poll.chat_id, notification)

    async def _send_notification_to_chat(self, chat_id: str, notification: Dict[str, any]):
        """Отправка уведомления в чат"""
        channel = f"chat:{chat_id}:polls"
        await redis_client.publish(channel, json.dumps(notification))

    def _poll_to_dict(self, poll: Poll) -> Dict[str, any]:
        """Конвертация опроса в словарь для отправки"""
        return {
            'id': poll.id,
            'title': poll.title,
            'description': poll.description,
            'creator_id': poll.creator_id,
            'chat_id': poll.chat_id,
            'group_id': poll.group_id,
            'type': poll.type.value,
            'visibility': poll.visibility.value,
            'status': poll.status.value,
            'options_count': len(poll.options),
            'allow_change_vote': poll.allow_change_vote,
            'allow_multiple_votes': poll.allow_multiple_votes,
            'max_choices': poll.max_choices,
            'start_date': poll.start_date.isoformat() if poll.start_date else None,
            'end_date': poll.end_date.isoformat() if poll.end_date else None,
            'created_at': poll.created_at.isoformat() if poll.created_at else None,
            'updated_at': poll.updated_at.isoformat() if poll.updated_at else None,
            'total_votes': poll.total_votes,
            'unique_voters': poll.unique_voters,
            'tags': poll.tags,
            'attachments_count': len(poll.attachments),
            'results_visible': poll.results_visible,
            'anonymous': poll.anonymous,
            'require_authentication': poll.require_authentication
        }

# Глобальный экземпляр для использования в приложении
enhanced_poll_service = EnhancedPollService()
# Voting and Polling System
# File: services/poll_service/voting_polling_system.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid
import hashlib
from dataclasses import dataclass

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
    CHAT_MEMBERS = "chat_members"
    GROUP_MEMBERS = "group_members"
    PROJECT_MEMBERS = "project_members"
    FRIENDS_ONLY = "friends_only"

class PollStatus(Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"
    ARCHIVED = "archived"

class PollResultVisibility(Enum):
    IMMEDIATE = "immediate"  # Результаты видны сразу после голосования
    AFTER_CLOSE = "after_close"  # Результаты видны только после закрытия
    ADMIN_ONLY = "admin_only"  # Результаты видны только администраторам

class Poll(BaseModel):
    id: str
    title: str
    description: str
    creator_id: int
    type: PollType
    visibility: PollVisibility
    status: PollStatus
    options: List[Dict[str, Any]]  # [{'id': 'option_id', 'text': 'option_text', 'votes': 0}]
    allow_multiple_votes: bool = False
    allow_change_vote: bool = True
    max_choices: Optional[int] = None  # Для multiple choice
    min_rating: int = 1  # Для рейтинга
    max_rating: int = 5  # Для рейтинга
    start_date: datetime
    end_date: Optional[datetime] = None
    result_visibility: PollResultVisibility = PollResultVisibility.IMMEDIATE
    allow_comments: bool = True
    anonymous_voting: bool = False
    shuffle_options: bool = False  # Перемешивать варианты при отображении
    chat_id: Optional[str] = None
    group_id: Optional[str] = None
    project_id: Optional[str] = None
    metadata: Optional[Dict] = None
    created_at: datetime = None
    updated_at: datetime = None
    closed_at: Optional[datetime] = None

class PollVote(BaseModel):
    id: str
    poll_id: str
    user_id: int
    option_ids: List[str]  # Для multiple choice
    rating: Optional[int] = None  # Для рейтинга
    text_response: Optional[str] = None  # Для текстовых ответов
    comment: Optional[str] = None  # Комментарий к голосованию
    created_at: datetime = None
    updated_at: datetime = None

class PollResult(BaseModel):
    poll_id: str
    total_votes: int
    option_results: List[Dict[str, Any]]  # [{'option_id': 'id', 'votes': count, 'percentage': percent}]
    user_responses: Optional[List[Dict[str, Any]]] = None  # Для анонимных опросов не используется
    created_at: datetime = None

class PollComment(BaseModel):
    id: str
    poll_id: str
    user_id: int
    content: str
    parent_comment_id: Optional[str] = None  # Для вложенных комментариев
    created_at: datetime = None
    updated_at: datetime = None

class VotingPollingService:
    def __init__(self):
        self.default_poll_settings = {
            'max_options': 10,
            'max_option_length': 200,
            'max_description_length': 1000,
            'max_title_length': 100,
            'default_duration_hours': 24,
            'allow_comments_default': True,
            'anonymous_voting_default': False,
            'shuffle_options_default': False
        }

    async def create_poll(self, title: str, description: str, creator_id: int,
                         options: List[str], poll_type: PollType,
                         visibility: PollVisibility = PollVisibility.PUBLIC,
                         allow_multiple_votes: bool = False,
                         allow_change_vote: bool = True,
                         max_choices: Optional[int] = None,
                         min_rating: int = 1,
                         max_rating: int = 5,
                         start_date: Optional[datetime] = None,
                         end_date: Optional[datetime] = None,
                         result_visibility: PollResultVisibility = PollResultVisibility.IMMEDIATE,
                         allow_comments: bool = True,
                         anonymous_voting: bool = False,
                         shuffle_options: bool = False,
                         chat_id: Optional[str] = None,
                         group_id: Optional[str] = None,
                         project_id: Optional[str] = None,
                         metadata: Optional[Dict] = None) -> Optional[str]:
        """Создание нового опроса/голосования"""
        # Проверяем ограничения
        if len(options) < 2:
            logger.error("Poll must have at least 2 options")
            return None

        if len(options) > self.default_poll_settings['max_options']:
            logger.error(f"Poll cannot have more than {self.default_poll_settings['max_options']} options")
            return None

        if len(title) > self.default_poll_settings['max_title_length']:
            logger.error(f"Title exceeds maximum length of {self.default_poll_settings['max_title_length']} characters")
            return None

        if len(description) > self.default_poll_settings['max_description_length']:
            logger.error(f"Description exceeds maximum length of {self.default_poll_settings['max_description_length']} characters")
            return None

        for option in options:
            if len(option) > self.default_poll_settings['max_option_length']:
                logger.error(f"Option exceeds maximum length of {self.default_poll_settings['max_option_length']} characters")
                return None

        poll_id = str(uuid.uuid4())

        # Создаем варианты ответов
        poll_options = []
        for option_text in options:
            option_id = str(uuid.uuid4())
            poll_options.append({
                'id': option_id,
                'text': option_text,
                'votes': 0
            })

        # Устанавливаем дату начала, если не указана
        if not start_date:
            start_date = datetime.utcnow()

        poll = Poll(
            id=poll_id,
            title=title,
            description=description,
            creator_id=creator_id,
            type=poll_type,
            visibility=visibility,
            status=PollStatus.ACTIVE if start_date <= datetime.utcnow() else PollStatus.DRAFT,
            options=poll_options,
            allow_multiple_votes=allow_multiple_votes,
            allow_change_vote=allow_change_vote,
            max_choices=max_choices,
            min_rating=min_rating,
            max_rating=max_rating,
            start_date=start_date,
            end_date=end_date,
            result_visibility=result_visibility,
            allow_comments=allow_comments,
            anonymous_voting=anonymous_voting,
            shuffle_options=shuffle_options,
            chat_id=chat_id,
            group_id=group_id,
            project_id=project_id,
            metadata=metadata or {},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем опрос в базу данных
        await self._save_poll_to_db(poll)

        # Добавляем в кэш
        await self._cache_poll(poll)

        # Уведомляем заинтересованные стороны
        await self._notify_poll_created(poll)

        # Создаем запись активности
        await self._log_activity(creator_id, "poll_created", {
            "poll_id": poll_id,
            "poll_type": poll_type.value,
            "options_count": len(options),
            "creator_id": creator_id
        })

        return poll_id

    async def _save_poll_to_db(self, poll: Poll):
        """Сохранение опроса в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO polls (
                    id, title, description, creator_id, type, visibility, status,
                    options, allow_multiple_votes, allow_change_vote, max_choices,
                    min_rating, max_rating, start_date, end_date, result_visibility,
                    allow_comments, anonymous_voting, shuffle_options, chat_id,
                    group_id, project_id, metadata, created_at, updated_at, closed_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                         $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26)
                """,
                poll.id, poll.title, poll.description, poll.creator_id,
                poll.type.value, poll.visibility.value, poll.status.value,
                json.dumps(poll.options), poll.allow_multiple_votes,
                poll.allow_change_vote, poll.max_choices, poll.min_rating,
                poll.max_rating, poll.start_date, poll.end_date,
                poll.result_visibility.value, poll.allow_comments,
                poll.anonymous_voting, poll.shuffle_options, poll.chat_id,
                poll.group_id, poll.project_id, json.dumps(poll.metadata),
                poll.created_at, poll.updated_at, poll.closed_at
            )

    async def get_poll(self, poll_id: str, user_id: Optional[int] = None) -> Optional[Poll]:
        """Получение опроса по ID"""
        # Сначала проверяем кэш
        cached_poll = await self._get_cached_poll(poll_id)
        if cached_poll:
            # Проверяем права доступа
            if await self._can_access_poll(cached_poll, user_id):
                return cached_poll
            else:
                return None

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, title, description, creator_id, type, visibility, status,
                       options, allow_multiple_votes, allow_change_vote, max_choices,
                       min_rating, max_rating, start_date, end_date, result_visibility,
                       allow_comments, anonymous_voting, shuffle_options, chat_id,
                       group_id, project_id, metadata, created_at, updated_at, closed_at
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
            type=PollType(row['type']),
            visibility=PollVisibility(row['visibility']),
            status=PollStatus(row['status']),
            options=json.loads(row['options']) if row['options'] else [],
            allow_multiple_votes=row['allow_multiple_votes'],
            allow_change_vote=row['allow_change_vote'],
            max_choices=row['max_choices'],
            min_rating=row['min_rating'],
            max_rating=row['max_rating'],
            start_date=row['start_date'],
            end_date=row['end_date'],
            result_visibility=PollResultVisibility(row['result_visibility']),
            allow_comments=row['allow_comments'],
            anonymous_voting=row['anonymous_voting'],
            shuffle_options=row['shuffle_options'],
            chat_id=row['chat_id'],
            group_id=row['group_id'],
            project_id=row['project_id'],
            metadata=json.loads(row['metadata']) if row['metadata'] else None,
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            closed_at=row['closed_at']
        )

        # Проверяем права доступа
        if not await self._can_access_poll(poll, user_id):
            return None

        # Кэшируем опрос
        await self._cache_poll(poll)

        return poll

    async def vote_poll(self, poll_id: str, user_id: int, option_ids: List[str],
                       rating: Optional[int] = None, text_response: Optional[str] = None,
                       comment: Optional[str] = None) -> bool:
        """Голосование в опросе"""
        poll = await self.get_poll(poll_id)
        if not poll:
            return False

        # Проверяем права на голосование
        if not await self._can_vote_poll(poll, user_id):
            return False

        # Проверяем, не истекло ли время голосования
        if poll.end_date and datetime.utcnow() > poll.end_date:
            await self.close_poll(poll_id, poll.creator_id)
            return False

        # Проверяем ограничения типа опроса
        if poll.type == PollType.SINGLE_CHOICE and len(option_ids) != 1:
            return False
        elif poll.type == PollType.MULTIPLE_CHOICE:
            if not poll.allow_multiple_votes and len(option_ids) > 1:
                return False
            if poll.max_choices and len(option_ids) > poll.max_choices:
                return False
        elif poll.type == PollType.RATING:
            if not rating or rating < poll.min_rating or rating > poll.max_rating:
                return False
        elif poll.type == PollType.TEXT_RESPONSE:
            if not text_response:
                return False

        # Проверяем, существуют ли указанные варианты
        option_ids_set = set(option_ids)
        poll_option_ids = {opt['id'] for opt in poll.options}
        if not option_ids_set.issubset(poll_option_ids):
            return False

        # Проверяем, голосовал ли пользователь ранее
        previous_vote = await self._get_user_vote(poll_id, user_id)
        if previous_vote and not poll.allow_change_vote:
            return False  # Пользователь не может изменить свой голос

        vote_id = str(uuid.uuid4())

        vote = PollVote(
            id=vote_id,
            poll_id=poll_id,
            user_id=user_id,
            option_ids=option_ids,
            rating=rating,
            text_response=text_response,
            comment=comment,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Обновляем результаты опроса
        await self._update_poll_results(poll, vote, previous_vote)

        # Сохраняем голос в базу данных
        await self._save_vote_to_db(vote)

        # Если пользователь может изменить голос, обновляем предыдущий голос
        if previous_vote and poll.allow_change_vote:
            await self._update_previous_vote(poll, previous_vote, vote)

        # Уведомляем участников опроса
        await self._notify_vote_cast(poll, vote)

        # Создаем запись активности
        await self._log_activity(user_id, "poll_voted", {
            "poll_id": poll_id,
            "user_id": user_id,
            "option_ids": option_ids,
            "rating": rating,
            "text_response_present": text_response is not None
        })

        return True

    async def _update_poll_results(self, poll: Poll, vote: PollVote, previous_vote: Optional[PollVote] = None):
        """Обновление результатов опроса"""
        # Если это изменение голоса, сначала уменьшаем старые результаты
        if previous_vote:
            for option_id in previous_vote.option_ids:
                for option in poll.options:
                    if option['id'] == option_id:
                        option['votes'] -= 1
                        break

        # Увеличиваем результаты для новых голосов
        for option_id in vote.option_ids:
            for option in poll.options:
                if option['id'] == option_id:
                    option['votes'] += 1
                    break

        # Обновляем общее количество голосов
        if not previous_vote:
            # Только если это новый голос, а не изменение
            # В реальной системе нужно отслеживать уникальных голосующих
            import logging
            logging.info(f"New vote added to poll {poll.id}, updating statistics")

        # Обновляем в базе данных
        await self._update_poll_in_db(poll)

        # Обновляем кэш
        await self._cache_poll(poll)

    async def _save_vote_to_db(self, vote: PollVote):
        """Сохранение голоса в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO poll_votes (
                    id, poll_id, user_id, option_ids, rating, text_response, comment, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                vote.id, vote.poll_id, vote.user_id, vote.option_ids,
                vote.rating, vote.text_response, vote.comment,
                vote.created_at, vote.updated_at
            )

    async def get_poll_results(self, poll_id: str, user_id: int) -> Optional[PollResult]:
        """Получение результатов опроса"""
        poll = await self.get_poll(poll_id, user_id)
        if not poll:
            return None

        # Проверяем права на просмотр результатов
        can_view_results = await self._can_view_poll_results(poll, user_id)
        if not can_view_results:
            return None

        # Подсчитываем результаты
        total_votes = sum(opt['votes'] for opt in poll.options)
        option_results = []

        for option in poll.options:
            percentage = (option['votes'] / total_votes * 100) if total_votes > 0 else 0
            option_results.append({
                'option_id': option['id'],
                'text': option['text'],
                'votes': option['votes'],
                'percentage': round(percentage, 2)
            })

        # Для анонимных опросов не включаем информацию о пользователях
        user_responses = None
        if not poll.anonymous_voting:
            user_responses = await self._get_user_responses(poll_id)

        result = PollResult(
            poll_id=poll_id,
            total_votes=total_votes,
            option_results=option_results,
            user_responses=user_responses,
            created_at=datetime.utcnow()
        )

        return result

    async def _get_user_responses(self, poll_id: str) -> List[Dict[str, Any]]:
        """Получение ответов пользователей (для неанонимных опросов)"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT pv.user_id, pv.option_ids, pv.rating, pv.text_response, 
                       pv.comment, pv.created_at, u.username
                FROM poll_votes pv
                JOIN users u ON pv.user_id = u.id
                WHERE pv.poll_id = $1
                ORDER BY pv.created_at DESC
                """,
                poll_id
            )

        responses = []
        for row in rows:
            response = {
                'user_id': row['user_id'],
                'username': row['username'],
                'option_ids': row['option_ids'],
                'rating': row['rating'],
                'text_response': row['text_response'],
                'comment': row['comment'],
                'created_at': row['created_at'].isoformat()
            }
            responses.append(response)

        return responses

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
        poll.closed_at = datetime.utcnow()
        poll.updated_at = datetime.utcnow()

        # Обновляем в базе данных
        await self._update_poll_in_db(poll)

        # Обновляем в кэше
        await self._cache_poll(poll)

        # Уведомляем участников
        await self._notify_poll_closed(poll)

        # Создаем запись активности
        await self._log_activity(closer_id, "poll_closed", {
            "poll_id": poll_id,
            "closer_id": closer_id
        })

        return True

    async def _update_poll_in_db(self, poll: Poll):
        """Обновление опроса в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE polls SET
                    status = $2, closed_at = $3, updated_at = $4
                WHERE id = $1
                """,
                poll.id, poll.status.value, poll.closed_at, poll.updated_at
            )

    async def add_poll_comment(self, poll_id: str, user_id: int, content: str,
                             parent_comment_id: Optional[str] = None) -> Optional[str]:
        """Добавление комментария к опросу"""
        poll = await self.get_poll(poll_id)
        if not poll or not poll.allow_comments:
            return None

        # Проверяем права на комментирование
        if not await self._can_comment_poll(poll, user_id):
            return None

        comment_id = str(uuid.uuid4())

        comment = PollComment(
            id=comment_id,
            poll_id=poll_id,
            user_id=user_id,
            content=content,
            parent_comment_id=parent_comment_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем комментарий в базу данных
        await self._save_poll_comment_to_db(comment)

        # Уведомляем участников опроса
        await self._notify_comment_added(poll, comment)

        # Создаем запись активности
        await self._log_activity(user_id, "poll_comment_added", {
            "poll_id": poll_id,
            "comment_id": comment_id,
            "user_id": user_id
        })

        return comment_id

    async def _save_poll_comment_to_db(self, comment: PollComment):
        """Сохранение комментария к опросу в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO poll_comments (
                    id, poll_id, user_id, content, parent_comment_id, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                comment.id, comment.poll_id, comment.user_id, comment.content,
                comment.parent_comment_id, comment.created_at, comment.updated_at
            )

    async def get_poll_comments(self, poll_id: str, user_id: int,
                              limit: int = 50, offset: int = 0) -> List[PollComment]:
        """Получение комментариев к опросу"""
        poll = await self.get_poll(poll_id, user_id)
        if not poll or not poll.allow_comments:
            return []

        # Проверяем права на просмотр комментариев
        if not await self._can_view_poll_comments(poll, user_id):
            return []

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, poll_id, user_id, content, parent_comment_id, created_at, updated_at
                FROM poll_comments
                WHERE poll_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                poll_id, limit, offset
            )

        comments = []
        for row in rows:
            comment = PollComment(
                id=row['id'],
                poll_id=row['poll_id'],
                user_id=row['user_id'],
                content=row['content'],
                parent_comment_id=row['parent_comment_id'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            comments.append(comment)

        return comments

    async def _can_access_poll(self, poll: Poll, user_id: Optional[int]) -> bool:
        """Проверка прав доступа к опросу"""
        if poll.visibility == PollVisibility.PUBLIC:
            return True

        if not user_id:
            return False

        if poll.creator_id == user_id:
            return True

        if poll.visibility == PollVisibility.FRIENDS_ONLY:
            return await self._are_friends(poll.creator_id, user_id)

        if poll.visibility == PollVisibility.CHAT_MEMBERS and poll.chat_id:
            return await self._is_chat_member(user_id, poll.chat_id)

        if poll.visibility == PollVisibility.GROUP_MEMBERS and poll.group_id:
            return await self._is_group_member(user_id, poll.group_id)

        if poll.visibility == PollVisibility.PROJECT_MEMBERS and poll.project_id:
            return await self._is_project_member(user_id, poll.project_id)

        return False

    async def _can_vote_poll(self, poll: Poll, user_id: int) -> bool:
        """Проверка прав на голосование в опросе"""
        # Проверяем статус опроса
        if poll.status != PollStatus.ACTIVE:
            return False

        # Проверяем права доступа
        if not await self._can_access_poll(poll, user_id):
            return False

        # Проверяем, не истекло ли время голосования
        if poll.end_date and datetime.utcnow() > poll.end_date:
            return False

        return True

    async def _can_view_poll_results(self, poll: Poll, user_id: int) -> bool:
        """Проверка прав на просмотр результатов опроса"""
        # Если результаты видны сразу
        if poll.result_visibility == PollResultVisibility.IMMEDIATE:
            return await self._can_access_poll(poll, user_id)

        # Если результаты видны только после закрытия
        if poll.result_visibility == PollResultVisibility.AFTER_CLOSE:
            return poll.status == PollStatus.CLOSED and await self._can_access_poll(poll, user_id)

        # Если результаты видны только администраторам
        if poll.result_visibility == PollResultVisibility.ADMIN_ONLY:
            return await self._is_admin(user_id) or poll.creator_id == user_id

        return False

    async def _can_comment_poll(self, poll: Poll, user_id: int) -> bool:
        """Проверка прав на комментирование опроса"""
        return await self._can_access_poll(poll, user_id)

    async def _can_view_poll_comments(self, poll: Poll, user_id: int) -> bool:
        """Проверка прав на просмотр комментариев к опросу"""
        return await self._can_access_poll(poll, user_id)

    async def _get_user_vote(self, poll_id: str, user_id: int) -> Optional[PollVote]:
        """Получение голоса пользователя в опросе"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, poll_id, user_id, option_ids, rating, text_response, comment, created_at, updated_at
                FROM poll_votes WHERE poll_id = $1 AND user_id = $2
                """,
                poll_id, user_id
            )

        if not row:
            return None

        return PollVote(
            id=row['id'],
            poll_id=row['poll_id'],
            user_id=row['user_id'],
            option_ids=row['option_ids'] or [],
            rating=row['rating'],
            text_response=row['text_response'],
            comment=row['comment'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

    async def _update_previous_vote(self, poll: Poll, previous_vote: PollVote, new_vote: PollVote):
        """Обновление предыдущего голоса при изменении"""
        # Удаляем предыдущий голос из базы данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM poll_votes WHERE id = $1",
                previous_vote.id
            )

    async def _cache_poll(self, poll: Poll):
        """Кэширование опроса"""
        await redis_client.setex(f"poll:{poll.id}", 300, poll.model_dump_json())

    async def _get_cached_poll(self, poll_id: str) -> Optional[Poll]:
        """Получение опроса из кэша"""
        cached = await redis_client.get(f"poll:{poll_id}")
        if cached:
            return Poll(**json.loads(cached.decode()))
        return None

    async def _notify_poll_created(self, poll: Poll):
        """Уведомление о создании опроса"""
        notification = {
            'type': 'poll_created',
            'poll': {
                'id': poll.id,
                'title': poll.title,
                'description': poll.description,
                'type': poll.type.value,
                'creator_id': poll.creator_id,
                'options_count': len(poll.options),
                'start_date': poll.start_date.isoformat(),
                'end_date': poll.end_date.isoformat() if poll.end_date else None
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем в чат, если опрос создан в чате
        if poll.chat_id:
            await redis_client.publish(f"chat:{poll.chat_id}:polls", json.dumps(notification))

    async def _notify_vote_cast(self, poll: Poll, vote: PollVote):
        """Уведомление о голосовании"""
        notification = {
            'type': 'vote_cast',
            'poll_id': poll.id,
            'user_id': vote.user_id if not poll.anonymous_voting else None,
            'option_ids': vote.option_ids,
            'rating': vote.rating,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем в чат
        if poll.chat_id:
            await redis_client.publish(f"chat:{poll.chat_id}:polls", json.dumps(notification))

        # Отправляем создателю опроса
        await redis_client.publish(f"user:{poll.creator_id}:polls", json.dumps(notification))

    async def _notify_poll_closed(self, poll: Poll):
        """Уведомление о закрытии опроса"""
        notification = {
            'type': 'poll_closed',
            'poll_id': poll.id,
            'title': poll.title,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем в чат
        if poll.chat_id:
            await redis_client.publish(f"chat:{poll.chat_id}:polls", json.dumps(notification))

        # Отправляем участникам опроса
        await self._notify_poll_participants(poll, notification)

    async def _notify_comment_added(self, poll: Poll, comment: PollComment):
        """Уведомление о добавлении комментария"""
        notification = {
            'type': 'poll_comment_added',
            'poll_id': poll.id,
            'comment': {
                'id': comment.id,
                'user_id': comment.user_id,
                'content': comment.content,
                'parent_comment_id': comment.parent_comment_id,
                'created_at': comment.created_at.isoformat()
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем в чат
        if poll.chat_id:
            await redis_client.publish(f"chat:{poll.chat_id}:polls", json.dumps(notification))

        # Отправляем создателю опроса
        await redis_client.publish(f"user:{poll.creator_id}:polls", json.dumps(notification))

    async def _notify_poll_participants(self, poll: Poll, notification: Dict[str, Any]):
        """Уведомление участников опроса"""
        # Получаем всех, кто голосовал в опросе
        async with db_pool.acquire() as conn:
            voter_ids = await conn.fetch(
                """
                SELECT DISTINCT user_id FROM poll_votes WHERE poll_id = $1
                """,
                poll.id
            )

        for voter_id in voter_ids:
            await redis_client.publish(f"user:{voter_id['user_id']}:polls", json.dumps(notification))

    async def get_user_polls(self, user_id: int, status: Optional[PollStatus] = None,
                           poll_type: Optional[PollType] = None,
                           limit: int = 50, offset: int = 0) -> List[Poll]:
        """Получение опросов пользователя"""
        conditions = ["(creator_id = $1 OR $1 = ANY(mentions))"]
        params = [user_id]
        param_idx = 2

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        if poll_type:
            conditions.append(f"type = ${param_idx}")
            params.append(poll_type.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, title, description, creator_id, type, visibility, status,
                   options, allow_multiple_votes, allow_change_vote, max_choices,
                   min_rating, max_rating, start_date, end_date, result_visibility,
                   allow_comments, anonymous_voting, shuffle_options, chat_id,
                   group_id, project_id, metadata, created_at, updated_at, closed_at
            FROM polls
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        polls = []
        for row in rows:
            poll = Poll(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                creator_id=row['creator_id'],
                type=PollType(row['type']),
                visibility=PollVisibility(row['visibility']),
                status=PollStatus(row['status']),
                options=json.loads(row['options']) if row['options'] else [],
                allow_multiple_votes=row['allow_multiple_votes'],
                allow_change_vote=row['allow_change_vote'],
                max_choices=row['max_choices'],
                min_rating=row['min_rating'],
                max_rating=row['max_rating'],
                start_date=row['start_date'],
                end_date=row['end_date'],
                result_visibility=PollResultVisibility(row['result_visibility']),
                allow_comments=row['allow_comments'],
                anonymous_voting=row['anonymous_voting'],
                shuffle_options=row['shuffle_options'],
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                closed_at=row['closed_at']
            )
            polls.append(poll)

        return polls

    async def get_poll_statistics(self, poll_id: str) -> Dict[str, Any]:
        """Получение статистики по опросу"""
        poll = await self.get_poll(poll_id)
        if not poll:
            return {}

        async with db_pool.acquire() as conn:
            # Общая статистика
            total_votes = await conn.fetchval(
                "SELECT COUNT(*) FROM poll_votes WHERE poll_id = $1",
                poll_id
            )

            unique_voters = await conn.fetchval(
                "SELECT COUNT(DISTINCT user_id) FROM poll_votes WHERE poll_id = $1",
                poll_id
            )

            # Статистика по времени
            time_stats = await conn.fetchrow(
                """
                SELECT 
                    MIN(created_at) as first_vote,
                    MAX(created_at) as last_vote,
                    AVG(EXTRACT(EPOCH FROM (created_at - $2))) as avg_time_to_vote
                FROM poll_votes 
                WHERE poll_id = $1
                """,
                poll_id, poll.start_date
            )

            # Статистика по вариантам
            option_stats = await conn.fetch(
                """
                SELECT option_id, COUNT(*) as vote_count
                FROM (
                    SELECT UNNEST(option_ids) as option_id
                    FROM poll_votes
                    WHERE poll_id = $1
                ) as unnested
                GROUP BY option_id
                """,
                poll_id
            )

        stats = {
            'poll_id': poll_id,
            'total_votes': total_votes or 0,
            'unique_voters': unique_voters or 0,
            'voter_participation_rate': (unique_voters or 0) / (len(poll.options) * 10) if len(poll.options) > 0 else 0,  # Примерный расчет
            'first_vote_at': time_stats['first_vote'].isoformat() if time_stats['first_vote'] else None,
            'last_vote_at': time_stats['last_vote'].isoformat() if time_stats['last_vote'] else None,
            'avg_time_to_vote': time_stats['avg_time_to_vote'] if time_stats['avg_time_to_vote'] else 0,
            'option_statistics': [
                {
                    'option_id': row['option_id'],
                    'vote_count': row['vote_count']
                }
                for row in option_stats
            ],
            'timestamp': datetime.utcnow().isoformat()
        }

        return stats

    async def get_active_polls(self, user_id: int, chat_id: Optional[str] = None,
                             group_id: Optional[str] = None,
                             limit: int = 20, offset: int = 0) -> List[Poll]:
        """Получение активных опросов"""
        conditions = ["status = 'active'"]
        params = []
        param_idx = 1

        if chat_id:
            conditions.append(f"chat_id = ${param_idx}")
            params.append(chat_id)
            param_idx += 1
        elif group_id:
            conditions.append(f"group_id = ${param_idx}")
            params.append(group_id)
            param_idx += 1

        # Проверяем права доступа к опросам
        conditions.append("(visibility = 'public' OR creator_id = $param_idx OR $param_idx = ANY(mentions))")
        params.append(user_id)
        param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, title, description, creator_id, type, visibility, status,
                   options, allow_multiple_votes, allow_change_vote, max_choices,
                   min_rating, max_rating, start_date, end_date, result_visibility,
                   allow_comments, anonymous_voting, shuffle_options, chat_id,
                   group_id, project_id, metadata, created_at, updated_at, closed_at
            FROM polls
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        polls = []
        for row in rows:
            poll = Poll(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                creator_id=row['creator_id'],
                type=PollType(row['type']),
                visibility=PollVisibility(row['visibility']),
                status=PollStatus(row['status']),
                options=json.loads(row['options']) if row['options'] else [],
                allow_multiple_votes=row['allow_multiple_votes'],
                allow_change_vote=row['allow_change_vote'],
                max_choices=row['max_choices'],
                min_rating=row['min_rating'],
                max_rating=row['max_rating'],
                start_date=row['start_date'],
                end_date=row['end_date'],
                result_visibility=PollResultVisibility(row['result_visibility']),
                allow_comments=row['allow_comments'],
                anonymous_voting=row['anonymous_voting'],
                shuffle_options=row['shuffle_options'],
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                closed_at=row['closed_at']
            )
            polls.append(poll)

        return polls

    async def _are_friends(self, user1_id: int, user2_id: int) -> bool:
        """Проверка, являются ли пользователи друзьями"""
        # В реальной системе здесь будет проверка в таблице друзей
        return False

    async def _is_chat_member(self, user_id: int, chat_id: str) -> bool:
        """Проверка, является ли пользователь членом чата"""
        # В реальной системе здесь будет проверка в таблице участников чата
        return False

    async def _is_group_member(self, user_id: int, group_id: str) -> bool:
        """Проверка, является ли пользователь членом группы"""
        # В реальной системе здесь будет проверка в таблице участников группы
        return False

    async def _is_project_member(self, user_id: int, project_id: str) -> bool:
        """Проверка, является ли пользователь участником проекта"""
        # В реальной системе здесь будет проверка в таблице участников проекта
        return False

    async def _is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        # В реальной системе здесь будет проверка прав пользователя
        return False

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
voting_polling_service = VotingPollingService()
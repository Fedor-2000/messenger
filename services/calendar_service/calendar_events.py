# Calendar and Events Management System
# File: services/calendar_service/calendar_events.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class EventPrivacy(Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    FRIENDS_ONLY = "friends_only"
    GROUP_MEMBERS = "group_members"

class EventStatus(Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    POSTPONED = "postponed"

class EventType(Enum):
    MEETING = "meeting"
    CALL = "call"
    BIRTHDAY = "birthday"
    ANNIVERSARY = "anniversary"
    TASK_DEADLINE = "task_deadline"
    PROJECT_MILESTONE = "project_milestone"
    PERSONAL = "personal"
    GROUP_EVENT = "group_event"
    CHAT_EVENT = "chat_event"
    CUSTOM = "custom"

class RecurrencePattern(Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    CUSTOM = "custom"

class ReminderType(Enum):
    EMAIL = "email"
    PUSH = "push"
    IN_APP = "in_app"
    SMS = "sms"

class CalendarEvent(BaseModel):
    id: str
    title: str
    description: str
    start_time: datetime
    end_time: datetime
    timezone: str = "UTC"
    creator_id: int
    attendees: List[int] = []  # ID участников
    event_type: EventType
    privacy: EventPrivacy
    status: EventStatus
    location: Optional[str] = None
    video_call_url: Optional[str] = None
    recurrence_pattern: Optional[RecurrencePattern] = None
    recurrence_end: Optional[datetime] = None
    reminder_settings: List[Dict] = []  # [{'type': 'push', 'minutes_before': 15}]
    chat_id: Optional[str] = None
    group_id: Optional[str] = None
    project_id: Optional[str] = None
    task_id: Optional[str] = None  # Связь с задачей
    metadata: Optional[Dict] = None
    created_at: datetime = None
    updated_at: datetime = None
    cancelled_at: Optional[datetime] = None

class EventAttendee(BaseModel):
    id: str
    event_id: str
    user_id: int
    status: str  # 'accepted', 'declined', 'tentative', 'needs_action'
    joined_at: Optional[datetime] = None
    created_at: datetime = None

class EventReminder(BaseModel):
    id: str
    event_id: str
    user_id: int
    reminder_type: ReminderType
    minutes_before: int
    sent_at: Optional[datetime] = None
    created_at: datetime = None

class CalendarService:
    def __init__(self):
        self.default_timezone = "UTC"
        self.max_attendees = 100  # Максимальное количество участников
        self.max_recurrence_occurrences = 365  # Максимальное количество повторений

    async def create_event(self, title: str, description: str, start_time: datetime,
                          end_time: datetime, creator_id: int,
                          attendees: List[int] = None,
                          event_type: EventType = EventType.CUSTOM,
                          privacy: EventPrivacy = EventPrivacy.PRIVATE,
                          location: Optional[str] = None,
                          video_call_url: Optional[str] = None,
                          recurrence_pattern: Optional[RecurrencePattern] = None,
                          recurrence_end: Optional[datetime] = None,
                          reminder_settings: List[Dict] = None,
                          chat_id: Optional[str] = None,
                          group_id: Optional[str] = None,
                          project_id: Optional[str] = None,
                          task_id: Optional[str] = None,
                          metadata: Optional[Dict] = None) -> Optional[str]:
        """Создание нового события"""
        event_id = str(uuid.uuid4())

        event = CalendarEvent(
            id=event_id,
            title=title,
            description=description,
            start_time=start_time,
            end_time=end_time,
            timezone=self.default_timezone,
            creator_id=creator_id,
            attendees=attendees or [],
            event_type=event_type,
            privacy=privacy,
            status=EventStatus.SCHEDULED,
            location=location,
            video_call_url=video_call_url,
            recurrence_pattern=recurrence_pattern,
            recurrence_end=recurrence_end,
            reminder_settings=reminder_settings or [],
            chat_id=chat_id,
            group_id=group_id,
            project_id=project_id,
            task_id=task_id,
            metadata=metadata or {},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Проверяем права доступа
        if not await self._can_create_event(event, creator_id):
            return None

        # Проверяем конфликты по времени
        if await self._has_time_conflict(event):
            # В реальной системе можно предложить пользователю варианты
            import logging
            logging.warning(f"Time conflict detected for event {event.id} for user {event.creator_id}")

        # Сохраняем событие в базу данных
        await self._save_event_to_db(event)

        # Добавляем участников
        if event.attendees:
            await self._add_attendees_to_event(event.id, event.attendees, creator_id)

        # Создаем напоминания
        if event.reminder_settings:
            await self._create_reminders_for_event(event)

        # Добавляем в кэш
        await self._cache_event(event)

        # Уведомляем участников
        await self._notify_event_created(event)

        # Создаем запись активности
        await self._log_activity(event.id, creator_id, "created", {
            "title": event.title,
            "attendee_count": len(event.attendees),
            "event_type": event.event_type.value
        })

        return event_id

    async def _save_event_to_db(self, event: CalendarEvent):
        """Сохранение события в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO calendar_events (
                    id, title, description, start_time, end_time, timezone,
                    creator_id, attendees, event_type, privacy, status,
                    location, video_call_url, recurrence_pattern, recurrence_end,
                    reminder_settings, chat_id, group_id, project_id, task_id,
                    metadata, created_at, updated_at, cancelled_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                         $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24)
                """,
                event.id, event.title, event.description, event.start_time,
                event.end_time, event.timezone, event.creator_id,
                event.attendees, event.event_type.value, event.privacy.value,
                event.status.value, event.location, event.video_call_url,
                event.recurrence_pattern.value if event.recurrence_pattern else None,
                event.recurrence_end, json.dumps(event.reminder_settings),
                event.chat_id, event.group_id, event.project_id, event.task_id,
                json.dumps(event.metadata) if event.metadata else None,
                event.created_at, event.updated_at, event.cancelled_at
            )

    async def get_event(self, event_id: str, user_id: Optional[int] = None) -> Optional[CalendarEvent]:
        """Получение события по ID"""
        # Сначала проверяем кэш
        cached_event = await self._get_cached_event(event_id)
        if cached_event:
            # Проверяем права доступа
            if await self._can_access_event(cached_event, user_id):
                return cached_event
            else:
                return None

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, title, description, start_time, end_time, timezone,
                       creator_id, attendees, event_type, privacy, status,
                       location, video_call_url, recurrence_pattern, recurrence_end,
                       reminder_settings, chat_id, group_id, project_id, task_id,
                       metadata, created_at, updated_at, cancelled_at
                FROM calendar_events WHERE id = $1
                """,
                event_id
            )

        if not row:
            return None

        event = CalendarEvent(
            id=row['id'],
            title=row['title'],
            description=row['description'],
            start_time=row['start_time'],
            end_time=row['end_time'],
            timezone=row['timezone'],
            creator_id=row['creator_id'],
            attendees=row['attendees'] or [],
            event_type=EventType(row['event_type']),
            privacy=EventPrivacy(row['privacy']),
            status=EventStatus(row['status']),
            location=row['location'],
            video_call_url=row['video_call_url'],
            recurrence_pattern=RecurrencePattern(row['recurrence_pattern']) if row['recurrence_pattern'] else None,
            recurrence_end=row['recurrence_end'],
            reminder_settings=json.loads(row['reminder_settings']) if row['reminder_settings'] else [],
            chat_id=row['chat_id'],
            group_id=row['group_id'],
            project_id=row['project_id'],
            task_id=row['task_id'],
            metadata=json.loads(row['metadata']) if row['metadata'] else None,
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            cancelled_at=row['cancelled_at']
        )

        # Проверяем права доступа
        if not await self._can_access_event(event, user_id):
            return None

        # Кэшируем событие
        await self._cache_event(event)

        return event

    async def update_event(self, event_id: str, user_id: int, updates: Dict[str, Any]) -> bool:
        """Обновление события"""
        event = await self.get_event(event_id, user_id)
        if not event:
            return False

        # Проверяем права на обновление
        if not await self._can_update_event(event, user_id):
            return False

        # Обновляем поля события
        for field, value in updates.items():
            if hasattr(event, field):
                if field == 'event_type' and isinstance(value, str):
                    setattr(event, field, EventType(value))
                elif field == 'privacy' and isinstance(value, str):
                    setattr(event, field, EventPrivacy(value))
                elif field == 'status' and isinstance(value, str):
                    setattr(event, field, EventStatus(value))
                elif field == 'recurrence_pattern' and isinstance(value, str):
                    setattr(event, field, RecurrencePattern(value) if value else None)
                else:
                    setattr(event, field, value)

        event.updated_at = datetime.utcnow()

        # Если статус изменился на "cancelled"
        if updates.get('status') == EventStatus.CANCELLED.value:
            event.cancelled_at = datetime.utcnow()

        # Обновляем в базе данных
        await self._update_event_in_db(event)

        # Обновляем кэш
        await self._cache_event(event)

        # Уведомляем участников об изменении
        await self._notify_event_updated(event)

        # Создаем запись активности
        await self._log_activity(event.id, user_id, "updated", updates)

        return True

    async def _update_event_in_db(self, event: CalendarEvent):
        """Обновление события в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE calendar_events SET
                    title = $2, description = $3, start_time = $4, end_time = $5,
                    timezone = $6, attendees = $7, event_type = $8, privacy = $9,
                    status = $10, location = $11, video_call_url = $12,
                    recurrence_pattern = $13, recurrence_end = $14,
                    reminder_settings = $15, chat_id = $16, group_id = $17,
                    project_id = $18, task_id = $19, metadata = $20,
                    updated_at = $21, cancelled_at = $22
                WHERE id = $1
                """,
                event.id, event.title, event.description, event.start_time,
                event.end_time, event.timezone, event.attendees,
                event.event_type.value, event.privacy.value, event.status.value,
                event.location, event.video_call_url,
                event.recurrence_pattern.value if event.recurrence_pattern else None,
                event.recurrence_end, json.dumps(event.reminder_settings),
                event.chat_id, event.group_id, event.project_id, event.task_id,
                json.dumps(event.metadata) if event.metadata else None,
                event.updated_at, event.cancelled_at
            )

    async def delete_event(self, event_id: str, user_id: int) -> bool:
        """Удаление события"""
        event = await self.get_event(event_id, user_id)
        if not event:
            return False

        # Проверяем права на удаление
        if not await self._can_delete_event(event, user_id):
            return False

        # Удаляем из базы данных
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM calendar_events WHERE id = $1", event_id)

        # Удаляем из кэша
        await self._uncache_event(event_id)

        # Удаляем участников
        await self._remove_attendees_from_event(event_id)

        # Удаляем напоминания
        await self._remove_reminders_for_event(event_id)

        # Уведомляем участников об удалении
        await self._notify_event_deleted(event)

        # Создаем запись активности
        await self._log_activity(event_id, user_id, "deleted", {})

        return True

    async def add_attendee(self, event_id: str, user_id: int, added_by: int) -> bool:
        """Добавление участника к событию"""
        event = await self.get_event(event_id)
        if not event:
            return False

        # Проверяем права на добавление участника
        if not await self._can_modify_attendees(event, added_by):
            return False

        # Проверяем, не является ли пользователь уже участником
        if user_id in event.attendees:
            return True  # Уже участник

        # Проверяем ограничение на количество участников
        if len(event.attendees) >= self.max_attendees:
            return False

        # Добавляем участника
        event.attendees.append(user_id)
        event.updated_at = datetime.utcnow()

        # Обновляем в базе данных
        await self._update_event_in_db(event)

        # Обновляем кэш
        await self._cache_event(event)

        # Добавляем в таблицу участников
        await self._add_attendee_to_db(event_id, user_id)

        # Создаем напоминания для нового участника
        await self._create_reminders_for_user(event, user_id)

        # Уведомляем участника
        await self._notify_attendee_added(event, user_id)

        # Создаем запись активности
        await self._log_activity(event_id, added_by, "attendee_added", {
            "added_user_id": user_id
        })

        return True

    async def remove_attendee(self, event_id: str, user_id: int, removed_by: int) -> bool:
        """Удаление участника из события"""
        event = await self.get_event(event_id)
        if not event or user_id not in event.attendees:
            return False

        # Проверяем права на удаление участника
        if not await self._can_modify_attendees(event, removed_by):
            return False

        # Удаляем участника
        event.attendees.remove(user_id)
        event.updated_at = datetime.utcnow()

        # Обновляем в базе данных
        await self._update_event_in_db(event)

        # Обновляем кэш
        await self._cache_event(event)

        # Удаляем из таблицы участников
        await self._remove_attendee_from_db(event_id, user_id)

        # Удаляем напоминания для участника
        await self._remove_reminders_for_user(event_id, user_id)

        # Уведомляем участника
        await self._notify_attendee_removed(event, user_id)

        # Создаем запись активности
        await self._log_activity(event_id, removed_by, "attendee_removed", {
            "removed_user_id": user_id
        })

        return True

    async def respond_to_event(self, event_id: str, user_id: int, response: str) -> bool:
        """Ответ участника на приглашение"""
        event = await self.get_event(event_id)
        if not event or user_id not in event.attendees:
            return False

        # Обновляем статус участника
        await self._update_attendee_status(event_id, user_id, response)

        # Уведомляем создателя события
        await self._notify_response_to_creator(event, user_id, response)

        # Создаем запись активности
        await self._log_activity(event_id, user_id, "responded", {
            "response": response
        })

        return True

    async def get_user_events(self, user_id: int, start_date: datetime, 
                            end_date: datetime, event_type: Optional[EventType] = None,
                            limit: int = 50, offset: int = 0) -> List[CalendarEvent]:
        """Получение событий пользователя в определенном диапазоне"""
        conditions = [
            "($1 = ANY(attendees) OR creator_id = $1)",
            "start_time >= $2",
            "end_time <= $3"
        ]
        params = [user_id, start_date, end_date]
        param_idx = 4

        if event_type:
            conditions.append(f"event_type = ${param_idx}")
            params.append(event_type.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, title, description, start_time, end_time, timezone,
                   creator_id, attendees, event_type, privacy, status,
                   location, video_call_url, recurrence_pattern, recurrence_end,
                   reminder_settings, chat_id, group_id, project_id, task_id,
                   metadata, created_at, updated_at, cancelled_at
            FROM calendar_events
            WHERE {where_clause}
            ORDER BY start_time
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        events = []
        for row in rows:
            event = CalendarEvent(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                start_time=row['start_time'],
                end_time=row['end_time'],
                timezone=row['timezone'],
                creator_id=row['creator_id'],
                attendees=row['attendees'] or [],
                event_type=EventType(row['event_type']),
                privacy=EventPrivacy(row['privacy']),
                status=EventStatus(row['status']),
                location=row['location'],
                video_call_url=row['video_call_url'],
                recurrence_pattern=RecurrencePattern(row['recurrence_pattern']) if row['recurrence_pattern'] else None,
                recurrence_end=row['recurrence_end'],
                reminder_settings=json.loads(row['reminder_settings']) if row['reminder_settings'] else [],
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                task_id=row['task_id'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                cancelled_at=row['cancelled_at']
            )
            
            # Проверяем права доступа
            if await self._can_access_event(event, user_id):
                events.append(event)

        return events

    async def get_chat_events(self, chat_id: str, start_date: datetime, 
                            end_date: datetime) -> List[CalendarEvent]:
        """Получение событий чата"""
        sql_query = """
            SELECT id, title, description, start_time, end_time, timezone,
                   creator_id, attendees, event_type, privacy, status,
                   location, video_call_url, recurrence_pattern, recurrence_end,
                   reminder_settings, chat_id, group_id, project_id, task_id,
                   metadata, created_at, updated_at, cancelled_at
            FROM calendar_events
            WHERE chat_id = $1 AND start_time >= $2 AND end_time <= $3
            ORDER BY start_time
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, chat_id, start_date, end_date)

        events = []
        for row in rows:
            event = CalendarEvent(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                start_time=row['start_time'],
                end_time=row['end_time'],
                timezone=row['timezone'],
                creator_id=row['creator_id'],
                attendees=row['attendees'] or [],
                event_type=EventType(row['event_type']),
                privacy=EventPrivacy(row['privacy']),
                status=EventStatus(row['status']),
                location=row['location'],
                video_call_url=row['video_call_url'],
                recurrence_pattern=RecurrencePattern(row['recurrence_pattern']) if row['recurrence_pattern'] else None,
                recurrence_end=row['recurrence_end'],
                reminder_settings=json.loads(row['reminder_settings']) if row['reminder_settings'] else [],
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                task_id=row['task_id'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                cancelled_at=row['cancelled_at']
            )
            events.append(event)

        return events

    async def _can_access_event(self, event: CalendarEvent, user_id: Optional[int]) -> bool:
        """Проверка прав доступа к событию"""
        if event.privacy == EventPrivacy.PUBLIC:
            return True

        if not user_id:
            return False

        if event.creator_id == user_id:
            return True

        if user_id in event.attendees:
            return True

        if event.privacy == EventPrivacy.FRIENDS_ONLY:
            return await self._are_friends(event.creator_id, user_id)

        if event.privacy == EventPrivacy.GROUP_MEMBERS and event.group_id:
            return await self._is_group_member(user_id, event.group_id)

        return False

    async def _can_create_event(self, event: CalendarEvent, user_id: int) -> bool:
        """Проверка прав на создание события"""
        # Проверяем, является ли пользователь участником чата/группы
        if event.chat_id:
            return await self._can_access_chat(event.chat_id, user_id)
        elif event.group_id:
            return await self._is_group_member(user_id, event.group_id)
        elif event.project_id:
            return await self._is_project_member(user_id, event.project_id)
        else:
            # Личное событие
            return event.creator_id == user_id

    async def _can_update_event(self, event: CalendarEvent, user_id: int) -> bool:
        """Проверка прав на обновление события"""
        # Только создатель может обновлять событие
        return event.creator_id == user_id

    async def _can_delete_event(self, event: CalendarEvent, user_id: int) -> bool:
        """Проверка прав на удаление события"""
        # Только создатель может удалять событие
        return event.creator_id == user_id

    async def _can_modify_attendees(self, event: CalendarEvent, user_id: int) -> bool:
        """Проверка прав на изменение участников"""
        # Создатель события или администратор чата/группы
        if event.creator_id == user_id:
            return True

        if event.chat_id:
            return await self._is_chat_admin(event.chat_id, user_id)

        if event.group_id:
            return await self._is_group_admin(event.group_id, user_id)

        if event.project_id:
            return await self._is_project_admin(user_id, event.project_id)

        return False

    async def _has_time_conflict(self, event: CalendarEvent) -> bool:
        """Проверка конфликта по времени"""
        # Проверяем, есть ли у участников другие события в это время
        for attendee_id in event.attendees:
            conflicts = await self._get_conflicting_events(attendee_id, event.start_time, event.end_time)
            if conflicts:
                return True

        return False

    async def _get_conflicting_events(self, user_id: int, start_time: datetime, end_time: datetime) -> List[CalendarEvent]:
        """Получение конфликтующих событий пользователя"""
        sql_query = """
            SELECT id, title, start_time, end_time
            FROM calendar_events
            WHERE $1 = ANY(attendees)
              AND (
                  (start_time <= $2 AND end_time >= $2) OR
                  (start_time <= $3 AND end_time >= $3) OR
                  (start_time >= $2 AND end_time <= $3)
              )
              AND status != 'cancelled'
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, user_id, start_time, end_time)

        conflicting_events = []
        for row in rows:
            event = CalendarEvent(
                id=row['id'],
                title=row['title'],
                start_time=row['start_time'],
                end_time=row['end_time'],
                # Инициализируем минимально необходимые поля
                creator_id=-1,  # Заглушка
                event_type=EventType.CUSTOM,
                privacy=EventPrivacy.PRIVATE,
                status=EventStatus.SCHEDULED
            )
            conflicting_events.append(event)

        return conflicting_events

    async def _add_attendees_to_event(self, event_id: str, attendee_ids: List[int], added_by: int):
        """Добавление нескольких участников к событию"""
        for attendee_id in attendee_ids:
            await self._add_attendee_to_db(event_id, attendee_id)

    async def _add_attendee_to_db(self, event_id: str, user_id: int):
        """Добавление участника в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO event_attendees (event_id, user_id, status, created_at)
                VALUES ($1, $2, 'needs_action', $3)
                ON CONFLICT (event_id, user_id) DO NOTHING
                """,
                event_id, user_id, datetime.utcnow()
            )

    async def _remove_attendees_from_event(self, event_id: str):
        """Удаление всех участников события"""
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM event_attendees WHERE event_id = $1", event_id)

    async def _remove_attendee_from_db(self, event_id: str, user_id: int):
        """Удаление участника из базы данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM event_attendees WHERE event_id = $1 AND user_id = $2",
                event_id, user_id
            )

    async def _update_attendee_status(self, event_id: str, user_id: int, status: str):
        """Обновление статуса участника"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE event_attendees SET status = $3, updated_at = $4
                WHERE event_id = $1 AND user_id = $2
                """,
                event_id, user_id, status, datetime.utcnow()
            )

    async def _create_reminders_for_event(self, event: CalendarEvent):
        """Создание напоминаний для события"""
        for attendee_id in event.attendees:
            await self._create_reminders_for_user(event, attendee_id)

    async def _create_reminders_for_user(self, event: CalendarEvent, user_id: int):
        """Создание напоминаний для конкретного пользователя"""
        for reminder_setting in event.reminder_settings:
            reminder_type = reminder_setting.get('type')
            minutes_before = reminder_setting.get('minutes_before', 15)

            # Вычисляем время напоминания
            reminder_time = event.start_time - timedelta(minutes=minutes_before)

            # Проверяем, не прошло ли время напоминания
            if reminder_time <= datetime.utcnow():
                # Отправляем напоминание немедленно
                await self._send_reminder(event, user_id, reminder_type)
            else:
                # Планируем напоминание
                await self._schedule_reminder(event, user_id, reminder_type, reminder_time)

    async def _schedule_reminder(self, event: CalendarEvent, user_id: int, 
                               reminder_type: ReminderType, reminder_time: datetime):
        """Планирование напоминания"""
        reminder_id = str(uuid.uuid4())

        reminder = EventReminder(
            id=reminder_id,
            event_id=event.id,
            user_id=user_id,
            reminder_type=reminder_type,
            minutes_before=(event.start_time - reminder_time).total_seconds() / 60,
            created_at=datetime.utcnow()
        )

        # Сохраняем в базу данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO event_reminders (id, event_id, user_id, reminder_type, minutes_before, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                reminder.id, reminder.event_id, reminder.user_id,
                reminder.reminder_type.value, reminder.minutes_before, reminder.created_at
            )

        # Добавляем в очередь планировщика
        await redis_client.zadd(
            "event_reminders_queue",
            {f"{reminder.id}:{reminder.user_id}": reminder_time.timestamp()}
        )

    async def _send_reminder(self, event: CalendarEvent, user_id: int, reminder_type: ReminderType):
        """Отправка напоминания пользователю"""
        reminder_notification = {
            'type': 'event_reminder',
            'event': {
                'id': event.id,
                'title': event.title,
                'start_time': event.start_time.isoformat(),
                'location': event.location,
                'attendees_count': len(event.attendees)
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        if reminder_type == ReminderType.PUSH:
            await self._send_push_notification(user_id, reminder_notification)
        elif reminder_type == ReminderType.EMAIL:
            await self._send_email_notification(user_id, reminder_notification)
        elif reminder_type == ReminderType.IN_APP:
            await self._send_in_app_notification(user_id, reminder_notification)
        elif reminder_type == ReminderType.SMS:
            await self._send_sms_notification(user_id, reminder_notification)

    async def _remove_reminders_for_event(self, event_id: str):
        """Удаление всех напоминаний для события"""
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM event_reminders WHERE event_id = $1", event_id)

    async def _remove_reminders_for_user(self, event_id: str, user_id: int):
        """Удаление напоминаний для конкретного пользователя и события"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM event_reminders WHERE event_id = $1 AND user_id = $2",
                event_id, user_id
            )

    async def _cache_event(self, event: CalendarEvent):
        """Кэширование события"""
        await redis_client.setex(f"event:{event.id}", 300, event.model_dump_json())

    async def _get_cached_event(self, event_id: str) -> Optional[CalendarEvent]:
        """Получение события из кэша"""
        cached = await redis_client.get(f"event:{event_id}")
        if cached:
            return CalendarEvent(**json.loads(cached))
        return None

    async def _uncache_event(self, event_id: str):
        """Удаление события из кэша"""
        await redis_client.delete(f"event:{event_id}")

    async def _notify_event_created(self, event: CalendarEvent):
        """Уведомление о создании события"""
        notification = {
            'type': 'event_created',
            'event': self._event_to_dict(event),
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление участникам
        for attendee_id in event.attendees:
            await self._send_notification_to_user(attendee_id, notification)

        # Если событие связано с чатом, отправляем в чат
        if event.chat_id:
            await self._send_notification_to_chat(event.chat_id, notification)

    async def _notify_event_updated(self, event: CalendarEvent):
        """Уведомление об обновлении события"""
        notification = {
            'type': 'event_updated',
            'event': self._event_to_dict(event),
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление всем участникам
        all_relevant_users = set(event.attendees + [event.creator_id])
        for user_id in all_relevant_users:
            await self._send_notification_to_user(user_id, notification)

        # Если событие связано с чатом, отправляем в чат
        if event.chat_id:
            await self._send_notification_to_chat(event.chat_id, notification)

    async def _notify_event_deleted(self, event: CalendarEvent):
        """Уведомление об удалении события"""
        notification = {
            'type': 'event_deleted',
            'event_id': event.id,
            'event_title': event.title,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление всем участникам
        all_relevant_users = set(event.attendees + [event.creator_id])
        for user_id in all_relevant_users:
            await self._send_notification_to_user(user_id, notification)

        # Если событие связано с чатом, отправляем в чат
        if event.chat_id:
            await self._send_notification_to_chat(event.chat_id, notification)

    async def _notify_attendee_added(self, event: CalendarEvent, user_id: int):
        """Уведомление участника о добавлении к событию"""
        notification = {
            'type': 'attendee_added',
            'event': self._event_to_dict(event),
            'timestamp': datetime.utcnow().isoformat()
        }

        await self._send_notification_to_user(user_id, notification)

    async def _notify_attendee_removed(self, event: CalendarEvent, user_id: int):
        """Уведомление участника об удалении из события"""
        notification = {
            'type': 'attendee_removed',
            'event': self._event_to_dict(event),
            'timestamp': datetime.utcnow().isoformat()
        }

        await self._send_notification_to_user(user_id, notification)

    async def _notify_response_to_creator(self, event: CalendarEvent, user_id: int, response: str):
        """Уведомление создателя о ответе участника"""
        notification = {
            'type': 'attendee_responded',
            'event_id': event.id,
            'event_title': event.title,
            'user_id': user_id,
            'response': response,
            'timestamp': datetime.utcnow().isoformat()
        }

        await self._send_notification_to_user(event.creator_id, notification)

    def _event_to_dict(self, event: CalendarEvent) -> Dict[str, Any]:
        """Конвертация события в словарь для уведомлений"""
        return {
            'id': event.id,
            'title': event.title,
            'description': event.description,
            'start_time': event.start_time.isoformat(),
            'end_time': event.end_time.isoformat(),
            'timezone': event.timezone,
            'creator_id': event.creator_id,
            'attendee_count': len(event.attendees),
            'event_type': event.event_type.value,
            'privacy': event.privacy.value,
            'status': event.status.value,
            'location': event.location,
            'video_call_url': event.video_call_url,
            'recurrence_pattern': event.recurrence_pattern.value if event.recurrence_pattern else None,
            'created_at': event.created_at.isoformat() if event.created_at else None,
            'updated_at': event.updated_at.isoformat() if event.updated_at else None
        }

    async def _send_notification_to_user(self, user_id: int, notification: Dict[str, Any]):
        """Отправка уведомления пользователю"""
        channel = f"user:{user_id}:calendar"
        await redis_client.publish(channel, json.dumps(notification))

    async def _send_notification_to_chat(self, chat_id: str, notification: Dict[str, Any]):
        """Отправка уведомления в чат"""
        channel = f"chat:{chat_id}:calendar"
        await redis_client.publish(channel, json.dumps(notification))

    async def _send_push_notification(self, user_id: int, notification: Dict[str, Any]):
        """Отправка push-уведомления"""
        # В реальной системе здесь будет интеграция с push-сервисом
        import logging
        logging.info(f"Push notification sent to user {user_id}: {notification.get('title', 'Calendar Event')}")
        return True

    async def _send_email_notification(self, user_id: int, notification: Dict[str, Any]):
        """Отправка email-уведомления"""
        # В реальной системе здесь будет интеграция с email-сервисом
        import logging
        logging.info(f"Email notification sent to user {user_id}: {notification.get('title', 'Calendar Event')}")
        return True

    async def _send_in_app_notification(self, user_id: int, notification: Dict[str, Any]):
        """Отправка in-app уведомления"""
        # Отправляем через WebSocket или Redis
        await self._send_notification_to_user(user_id, notification)

    async def _send_sms_notification(self, user_id: int, notification: Dict[str, Any]):
        """Отправка SMS-уведомления"""
        # В реальной системе здесь будет интеграция с SMS-сервисом
        import logging
        logging.info(f"SMS notification sent to user {user_id}: {notification.get('title', 'Calendar Event')}")
        return True

    async def _log_activity(self, event_id: str, user_id: int, action: str, details: Dict[str, Any]):
        """Логирование активности по событию"""
        activity_id = str(uuid.uuid4())
        activity = {
            'id': activity_id,
            'event_id': event_id,
            'user_id': user_id,
            'action': action,
            'details': details,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Сохраняем в базу данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO event_activities (id, event_id, user_id, action, details, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                activity_id, event_id, user_id, action, json.dumps(details), datetime.utcnow()
            )

    async def _are_friends(self, user1_id: int, user2_id: int) -> bool:
        """Проверка, являются ли пользователи друзьями"""
        # В реальной системе здесь будет проверка в таблице друзей
        return False

    async def _is_group_member(self, user_id: int, group_id: str) -> bool:
        """Проверка, является ли пользователь членом группы"""
        # В реальной системе здесь будет проверка в таблице участников группы
        return False

    async def _is_project_member(self, user_id: int, project_id: str) -> bool:
        """Проверка, является ли пользователь участником проекта"""
        # В реальной системе здесь будет проверка в таблице участников проекта
        return False

    async def _is_chat_admin(self, chat_id: str, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором чата"""
        # В реальной системе здесь будет проверка прав в чате
        return False

    async def _is_group_admin(self, group_id: str, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором группы"""
        # В реальной системе здесь будет проверка прав в группе
        return False

    async def _is_project_admin(self, user_id: int, project_id: str) -> bool:
        """Проверка, является ли пользователь администратором проекта"""
        # В реальной системе здесь будет проверка прав в проекте
        return False

    async def _can_access_chat(self, chat_id: str, user_id: int) -> bool:
        """Проверка прав доступа к чату"""
        # В реальной системе здесь будет проверка участия в чате
        return False

    def requires_moderation(self, content_type: ContentType) -> bool:
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
calendar_service = CalendarService()
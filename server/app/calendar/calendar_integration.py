# server/app/calendar/calendar_integration.py
import asyncio
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import uuid
from datetime import datetime, timedelta
import asyncpg
import icalendar
from icalendar import Calendar, Event as CalendarEvent
import recurring_ical_events
import pytz
from dateutil import parser

class EventType(Enum):
    MEETING = "meeting"
    DEADLINE = "deadline"
    REMINDER = "reminder"
    BIRTHDAY = "birthday"
    ANNIVERSARY = "anniversary"
    CUSTOM = "custom"

class EventPrivacy(Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    CONFIDENTIAL = "confidential"

class RecurrencePattern(Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    WEEKLY_ON_DAYS = "weekly_on_days"
    MONTHLY_BY_DAY = "monthly_by_day"

@dataclass
class CalendarEvent:
    id: str
    title: str
    description: str
    start_time: datetime
    end_time: datetime
    timezone: str
    creator_id: int
    attendees: List[int]
    event_type: EventType
    privacy: EventPrivacy
    location: Optional[str] = None
    recurrence_pattern: Optional[RecurrencePattern] = None
    recurrence_end: Optional[datetime] = None
    reminder_minutes: Optional[int] = None
    created_at: datetime = None
    updated_at: datetime = None
    chat_id: Optional[str] = None
    related_task_id: Optional[str] = None
    color: Optional[str] = None
    is_allday: bool = False

class CalendarIntegration:
    """Интеграция календаря с мессенджером"""
    
    def __init__(self, db_pool, redis_client):
        self.db_pool = db_pool
        self.redis = redis_client
        self.timezone = pytz.UTC
        self.reminder_queue = []
    
    async def create_event(self, title: str, description: str, start_time: datetime, 
                          end_time: datetime, creator_id: int, 
                          attendees: List[int] = None,
                          event_type: EventType = EventType.CUSTOM,
                          privacy: EventPrivacy = EventPrivacy.PRIVATE,
                          location: Optional[str] = None,
                          chat_id: Optional[str] = None,
                          reminder_minutes: Optional[int] = 15,
                          recurrence_pattern: Optional[RecurrencePattern] = None,
                          recurrence_end: Optional[datetime] = None) -> str:
        """Создание нового события"""
        event_id = str(uuid.uuid4())
        
        event = CalendarEvent(
            id=event_id,
            title=title,
            description=description,
            start_time=start_time,
            end_time=end_time,
            timezone=str(self.timezone),
            creator_id=creator_id,
            attendees=attendees or [],
            event_type=event_type,
            privacy=privacy,
            location=location,
            recurrence_pattern=recurrence_pattern,
            recurrence_end=recurrence_end,
            reminder_minutes=reminder_minutes,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            chat_id=chat_id
        )
        
        # Сохраняем событие в базу данных
        await self._save_event_to_db(event)
        
        # Уведомляем участников
        await self._notify_attendees(event, "created")
        
        # Добавляем напоминание
        if reminder_minutes:
            await self._schedule_reminder(event)
        
        # Если событие связано с чатом, уведомляем чат
        if chat_id:
            await self._notify_chat(chat_id, event, "created")
        
        return event_id
    
    async def _save_event_to_db(self, event: CalendarEvent):
        """Сохранение события в базу данных"""
        async with self.db_pool.acquire() as conn:
            # Сохраняем основную информацию о событии
            await conn.execute(
                """
                INSERT INTO calendar_events (
                    id, title, description, start_time, end_time, timezone,
                    creator_id, event_type, privacy, location, 
                    recurrence_pattern, recurrence_end, reminder_minutes,
                    created_at, updated_at, chat_id
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                """,
                event.id, event.title, event.description, event.start_time,
                event.end_time, event.timezone, event.creator_id,
                event.event_type.value, event.privacy.value, event.location,
                event.recurrence_pattern.value if event.recurrence_pattern else None,
                event.recurrence_end, event.reminder_minutes,
                event.created_at, event.updated_at, event.chat_id
            )
            
            # Сохраняем участников
            for attendee_id in event.attendees:
                await conn.execute(
                    "INSERT INTO event_attendees (event_id, user_id) VALUES ($1, $2)",
                    event.id, attendee_id
                )
    
    async def get_event(self, event_id: str) -> Optional[CalendarEvent]:
        """Получение события по ID"""
        async with self.db_pool.acquire() as conn:
            # Получаем основную информацию о событии
            event_row = await conn.fetchrow(
                """
                SELECT id, title, description, start_time, end_time, timezone,
                       creator_id, event_type, privacy, location,
                       recurrence_pattern, recurrence_end, reminder_minutes,
                       created_at, updated_at, chat_id
                FROM calendar_events WHERE id = $1
                """,
                event_id
            )
            
            if not event_row:
                return None
            
            # Получаем участников
            attendees_rows = await conn.fetch(
                "SELECT user_id FROM event_attendees WHERE event_id = $1",
                event_id
            )
            attendees = [row['user_id'] for row in attendees_rows]
            
            event = CalendarEvent(
                id=event_row['id'],
                title=event_row['title'],
                description=event_row['description'],
                start_time=event_row['start_time'],
                end_time=event_row['end_time'],
                timezone=event_row['timezone'],
                creator_id=event_row['creator_id'],
                attendees=attendees,
                event_type=EventType(event_row['event_type']),
                privacy=EventPrivacy(event_row['privacy']),
                location=event_row['location'],
                recurrence_pattern=RecurrencePattern(event_row['recurrence_pattern']) if event_row['recurrence_pattern'] else None,
                recurrence_end=event_row['recurrence_end'],
                reminder_minutes=event_row['reminder_minutes'],
                created_at=event_row['created_at'],
                updated_at=event_row['updated_at'],
                chat_id=event_row['chat_id']
            )
            
            return event
    
    async def update_event(self, event_id: str, **updates) -> bool:
        """Обновление события"""
        event = await self.get_event(event_id)
        if not event:
            return False
        
        # Обновляем поля события
        for field, value in updates.items():
            if hasattr(event, field):
                if field == 'event_type' and isinstance(value, str):
                    setattr(event, field, EventType(value))
                elif field == 'privacy' and isinstance(value, str):
                    setattr(event, field, EventPrivacy(value))
                elif field == 'recurrence_pattern' and isinstance(value, str):
                    setattr(event, field, RecurrencePattern(value) if value else None)
                else:
                    setattr(event, field, value)
        
        event.updated_at = datetime.utcnow()
        
        # Обновляем в базе данных
        await self._update_event_in_db(event)
        
        # Уведомляем участников об изменении
        await self._notify_attendees(event, "updated")
        
        # Если событие связано с чатом, уведомляем чат
        if event.chat_id:
            await self._notify_chat(event.chat_id, event, "updated")
        
        return True
    
    async def _update_event_in_db(self, event: CalendarEvent):
        """Обновление события в базе данных"""
        async with self.db_pool.acquire() as conn:
            # Обновляем основную информацию
            await conn.execute(
                """
                UPDATE calendar_events SET
                    title = $2, description = $3, start_time = $4, end_time = $5,
                    timezone = $6, event_type = $7, privacy = $8, location = $9,
                    recurrence_pattern = $10, recurrence_end = $11, reminder_minutes = $12,
                    updated_at = $13, chat_id = $14
                WHERE id = $1
                """,
                event.id, event.title, event.description, event.start_time,
                event.end_time, event.timezone, event.event_type.value,
                event.privacy.value, event.location,
                event.recurrence_pattern.value if event.recurrence_pattern else None,
                event.recurrence_end, event.reminder_minutes,
                event.updated_at, event.chat_id
            )
            
            # Удаляем старых участников
            await conn.execute("DELETE FROM event_attendees WHERE event_id = $1", event.id)
            
            # Добавляем новых участников
            for attendee_id in event.attendees:
                await conn.execute(
                    "INSERT INTO event_attendees (event_id, user_id) VALUES ($1, $2)",
                    event.id, attendee_id
                )
    
    async def delete_event(self, event_id: str) -> bool:
        """Удаление события"""
        event = await self.get_event(event_id)
        if not event:
            return False
        
        # Удаляем из базы данных
        async with self.db_pool.acquire() as conn:
            await conn.execute("DELETE FROM event_attendees WHERE event_id = $1", event_id)
            await conn.execute("DELETE FROM calendar_events WHERE id = $1", event_id)
        
        # Уведомляем участников об удалении
        await self._notify_attendees(event, "deleted")
        
        # Если событие связано с чатом, уведомляем чат
        if event.chat_id:
            await self._notify_chat(event.chat_id, event, "deleted")
        
        return True
    
    async def get_user_events(self, user_id: int, start_date: datetime, 
                             end_date: datetime, event_type: Optional[EventType] = None) -> List[CalendarEvent]:
        """Получение событий пользователя в определенном диапазоне"""
        conditions = [
            "(ce.creator_id = $1 OR ea.user_id = $1)",
            "ce.start_time >= $2",
            "ce.end_time <= $3"
        ]
        params = [user_id, start_date, end_date]
        param_idx = 4
        
        if event_type:
            conditions.append(f"ce.event_type = ${param_idx}")
            params.append(event_type.value)
            param_idx += 1
        
        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT ce.id, ce.title, ce.description, ce.start_time, ce.end_time, ce.timezone,
                   ce.creator_id, ce.event_type, ce.privacy, ce.location,
                   ce.recurrence_pattern, ce.recurrence_end, ce.reminder_minutes,
                   ce.created_at, ce.updated_at, ce.chat_id
            FROM calendar_events ce
            LEFT JOIN event_attendees ea ON ce.id = ea.event_id
            WHERE {where_clause}
            ORDER BY ce.start_time
        """
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        events = []
        for row in rows:
            # Получаем участников для каждого события
            attendees_rows = await conn.fetch(
                "SELECT user_id FROM event_attendees WHERE event_id = $1",
                row['id']
            )
            attendees = [att_row['user_id'] for att_row in attendees_rows]
            
            event = CalendarEvent(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                start_time=row['start_time'],
                end_time=row['end_time'],
                timezone=row['timezone'],
                creator_id=row['creator_id'],
                attendees=attendees,
                event_type=EventType(row['event_type']),
                privacy=EventPrivacy(row['privacy']),
                location=row['location'],
                recurrence_pattern=RecurrencePattern(row['recurrence_pattern']) if row['recurrence_pattern'] else None,
                recurrence_end=row['recurrence_end'],
                reminder_minutes=row['reminder_minutes'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                chat_id=row['chat_id']
            )
            events.append(event)
        
        return events
    
    async def get_chat_events(self, chat_id: str, start_date: datetime, 
                             end_date: datetime) -> List[CalendarEvent]:
        """Получение событий, связанных с чатом"""
        query = """
            SELECT ce.id, ce.title, ce.description, ce.start_time, ce.end_time, ce.timezone,
                   ce.creator_id, ce.event_type, ce.privacy, ce.location,
                   ce.recurrence_pattern, ce.recurrence_end, ce.reminder_minutes,
                   ce.created_at, ce.updated_at, ce.chat_id
            FROM calendar_events ce
            WHERE ce.chat_id = $1
                AND ce.start_time >= $2
                AND ce.end_time <= $3
            ORDER BY ce.start_time
        """
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, chat_id, start_date, end_date)
        
        events = []
        for row in rows:
            # Получаем участников
            attendees_rows = await conn.fetch(
                "SELECT user_id FROM event_attendees WHERE event_id = $1",
                row['id']
            )
            attendees = [att_row['user_id'] for att_row in attendees_rows]
            
            event = CalendarEvent(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                start_time=row['start_time'],
                end_time=row['end_time'],
                timezone=row['timezone'],
                creator_id=row['creator_id'],
                attendees=attendees,
                event_type=EventType(row['event_type']),
                privacy=EventPrivacy(row['privacy']),
                location=row['location'],
                recurrence_pattern=RecurrencePattern(row['recurrence_pattern']) if row['recurrence_pattern'] else None,
                recurrence_end=row['recurrence_end'],
                reminder_minutes=row['reminder_minutes'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                chat_id=row['chat_id']
            )
            events.append(event)
        
        return events
    
    async def invite_attendees(self, event_id: str, attendee_ids: List[int]) -> bool:
        """Приглашение участников на событие"""
        event = await self.get_event(event_id)
        if not event:
            return False
        
        # Добавляем новых участников
        for attendee_id in attendee_ids:
            if attendee_id not in event.attendees:
                event.attendees.append(attendee_id)
        
        # Обновляем в базе данных
        async with self.db_pool.acquire() as conn:
            for attendee_id in attendee_ids:
                await conn.execute(
                    """
                    INSERT INTO event_attendees (event_id, user_id)
                    VALUES ($1, $2)
                    ON CONFLICT (event_id, user_id) DO NOTHING
                    """,
                    event_id, attendee_id
                )
        
        # Уведомляем новых участников
        for attendee_id in attendee_ids:
            await self._notify_user_invitation(attendee_id, event)
        
        return True
    
    async def rsvp_event(self, event_id: str, user_id: int, status: str) -> bool:
        """Ответ на приглашение (RSVP)"""
        event = await self.get_event(event_id)
        if not event or user_id not in event.attendees:
            return False
        
        # В реальной системе здесь будет обновление статуса участника
        # Пока просто уведомляем о статусе
        await self._notify_rsvp_status(event, user_id, status)
        
        return True
    
    async def export_calendar_to_ics(self, user_id: int, start_date: datetime, 
                                    end_date: datetime) -> str:
        """Экспорт календаря пользователя в формат ICS"""
        events = await self.get_user_events(user_id, start_date, end_date)
        
        cal = Calendar()
        cal.add('prodid', '-//Messenger Calendar//mxm.dk//')
        cal.add('version', '2.0')
        
        for event in events:
            cal_event = CalendarEvent()
            cal_event.add('summary', event.title)
            cal_event.add('description', event.description)
            cal_event.add('dtstart', event.start_time)
            cal_event.add('dtend', event.end_time)
            cal_event.add('dtstamp', datetime.utcnow())
            cal_event.add('uid', event.id)
            cal_event.add('created', event.created_at)
            cal_event.add('last-modified', event.updated_at)
            
            if event.location:
                cal_event.add('location', event.location)
            
            # Добавляем участников
            for attendee_id in event.attendees:
                # В реальной системе здесь будет получение email пользователя
                cal_event.add('attendee', f'mailto:user{attendee_id}@example.com')
            
            cal.add_component(cal_event)
        
        return cal.to_ical().decode('utf-8')
    
    async def import_calendar_from_ics(self, user_id: int, ics_content: str) -> List[str]:
        """Импорт событий из ICS файла"""
        calendar = icalendar.Calendar.from_ical(ics_content)
        imported_event_ids = []
        
        for component in calendar.walk():
            if component.name == "VEVENT":
                event = CalendarEvent(
                    id=str(uuid.uuid4()),
                    title=str(component.get('summary', '')),
                    description=str(component.get('description', '')),
                    start_time=component.get('dtstart').dt,
                    end_time=component.get('dtend').dt if component.get('dtend') else component.get('dtstart').dt + timedelta(hours=1),
                    timezone=str(component.get('dtstart').dt.tzinfo) if component.get('dtstart').dt.tzinfo else 'UTC',
                    creator_id=user_id,
                    attendees=[user_id],  # Импортер как участник
                    event_type=EventType.CUSTOM,
                    privacy=EventPrivacy.PRIVATE,
                    location=str(component.get('location', '')) if component.get('location') else None,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                
                # Сохраняем событие
                await self._save_event_to_db(event)
                imported_event_ids.append(event.id)
        
        return imported_event_ids
    
    async def _notify_attendees(self, event: CalendarEvent, action: str):
        """Уведомление участников о событии"""
        notification = {
            'type': 'calendar_event',
            'action': action,
            'event': self._event_to_dict(event),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Уведомляем всех участников
        for attendee_id in event.attendees:
            await self._send_notification_to_user(attendee_id, notification)
    
    async def _notify_user_invitation(self, user_id: int, event: CalendarEvent):
        """Уведомление пользователя о приглашении"""
        notification = {
            'type': 'calendar_invitation',
            'event': self._event_to_dict(event),
            'inviter_id': event.creator_id,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await self._send_notification_to_user(user_id, notification)
    
    async def _notify_rsvp_status(self, event: CalendarEvent, user_id: int, status: str):
        """Уведомление о статусе RSVP"""
        notification = {
            'type': 'rsvp_status',
            'event_id': event.id,
            'user_id': user_id,
            'status': status,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Уведомляем организатора
        await self._send_notification_to_user(event.creator_id, notification)
        
        # Уведомляем других участников
        for attendee_id in event.attendees:
            if attendee_id != event.creator_id and attendee_id != user_id:
                await self._send_notification_to_user(attendee_id, notification)
    
    async def _notify_chat(self, chat_id: str, event: CalendarEvent, action: str):
        """Уведомление чата о событии"""
        notification = {
            'type': 'chat_calendar_event',
            'action': action,
            'event': self._event_to_dict(event),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await self._send_notification_to_chat(chat_id, notification)
    
    async def _send_notification_to_user(self, user_id: int, notification: Dict[str, Any]):
        """Отправка уведомления пользователю"""
        channel = f"user:{user_id}:calendar"
        await self.redis.publish(channel, json.dumps(notification))
    
    async def _send_notification_to_chat(self, chat_id: str, notification: Dict[str, Any]):
        """Отправка уведомления в чат"""
        channel = f"chat:{chat_id}:calendar"
        await self.redis.publish(channel, json.dumps(notification))
    
    def _event_to_dict(self, event: CalendarEvent) -> Dict[str, Any]:
        """Конвертация события в словарь для отправки"""
        return {
            'id': event.id,
            'title': event.title,
            'description': event.description,
            'start_time': event.start_time.isoformat(),
            'end_time': event.end_time.isoformat(),
            'timezone': event.timezone,
            'creator_id': event.creator_id,
            'attendees': event.attendees,
            'event_type': event.event_type.value,
            'privacy': event.privacy.value,
            'location': event.location,
            'recurrence_pattern': event.recurrence_pattern.value if event.recurrence_pattern else None,
            'recurrence_end': event.recurrence_end.isoformat() if event.recurrence_end else None,
            'reminder_minutes': event.reminder_minutes,
            'created_at': event.created_at.isoformat() if event.created_at else None,
            'updated_at': event.updated_at.isoformat() if event.updated_at else None,
            'chat_id': event.chat_id,
            'is_allday': event.is_allday
        }
    
    async def _schedule_reminder(self, event: CalendarEvent):
        """Планирование напоминания"""
        if not event.reminder_minutes:
            return
        
        reminder_time = event.start_time - timedelta(minutes=event.reminder_minutes)
        time_to_reminder = (reminder_time - datetime.utcnow()).total_seconds()
        
        if time_to_reminder > 0:
            # Запускаем асинхронную задачу для напоминания
            asyncio.create_task(self._send_reminder(event, time_to_reminder))
    
    async def _send_reminder(self, event: CalendarEvent, delay: float):
        """Отправка напоминания после задержки"""
        await asyncio.sleep(delay)
        
        reminder_notification = {
            'type': 'event_reminder',
            'event': self._event_to_dict(event),
            'minutes_before': event.reminder_minutes,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Отправляем напоминание всем участникам
        for attendee_id in event.attendees:
            await self._send_notification_to_user(attendee_id, reminder_notification)

# Глобальный экземпляр для использования в приложении
calendar_integration = CalendarIntegration(None, None)  # Будет инициализирован в основном приложении
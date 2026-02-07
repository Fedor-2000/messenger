# Chat Microservice
# File: services/chat_microservice/main.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid

import asyncpg
import redis.asyncio as redis
from aiohttp import web
import aiohttp
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class MessageType(Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FILE = "file"
    SYSTEM = "system"
    NOTIFICATION = "notification"
    REACTION = "reaction"
    EDIT = "edit"
    DELETE = "delete"

class ChatType(Enum):
    PRIVATE = "private"
    GROUP = "group"
    CHANNEL = "channel"
    BROADCAST = "broadcast"

class MessageStatus(Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"

class ChatMemberRole(Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MODERATOR = "moderator"
    MEMBER = "member"
    GUEST = "guest"

class ChatMessage(BaseModel):
    id: str
    chat_id: str
    sender_id: int
    content: str
    message_type: MessageType
    timestamp: datetime = None
    edited_at: Optional[datetime] = None
    is_edited: bool = False
    reply_to: Optional[str] = None  # ID сообщения, на которое идет ответ
    mentions: List[int] = []  # ID упомянутых пользователей
    reactions: Dict[str, List[int]] = {}  # {'like': [user_id1, user_id2], 'love': [user_id3]}
    attachments: List[Dict[str, str]] = []  # [{'id': 'file_id', 'name': 'file_name', 'type': 'image'}]
    metadata: Optional[Dict[str, Any]] = None
    status: MessageStatus = MessageStatus.SENT

class ChatRoom(BaseModel):
    id: str
    name: Optional[str] = None
    type: ChatType
    creator_id: int
    members: List[Dict[str, Any]] = []  # [{'user_id': id, 'role': role, 'joined_at': timestamp}]
    created_at: datetime = None
    updated_at: datetime = None
    last_message: Optional[str] = None
    last_activity: Optional[datetime] = None
    unread_counts: Dict[int, int] = {}  # {user_id: count}
    is_archived: bool = False
    is_encrypted: bool = False
    encryption_key: Optional[str] = None

class ChatService:
    def __init__(self):
        self.max_message_length = 10000  # 10,000 символов
        self.max_file_attachments = 10
        self.max_group_members = 1000
        self.message_retention_days = 365  # Хранить сообщения 1 год

    async def create_chat(self, chat_type: ChatType, creator_id: int,
                         name: Optional[str] = None,
                         participants: Optional[List[int]] = None,
                         is_encrypted: bool = False) -> Optional[str]:
        """Создание нового чата"""
        chat_id = str(uuid.uuid4())

        # Проверяем права на создание чата
        if not await self._can_create_chat(creator_id, chat_type):
            return None

        # Для группового чата проверяем ограничения
        if chat_type == ChatType.GROUP:
            if not participants or len(participants) < 2:
                return None
            if len(participants) > self.max_group_members:
                return None

        # Создаем комнату чата
        chat_room = ChatRoom(
            id=chat_id,
            name=name,
            type=chat_type,
            creator_id=creator_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            is_encrypted=is_encrypted
        )

        # Добавляем участников
        if participants:
            for user_id in participants:
                member_info = {
                    'user_id': user_id,
                    'role': ChatMemberRole.MEMBER.value if user_id != creator_id else ChatMemberRole.OWNER.value,
                    'joined_at': datetime.utcnow().isoformat()
                }
                chat_room.members.append(member_info)

        # Генерируем ключ шифрования, если чат зашифрован
        if is_encrypted:
            import secrets
            chat_room.encryption_key = secrets.token_urlsafe(32)

        # Сохраняем чат в базу данных
        await self._save_chat_to_db(chat_room)

        # Добавляем в кэш
        await self._cache_chat(chat_room)

        # Уведомляем участников
        await self._notify_chat_created(chat_room)

        # Создаем запись активности
        await self._log_activity(creator_id, "chat_created", {
            "chat_id": chat_id,
            "chat_type": chat_type.value,
            "participant_count": len(participants) if participants else 1
        })

        return chat_id

    async def _save_chat_to_db(self, chat: ChatRoom):
        """Сохранение чата в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chats (
                    id, name, type, creator_id, members, created_at, updated_at,
                    last_message, last_activity, unread_counts, is_archived,
                    is_encrypted, encryption_key
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """,
                chat.id, chat.name, chat.type.value, chat.creator_id,
                json.dumps(chat.members), chat.created_at, chat.updated_at,
                chat.last_message, chat.last_activity,
                json.dumps(chat.unread_counts), chat.is_archived,
                chat.is_encrypted, chat.encryption_key
            )

    async def send_message(self, chat_id: str, sender_id: int, content: str,
                          message_type: MessageType = MessageType.TEXT,
                          reply_to: Optional[str] = None,
                          mentions: Optional[List[int]] = None,
                          attachments: Optional[List[Dict[str, str]]] = None,
                          metadata: Optional[Dict] = None) -> Optional[str]:
        """Отправка сообщения в чат"""
        # Проверяем, существует ли чат
        chat = await self.get_chat(chat_id)
        if not chat:
            return None

        # Проверяем права на отправку сообщения
        if not await self._can_send_message(chat, sender_id):
            return None

        # Проверяем ограничения
        if message_type == MessageType.TEXT and len(content) > self.max_message_length:
            return None

        if attachments and len(attachments) > self.max_file_attachments:
            return None

        message_id = str(uuid.uuid4())

        message = ChatMessage(
            id=message_id,
            chat_id=chat_id,
            sender_id=sender_id,
            content=content,
            message_type=message_type,
            timestamp=datetime.utcnow(),
            reply_to=reply_to,
            mentions=mentions or [],
            attachments=attachments or [],
            metadata=metadata or {},
            status=MessageStatus.SENT
        )

        # Если чат зашифрован, шифруем сообщение
        if chat.is_encrypted and chat.encryption_key:
            message.content = await self._encrypt_message(message.content, chat.encryption_key)

        # Сохраняем сообщение в базу данных
        await self._save_message_to_db(message)

        # Обновляем информацию о чате
        await self._update_chat_last_message(chat_id, message)

        # Рассылка сообщения участникам чата
        await self._broadcast_message_to_chat(chat_id, message)

        # Обновляем счетчики непрочитанных сообщений
        await self._update_unread_counts(chat_id, sender_id)

        # Добавляем в кэш
        await self._cache_message(message)

        # Создаем запись активности
        await self._log_activity(sender_id, "message_sent", {
            "message_id": message_id,
            "chat_id": chat_id,
            "message_type": message_type.value,
            "content_length": len(content)
        })

        return message_id

    async def _save_message_to_db(self, message: ChatMessage):
        """Сохранение сообщения в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO messages (
                    id, chat_id, sender_id, content, message_type, timestamp,
                    edited_at, is_edited, reply_to, mentions, reactions,
                    attachments, metadata, status
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                """,
                message.id, message.chat_id, message.sender_id, message.content,
                message.message_type.value, message.timestamp, message.edited_at,
                message.is_edited, message.reply_to, message.mentions,
                json.dumps(message.reactions), json.dumps(message.attachments),
                json.dumps(message.metadata) if message.metadata else None,
                message.status.value
            )

    async def get_chat_messages(self, chat_id: str, user_id: int,
                               limit: int = 50, offset: int = 0,
                               since: Optional[datetime] = None) -> List[ChatMessage]:
        """Получение сообщений чата"""
        # Проверяем права доступа к чату
        if not await self._can_access_chat(chat_id, user_id):
            return []

        conditions = ["chat_id = $1"]
        params = [chat_id]
        param_idx = 2

        if since:
            conditions.append(f"timestamp >= ${param_idx}")
            params.append(since)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, chat_id, sender_id, content, message_type, timestamp,
                   edited_at, is_edited, reply_to, mentions, reactions,
                   attachments, metadata, status
            FROM messages
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        messages = []
        for row in rows:
            message = ChatMessage(
                id=row['id'],
                chat_id=row['chat_id'],
                sender_id=row['sender_id'],
                content=row['content'],
                message_type=MessageType(row['message_type']),
                timestamp=row['timestamp'],
                edited_at=row['edited_at'],
                is_edited=row['is_edited'],
                reply_to=row['reply_to'],
                mentions=row['mentions'] or [],
                reactions=json.loads(row['reactions']) if row['reactions'] else {},
                attachments=json.loads(row['attachments']) if row['attachments'] else [],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                status=MessageStatus(row['status'])
            )

            # Если чат зашифрован, расшифровываем сообщение
            chat = await self.get_chat(chat_id)
            if chat and chat.is_encrypted and chat.encryption_key:
                message.content = await self._decrypt_message(message.content, chat.encryption_key)

            messages.append(message)

        # Обновляем статус прочтения для пользователя
        await self._mark_messages_as_read(chat_id, user_id, [msg.id for msg in messages])

        return messages

    async def get_user_chats(self, user_id: int) -> List[ChatRoom]:
        """Получение чатов пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, type, creator_id, members, created_at, updated_at,
                       last_message, last_activity, unread_counts, is_archived,
                       is_encrypted
                FROM chats
                WHERE $1 = ANY(SELECT jsonb_array_elements_text(members->'user_id'::text))
                ORDER BY last_activity DESC
                """,
                user_id
            )

        chats = []
        for row in rows:
            chat = ChatRoom(
                id=row['id'],
                name=row['name'],
                type=ChatType(row['type']),
                creator_id=row['creator_id'],
                members=json.loads(row['members']) if row['members'] else [],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                last_message=row['last_message'],
                last_activity=row['last_activity'],
                unread_counts=json.loads(row['unread_counts']) if row['unread_counts'] else {},
                is_archived=row['is_archived'],
                is_encrypted=row['is_encrypted']
            )
            chats.append(chat)

        return chats

    async def add_reaction(self, message_id: str, user_id: int, 
                          reaction_type: str) -> bool:
        """Добавление реакции к сообщению"""
        message = await self.get_message(message_id)
        if not message:
            return False

        # Проверяем права на добавление реакции
        chat = await self.get_chat(message.chat_id)
        if not chat or not await self._can_access_chat(chat.id, user_id):
            return False

        # Добавляем реакцию
        if reaction_type not in message.reactions:
            message.reactions[reaction_type] = []
        if user_id not in message.reactions[reaction_type]:
            message.reactions[reaction_type].append(user_id)

        # Обновляем сообщение в базе данных
        await self._update_message_reactions(message_id, message.reactions)

        # Обновляем кэш
        await self._cache_message(message)

        # Рассылка реакции участникам чата
        await self._broadcast_reaction_to_chat(message.chat_id, message_id, user_id, reaction_type)

        # Создаем запись активности
        await self._log_activity(user_id, "reaction_added", {
            "message_id": message_id,
            "reaction_type": reaction_type
        })

        return True

    async def _update_message_reactions(self, message_id: str, reactions: Dict[str, List[int]]):
        """Обновление реакций в сообщении"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE messages SET reactions = $1 WHERE id = $2",
                json.dumps(reactions), message_id
            )

    async def _broadcast_message_to_chat(self, chat_id: str, message: ChatMessage):
        """Рассылка сообщения всем участникам чата"""
        # Получаем всех участников чата
        chat = await self.get_chat(chat_id)
        if not chat:
            return

        # Подготавливаем сообщение для отправки
        message_data = {
            'type': 'new_message',
            'message': message.dict(),
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем через Redis pub/sub
        await redis_client.publish(f"chat:{chat_id}", json.dumps(message_data))

    async def _broadcast_reaction_to_chat(self, chat_id: str, message_id: str, 
                                        user_id: int, reaction_type: str):
        """Рассылка реакции всем участникам чата"""
        reaction_data = {
            'type': 'message_reaction',
            'message_id': message_id,
            'user_id': user_id,
            'reaction_type': reaction_type,
            'timestamp': datetime.utcnow().isoformat()
        }

        await redis_client.publish(f"chat:{chat_id}", json.dumps(reaction_data))

    async def _update_chat_last_message(self, chat_id: str, message: ChatMessage):
        """Обновление информации о последнем сообщении в чате"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE chats SET 
                    last_message = $1, 
                    last_activity = $2,
                    updated_at = $3
                WHERE id = $4
                """,
                f"{message.sender_id}: {message.content[:50]}...",  # Краткое содержание
                message.timestamp,
                datetime.utcnow(),
                chat_id
            )

        # Обновляем в кэше
        chat = await self.get_chat(chat_id)
        if chat:
            chat.last_message = f"{message.sender_id}: {message.content[:50]}..."
            chat.last_activity = message.timestamp
            chat.updated_at = datetime.utcnow()
            await self._cache_chat(chat)

    async def _update_unread_counts(self, chat_id: str, sender_id: int):
        """Обновление счетчиков непрочитанных сообщений"""
        chat = await self.get_chat(chat_id)
        if not chat:
            return

        # Увеличиваем счетчик непрочитанных для всех участников кроме отправителя
        for member in chat.members:
            member_id = member['user_id']
            if member_id != sender_id:
                # Получаем текущий счетчик
                current_count = chat.unread_counts.get(str(member_id), 0)
                chat.unread_counts[str(member_id)] = current_count + 1

        # Обновляем в базе данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE chats SET unread_counts = $1 WHERE id = $2",
                json.dumps(chat.unread_counts), chat_id
            )

        # Обновляем в кэше
        await self._cache_chat(chat)

    async def _mark_messages_as_read(self, chat_id: str, user_id: int, 
                                   message_ids: List[str]):
        """Отметка сообщений как прочитанных"""
        # Обновляем статус прочтения в базе данных
        async with db_pool.acquire() as conn:
            for message_id in message_ids:
                await conn.execute(
                    """
                    UPDATE messages SET status = $1 
                    WHERE id = $2 AND chat_id = $3 AND sender_id != $4
                    """,
                    MessageStatus.READ.value, message_id, chat_id, user_id
                )

        # Обновляем счетчик непрочитанных в чате
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE chats SET unread_counts = unread_counts - 1
                WHERE id = $1 AND unread_counts > 0
                """,
                chat_id
            )

    async def _can_create_chat(self, user_id: int, chat_type: ChatType) -> bool:
        """Проверка прав на создание чата"""
        # Для всех типов чатов пользователь должен быть активным
        return await self._is_user_active(user_id)

    async def _can_send_message(self, chat: ChatRoom, user_id: int) -> bool:
        """Проверка прав на отправку сообщения в чат"""
        # Проверяем, является ли пользователь участником чата
        member = next((m for m in chat.members if m['user_id'] == user_id), None)
        if not member:
            return False

        # Проверяем, не заблокирован ли пользователь
        if member.get('role') == 'banned':
            return False

        return True

    async def _can_access_chat(self, chat_id: str, user_id: int) -> bool:
        """Проверка прав на доступ к чату"""
        chat = await self.get_chat(chat_id)
        if not chat:
            return False

        # Проверяем, является ли пользователь участником чата
        return any(member['user_id'] == user_id for member in chat.members)

    async def get_chat(self, chat_id: str) -> Optional[ChatRoom]:
        """Получение чата по ID"""
        # Сначала проверяем кэш
        cached_chat = await self._get_cached_chat(chat_id)
        if cached_chat:
            return cached_chat

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, type, creator_id, members, created_at, updated_at,
                       last_message, last_activity, unread_counts, is_archived,
                       is_encrypted
                FROM chats WHERE id = $1
                """,
                chat_id
            )

        if not row:
            return None

        chat = ChatRoom(
            id=row['id'],
            name=row['name'],
            type=ChatType(row['type']),
            creator_id=row['creator_id'],
            members=json.loads(row['members']) if row['members'] else [],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            last_message=row['last_message'],
            last_activity=row['last_activity'],
            unread_counts=json.loads(row['unread_counts']) if row['unread_counts'] else {},
            is_archived=row['is_archived'],
            is_encrypted=row['is_encrypted']
        )

        # Кэшируем чат
        await self._cache_chat(chat)

        return chat

    async def get_message(self, message_id: str) -> Optional[ChatMessage]:
        """Получение сообщения по ID"""
        # Сначала проверяем кэш
        cached_message = await self._get_cached_message(message_id)
        if cached_message:
            return cached_message

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, chat_id, sender_id, content, message_type, timestamp,
                       edited_at, is_edited, reply_to, mentions, reactions,
                       attachments, metadata, status
                FROM messages WHERE id = $1
                """,
                message_id
            )

        if not row:
            return None

        message = ChatMessage(
            id=row['id'],
            chat_id=row['chat_id'],
            sender_id=row['sender_id'],
            content=row['content'],
            message_type=MessageType(row['message_type']),
            timestamp=row['timestamp'],
            edited_at=row['edited_at'],
            is_edited=row['is_edited'],
            reply_to=row['reply_to'],
            mentions=row['mentions'] or [],
            reactions=json.loads(row['reactions']) if row['reactions'] else {},
            attachments=json.loads(row['attachments']) if row['attachments'] else [],
            metadata=json.loads(row['metadata']) if row['metadata'] else None,
            status=MessageStatus(row['status'])
        )

        # Кэшируем сообщение
        await self._cache_message(message)

        return message

    async def _cache_chat(self, chat: ChatRoom):
        """Кэширование чата"""
        await redis_client.setex(f"chat:{chat.id}", 300, chat.model_dump_json())

    async def _get_cached_chat(self, chat_id: str) -> Optional[ChatRoom]:
        """Получение чата из кэша"""
        cached = await redis_client.get(f"chat:{chat_id}")
        if cached:
            return ChatRoom(**json.loads(cached.decode()))
        return None

    async def _cache_message(self, message: ChatMessage):
        """Кэширование сообщения"""
        await redis_client.setex(f"message:{message.id}", 300, message.model_dump_json())

    async def _get_cached_message(self, message_id: str) -> Optional[ChatMessage]:
        """Получение сообщения из кэша"""
        cached = await redis_client.get(f"message:{message_id}")
        if cached:
            return ChatMessage(**json.loads(cached.decode()))
        return None

    async def _notify_chat_created(self, chat: ChatRoom):
        """Уведомление о создании чата"""
        notification = {
            'type': 'chat_created',
            'chat': {
                'id': chat.id,
                'name': chat.name,
                'type': chat.type.value,
                'creator_id': chat.creator_id,
                'member_count': len(chat.members)
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление участникам
        for member in chat.members:
            await self._send_notification_to_user(member['user_id'], notification)

    async def _encrypt_message(self, content: str, encryption_key: str) -> str:
        """Шифрование сообщения"""
        # В реальной системе здесь будет использование криптографической библиотеки
        # для шифрования сообщения с использованием предоставленного ключа
        # Пока возвращаем зашифрованную строку как есть
        return content

    async def _decrypt_message(self, encrypted_content: str, encryption_key: str) -> str:
        """Расшифровка сообщения"""
        # В реальной системе здесь будет использование криптографической библиотеки
        # для расшифровки сообщения с использованием предоставленного ключа
        # Пока возвращаем расшифрованную строку как есть
        return encrypted_content

    async def _is_user_active(self, user_id: int) -> bool:
        """Проверка, является ли пользователь активным"""
        # В реальной системе здесь будет проверка статуса пользователя
        return True

    async def _send_notification_to_user(self, user_id: int, notification: Dict[str, Any]):
        """Отправка уведомления пользователю"""
        channel = f"user:{user_id}:chats"
        await redis_client.publish(channel, json.dumps(notification))

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
chat_service = ChatService()
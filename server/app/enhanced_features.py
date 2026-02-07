# server/app/enhanced_features.py
import asyncio
import json
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
import uuid
from enum import Enum
import re
from dataclasses import dataclass, asdict
from pathlib import Path
import mimetypes
import aiofiles
from PIL import Image
import io

from .performance_optimizer import PaginationHelper
from .advanced_encryption import EndToEndEncryption

class MessageType(Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FILE = "file"
    SYSTEM = "system"
    REACTION = "reaction"
    EDITED = "edited"
    DELETED = "deleted"

class GroupPermission(Enum):
    SEND_MESSAGES = "send_messages"
    EDIT_MESSAGES = "edit_messages"
    DELETE_MESSAGES = "delete_messages"
    INVITE_USERS = "invite_users"
    REMOVE_USERS = "remove_users"
    CHANGE_SETTINGS = "change_settings"
    ADMIN = "admin"

@dataclass
class Message:
    id: str
    sender_id: int
    chat_id: str
    content: str
    message_type: MessageType
    timestamp: datetime
    reply_to: Optional[str] = None
    edited: bool = False
    edited_at: Optional[datetime] = None
    reactions: Optional[Dict[str, List[int]]] = None  # emoji -> list of user_ids who reacted
    mentions: Optional[List[int]] = None  # list of mentioned user_ids
    file_info: Optional[Dict[str, Any]] = None  # for file/image messages

@dataclass
class Group:
    id: str
    name: str
    description: Optional[str] = None
    creator_id: int = 0
    members: List[int] = None
    admins: List[int] = None
    permissions: Dict[int, List[GroupPermission]] = None
    created_at: datetime = None
    updated_at: datetime = None
    avatar: Optional[str] = None

@dataclass
class User:
    id: int
    username: str
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None
    bio: Optional[str] = None
    created_at: datetime = None
    last_seen: datetime = None
    online_status: str = "offline"  # online, offline, away, busy
    privacy_settings: Optional[Dict[str, Any]] = None

class EnhancedChatManager:
    """Расширенный менеджер чатов с новыми функциями"""
    
    def __init__(self, db_pool, redis_client):
        self.db_pool = db_pool
        self.redis = redis_client
        self.pagination_helper = PaginationHelper()
        self.e2e_encryption = EndToEndEncryption()
        self.active_typing_indicators = {}  # chat_id -> set of user_ids typing
    
    async def create_private_chat(self, user1_id: int, user2_id: int) -> str:
        """Создание приватного чата"""
        chat_id = f"private_{min(user1_id, user2_id)}_{max(user1_id, user2_id)}"
        
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chats (id, type, participants, created_at) 
                VALUES ($1, 'private', ARRAY[$2, $3], $4)
                ON CONFLICT (id) DO UPDATE SET updated_at = $4
                """,
                chat_id, user1_id, user2_id, datetime.utcnow()
            )
        
        return chat_id
    
    async def create_group_chat(self, name: str, creator_id: int, 
                               participants: List[int], 
                               description: Optional[str] = None) -> str:
        """Создание группового чата"""
        group_id = f"group_{uuid.uuid4()}"
        
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chats (id, type, name, description, creator_id, participants, created_at) 
                VALUES ($1, 'group', $2, $3, $4, $5, $6)
                """,
                group_id, name, description, creator_id, participants, datetime.utcnow()
            )
            
            # Создаем записи разрешений для участников
            for participant_id in participants:
                permission = GroupPermission.ADMIN if participant_id == creator_id else GroupPermission.SEND_MESSAGES
                await conn.execute(
                    """
                    INSERT INTO group_permissions (group_id, user_id, permission) 
                    VALUES ($1, $2, $3)
                    """,
                    group_id, participant_id, permission.value
                )
        
        return group_id
    
    async def send_message(self, 
                          chat_id: str, 
                          sender_id: int, 
                          content: str, 
                          message_type: MessageType = MessageType.TEXT,
                          reply_to: Optional[str] = None,
                          mentions: Optional[List[int]] = None,
                          encrypt_for_recipients: bool = False) -> str:
        """Отправка сообщения с поддержкой новых функций"""
        message_id = str(uuid.uuid4())
        
        # Если нужно зашифровать для получателей (end-to-end)
        if encrypt_for_recipients:
            # Получаем список участников чата
            participants = await self.get_chat_participants(chat_id)
            encrypted_content = {}
            
            for participant_id in participants:
                if participant_id != sender_id:  # Не шифруем для отправителя
                    # Получаем реальный публичный ключ пользователя из базы данных
                    user_public_key = await self._get_user_public_key(participant_id)
                    if user_public_key:
                        encrypted_content[str(participant_id)] = self.e2e_encryption.encrypt_for_user(
                            content,
                            user_public_key
                        )
                    else:
                        # Если нет публичного ключа, сохраняем как обычный текст (для совместимости)
                        encrypted_content[str(participant_id)] = content
            
            content = json.dumps(encrypted_content)
        
        message = Message(
            id=message_id,
            sender_id=sender_id,
            chat_id=chat_id,
            content=content,
            message_type=message_type,
            timestamp=datetime.utcnow(),
            reply_to=reply_to,
            mentions=mentions or []
        )
        
        # Сохраняем в базу данных
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO messages (id, chat_id, sender_id, content, message_type, timestamp, reply_to, mentions) 
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                message.id, message.chat_id, message.sender_id, message.content,
                message.message_type.value, message.timestamp, message.reply_to, message.mentions
            )
        
        # Отправляем через Redis
        message_data = asdict(message)
        await self.redis.publish(f"chat:{chat_id}", json.dumps(message_data))
        
        # Уведомляем участников о новых сообщениях
        await self.notify_new_message(chat_id, message)
        
        return message_id
    
    async def edit_message(self, message_id: str, user_id: int, new_content: str) -> bool:
        """Редактирование сообщения"""
        async with self.db_pool.acquire() as conn:
            # Проверяем, является ли пользователь отправителем
            original_message = await conn.fetchrow(
                "SELECT sender_id, chat_id FROM messages WHERE id = $1",
                message_id
            )
            
            if not original_message or original_message['sender_id'] != user_id:
                return False  # Пользователь не может редактировать это сообщение
            
            # Обновляем сообщение
            await conn.execute(
                """
                UPDATE messages 
                SET content = $1, edited = TRUE, edited_at = $2 
                WHERE id = $3
                """,
                new_content, datetime.utcnow(), message_id
            )
        
        # Отправляем обновленное сообщение
        updated_message = {
            'type': 'message_edited',
            'message_id': message_id,
            'content': new_content,
            'edited_at': datetime.utcnow().isoformat()
        }
        
        chat_id = original_message['chat_id']
        await self.redis.publish(f"chat:{chat_id}", json.dumps(updated_message))
        
        return True
    
    async def delete_message(self, message_id: str, user_id: int, hard_delete: bool = False) -> bool:
        """Удаление сообщения"""
        async with self.db_pool.acquire() as conn:
            message = await conn.fetchrow(
                "SELECT sender_id, chat_id FROM messages WHERE id = $1",
                message_id
            )
            
            if not message:
                return False
            
            # Проверяем права: отправитель или админ группы
            can_delete = message['sender_id'] == user_id or await self.is_group_admin(message['chat_id'], user_id)
            
            if not can_delete:
                return False
            
            if hard_delete:
                # Полное удаление из базы
                await conn.execute("DELETE FROM messages WHERE id = $1", message_id)
            else:
                # Мягкое удаление (помечаем как удаленное)
                await conn.execute(
                    "UPDATE messages SET deleted = TRUE, deleted_at = $1 WHERE id = $2",
                    datetime.utcnow(), message_id
                )
        
        # Уведомляем об удалении
        deletion_notification = {
            'type': 'message_deleted',
            'message_id': message_id,
            'deleted_at': datetime.utcnow().isoformat()
        }
        
        await self.redis.publish(f"chat:{message['chat_id']}", json.dumps(deletion_notification))
        
        return True
    
    async def add_reaction(self, message_id: str, user_id: int, emoji: str) -> bool:
        """Добавление реакции к сообщению"""
        async with self.db_pool.acquire() as conn:
            # Проверяем, существует ли сообщение
            message = await conn.fetchrow(
                "SELECT chat_id FROM messages WHERE id = $1",
                message_id
            )
            
            if not message:
                return False
            
            # Добавляем реакцию
            await conn.execute(
                """
                INSERT INTO message_reactions (message_id, user_id, emoji, created_at) 
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (message_id, user_id, emoji) DO UPDATE SET created_at = $4
                """,
                message_id, user_id, emoji, datetime.utcnow()
            )
        
        # Уведомляем о реакции
        reaction_update = {
            'type': 'reaction_added',
            'message_id': message_id,
            'user_id': user_id,
            'emoji': emoji
        }
        
        await self.redis.publish(f"chat:{message['chat_id']}", json.dumps(reaction_update))
        
        return True
    
    async def remove_reaction(self, message_id: str, user_id: int, emoji: str) -> bool:
        """Удаление реакции из сообщения"""
        async with self.db_pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM message_reactions WHERE message_id = $1 AND user_id = $2 AND emoji = $3",
                message_id, user_id, emoji
            )
        
        if result:
            reaction_update = {
                'type': 'reaction_removed',
                'message_id': message_id,
                'user_id': user_id,
                'emoji': emoji
            }
            
            # Получаем chat_id для отправки уведомления
            async with self.db_pool.acquire() as conn:
                message = await conn.fetchrow(
                    "SELECT chat_id FROM messages WHERE id = $1",
                    message_id
                )
                if message:
                    await self.redis.publish(f"chat:{message['chat_id']}", json.dumps(reaction_update))
        
        return bool(result)
    
    async def upload_file(self, chat_id: str, user_id: int, file_data: bytes, 
                         filename: str, file_type: str) -> Optional[str]:
        """Загрузка файла в чат"""
        # Определяем MIME-тип
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            mime_type = "application/octet-stream"
        
        # Генерируем уникальное имя файла
        file_id = str(uuid.uuid4())
        file_extension = Path(filename).suffix
        stored_filename = f"{file_id}{file_extension}"
        
        # Сохраняем файл (в реальном приложении - в S3 или другом хранилище)
        upload_dir = Path("uploads") / chat_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = upload_dir / stored_filename
        
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_data)
        
        # Сохраняем информацию о файле в базе
        file_info = {
            'original_name': filename,
            'stored_name': stored_filename,
            'size': len(file_data),
            'mime_type': mime_type,
            'uploaded_by': user_id,
            'uploaded_at': datetime.utcnow().isoformat()
        }
        
        # Отправляем сообщение о файле
        message_id = await self.send_message(
            chat_id=chat_id,
            sender_id=user_id,
            content=f"Файл: {filename}",
            message_type=MessageType.FILE,
            file_info=file_info
        )
        
        return message_id
    
    async def search_messages(self, user_id: int, query: str, 
                             chat_id: Optional[str] = None, 
                             limit: int = 50) -> List[Dict[str, Any]]:
        """Поиск сообщений"""
        conditions = []
        params = [f"%{query}%"]
        param_index = 1
        
        # Проверяем, имеет ли пользователь доступ к чату
        if chat_id:
            if not await self.user_can_access_chat(user_id, chat_id):
                return []
            
            conditions.append(f"chat_id = ${param_index}")
            params.append(chat_id)
            param_index += 1
        else:
            # Только чаты, к которым у пользователя есть доступ
            accessible_chats = await self.get_user_chats(user_id)
            if accessible_chats:
                chat_placeholders = ', '.join([f"${i}" for i in range(param_index, param_index + len(accessible_chats))])
                conditions.append(f"chat_id IN ({chat_placeholders})")
                params.extend(accessible_chats)
                param_index += len(accessible_chats)
            else:
                return []  # Пользователь не имеет доступа к чатам
        
        # Формируем запрос
        where_clause = " AND ".join(conditions)
        search_query = f"""
            SELECT id, chat_id, sender_id, content, message_type, timestamp, reply_to
            FROM messages 
            WHERE content ILIKE ${param_index} AND deleted = FALSE
            AND {where_clause}
            ORDER BY timestamp DESC
            LIMIT ${param_index + 1}
        """
        
        params.append(limit)
        
        async with self.db_pool.acquire() as conn:
            results = await conn.fetch(search_query, *params)
        
        return [dict(row) for row in results]
    
    async def get_chat_participants(self, chat_id: str) -> List[int]:
        """Получение участников чата"""
        async with self.db_pool.acquire() as conn:
            chat = await conn.fetchrow(
                "SELECT participants FROM chats WHERE id = $1",
                chat_id
            )
            return chat['participants'] if chat else []
    
    async def add_user_to_group(self, group_id: str, added_by: int, user_id: int) -> bool:
        """Добавление пользователя в группу"""
        if not await self.has_permission(group_id, added_by, GroupPermission.INVITE_USERS):
            return False
        
        async with self.db_pool.acquire() as conn:
            # Добавляем пользователя в чат
            await conn.execute(
                """
                UPDATE chats 
                SET participants = array_append(participants, $1), updated_at = $2
                WHERE id = $3
                """,
                user_id, datetime.utcnow(), group_id
            )
        
        # Уведомляем о добавлении
        notification = {
            'type': 'user_added_to_group',
            'group_id': group_id,
            'added_user_id': user_id,
            'added_by': added_by
        }
        
        await self.redis.publish(f"chat:{group_id}", json.dumps(notification))
        
        return True
    
    async def remove_user_from_group(self, group_id: str, removed_by: int, user_id: int) -> bool:
        """Удаление пользователя из группы"""
        if not await self.has_permission(group_id, removed_by, GroupPermission.REMOVE_USERS):
            return False
        
        # Нельзя удалить создателя группы
        group_info = await self.get_group_info(group_id)
        if group_info and group_info.creator_id == user_id:
            return False
        
        async with self.db_pool.acquire() as conn:
            # Удаляем пользователя из чата
            await conn.execute(
                """
                UPDATE chats 
                SET participants = array_remove(participants, $1), updated_at = $2
                WHERE id = $3
                """,
                user_id, datetime.utcnow(), group_id
            )
        
        # Уведомляем об удалении
        notification = {
            'type': 'user_removed_from_group',
            'group_id': group_id,
            'removed_user_id': user_id,
            'removed_by': removed_by
        }
        
        await self.redis.publish(f"chat:{group_id}", json.dumps(notification))
        
        return True
    
    async def has_permission(self, group_id: str, user_id: int, permission: GroupPermission) -> bool:
        """Проверка наличия разрешения у пользователя в группе"""
        async with self.db_pool.acquire() as conn:
            # Проверяем специальные права (админ)
            admin_check = await conn.fetchval(
                "SELECT COUNT(*) FROM group_permissions WHERE group_id = $1 AND user_id = $2 AND permission = $3",
                group_id, user_id, GroupPermission.ADMIN.value
            )
            
            if admin_check:
                return True
            
            # Проверяем конкретное разрешение
            perm_check = await conn.fetchval(
                "SELECT COUNT(*) FROM group_permissions WHERE group_id = $1 AND user_id = $2 AND permission = $3",
                group_id, user_id, permission.value
            )
            
            return bool(perm_check)
    
    async def get_group_info(self, group_id: str) -> Optional[Group]:
        """Получение информации о группе"""
        async with self.db_pool.acquire() as conn:
            group = await conn.fetchrow(
                "SELECT id, name, description, creator_id, participants, created_at, updated_at, avatar FROM groups WHERE id = $1",
                group_id
            )
            
            if group:
                return Group(
                    id=group['id'],
                    name=group['name'],
                    description=group['description'],
                    creator_id=group['creator_id'],
                    members=group['participants'],
                    created_at=group['created_at'],
                    updated_at=group['updated_at'],
                    avatar=group['avatar']
                )
        
        return None
    
    async def notify_new_message(self, chat_id: str, message: Message):
        """Уведомление участников о новом сообщении"""
        # Уведомление через Redis
        notification = {
            'type': 'new_message',
            'chat_id': chat_id,
            'message': asdict(message)
        }
        
        await self.redis.publish(f"chat:{chat_id}", json.dumps(notification))
        
        # Также отправляем уведомления в реальном времени (если кто-то онлайн)
        active_users = await self.redis.smembers(f"active_users:{chat_id}")
        for user_id in active_users:
            await self.redis.publish(f"user:{user_id}:notifications", json.dumps(notification))
    
    async def user_can_access_chat(self, user_id: int, chat_id: str) -> bool:
        """Проверка, имеет ли пользователь доступ к чату"""
        async with self.db_pool.acquire() as conn:
            chat = await conn.fetchrow(
                "SELECT participants FROM chats WHERE id = $1",
                chat_id
            )
            
            if not chat:
                return False
            
            return user_id in chat['participants']
    
    async def get_user_chats(self, user_id: int) -> List[str]:
        """Получение списка чатов, к которым у пользователя есть доступ"""
        async with self.db_pool.acquire() as conn:
            chats = await conn.fetch(
                "SELECT id FROM chats WHERE $1 = ANY(participants)",
                user_id
            )
            return [chat['id'] for chat in chats]
    
    async def is_group_admin(self, group_id: str, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором группы"""
        return await self.has_permission(group_id, user_id, GroupPermission.ADMIN)

class TypingIndicatorManager:
    """Менеджер индикаторов набора текста"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def user_started_typing(self, chat_id: str, user_id: int):
        """Пользователь начал набирать текст"""
        await self.redis.sadd(f"typing:{chat_id}", user_id)
        await self.redis.expire(f"typing:{chat_id}", 10)  # Удаляем через 10 секунд
        
        # Уведомляем других пользователей в чате
        typing_notification = {
            'type': 'user_typing_start',
            'chat_id': chat_id,
            'user_id': user_id
        }
        
        await self.redis.publish(f"chat:{chat_id}", json.dumps(typing_notification))
    
    async def user_stopped_typing(self, chat_id: str, user_id: int):
        """Пользователь закончил набирать текст"""
        await self.redis.srem(f"typing:{chat_id}", user_id)
        
        # Уведомляем других пользователей в чате
        typing_notification = {
            'type': 'user_typing_stop',
            'chat_id': chat_id,
            'user_id': user_id
        }
        
        await self.redis.publish(f"chat:{chat_id}", json.dumps(typing_notification))
    
    async def get_typing_users(self, chat_id: str) -> List[int]:
        """Получение списка пользователей, которые сейчас набирают текст"""
        typing_users = await self.redis.smembers(f"typing:{chat_id}")
        return [int(uid) for uid in typing_users if uid.isdigit()]

class MentionManager:
    """Менеджер упоминаний пользователей"""
    
    def __init__(self, db_pool, redis_client):
        self.db_pool = db_pool
        self.redis = redis_client
    
    async def parse_mentions(self, text: str) -> List[int]:
        """Парсинг упоминаний в тексте (@username)"""
        # Ищем упоминания в формате @username
        mention_pattern = r'@(\w+)'
        matches = re.findall(mention_pattern, text)
        
        user_ids = []
        for username in matches:
            user_id = await self.get_user_id_by_username(username)
            if user_id:
                user_ids.append(user_id)
        
        return user_ids
    
    async def get_user_id_by_username(self, username: str) -> Optional[int]:
        """Получение ID пользователя по имени"""
        async with self.db_pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT id FROM users WHERE username = $1",
                username
            )
            return result
    
    async def notify_mentions(self, chat_id: str, mentioned_user_ids: List[int], message_id: str):
        """Уведомление упомянутых пользователей"""
        for user_id in mentioned_user_ids:
            notification = {
                'type': 'mention_notification',
                'chat_id': chat_id,
                'message_id': message_id,
                'mentioned_by': await self.get_current_user_id()  # В реальном приложении передавался бы
            }
            
            await self.redis.publish(f"user:{user_id}:notifications", json.dumps(notification))
    
    async def _get_user_public_key(self, user_id: int) -> Optional[str]:
        """Получение публичного ключа пользователя для сквозного шифрования"""
        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT public_key FROM user_encryption_keys WHERE user_id = $1
                    """,
                    user_id
                )

            return row['public_key'] if row and row['public_key'] else None
        except Exception as e:
            logger.error(f"Error getting public key for user {user_id}: {e}")
            return None

    async def get_current_user_id(self) -> int:
        """Вспомогательный метод - в реальном приложении получал бы ID текущего пользователя"""
        return 1  # Заглушка
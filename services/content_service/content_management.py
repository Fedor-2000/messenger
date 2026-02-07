# Content Management System
# File: services/content_service/content_management.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid
import hashlib
from pathlib import Path
import aiofiles
from PIL import Image
import io

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class ContentType(Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    LINK = "link"
    EMBED = "embed"
    CODE_SNIPPET = "code_snippet"
    POLL = "poll"
    TASK = "task"
    CALENDAR_EVENT = "calendar_event"
    FILE_ATTACHMENT = "file_attachment"

class ContentStatus(Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    DELETED = "deleted"
    PENDING_MODERATION = "pending_moderation"

class ContentVisibility(Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    FRIENDS_ONLY = "friends_only"
    GROUP_MEMBERS = "group_members"
    SPECIFIC_USERS = "specific_users"

class ContentModerationStatus(Enum):
    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"
    FLAGGED = "flagged"

class Content(BaseModel):
    id: str
    user_id: int
    type: ContentType
    title: str
    content: str
    preview: Optional[str] = None  # Краткое описание или превью
    tags: List[str] = []
    mentions: List[int] = []  # ID упомянутых пользователей
    attachments: List[Dict] = []  # [{'id': 'file_id', 'name': 'file_name', 'type': 'file_type'}]
    reactions: Dict[str, List[int]] = {}  # {'like': [user_id1, user_id2], 'love': [user_id3]}
    shares: int = 0
    views: int = 0
    likes: int = 0
    comments_count: int = 0
    status: ContentStatus
    visibility: ContentVisibility
    moderation_status: ContentModerationStatus
    parent_content_id: Optional[str] = None  # Для комментариев и репостов
    chat_id: Optional[str] = None
    group_id: Optional[str] = None
    project_id: Optional[str] = None
    scheduled_publish: Optional[datetime] = None
    published_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime = None
    updated_at: datetime = None
    edited_at: Optional[datetime] = None
    is_edited: bool = False
    is_pinned: bool = False
    is_featured: bool = False
    language: str = "ru"  # Язык контента
    metadata: Optional[Dict] = None  # Дополнительные метаданные

class ContentComment(BaseModel):
    id: str
    content_id: str
    user_id: int
    parent_comment_id: Optional[str] = None  # Для вложенных комментариев
    text: str
    likes: int = 0
    replies_count: int = 0
    is_edited: bool = False
    edited_at: Optional[datetime] = None
    created_at: datetime = None
    updated_at: datetime = None

class ContentReaction(BaseModel):
    id: str
    content_id: str
    user_id: int
    reaction_type: str  # 'like', 'love', 'laugh', 'wow', 'sad', 'angry', etc.
    created_at: datetime = None

class ContentShare(BaseModel):
    id: str
    content_id: str
    user_id: int
    target_type: str  # 'user', 'chat', 'group', 'external'
    target_id: str
    created_at: datetime = None

class ContentModeration(BaseModel):
    id: str
    content_id: str
    moderator_id: int
    status: ContentModerationStatus
    reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = None
    updated_at: datetime = None

class ContentManagementService:
    def __init__(self):
        self.upload_dir = Path("/app/uploads/content")
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.max_file_size = 50 * 1024 * 1024  # 50 MB
        self.allowed_image_types = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        self.allowed_document_types = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.rtf'}

    async def create_content(self, user_id: int, content_type: ContentType, title: str,
                           content: str, preview: Optional[str] = None,
                           tags: Optional[List[str]] = None,
                           mentions: Optional[List[int]] = None,
                           attachments: Optional[List[Dict]] = None,
                           visibility: ContentVisibility = ContentVisibility.PUBLIC,
                           scheduled_publish: Optional[datetime] = None,
                           chat_id: Optional[str] = None,
                           group_id: Optional[str] = None,
                           project_id: Optional[str] = None,
                           language: str = "ru",
                           metadata: Optional[Dict] = None) -> Optional[str]:
        """Создание нового контента"""
        content_id = str(uuid.uuid4())

        content_obj = Content(
            id=content_id,
            user_id=user_id,
            type=content_type,
            title=title,
            content=content,
            preview=preview,
            tags=tags or [],
            mentions=mentions or [],
            attachments=attachments or [],
            status=ContentStatus.PUBLISHED if not scheduled_publish else ContentStatus.DRAFT,
            visibility=visibility,
            moderation_status=ContentModerationStatus.PENDING if self.requires_moderation(content_type) else ContentModerationStatus.APPROVED,
            scheduled_publish=scheduled_publish,
            chat_id=chat_id,
            group_id=group_id,
            project_id=project_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            language=language,
            metadata=metadata or {}
        )

        # Проверяем необходимость модерации
        if content_obj.moderation_status == ContentModerationStatus.PENDING:
            await self._submit_for_moderation(content_obj)

        # Если контент не требует модерации и не запланирован к публикации, публикуем сразу
        if (content_obj.moderation_status == ContentModerationStatus.APPROVED and 
            not content_obj.scheduled_publish):
            content_obj.published_at = datetime.utcnow()

        # Сохраняем контент в базу данных
        await self._save_content(content_obj)

        # Добавляем в кэш
        await self._cache_content(content_obj)

        # Уведомляем заинтересованные стороны
        await self._notify_content_created(content_obj)

        # Если контент запланирован, добавляем в очередь планировщика
        if content_obj.scheduled_publish:
            await self._schedule_content_publish(content_obj)

        return content_id

    async def _save_content(self, content: Content):
        """Сохранение контента в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO content (
                    id, user_id, type, title, content, preview, tags, mentions,
                    attachments, status, visibility, moderation_status,
                    parent_content_id, chat_id, group_id, project_id,
                    scheduled_publish, published_at, expires_at, created_at,
                    updated_at, edited_at, is_edited, is_pinned, is_featured,
                    language, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                         $13, $14, $15, $16, $17, $18, $19, $20, $21, $22,
                         $23, $24, $25, $26, $27)
                """,
                content.id, content.user_id, content.type.value, content.title,
                content.content, content.preview, content.tags, content.mentions,
                json.dumps(content.attachments), content.status.value,
                content.visibility.value, content.moderation_status.value,
                content.parent_content_id, content.chat_id, content.group_id,
                content.project_id, content.scheduled_publish, content.published_at,
                content.expires_at, content.created_at, content.updated_at,
                content.edited_at, content.is_edited, content.is_pinned,
                content.is_featured, content.language,
                json.dumps(content.metadata) if content.metadata else None
            )

    async def get_content(self, content_id: str, user_id: Optional[int] = None) -> Optional[Content]:
        """Получение контента по ID"""
        # Сначала проверяем кэш
        cached_content = await self._get_cached_content(content_id)
        if cached_content:
            # Проверяем права доступа
            if await self._can_access_content(cached_content, user_id):
                # Увеличиваем счетчик просмотров
                await self._increment_views(cached_content.id)
                return cached_content
            else:
                return None

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, user_id, type, title, content, preview, tags, mentions,
                       attachments, status, visibility, moderation_status,
                       parent_content_id, chat_id, group_id, project_id,
                       scheduled_publish, published_at, expires_at, created_at,
                       updated_at, edited_at, is_edited, is_pinned, is_featured,
                       language, metadata
                FROM content WHERE id = $1
                """,
                content_id
            )

        if not row:
            return None

        content = Content(
            id=row['id'],
            user_id=row['user_id'],
            type=ContentType(row['type']),
            title=row['title'],
            content=row['content'],
            preview=row['preview'],
            tags=row['tags'] or [],
            mentions=row['mentions'] or [],
            attachments=json.loads(row['attachments']) if row['attachments'] else [],
            status=ContentStatus(row['status']),
            visibility=ContentVisibility(row['visibility']),
            moderation_status=ContentModerationStatus(row['moderation_status']),
            parent_content_id=row['parent_content_id'],
            chat_id=row['chat_id'],
            group_id=row['group_id'],
            project_id=row['project_id'],
            scheduled_publish=row['scheduled_publish'],
            published_at=row['published_at'],
            expires_at=row['expires_at'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            edited_at=row['edited_at'],
            is_edited=row['is_edited'],
            is_pinned=row['is_pinned'],
            is_featured=row['is_featured'],
            language=row['language'],
            metadata=json.loads(row['metadata']) if row['metadata'] else None
        )

        # Проверяем права доступа
        if not await self._can_access_content(content, user_id):
            return None

        # Увеличиваем счетчик просмотров
        await self._increment_views(content.id)

        # Кэшируем контент
        await self._cache_content(content)

        return content

    async def update_content(self, content_id: str, user_id: int,
                           title: Optional[str] = None,
                           content: Optional[str] = None,
                           preview: Optional[str] = None,
                           tags: Optional[List[str]] = None,
                           mentions: Optional[List[int]] = None,
                           attachments: Optional[List[Dict]] = None,
                           visibility: Optional[ContentVisibility] = None,
                           language: Optional[str] = None,
                           metadata: Optional[Dict] = None) -> bool:
        """Обновление контента"""
        content_obj = await self.get_content(content_id, user_id)
        if not content_obj:
            return False

        # Проверяем права на редактирование
        if content_obj.user_id != user_id:
            return False

        # Обновляем поля
        if title is not None:
            content_obj.title = title
        if content is not None:
            content_obj.content = content
        if preview is not None:
            content_obj.preview = preview
        if tags is not None:
            content_obj.tags = tags
        if mentions is not None:
            content_obj.mentions = mentions
        if attachments is not None:
            content_obj.attachments = attachments
        if visibility is not None:
            content_obj.visibility = visibility
        if language is not None:
            content_obj.language = language
        if metadata is not None:
            content_obj.metadata = metadata

        content_obj.is_edited = True
        content_obj.edited_at = datetime.utcnow()
        content_obj.updated_at = datetime.utcnow()

        # Обновляем в базе данных
        await self._update_content_in_db(content_obj)

        # Обновляем в кэше
        await self._cache_content(content_obj)

        # Уведомляем заинтересованные стороны
        await self._notify_content_updated(content_obj)

        return True

    async def _update_content_in_db(self, content: Content):
        """Обновление контента в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE content SET
                    title = $2, content = $3, preview = $4, tags = $5, mentions = $6,
                    attachments = $7, visibility = $8, updated_at = $9, edited_at = $10,
                    is_edited = $11, language = $12, metadata = $13
                WHERE id = $1
                """,
                content.id, content.title, content.content, content.preview,
                content.tags, content.mentions, json.dumps(content.attachments),
                content.visibility.value, content.updated_at, content.edited_at,
                content.is_edited, content.language,
                json.dumps(content.metadata) if content.metadata else None
            )

    async def delete_content(self, content_id: str, user_id: int, hard_delete: bool = False) -> bool:
        """Удаление контента"""
        content_obj = await self.get_content(content_id, user_id)
        if not content_obj:
            return False

        # Проверяем права на удаление
        if content_obj.user_id != user_id and not await self._is_admin(user_id):
            return False

        if hard_delete:
            # Полное удаление из базы данных
            async with db_pool.acquire() as conn:
                await conn.execute("DELETE FROM content WHERE id = $1", content_id)
        else:
            # Мягкое удаление - изменяем статус
            content_obj.status = ContentStatus.DELETED
            content_obj.updated_at = datetime.utcnow()

            await self._update_content_in_db(content_obj)

        # Удаляем из кэша
        await self._uncache_content(content_id)

        # Удаляем связанные данные
        await self._delete_related_data(content_id)

        # Уведомляем заинтересованные стороны
        await self._notify_content_deleted(content_obj)

        return True

    async def publish_content(self, content_id: str, user_id: int) -> bool:
        """Публикация контента (если он был в черновиках)"""
        content_obj = await self.get_content(content_id, user_id)
        if not content_obj:
            return False

        # Проверяем права
        if content_obj.user_id != user_id:
            return False

        # Проверяем статус
        if content_obj.status != ContentStatus.DRAFT:
            return False

        # Проверяем модерацию
        if content_obj.moderation_status != ContentModerationStatus.APPROVED:
            return False

        content_obj.status = ContentStatus.PUBLISHED
        content_obj.published_at = datetime.utcnow()
        content_obj.updated_at = datetime.utcnow()

        # Обновляем в базе данных
        await self._update_content_in_db(content_obj)

        # Обновляем в кэше
        await self._cache_content(content_obj)

        # Уведомляем заинтересованные стороны
        await self._notify_content_published(content_obj)

        return True

    async def add_comment(self, content_id: str, user_id: int, text: str,
                         parent_comment_id: Optional[str] = None) -> Optional[str]:
        """Добавление комментария к контенту"""
        content_obj = await self.get_content(content_id)
        if not content_obj:
            return None

        # Проверяем права на комментирование
        if not await self._can_comment_content(content_obj, user_id):
            return None

        comment_id = str(uuid.uuid4())

        comment = ContentComment(
            id=comment_id,
            content_id=content_id,
            user_id=user_id,
            parent_comment_id=parent_comment_id,
            text=text,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем комментарий
        await self._save_comment(comment)

        # Обновляем счетчик комментариев в контенте
        await self._increment_comments_count(content_id)

        # Уведомляем автора контента и других комментаторов
        await self._notify_comment_added(content_obj, comment)

        return comment_id

    async def add_reaction(self, content_id: str, user_id: int, reaction_type: str) -> bool:
        """Добавление реакции к контенту"""
        content_obj = await self.get_content(content_id)
        if not content_obj:
            return False

        # Проверяем права
        if not await self._can_interact_with_content(content_obj, user_id):
            return False

        reaction_id = str(uuid.uuid4())

        reaction = ContentReaction(
            id=reaction_id,
            content_id=content_id,
            user_id=user_id,
            reaction_type=reaction_type,
            created_at=datetime.utcnow()
        )

        # Сохраняем реакцию
        await self._save_reaction(reaction)

        # Обновляем счетчики реакций в контенте
        await self._update_reaction_counts(content_id, user_id, reaction_type, increment=True)

        # Уведомляем автора контента
        await self._notify_reaction_added(content_obj, reaction)

        return True

    async def remove_reaction(self, content_id: str, user_id: int, reaction_type: str) -> bool:
        """Удаление реакции с контента"""
        # Удаляем реакцию из базы данных
        async with db_pool.acquire() as conn:
            result = await conn.fetchval(
                """
                DELETE FROM content_reactions 
                WHERE content_id = $1 AND user_id = $2 AND reaction_type = $3
                RETURNING id
                """,
                content_id, user_id, reaction_type
            )

        if not result:
            return False

        # Обновляем счетчики реакций в контенте
        await self._update_reaction_counts(content_id, user_id, reaction_type, increment=False)

        return True

    async def share_content(self, content_id: str, user_id: int, target_type: str, target_id: str) -> Optional[str]:
        """Поделиться контентом"""
        content_obj = await self.get_content(content_id)
        if not content_obj:
            return None

        # Проверяем права на шеринг
        if not await self._can_share_content(content_obj, user_id):
            return None

        share_id = str(uuid.uuid4())

        share = ContentShare(
            id=share_id,
            content_id=content_id,
            user_id=user_id,
            target_type=target_type,
            target_id=target_id,
            created_at=datetime.utcnow()
        )

        # Сохраняем шер
        await self._save_share(share)

        # Увеличиваем счетчик шеров
        await self._increment_shares_count(content_id)

        # Уведомляем о шере
        await self._notify_content_shared(content_obj, share)

        return share_id

    async def search_content(self, query: str, user_id: Optional[int] = None,
                           content_types: Optional[List[ContentType]] = None,
                           tags: Optional[List[str]] = None,
                           date_from: Optional[datetime] = None,
                           date_to: Optional[datetime] = None,
                           limit: int = 20, offset: int = 0) -> List[Content]:
        """Поиск контента"""
        conditions = ["status = 'published' AND moderation_status = 'approved'"]
        params = []
        param_idx = 1

        # Проверяем права доступа к контенту
        if user_id:
            conditions.append("(visibility = 'public' OR user_id = $1 OR $1 = ANY(mentions))")
            params.append(user_id)
            param_idx += 1
        else:
            conditions.append("visibility = 'public'")
        
        # Фильтр по типам контента
        if content_types:
            type_values = [ct.value for ct in content_types]
            conditions.append(f"type = ANY(${'$'.join([str(i) for i in range(param_idx, param_idx + len(type_values))])})")
            params.extend(type_values)
            param_idx += len(type_values)

        # Фильтр по тегам
        if tags:
            for tag in tags:
                conditions.append(f"LOWER(${'$'.join([str(i) for i in range(param_idx, param_idx + len(tags))])}) = ANY(LOWER(tags))")
                params.extend(tags)
                param_idx += len(tags)

        # Фильтр по дате
        if date_from:
            conditions.append(f"created_at >= ${param_idx}")
            params.append(date_from)
            param_idx += 1

        if date_to:
            conditions.append(f"created_at <= ${param_idx}")
            params.append(date_to)
            param_idx += 1

        # Фильтр по содержимому
        if query:
            conditions.append(f"(LOWER(title) LIKE LOWER(${'$'.join([str(i) for i in range(param_idx, param_idx + 1)])}) OR LOWER(content) LIKE LOWER(${'$'.join([str(i) for i in range(param_idx, param_idx + 1)])}))")
            params.extend([f'%{query}%', f'%{query}%'])
            param_idx += 2

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, user_id, type, title, content, preview, tags, mentions,
                   attachments, status, visibility, moderation_status,
                   parent_content_id, chat_id, group_id, project_id,
                   scheduled_publish, published_at, expires_at, created_at,
                   updated_at, edited_at, is_edited, is_pinned, is_featured,
                   language, metadata
            FROM content
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        contents = []
        for row in rows:
            content = Content(
                id=row['id'],
                user_id=row['user_id'],
                type=ContentType(row['type']),
                title=row['title'],
                content=row['content'],
                preview=row['preview'],
                tags=row['tags'] or [],
                mentions=row['mentions'] or [],
                attachments=json.loads(row['attachments']) if row['attachments'] else [],
                status=ContentStatus(row['status']),
                visibility=ContentVisibility(row['visibility']),
                moderation_status=ContentModerationStatus(row['moderation_status']),
                parent_content_id=row['parent_content_id'],
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                scheduled_publish=row['scheduled_publish'],
                published_at=row['published_at'],
                expires_at=row['expires_at'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                edited_at=row['edited_at'],
                is_edited=row['is_edited'],
                is_pinned=row['is_pinned'],
                is_featured=row['is_featured'],
                language=row['language'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None
            )
            contents.append(content)

        return contents

    async def get_user_content(self, user_id: int, content_type: Optional[ContentType] = None,
                              status: Optional[ContentStatus] = None,
                              limit: int = 20, offset: int = 0) -> List[Content]:
        """Получение контента пользователя"""
        conditions = ["user_id = $1"]
        params = [user_id]
        param_idx = 2

        if content_type:
            conditions.append(f"type = ${param_idx}")
            params.append(content_type.value)
            param_idx += 1

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, user_id, type, title, content, preview, tags, mentions,
                   attachments, status, visibility, moderation_status,
                   parent_content_id, chat_id, group_id, project_id,
                   scheduled_publish, published_at, expires_at, created_at,
                   updated_at, edited_at, is_edited, is_pinned, is_featured,
                   language, metadata
            FROM content
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        contents = []
        for row in rows:
            content = Content(
                id=row['id'],
                user_id=row['user_id'],
                type=ContentType(row['type']),
                title=row['title'],
                content=row['content'],
                preview=row['preview'],
                tags=row['tags'] or [],
                mentions=row['mentions'] or [],
                attachments=json.loads(row['attachments']) if row['attachments'] else [],
                status=ContentStatus(row['status']),
                visibility=ContentVisibility(row['visibility']),
                moderation_status=ContentModerationStatus(row['moderation_status']),
                parent_content_id=row['parent_content_id'],
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                scheduled_publish=row['scheduled_publish'],
                published_at=row['published_at'],
                expires_at=row['expires_at'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                edited_at=row['edited_at'],
                is_edited=row['is_edited'],
                is_pinned=row['is_pinned'],
                is_featured=row['is_featured'],
                language=row['language'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None
            )
            contents.append(content)

        return contents

    async def get_trending_content(self, limit: int = 20, hours: int = 24) -> List[Content]:
        """Получение трендового контента"""
        since = datetime.utcnow() - timedelta(hours=hours)

        sql_query = """
            SELECT id, user_id, type, title, content, preview, tags, mentions,
                   attachments, status, visibility, moderation_status,
                   parent_content_id, chat_id, group_id, project_id,
                   scheduled_publish, published_at, expires_at, created_at,
                   updated_at, edited_at, is_edited, is_pinned, is_featured,
                   language, metadata,
                   (likes + comments_count + shares) as engagement_score
            FROM content
            WHERE status = 'published' 
              AND moderation_status = 'approved'
              AND published_at > $1
            ORDER BY engagement_score DESC
            LIMIT $2
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, since, limit)

        contents = []
        for row in rows:
            content = Content(
                id=row['id'],
                user_id=row['user_id'],
                type=ContentType(row['type']),
                title=row['title'],
                content=row['content'],
                preview=row['preview'],
                tags=row['tags'] or [],
                mentions=row['mentions'] or [],
                attachments=json.loads(row['attachments']) if row['attachments'] else [],
                status=ContentStatus(row['status']),
                visibility=ContentVisibility(row['visibility']),
                moderation_status=ContentModerationStatus(row['moderation_status']),
                parent_content_id=row['parent_content_id'],
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                scheduled_publish=row['scheduled_publish'],
                published_at=row['published_at'],
                expires_at=row['expires_at'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                edited_at=row['edited_at'],
                is_edited=row['is_edited'],
                is_pinned=row['is_pinned'],
                is_featured=row['is_featured'],
                language=row['language'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None
            )
            contents.append(content)

        return contents

    async def _can_access_content(self, content: Content, user_id: Optional[int]) -> bool:
        """Проверка прав доступа к контенту"""
        if content.visibility == ContentVisibility.PUBLIC:
            return True

        if not user_id:
            return False

        if content.user_id == user_id:
            return True

        if content.visibility == ContentVisibility.PRIVATE:
            return False

        if content.visibility == ContentVisibility.FRIENDS_ONLY:
            # Проверяем, являются ли пользователи друзьями
            return await self._are_friends(content.user_id, user_id)

        if content.visibility == ContentVisibility.GROUP_MEMBERS:
            # Проверяем, состоит ли пользователь в группе
            if content.group_id:
                return await self._is_group_member(user_id, content.group_id)

        if content.visibility == ContentVisibility.SPECIFIC_USERS:
            # Проверяем, входит ли пользователь в список разрешенных
            return user_id in content.mentions

        return False

    async def _can_comment_content(self, content: Content, user_id: int) -> bool:
        """Проверка прав на комментирование контента"""
        # Проверяем, может ли пользователь видеть контент
        if not await self._can_access_content(content, user_id):
            return False

        # Проверяем, разрешены ли комментарии
        # В реальной системе здесь может быть дополнительная логика
        return True

    async def _can_interact_with_content(self, content: Content, user_id: int) -> bool:
        """Проверка прав на взаимодействие с контентом (лайки, шеры и т.д.)"""
        return await self._can_access_content(content, user_id)

    async def _can_share_content(self, content: Content, user_id: int) -> bool:
        """Проверка прав на шеринг контента"""
        return await self._can_access_content(content, user_id)

    async def _increment_views(self, content_id: str):
        """Увеличение счетчика просмотров"""
        await redis_client.incr(f"content_views:{content_id}")

    async def _increment_comments_count(self, content_id: str):
        """Увеличение счетчика комментариев"""
        await redis_client.incr(f"content_comments_count:{content_id}")

    async def _increment_shares_count(self, content_id: str):
        """Увеличение счетчика шеров"""
        await redis_client.incr(f"content_shares_count:{content_id}")

    async def _update_reaction_counts(self, content_id: str, user_id: int, 
                                    reaction_type: str, increment: bool = True):
        """Обновление счетчиков реакций"""
        reaction_key = f"content_reactions:{content_id}:{reaction_type}"
        user_reactions_key = f"user_reactions:{user_id}:{content_id}"

        if increment:
            # Добавляем реакцию пользователя
            await redis_client.sadd(user_reactions_key, reaction_type)
            # Увеличиваем счетчик реакции
            await redis_client.incr(reaction_key)
        else:
            # Удаляем реакцию пользователя
            await redis_client.srem(user_reactions_key, reaction_type)
            # Уменьшаем счетчик реакции
            await redis_client.decr(reaction_key)

    async def _save_comment(self, comment: ContentComment):
        """Сохранение комментария"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO content_comments (
                    id, content_id, user_id, parent_comment_id, text, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                comment.id, comment.content_id, comment.user_id,
                comment.parent_comment_id, comment.text,
                comment.created_at, comment.updated_at
            )

    async def _save_reaction(self, reaction: ContentReaction):
        """Сохранение реакции"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO content_reactions (
                    id, content_id, user_id, reaction_type, created_at
                ) VALUES ($1, $2, $3, $4, $5)
                """,
                reaction.id, reaction.content_id, reaction.user_id,
                reaction.reaction_type, reaction.created_at
            )

    async def _save_share(self, share: ContentShare):
        """Сохранение шера"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO content_shares (
                    id, content_id, user_id, target_type, target_id, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                share.id, share.content_id, share.user_id,
                share.target_type, share.target_id, share.created_at
            )

    async def _cache_content(self, content: Content):
        """Кэширование контента"""
        await redis_client.setex(f"content:{content.id}", 300, content.model_dump_json())

    async def _get_cached_content(self, content_id: str) -> Optional[Content]:
        """Получение контента из кэша"""
        cached = await redis_client.get(f"content:{content_id}")
        if cached:
            return Content(**json.loads(cached))
        return None

    async def _uncache_content(self, content_id: str):
        """Удаление контента из кэша"""
        await redis_client.delete(f"content:{content_id}")

    async def _delete_related_data(self, content_id: str):
        """Удаление связанных данных с контентом"""
        # Удаляем комментарии
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM content_comments WHERE content_id = $1", content_id)
            await conn.execute("DELETE FROM content_reactions WHERE content_id = $1", content_id)
            await conn.execute("DELETE FROM content_shares WHERE content_id = $1", content_id)

        # Удаляем из кэша
        await redis_client.delete(f"content_comments_count:{content_id}")
        await redis_client.delete(f"content_shares_count:{content_id}")
        await redis_client.delete(f"content_likes_count:{content_id}")

    async def _notify_content_created(self, content: Content):
        """Уведомление о создании контента"""
        notification = {
            'type': 'content_created',
            'content_id': content.id,
            'author_id': content.user_id,
            'title': content.title,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление подписчикам автора
        await self._send_notification_to_followers(content.user_id, notification)

        # Если контент привязан к чату, отправляем в чат
        if content.chat_id:
            await self._send_notification_to_chat(content.chat_id, notification)

    async def _notify_content_updated(self, content: Content):
        """Уведомление об обновлении контента"""
        notification = {
            'type': 'content_updated',
            'content_id': content.id,
            'author_id': content.user_id,
            'title': content.title,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление тем, кто взаимодействовал с контентом
        await self._send_notification_to_interactors(content.id, notification)

    async def _notify_content_published(self, content: Content):
        """Уведомление о публикации контента"""
        notification = {
            'type': 'content_published',
            'content_id': content.id,
            'author_id': content.user_id,
            'title': content.title,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление подписчикам автора
        await self._send_notification_to_followers(content.user_id, notification)

    async def _notify_content_deleted(self, content: Content):
        """Уведомление об удалении контента"""
        notification = {
            'type': 'content_deleted',
            'content_id': content.id,
            'author_id': content.user_id,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление тем, кто взаимодействовал с контентом
        await self._send_notification_to_interactors(content.id, notification)

    async def _notify_comment_added(self, content: Content, comment: ContentComment):
        """Уведомление о добавлении комментария"""
        notification = {
            'type': 'comment_added',
            'content_id': content.id,
            'comment_id': comment.id,
            'author_id': comment.user_id,
            'preview': comment.text[:50] + '...' if len(comment.text) > 50 else comment.text,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Уведомляем автора контента
        if comment.user_id != content.user_id:
            await self._send_notification_to_user(content.user_id, notification)

        # Уведомляем других комментаторов
        await self._send_notification_to_other_commentators(content.id, comment.user_id, notification)

    async def _notify_reaction_added(self, content: Content, reaction: ContentReaction):
        """Уведомление о добавлении реакции"""
        notification = {
            'type': 'reaction_added',
            'content_id': content.id,
            'user_id': reaction.user_id,
            'reaction_type': reaction.reaction_type,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Уведомляем автора контента
        if reaction.user_id != content.user_id:
            await self._send_notification_to_user(content.user_id, notification)

    async def _notify_content_shared(self, content: Content, share: ContentShare):
        """Уведомление о шеринге контента"""
        notification = {
            'type': 'content_shared',
            'content_id': content.id,
            'sharer_id': share.user_id,
            'target_type': share.target_type,
            'target_id': share.target_id,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Уведомляем автора контента
        if share.user_id != content.user_id:
            await self._send_notification_to_user(content.user_id, notification)

    async def _send_notification_to_user(self, user_id: int, notification: Dict[str, Any]):
        """Отправка уведомления пользователю"""
        channel = f"user:{user_id}:content"
        await redis_client.publish(channel, json.dumps(notification))

    async def _send_notification_to_followers(self, user_id: int, notification: Dict[str, Any]):
        """Отправка уведомления подписчикам пользователя"""
        # В реальной системе здесь будет получение списка подписчиков
        # и отправка уведомления каждому
        import logging
        logging.info(f"Sending notification to followers of user {user_id}")
        return True

    async def _send_notification_to_chat(self, chat_id: str, notification: Dict[str, Any]):
        """Отправка уведомления в чат"""
        channel = f"chat:{chat_id}:content"
        await redis_client.publish(channel, json.dumps(notification))

    async def _send_notification_to_interactors(self, content_id: str, notification: Dict[str, Any]):
        """Отправка уведомления тем, кто взаимодействовал с контентом"""
        # Получаем пользователей, которые комментировали или ставили реакции
        async with db_pool.acquire() as conn:
            commenters = await conn.fetch(
                "SELECT DISTINCT user_id FROM content_comments WHERE content_id = $1",
                content_id
            )
            reactors = await conn.fetch(
                "SELECT DISTINCT user_id FROM content_reactions WHERE content_id = $1",
                content_id
            )

        all_interactors = set()
        all_interactors.update([row['user_id'] for row in commenters])
        all_interactors.update([row['user_id'] for row in reactors])

        for user_id in all_interactors:
            await self._send_notification_to_user(user_id, notification)

    async def _send_notification_to_other_commentators(self, content_id: str, excluding_user_id: int, 
                                                    notification: Dict[str, Any]):
        """Отправка уведомления другим комментаторам"""
        async with db_pool.acquire() as conn:
            other_commentators = await conn.fetch(
                "SELECT DISTINCT user_id FROM content_comments WHERE content_id = $1 AND user_id != $2",
                content_id, excluding_user_id
            )

        for row in other_commentators:
            await self._send_notification_to_user(row['user_id'], notification)

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
content_management_service = ContentManagementService()
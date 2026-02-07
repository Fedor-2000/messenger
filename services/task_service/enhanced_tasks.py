# Enhanced Task Management System
# File: services/task_service/enhanced_tasks.py

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

class TaskPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class TaskStatus(Enum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"

class TaskType(Enum):
    PERSONAL = "personal"
    GROUP = "group"
    PROJECT = "project"
    CHAT = "chat"
    AUTOMATED = "automated"  # Задачи, созданные AI-ассистентом

class TaskVisibility(Enum):
    PRIVATE = "private"
    TEAM = "team"
    PUBLIC = "public"

class TaskDependencyType(Enum):
    BLOCKS = "blocks"  # Задача A блокирует задачу B
    DEPENDS_ON = "depends_on"  # Задача A зависит от задачи B
    RELATED_TO = "related_to"  # Задача A связана с задачей B

class Task(BaseModel):
    id: str
    title: str
    description: str
    assignee_ids: List[int]  # Можно назначить нескольким пользователям
    creator_id: int
    due_date: Optional[datetime] = None
    priority: TaskPriority
    status: TaskStatus
    task_type: TaskType
    visibility: TaskVisibility
    chat_id: Optional[str] = None
    group_id: Optional[str] = None
    project_id: Optional[str] = None
    parent_task_id: Optional[str] = None  # Для подзадач
    estimated_hours: Optional[float] = None
    actual_hours: Optional[float] = None
    tags: List[str] = []
    attachments: List[Dict] = []  # [{'id': 'file_id', 'name': 'file_name'}]
    subtasks: List[str] = []  # IDs of subtasks
    dependencies: List[Dict] = []  # [{'task_id': 'id', 'type': 'dependency_type'}]
    created_at: datetime = None
    updated_at: datetime = None
    completed_at: Optional[datetime] = None
    kanban_column: str = "todo"  # Для Kanban доски

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_ids: Optional[List[int]] = None
    due_date: Optional[datetime] = None
    priority: Optional[TaskPriority] = None
    status: Optional[TaskStatus] = None
    visibility: Optional[TaskVisibility] = None
    estimated_hours: Optional[float] = None
    tags: Optional[List[str]] = None
    kanban_column: Optional[str] = None

class TaskComment(BaseModel):
    id: str
    task_id: str
    user_id: int
    content: str
    created_at: datetime = None
    updated_at: datetime = None

class TaskActivity(BaseModel):
    id: str
    task_id: str
    user_id: int
    action: str  # created, updated, assigned, completed, etc.
    details: Dict
    created_at: datetime = None

class EnhancedTaskService:
    def __init__(self):
        self.db_pool = None
        self.redis_client = None
        self.active_tasks = {}

    async def create_task(self, title: str, description: str, creator_id: int,
                         assignee_ids: List[int], task_type: TaskType,
                         due_date: Optional[datetime] = None,
                         priority: TaskPriority = TaskPriority.MEDIUM,
                         visibility: TaskVisibility = TaskVisibility.PRIVATE,
                         chat_id: Optional[str] = None,
                         group_id: Optional[str] = None,
                         project_id: Optional[str] = None,
                         parent_task_id: Optional[str] = None,
                         estimated_hours: Optional[float] = None,
                         tags: Optional[List[str]] = None) -> Optional[Task]:
        """Создание новой задачи"""
        task_id = str(uuid.uuid4())
        
        task = Task(
            id=task_id,
            title=title,
            description=description,
            assignee_ids=assignee_ids,
            creator_id=creator_id,
            due_date=due_date,
            priority=priority,
            status=TaskStatus.TODO,
            task_type=task_type,
            visibility=visibility,
            chat_id=chat_id,
            group_id=group_id,
            project_id=project_id,
            parent_task_id=parent_task_id,
            estimated_hours=estimated_hours,
            tags=tags or [],
            attachments=[],
            subtasks=[],
            dependencies=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем задачу в базу данных
        await self._save_task_to_db(task)

        # Добавляем в кэш
        await self._cache_task(task)

        # Уведомляем заинтересованные стороны
        await self._notify_task_created(task)

        # Создаем запись активности
        await self._log_activity(task.id, creator_id, "created", {
            "title": task.title,
            "assignees": task.assignee_ids
        })

        return task

    async def _save_task_to_db(self, task: Task):
        """Сохранение задачи в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO tasks (
                    id, title, description, assignee_ids, creator_id,
                    due_date, priority, status, task_type, visibility,
                    chat_id, group_id, project_id, parent_task_id,
                    estimated_hours, actual_hours, tags, attachments,
                    subtasks, dependencies, created_at, updated_at,
                    completed_at, kanban_column
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 
                         $11, $12, $13, $14, $15, $16, $17, $18, 
                         $19, $20, $21, $22, $23, $24)
                """,
                task.id, task.title, task.description, task.assignee_ids,
                task.creator_id, task.due_date, task.priority.value,
                task.status.value, task.task_type.value, task.visibility.value,
                task.chat_id, task.group_id, task.project_id, task.parent_task_id,
                task.estimated_hours, task.actual_hours, task.tags,
                json.dumps(task.attachments), task.subtasks,
                json.dumps(task.dependencies), task.created_at,
                task.updated_at, task.completed_at, task.kanban_column
            )

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Получение задачи по ID"""
        # Сначала проверяем кэш
        cached_task = await self._get_cached_task(task_id)
        if cached_task:
            return cached_task

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, title, description, assignee_ids, creator_id,
                       due_date, priority, status, task_type, visibility,
                       chat_id, group_id, project_id, parent_task_id,
                       estimated_hours, actual_hours, tags, attachments,
                       subtasks, dependencies, created_at, updated_at,
                       completed_at, kanban_column
                FROM tasks WHERE id = $1
                """,
                task_id
            )

        if not row:
            return None

        task = Task(
            id=row['id'],
            title=row['title'],
            description=row['description'],
            assignee_ids=row['assignee_ids'] or [],
            creator_id=row['creator_id'],
            due_date=row['due_date'],
            priority=TaskPriority(row['priority']),
            status=TaskStatus(row['status']),
            task_type=TaskType(row['task_type']),
            visibility=TaskVisibility(row['visibility']),
            chat_id=row['chat_id'],
            group_id=row['group_id'],
            project_id=row['project_id'],
            parent_task_id=row['parent_task_id'],
            estimated_hours=row['estimated_hours'],
            actual_hours=row['actual_hours'],
            tags=row['tags'] or [],
            attachments=json.loads(row['attachments']) if row['attachments'] else [],
            subtasks=row['subtasks'] or [],
            dependencies=json.loads(row['dependencies']) if row['dependencies'] else [],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            completed_at=row['completed_at'],
            kanban_column=row['kanban_column']
        )

        # Кэшируем задачу
        await self._cache_task(task)

        return task

    async def update_task(self, task_id: str, user_id: int, updates: TaskUpdate) -> bool:
        """Обновление задачи"""
        task = await self.get_task(task_id)
        if not task:
            return False

        # Проверяем права на обновление
        if not await self._can_update_task(task, user_id):
            return False

        # Обновляем поля задачи
        for field, value in updates.dict(exclude_unset=True).items():
            if value is not None:
                if field == 'priority' and isinstance(value, str):
                    setattr(task, field, TaskPriority(value))
                elif field == 'status' and isinstance(value, str):
                    setattr(task, field, TaskStatus(value))
                elif field == 'task_type' and isinstance(value, str):
                    setattr(task, field, TaskType(value))
                elif field == 'visibility' and isinstance(value, str):
                    setattr(task, field, TaskVisibility(value))
                else:
                    setattr(task, field, value)

        # Обновляем время обновления
        task.updated_at = datetime.utcnow()

        # Если статус изменился на "completed"
        if updates.status == TaskStatus.DONE:
            task.completed_at = datetime.utcnow()

        # Сохраняем в базу данных
        await self._update_task_in_db(task)

        # Обновляем кэш
        await self._cache_task(task)

        # Уведомляем заинтересованные стороны
        await self._notify_task_updated(task)

        # Создаем запись активности
        await self._log_activity(task.id, user_id, "updated", updates.dict(exclude_unset=True))

        return True

    async def _update_task_in_db(self, task: Task):
        """Обновление задачи в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE tasks SET
                    title = $2, description = $3, assignee_ids = $4,
                    due_date = $5, priority = $6, status = $7,
                    visibility = $8, estimated_hours = $9, actual_hours = $10,
                    tags = $11, updated_at = $12, completed_at = $13,
                    kanban_column = $14
                WHERE id = $1
                """,
                task.id, task.title, task.description, task.assignee_ids,
                task.due_date, task.priority.value, task.status.value,
                task.visibility.value, task.estimated_hours, task.actual_hours,
                task.tags, task.updated_at, task.completed_at, task.kanban_column
            )

    async def delete_task(self, task_id: str, user_id: int) -> bool:
        """Удаление задачи"""
        task = await self.get_task(task_id)
        if not task:
            return False

        # Проверяем права на удаление
        if not await self._can_delete_task(task, user_id):
            return False

        # Удаляем из базы данных
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)

        # Удаляем из кэша
        await self._uncache_task(task_id)

        # Удаляем подзадачи
        await self._delete_subtasks(task_id)

        # Удаляем зависимости
        await self._remove_dependencies(task_id)

        # Уведомляем заинтересованные стороны
        await self._notify_task_deleted(task)

        # Создаем запись активности
        await self._log_activity(task_id, user_id, "deleted", {})

        return True

    async def assign_task(self, task_id: str, assignee_ids: List[int], user_id: int) -> bool:
        """Назначение задачи пользователю"""
        task = await self.get_task(task_id)
        if not task:
            return False

        # Проверяем права на назначение
        if not await self._can_assign_task(task, user_id):
            return False

        old_assignees = task.assignee_ids[:]
        task.assignee_ids = assignee_ids
        task.updated_at = datetime.utcnow()

        # Сохраняем в базу данных
        await self._update_task_in_db(task)

        # Обновляем кэш
        await self._cache_task(task)

        # Уведомляем заинтересованные стороны
        await self._notify_task_assigned(task, old_assignees)

        # Создаем запись активности
        await self._log_activity(task.id, user_id, "assigned", {
            "old_assignees": old_assignees,
            "new_assignees": assignee_ids
        })

        return True

    async def complete_task(self, task_id: str, user_id: int) -> bool:
        """Отметка задачи как выполненной"""
        task = await self.get_task(task_id)
        if not task:
            return False

        # Проверяем права на завершение
        if not await self._can_complete_task(task, user_id):
            return False

        task.status = TaskStatus.DONE
        task.completed_at = datetime.utcnow()
        task.updated_at = datetime.utcnow()

        # Обновляем в базе данных
        await self._update_task_in_db(task)

        # Обновляем кэш
        await self._cache_task(task)

        # Уведомляем заинтересованные стороны
        await self._notify_task_completed(task)

        # Создаем запись активности
        await self._log_activity(task.id, user_id, "completed", {})

        # Обновляем статус родительской задачи, если все подзадачи выполнены
        if task.parent_task_id:
            await self._update_parent_task_status(task.parent_task_id)

        return True

    async def create_subtask(self, parent_task_id: str, title: str, description: str,
                           creator_id: int, assignee_ids: List[int]) -> Optional[str]:
        """Создание подзадачи"""
        parent_task = await self.get_task(parent_task_id)
        if not parent_task:
            return None

        # Создаем подзадачу с похожими параметрами
        subtask = await self.create_task(
            title=title,
            description=description,
            creator_id=creator_id,
            assignee_ids=assignee_ids,
            task_type=parent_task.task_type,
            due_date=parent_task.due_date,  # Наследуем срок
            priority=parent_task.priority,  # Наследуем приоритет
            visibility=parent_task.visibility,  # Наследуем видимость
            chat_id=parent_task.chat_id,
            group_id=parent_task.group_id,
            project_id=parent_task.project_id,
            parent_task_id=parent_task_id,
            estimated_hours=None  # Не наследуем оценку времени
        )

        if subtask:
            # Добавляем подзадачу к родительской задаче
            parent_task.subtasks.append(subtask.id)
            await self._update_task_in_db(parent_task)
            await self._cache_task(parent_task)

            # Создаем запись активности
            await self._log_activity(parent_task_id, creator_id, "subtask_created", {
                "subtask_id": subtask.id,
                "subtask_title": subtask.title
            })

        return subtask.id if subtask else None

    async def add_dependency(self, task_id: str, dependent_task_id: str, 
                           dependency_type: TaskDependencyType, user_id: int) -> bool:
        """Добавление зависимости между задачами"""
        task = await self.get_task(task_id)
        dependent_task = await self.get_task(dependent_task_id)
        
        if not task or not dependent_task:
            return False

        # Проверяем, не создастся ли цикл
        if await self._would_create_cycle(task_id, dependent_task_id):
            return False

        # Добавляем зависимость
        dependency = {
            'task_id': dependent_task_id,
            'type': dependency_type.value
        }
        
        if dependency not in task.dependencies:
            task.dependencies.append(dependency)
            task.updated_at = datetime.utcnow()

            # Сохраняем в базу данных
            await self._update_task_in_db(task)

            # Обновляем кэш
            await self._cache_task(task)

            # Создаем запись активности
            await self._log_activity(task.id, user_id, "dependency_added", {
                "dependent_task_id": dependent_task_id,
                "dependency_type": dependency_type.value
            })

        return True

    async def _would_create_cycle(self, task_id: str, dependent_task_id: str) -> bool:
        """Проверка, создаст ли добавление зависимости цикл"""
        # Реализация проверки цикла в зависимостях задач
        # Это упрощенная реализация - в реальности потребуется более сложный алгоритм
        visited = set()
        stack = [dependent_task_id]
        
        while stack:
            current_task_id = stack.pop()
            if current_task_id == task_id:
                return True  # Обнаружен цикл
            
            if current_task_id in visited:
                continue
            
            visited.add(current_task_id)
            
            current_task = await self.get_task(current_task_id)
            if current_task:
                for dep in current_task.dependencies:
                    stack.append(dep['task_id'])
        
        return False

    async def _update_parent_task_status(self, parent_task_id: str):
        """Обновление статуса родительской задачи на основе подзадач"""
        parent_task = await self.get_task(parent_task_id)
        if not parent_task or not parent_task.subtasks:
            return

        # Получаем все подзадачи
        subtasks = []
        for subtask_id in parent_task.subtasks:
            subtask = await self.get_task(subtask_id)
            if subtask:
                subtasks.append(subtask)

        # Проверяем статусы подзадач
        all_completed = all(subtask.status == TaskStatus.DONE for subtask in subtasks)
        any_cancelled = any(subtask.status == TaskStatus.CANCELLED for subtask in subtasks)
        any_in_progress = any(subtask.status in [TaskStatus.IN_PROGRESS, TaskStatus.REVIEW] for subtask in subtasks)

        new_status = None
        if all_completed:
            new_status = TaskStatus.DONE
        elif any_cancelled:
            new_status = TaskStatus.CANCELLED
        elif any_in_progress:
            new_status = TaskStatus.IN_PROGRESS
        else:
            new_status = TaskStatus.TODO

        if new_status and parent_task.status != new_status:
            # Обновляем статус родительской задачи
            parent_task.status = new_status
            parent_task.updated_at = datetime.utcnow()

            # Сохраняем в базу данных
            await self._update_task_in_db(parent_task)

            # Обновляем кэш
            await self._cache_task(parent_task)

            # Создаем запись активности
            await self._log_activity(parent_task_id, parent_task.creator_id, "status_changed", {
                "old_status": parent_task.status.value,
                "new_status": new_status.value
            })

    async def get_user_tasks(self, user_id: int, status: Optional[TaskStatus] = None,
                           task_type: Optional[TaskType] = None,
                           limit: int = 50, offset: int = 0) -> List[Task]:
        """Получение задач пользователя"""
        conditions = ["($1 = ANY(assignee_ids) OR creator_id = $1)"]
        params = [user_id]
        param_idx = 2

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        if task_type:
            conditions.append(f"task_type = ${param_idx}")
            params.append(task_type.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT id, title, description, assignee_ids, creator_id,
                   due_date, priority, status, task_type, visibility,
                   chat_id, group_id, project_id, parent_task_id,
                   estimated_hours, actual_hours, tags, attachments,
                   subtasks, dependencies, created_at, updated_at,
                   completed_at, kanban_column
            FROM tasks
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        tasks = []
        for row in rows:
            task = Task(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                assignee_ids=row['assignee_ids'] or [],
                creator_id=row['creator_id'],
                due_date=row['due_date'],
                priority=TaskPriority(row['priority']),
                status=TaskStatus(row['status']),
                task_type=TaskType(row['task_type']),
                visibility=TaskVisibility(row['visibility']),
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                parent_task_id=row['parent_task_id'],
                estimated_hours=row['estimated_hours'],
                actual_hours=row['actual_hours'],
                tags=row['tags'] or [],
                attachments=json.loads(row['attachments']) if row['attachments'] else [],
                subtasks=row['subtasks'] or [],
                dependencies=json.loads(row['dependencies']) if row['dependencies'] else [],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                completed_at=row['completed_at'],
                kanban_column=row['kanban_column']
            )
            tasks.append(task)

        return tasks

    async def get_project_tasks(self, project_id: str, status: Optional[TaskStatus] = None,
                              limit: int = 50, offset: int = 0) -> List[Task]:
        """Получение задач проекта"""
        conditions = ["project_id = $1"]
        params = [project_id]
        param_idx = 2

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT id, title, description, assignee_ids, creator_id,
                   due_date, priority, status, task_type, visibility,
                   chat_id, group_id, project_id, parent_task_id,
                   estimated_hours, actual_hours, tags, attachments,
                   subtasks, dependencies, created_at, updated_at,
                   completed_at, kanban_column
            FROM tasks
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        tasks = []
        for row in rows:
            task = Task(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                assignee_ids=row['assignee_ids'] or [],
                creator_id=row['creator_id'],
                due_date=row['due_date'],
                priority=TaskPriority(row['priority']),
                status=TaskStatus(row['status']),
                task_type=TaskType(row['task_type']),
                visibility=TaskVisibility(row['visibility']),
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                parent_task_id=row['parent_task_id'],
                estimated_hours=row['estimated_hours'],
                actual_hours=row['actual_hours'],
                tags=row['tags'] or [],
                attachments=json.loads(row['attachments']) if row['attachments'] else [],
                subtasks=row['subtasks'] or [],
                dependencies=json.loads(row['dependencies']) if row['dependencies'] else [],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                completed_at=row['completed_at'],
                kanban_column=row['kanban_column']
            )
            tasks.append(task)

        return tasks

    async def get_kanban_board(self, project_id: str) -> Dict[str, List[Task]]:
        """Получение Kanban доски для проекта"""
        query = """
            SELECT id, title, description, assignee_ids, creator_id,
                   due_date, priority, status, task_type, visibility,
                   chat_id, group_id, project_id, parent_task_id,
                   estimated_hours, actual_hours, tags, attachments,
                   subtasks, dependencies, created_at, updated_at,
                   completed_at, kanban_column
            FROM tasks
            WHERE project_id = $1
            ORDER BY updated_at DESC
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, project_id)

        # Группируем задачи по колонкам Kanban
        kanban_board = {
            'backlog': [],
            'todo': [],
            'in_progress': [],
            'review': [],
            'done': []
        }

        for row in rows:
            task = Task(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                assignee_ids=row['assignee_ids'] or [],
                creator_id=row['creator_id'],
                due_date=row['due_date'],
                priority=TaskPriority(row['priority']),
                status=TaskStatus(row['status']),
                task_type=TaskType(row['task_type']),
                visibility=TaskVisibility(row['visibility']),
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                parent_task_id=row['parent_task_id'],
                estimated_hours=row['estimated_hours'],
                actual_hours=row['actual_hours'],
                tags=row['tags'] or [],
                attachments=json.loads(row['attachments']) if row['attachments'] else [],
                subtasks=row['subtasks'] or [],
                dependencies=json.loads(row['dependencies']) if row['dependencies'] else [],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                completed_at=row['completed_at'],
                kanban_column=row['kanban_column']
            )
            
            column = task.kanban_column
            if column in kanban_board:
                kanban_board[column].append(task)

        return kanban_board

    async def add_comment(self, task_id: str, user_id: int, content: str) -> Optional[TaskComment]:
        """Добавление комментария к задаче"""
        task = await self.get_task(task_id)
        if not task:
            return None

        comment_id = str(uuid.uuid4())
        comment = TaskComment(
            id=comment_id,
            task_id=task_id,
            user_id=user_id,
            content=content,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем комментарий в базу данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO task_comments (id, task_id, user_id, content, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                comment.id, comment.task_id, comment.user_id, comment.content,
                comment.created_at, comment.updated_at
            )

        # Уведомляем участников задачи
        await self._notify_task_commented(task, comment)

        # Создаем запись активности
        await self._log_activity(task_id, user_id, "commented", {
            "comment_id": comment_id,
            "content_preview": content[:50]
        })

        return comment

    async def get_task_comments(self, task_id: str, limit: int = 50, offset: int = 0) -> List[TaskComment]:
        """Получение комментариев к задаче"""
        query = """
            SELECT id, task_id, user_id, content, created_at, updated_at
            FROM task_comments
            WHERE task_id = $1
            ORDER BY created_at ASC
            LIMIT $2 OFFSET $3
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, task_id, limit, offset)

        comments = []
        for row in rows:
            comment = TaskComment(
                id=row['id'],
                task_id=row['task_id'],
                user_id=row['user_id'],
                content=row['content'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            comments.append(comment)

        return comments

    async def _log_activity(self, task_id: str, user_id: int, action: str, details: Dict):
        """Логирование активности по задаче"""
        activity_id = str(uuid.uuid4())
        activity = TaskActivity(
            id=activity_id,
            task_id=task_id,
            user_id=user_id,
            action=action,
            details=details,
            created_at=datetime.utcnow()
        )

        # Сохраняем активность в базу данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO task_activities (id, task_id, user_id, action, details, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                activity.id, activity.task_id, activity.user_id, 
                activity.action, json.dumps(activity.details), activity.created_at
            )

    async def get_task_activities(self, task_id: str, limit: int = 50, offset: int = 0) -> List[TaskActivity]:
        """Получение активности по задаче"""
        query = """
            SELECT id, task_id, user_id, action, details, created_at
            FROM task_activities
            WHERE task_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, task_id, limit, offset)

        activities = []
        for row in rows:
            activity = TaskActivity(
                id=row['id'],
                task_id=row['task_id'],
                user_id=row['user_id'],
                action=row['action'],
                details=json.loads(row['details']),
                created_at=row['created_at']
            )
            activities.append(activity)

        return activities

    async def _can_update_task(self, task: Task, user_id: int) -> bool:
        """Проверка прав на обновление задачи"""
        # Права на обновление: создатель, назначенный пользователь или администратор
        return (task.creator_id == user_id or 
                user_id in task.assignee_ids or 
                await self._is_admin(user_id, task))

    async def _can_delete_task(self, task: Task, user_id: int) -> bool:
        """Проверка прав на удаление задачи"""
        # Права на удаление: только создатель или администратор
        return (task.creator_id == user_id or 
                await self._is_admin(user_id, task))

    async def _can_assign_task(self, task: Task, user_id: int) -> bool:
        """Проверка прав на назначение задачи"""
        # Права на назначение: создатель, администратор или менеджер проекта
        return (task.creator_id == user_id or 
                await self._is_admin(user_id, task) or
                await self._is_project_manager(user_id, task))

    async def _can_complete_task(self, task: Task, user_id: int) -> bool:
        """Проверка прав на завершение задачи"""
        # Права на завершение: назначенный пользователь, создатель или администратор
        return (user_id in task.assignee_ids or 
                task.creator_id == user_id or 
                await self._is_admin(user_id, task))

    async def _is_admin(self, user_id: int, task: Task) -> bool:
        """Проверка, является ли пользователь администратором"""
        # В реальном приложении здесь будет проверка прав пользователя
        return False

    async def _is_project_manager(self, user_id: int, task: Task) -> bool:
        """Проверка, является ли пользователь менеджером проекта"""
        # В реальном приложении здесь будет проверка прав пользователя
        return False

    async def _cache_task(self, task: Task):
        """Кэширование задачи"""
        await redis_client.setex(f"task:{task.id}", 300, task.model_dump_json())

    async def _get_cached_task(self, task_id: str) -> Optional[Task]:
        """Получение задачи из кэша"""
        cached = await redis_client.get(f"task:{task_id}")
        if cached:
            return Task(**json.loads(cached))
        return None

    async def _uncache_task(self, task_id: str):
        """Удаление задачи из кэша"""
        await redis_client.delete(f"task:{task_id}")

    async def _delete_subtasks(self, parent_task_id: str):
        """Удаление всех подзадач"""
        # Получаем все подзадачи
        async with db_pool.acquire() as conn:
            subtask_ids = await conn.fetchval(
                "SELECT subtasks FROM tasks WHERE id = $1", parent_task_id
            )
        
        if subtask_ids:
            for subtask_id in subtask_ids:
                await self.delete_task(subtask_id, -1)  # -1 означает системное удаление

    async def _remove_dependencies(self, task_id: str):
        """Удаление зависимостей от задачи"""
        # Удаляем зависимости, где эта задача является зависимой
        async with db_pool.acquire() as conn:
            # Получаем задачи, которые зависят от этой
            dependent_tasks = await conn.fetch(
                """
                SELECT id, dependencies FROM tasks 
                WHERE $1 = ANY(SELECT jsonb_array_elements_text(dependencies->'task_id'))
                """,
                task_id
            )
            
            for row in dependent_tasks:
                task_id_to_update = row['id']
                dependencies = json.loads(row['dependencies']) if row['dependencies'] else []
                # Удаляем зависимость
                dependencies = [dep for dep in dependencies if dep['task_id'] != task_id]
                
                # Обновляем задачу
                await conn.execute(
                    "UPDATE tasks SET dependencies = $1 WHERE id = $2",
                    json.dumps(dependencies), task_id_to_update
                )
                
                # Обновляем кэш
                await self._uncache_task(task_id_to_update)

    async def _notify_task_created(self, task: Task):
        """Уведомление о создании задачи"""
        notification = {
            'type': 'task_created',
            'task': self._task_to_dict(task),
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление назначенным пользователям
        for assignee_id in task.assignee_ids:
            await self._send_notification_to_user(assignee_id, notification)

        # Если задача связана с чатом, отправляем в чат
        if task.chat_id:
            await self._send_notification_to_chat(task.chat_id, notification)

    async def _notify_task_updated(self, task: Task):
        """Уведомление об обновлении задачи"""
        notification = {
            'type': 'task_updated',
            'task': self._task_to_dict(task),
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление заинтересованным пользователям
        all_relevant_users = set(task.assignee_ids + [task.creator_id])
        for user_id in all_relevant_users:
            await self._send_notification_to_user(user_id, notification)

        # Если задача связана с чатом, отправляем в чат
        if task.chat_id:
            await self._send_notification_to_chat(task.chat_id, notification)

    async def _notify_task_assigned(self, task: Task, old_assignees: List[int]):
        """Уведомление о назначении задачи"""
        notification = {
            'type': 'task_assigned',
            'task': self._task_to_dict(task),
            'old_assignees': old_assignees,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление новым назначенным
        for assignee_id in task.assignee_ids:
            if assignee_id not in old_assignees:
                await self._send_notification_to_user(assignee_id, notification)

        # Отправляем уведомление создателю и старым назначенным
        await self._send_notification_to_user(task.creator_id, notification)
        for old_assignee in old_assignees:
            if old_assignee not in task.assignee_ids:
                await self._send_notification_to_user(old_assignee, notification)

    async def _notify_task_completed(self, task: Task):
        """Уведомление о завершении задачи"""
        notification = {
            'type': 'task_completed',
            'task': self._task_to_dict(task),
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление всем заинтересованным
        all_relevant_users = set(task.assignee_ids + [task.creator_id])
        for user_id in all_relevant_users:
            await self._send_notification_to_user(user_id, notification)

        # Если задача связана с чатом, отправляем в чат
        if task.chat_id:
            await self._send_notification_to_chat(task.chat_id, notification)

    async def _notify_task_deleted(self, task: Task):
        """Уведомление об удалении задачи"""
        notification = {
            'type': 'task_deleted',
            'task_id': task.id,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление заинтересованным пользователям
        all_relevant_users = set(task.assignee_ids + [task.creator_id])
        for user_id in all_relevant_users:
            await self._send_notification_to_user(user_id, notification)

        # Если задача связана с чатом, отправляем в чат
        if task.chat_id:
            await self._send_notification_to_chat(task.chat_id, notification)

    async def _notify_task_commented(self, task: Task, comment: TaskComment):
        """Уведомление о комментарии к задаче"""
        notification = {
            'type': 'task_commented',
            'task_id': task.id,
            'comment': {
                'id': comment.id,
                'user_id': comment.user_id,
                'content': comment.content,
                'created_at': comment.created_at.isoformat()
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление всем заинтересованным
        all_relevant_users = set(task.assignee_ids + [task.creator_id])
        for user_id in all_relevant_users:
            if user_id != comment.user_id:  # Не отправляем автору комментария
                await self._send_notification_to_user(user_id, notification)

    async def _send_notification_to_user(self, user_id: int, notification: Dict[str, any]):
        """Отправка уведомления пользователю"""
        channel = f"user:{user_id}:tasks"
        await redis_client.publish(channel, json.dumps(notification))

    async def _send_notification_to_chat(self, chat_id: str, notification: Dict[str, any]):
        """Отправка уведомления в чат"""
        channel = f"chat:{chat_id}:tasks"
        await redis_client.publish(channel, json.dumps(notification))

    def _task_to_dict(self, task: Task) -> Dict[str, any]:
        """Конвертация задачи в словарь для отправки"""
        return {
            'id': task.id,
            'title': task.title,
            'description': task.description,
            'assignee_ids': task.assignee_ids,
            'creator_id': task.creator_id,
            'due_date': task.due_date.isoformat() if task.due_date else None,
            'priority': task.priority.value,
            'status': task.status.value,
            'task_type': task.task_type.value,
            'visibility': task.visibility.value,
            'chat_id': task.chat_id,
            'group_id': task.group_id,
            'project_id': task.project_id,
            'parent_task_id': task.parent_task_id,
            'estimated_hours': task.estimated_hours,
            'actual_hours': task.actual_hours,
            'tags': task.tags,
            'subtasks_count': len(task.subtasks) if task.subtasks else 0,
            'dependencies_count': len(task.dependencies) if task.dependencies else 0,
            'attachments_count': len(task.attachments) if task.attachments else 0,
            'created_at': task.created_at.isoformat() if task.created_at else None,
            'updated_at': task.updated_at.isoformat() if task.updated_at else None,
            'completed_at': task.completed_at.isoformat() if task.completed_at else None,
            'kanban_column': task.kanban_column
        }

# Глобальный экземпляр для использования в приложении
enhanced_task_service = EnhancedTaskService()
# Task and Project Management Enhancement System
# File: services/task_service/task_project_enhancement.py

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
import aiohttp
from aiohttp import web
import aioredis

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
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    ARCHIVED = "archived"
    CANCELLED = "cancelled"

class TaskType(Enum):
    PERSONAL = "personal"
    GROUP = "group"
    PROJECT = "project"
    SHARED = "shared"

class ProjectStatus(Enum):
    PLANNING = "planning"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class TaskLabel(Enum):
    BUG = "bug"
    FEATURE = "feature"
    IMPROVEMENT = "improvement"
    MAINTENANCE = "maintenance"
    DESIGN = "design"
    DEVELOPMENT = "development"
    TESTING = "testing"
    DOCUMENTATION = "documentation"

class Task(BaseModel):
    id: str
    title: str
    description: str
    type: TaskType
    status: TaskStatus
    priority: TaskPriority
    creator_id: int
    assignee_ids: List[int] = []
    project_id: Optional[str] = None
    group_id: Optional[str] = None
    chat_id: Optional[str] = None
    due_date: Optional[datetime] = None
    estimated_hours: Optional[float] = None
    actual_hours: Optional[float] = None
    tags: List[str] = []
    labels: List[TaskLabel] = []
    parent_task_id: Optional[str] = None  # Для подзадач
    subtasks: List[str] = []  # IDs подзадач
    dependencies: List[str] = []  # IDs зависимых задач
    attachments: List[Dict[str, Any]] = []  # [{'id': 'file_id', 'name': 'file_name', 'type': 'image'}]
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime = None
    updated_at: datetime = None
    completed_at: Optional[datetime] = None

class Project(BaseModel):
    id: str
    name: str
    description: str
    owner_id: int
    members: List[Dict[str, Any]] = []  # [{'user_id': id, 'role': role, 'joined_at': timestamp}]
    status: ProjectStatus
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    budget: Optional[float] = None
    spent_budget: Optional[float] = None
    tags: List[str] = []
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime = None
    updated_at: datetime = None
    completed_at: Optional[datetime] = None

class TaskBoardColumn(BaseModel):
    id: str
    name: str
    status: TaskStatus
    position: int
    task_ids: List[str] = []
    created_at: datetime = None
    updated_at: datetime = None

class TaskComment(BaseModel):
    id: str
    task_id: str
    user_id: int
    content: str
    parent_comment_id: Optional[str] = None  # Для вложенных комментариев
    created_at: datetime = None
    updated_at: datetime = None

class TaskActivity(BaseModel):
    id: str
    task_id: str
    user_id: int
    action: str  # 'created', 'updated', 'assigned', 'completed', 'commented', etc.
    details: Dict[str, Any]
    created_at: datetime = None

class TaskProjectEnhancementService:
    def __init__(self):
        self.default_task_labels = [
            TaskLabel.BUG, TaskLabel.FEATURE, TaskLabel.IMPROVEMENT,
            TaskLabel.MAINTENANCE, TaskLabel.DESIGN, TaskLabel.DEVELOPMENT,
            TaskLabel.TESTING, TaskLabel.DOCUMENTATION
        ]
        
        self.default_project_statuses = [
            ProjectStatus.PLANNING, ProjectStatus.ACTIVE, ProjectStatus.ON_HOLD,
            ProjectStatus.COMPLETED, ProjectStatus.CANCELLED
        ]
        
        self.default_task_statuses = [
            TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW,
            TaskStatus.DONE, TaskStatus.ARCHIVED, TaskStatus.CANCELLED
        ]
        
        self.default_task_priorities = [
            TaskPriority.LOW, TaskPriority.MEDIUM, TaskPriority.HIGH, TaskPriority.URGENT
        ]
        
        self.task_workflow_templates = {
            'software_development': [
                TaskBoardColumn(id='todo', name='To Do', status=TaskStatus.TODO, position=0),
                TaskBoardColumn(id='in_progress', name='In Progress', status=TaskStatus.IN_PROGRESS, position=1),
                TaskBoardColumn(id='review', name='Review', status=TaskStatus.REVIEW, position=2),
                TaskBoardColumn(id='done', name='Done', status=TaskStatus.DONE, position=3)
            ],
            'content_creation': [
                TaskBoardColumn(id='planning', name='Planning', status=TaskStatus.TODO, position=0),
                TaskBoardColumn(id='draft', name='Draft', status=TaskStatus.IN_PROGRESS, position=1),
                TaskBoardColumn(id='editing', name='Editing', status=TaskStatus.REVIEW, position=2),
                TaskBoardColumn(id='published', name='Published', status=TaskStatus.DONE, position=3)
            ],
            'event_planning': [
                TaskBoardColumn(id='ideas', name='Ideas', status=TaskStatus.TODO, position=0),
                TaskBoardColumn(id='planning', name='Planning', status=TaskStatus.IN_PROGRESS, position=1),
                TaskBoardColumn(id='coordination', name='Coordination', status=TaskStatus.REVIEW, position=2),
                TaskBoardColumn(id='executed', name='Executed', status=TaskStatus.DONE, position=3)
            ]
        }

    async def initialize_task_system(self):
        """Инициализация системы задач и проектов"""
        # Создаем шаблоны рабочих процессов по умолчанию
        await self._create_default_workflows()
        
        # Создаем индексы для оптимизации запросов
        await self._create_task_indexes()
        
        logger.info("Task and project enhancement system initialized")

    async def _create_default_workflows(self):
        """Создание шаблонов рабочих процессов по умолчанию"""
        for template_name, columns in self.task_workflow_templates.items():
            for column in columns:
                await self._save_board_column(column)

    async def _create_task_indexes(self):
        """Создание индексов для оптимизации запросов задач"""
        async with db_pool.acquire() as conn:
            # Индекс для быстрого поиска задач по статусу и приоритету
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks(status, priority);
            """)
            
            # Индекс для быстрого поиска задач по проекту
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
            """)
            
            # Индекс для быстрого поиска задач по исполнителю
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks USING gin(assignee_ids);
            """)
            
            # Индекс для быстрого поиска задач по дате выполнения
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
            """)

    async def create_task(self, title: str, description: str, creator_id: int,
                         task_type: TaskType = TaskType.PERSONAL,
                         assignee_ids: Optional[List[int]] = None,
                         project_id: Optional[str] = None,
                         group_id: Optional[str] = None,
                         chat_id: Optional[str] = None,
                         due_date: Optional[datetime] = None,
                         estimated_hours: Optional[float] = None,
                         priority: TaskPriority = TaskPriority.MEDIUM,
                         tags: Optional[List[str]] = None,
                         labels: Optional[List[TaskLabel]] = None,
                         parent_task_id: Optional[str] = None,
                         dependencies: Optional[List[str]] = None,
                         attachments: Optional[List[Dict[str, Any]]] = None,
                         metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Создание новой задачи"""
        task_id = str(uuid.uuid4())

        task = Task(
            id=task_id,
            title=title,
            description=description,
            type=task_type,
            status=TaskStatus.TODO,
            priority=priority,
            creator_id=creator_id,
            assignee_ids=assignee_ids or [],
            project_id=project_id,
            group_id=group_id,
            chat_id=chat_id,
            due_date=due_date,
            estimated_hours=estimated_hours,
            actual_hours=0.0,
            tags=tags or [],
            labels=labels or [],
            parent_task_id=parent_task_id,
            subtasks=[],
            dependencies=dependencies or [],
            attachments=attachments or [],
            metadata=metadata or {},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем задачу в базу данных
        await self._save_task_to_db(task)

        # Добавляем в кэш
        await self._cache_task(task)

        # Если задача назначена на проект, обновляем статистику проекта
        if project_id:
            await self._update_project_task_stats(project_id)

        # Уведомляем исполнителей о новой задаче
        await self._notify_task_assigned(task)

        # Создаем запись активности
        await self._log_activity(creator_id, "task_created", {
            "task_id": task_id,
            "title": title,
            "assignee_count": len(assignee_ids or []),
            "project_id": project_id
        })

        return task_id

    async def _save_task_to_db(self, task: Task):
        """Сохранение задачи в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO tasks (
                    id, title, description, type, status, priority, creator_id, assignee_ids,
                    project_id, group_id, chat_id, due_date, estimated_hours, actual_hours,
                    tags, labels, parent_task_id, subtasks, dependencies, attachments,
                    metadata, created_at, updated_at, completed_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24)
                """,
                task.id, task.title, task.description, task.type.value, task.status.value,
                task.priority.value, task.creator_id, task.assignee_ids, task.project_id,
                task.group_id, task.chat_id, task.due_date, task.estimated_hours,
                task.actual_hours, task.tags, [label.value for label in task.labels],
                task.parent_task_id, task.subtasks, task.dependencies, task.attachments,
                json.dumps(task.metadata) if task.metadata else None, task.created_at,
                task.updated_at, task.completed_at
            )

    async def _cache_task(self, task: Task):
        """Кэширование задачи"""
        await redis_client.setex(f"task:{task.id}", 300, task.model_dump_json())

    async def _get_cached_task(self, task_id: str) -> Optional[Task]:
        """Получение задачи из кэша"""
        cached = await redis_client.get(f"task:{task_id}")
        if cached:
            return Task(**json.loads(cached.decode()))
        return None

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
                SELECT id, title, description, type, status, priority, creator_id, assignee_ids,
                       project_id, group_id, chat_id, due_date, estimated_hours, actual_hours,
                       tags, labels, parent_task_id, subtasks, dependencies, attachments,
                       metadata, created_at, updated_at, completed_at
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
            type=TaskType(row['type']),
            status=TaskStatus(row['status']),
            priority=TaskPriority(row['priority']),
            creator_id=row['creator_id'],
            assignee_ids=row['assignee_ids'] or [],
            project_id=row['project_id'],
            group_id=row['group_id'],
            chat_id=row['chat_id'],
            due_date=row['due_date'],
            estimated_hours=row['estimated_hours'],
            actual_hours=row['actual_hours'],
            tags=row['tags'] or [],
            labels=[TaskLabel(label) for label in row['labels']] if row['labels'] else [],
            parent_task_id=row['parent_task_id'],
            subtasks=row['subtasks'] or [],
            dependencies=row['dependencies'] or [],
            attachments=row['attachments'] or [],
            metadata=json.loads(row['metadata']) if row['metadata'] else None,
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            completed_at=row['completed_at']
        )

        # Кэшируем задачу
        await self._cache_task(task)

        return task

    async def update_task(self, task_id: str, user_id: int, 
                         title: Optional[str] = None,
                         description: Optional[str] = None,
                         status: Optional[TaskStatus] = None,
                         priority: Optional[TaskPriority] = None,
                         assignee_ids: Optional[List[int]] = None,
                         due_date: Optional[datetime] = None,
                         estimated_hours: Optional[float] = None,
                         tags: Optional[List[str]] = None,
                         labels: Optional[List[TaskLabel]] = None,
                         attachments: Optional[List[Dict[str, Any]]] = None) -> bool:
        """Обновление задачи"""
        task = await self.get_task(task_id)
        if not task:
            return False

        # Проверяем права на обновление задачи
        if not await self._can_update_task(task, user_id):
            return False

        # Обновляем поля задачи
        if title is not None:
            task.title = title
        if description is not None:
            task.description = description
        if status is not None:
            task.status = status
            if status == TaskStatus.DONE:
                task.completed_at = datetime.utcnow()
        if priority is not None:
            task.priority = priority
        if assignee_ids is not None:
            task.assignee_ids = assignee_ids
        if due_date is not None:
            task.due_date = due_date
        if estimated_hours is not None:
            task.estimated_hours = estimated_hours
        if tags is not None:
            task.tags = tags
        if labels is not None:
            task.labels = labels
        if attachments is not None:
            task.attachments = attachments

        task.updated_at = datetime.utcnow()

        # Обновляем в базе данных
        await self._update_task_in_db(task)

        # Обновляем в кэше
        await self._cache_task(task)

        # Если задача назначена на проект, обновляем статистику проекта
        if task.project_id:
            await self._update_project_task_stats(task.project_id)

        # Уведомляем заинтересованные стороны об изменении
        await self._notify_task_updated(task)

        # Создаем запись активности
        await self._log_activity(user_id, "task_updated", {
            "task_id": task_id,
            "updated_fields": [field for field in ['title', 'description', 'status', 'priority', 
                                                'assignee_ids', 'due_date', 'estimated_hours', 
                                                'tags', 'labels', 'attachments'] 
                             if locals()[field] is not None]
        })

        return True

    async def _update_task_in_db(self, task: Task):
        """Обновление задачи в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE tasks SET
                    title = $2, description = $3, status = $4, priority = $5,
                    assignee_ids = $6, due_date = $7, estimated_hours = $8,
                    actual_hours = $9, tags = $10, labels = $11, attachments = $12,
                    metadata = $13, updated_at = $14, completed_at = $15
                WHERE id = $1
                """,
                task.id, task.title, task.description, task.status.value,
                task.priority.value, task.assignee_ids, task.due_date,
                task.estimated_hours, task.actual_hours, task.tags,
                [label.value for label in task.labels], task.attachments,
                json.dumps(task.metadata) if task.metadata else None,
                task.updated_at, task.completed_at
            )

    async def _can_update_task(self, task: Task, user_id: int) -> bool:
        """Проверка прав на обновление задачи"""
        # Проверяем, является ли пользователь создателем задачи
        if task.creator_id == user_id:
            return True

        # Проверяем, является ли пользователь исполнителем задачи
        if user_id in task.assignee_ids:
            return True

        # Проверяем, является ли пользователь администратором проекта
        if task.project_id:
            return await self._is_project_admin(task.project_id, user_id)

        # Проверяем, является ли пользователь администратором группы
        if task.group_id:
            return await self._is_group_admin(task.group_id, user_id)

        return False

    async def create_project(self, name: str, description: str, owner_id: int,
                           members: Optional[List[Dict[str, Any]]] = None,
                           start_date: Optional[datetime] = None,
                           end_date: Optional[datetime] = None,
                           budget: Optional[float] = None,
                           tags: Optional[List[str]] = None,
                           metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Создание нового проекта"""
        project_id = str(uuid.uuid4())

        project = Project(
            id=project_id,
            name=name,
            description=description,
            owner_id=owner_id,
            members=members or [{'user_id': owner_id, 'role': 'owner', 'joined_at': datetime.utcnow().isoformat()}],
            status=ProjectStatus.PLANNING,
            start_date=start_date,
            end_date=end_date,
            budget=budget,
            spent_budget=0.0,
            tags=tags or [],
            metadata=metadata or {},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем проект в базу данных
        await self._save_project_to_db(project)

        # Добавляем в кэш
        await self._cache_project(project)

        # Создаем доску задач для проекта
        await self._create_project_task_board(project_id)

        # Уведомляем участников о новом проекте
        await self._notify_project_created(project)

        # Создаем запись активности
        await self._log_activity(owner_id, "project_created", {
            "project_id": project_id,
            "project_name": name,
            "member_count": len(members or [])
        })

        return project_id

    async def _save_project_to_db(self, project: Project):
        """Сохранение проекта в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO projects (
                    id, name, description, owner_id, members, status, start_date,
                    end_date, budget, spent_budget, tags, metadata, created_at, updated_at, completed_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                """,
                project.id, project.name, project.description, project.owner_id,
                json.dumps(project.members), project.status.value, project.start_date,
                project.end_date, project.budget, project.spent_budget, project.tags,
                json.dumps(project.metadata) if project.metadata else None,
                project.created_at, project.updated_at, project.completed_at
            )

    async def _cache_project(self, project: Project):
        """Кэширование проекта"""
        await redis_client.setex(f"project:{project.id}", 600, project.model_dump_json())

    async def _get_cached_project(self, project_id: str) -> Optional[Project]:
        """Получение проекта из кэша"""
        cached = await redis_client.get(f"project:{project_id}")
        if cached:
            return Project(**json.loads(cached.decode()))
        return None

    async def get_project(self, project_id: str) -> Optional[Project]:
        """Получение проекта по ID"""
        # Сначала проверяем кэш
        cached_project = await self._get_cached_project(project_id)
        if cached_project:
            return cached_project

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, description, owner_id, members, status, start_date,
                       end_date, budget, spent_budget, tags, metadata, created_at, updated_at, completed_at
                FROM projects WHERE id = $1
                """,
                project_id
            )

        if not row:
            return None

        project = Project(
            id=row['id'],
            name=row['name'],
            description=row['description'],
            owner_id=row['owner_id'],
            members=json.loads(row['members']) if row['members'] else [],
            status=ProjectStatus(row['status']),
            start_date=row['start_date'],
            end_date=row['end_date'],
            budget=row['budget'],
            spent_budget=row['spent_budget'],
            tags=row['tags'] or [],
            metadata=json.loads(row['metadata']) if row['metadata'] else None,
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            completed_at=row['completed_at']
        )

        # Кэшируем проект
        await self._cache_project(project)

        return project

    async def add_project_member(self, project_id: str, user_id: int, role: str) -> bool:
        """Добавление участника в проект"""
        project = await self.get_project(project_id)
        if not project:
            return False

        # Проверяем права на добавление участника
        if not await self._can_manage_project(project, user_id):
            return False

        # Проверяем, не является ли пользователь уже участником
        if any(member['user_id'] == user_id for member in project.members):
            return False

        # Добавляем участника
        new_member = {
            'user_id': user_id,
            'role': role,
            'joined_at': datetime.utcnow().isoformat()
        }
        project.members.append(new_member)

        project.updated_at = datetime.utcnow()

        # Обновляем в базе данных
        await self._update_project_in_db(project)

        # Обновляем в кэше
        await self._cache_project(project)

        # Уведомляем пользователя о добавлении в проект
        await self._notify_user_added_to_project(user_id, project)

        # Создаем запись активности
        await self._log_activity(project.owner_id, "project_member_added", {
            "project_id": project_id,
            "added_user_id": user_id,
            "role": role
        })

        return True

    async def _update_project_in_db(self, project: Project):
        """Обновление проекта в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE projects SET
                    members = $2, updated_at = $3
                WHERE id = $1
                """,
                project.id, json.dumps(project.members), project.updated_at
            )

    async def _can_manage_project(self, project: Project, user_id: int) -> bool:
        """Проверка прав на управление проектом"""
        # Проверяем, является ли пользователь владельцем проекта
        if project.owner_id == user_id:
            return True

        # Проверяем, является ли пользователь администратором проекта
        for member in project.members:
            if member['user_id'] == user_id and member['role'] in ['owner', 'admin']:
                return True

        return False

    async def _create_project_task_board(self, project_id: str):
        """Создание доски задач для проекта"""
        # Создаем колонки доски по умолчанию
        default_columns = self.task_workflow_templates['software_development']
        
        for column in default_columns:
            board_column = TaskBoardColumn(
                id=f"{project_id}_{column.id}",
                name=column.name,
                status=column.status,
                position=column.position,
                task_ids=[],
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            await self._save_board_column(board_column)

    async def _save_board_column(self, column: TaskBoardColumn):
        """Сохранение колонки доски задач"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO task_board_columns (
                    id, name, status, position, task_ids, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                column.id, column.name, column.status.value, column.position,
                column.task_ids, column.created_at, column.updated_at
            )

    async def _notify_task_assigned(self, task: Task):
        """Уведомление о назначении задачи"""
        for assignee_id in task.assignee_ids:
            notification = {
                'type': 'task_assigned',
                'task': {
                    'id': task.id,
                    'title': task.title,
                    'description': task.description[:100] + '...' if len(task.description) > 100 else task.description,
                    'priority': task.priority.value,
                    'due_date': task.due_date.isoformat() if task.due_date else None
                },
                'timestamp': datetime.utcnow().isoformat()
            }

            await redis_client.publish(f"user:{assignee_id}:tasks", json.dumps(notification))

    async def _notify_task_updated(self, task: Task):
        """Уведомление об обновлении задачи"""
        # Уведомляем создателя и исполнителей
        all_relevant_users = [task.creator_id] + task.assignee_ids
        for user_id in set(all_relevant_users):  # Убираем дубликаты
            notification = {
                'type': 'task_updated',
                'task': {
                    'id': task.id,
                    'title': task.title,
                    'status': task.status.value,
                    'updated_at': task.updated_at.isoformat()
                },
                'timestamp': datetime.utcnow().isoformat()
            }

            await redis_client.publish(f"user:{user_id}:tasks", json.dumps(notification))

    async def _notify_project_created(self, project: Project):
        """Уведомление о создании проекта"""
        for member in project.members:
            user_id = member['user_id']
            notification = {
                'type': 'project_created',
                'project': {
                    'id': project.id,
                    'name': project.name,
                    'description': project.description[:100] + '...' if len(project.description) > 100 else project.description,
                    'owner_id': project.owner_id
                },
                'timestamp': datetime.utcnow().isoformat()
            }

            await redis_client.publish(f"user:{user_id}:projects", json.dumps(notification))

    async def _notify_user_added_to_project(self, user_id: int, project: Project):
        """Уведомление пользователя о добавлении в проект"""
        notification = {
            'type': 'user_added_to_project',
            'project': {
                'id': project.id,
                'name': project.name,
                'role': next((m['role'] for m in project.members if m['user_id'] == user_id), 'member')
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        await redis_client.publish(f"user:{user_id}:projects", json.dumps(notification))

    async def get_user_tasks(self, user_id: int, task_type: Optional[TaskType] = None,
                           status: Optional[TaskStatus] = None,
                           project_id: Optional[str] = None,
                           limit: int = 50, offset: int = 0) -> List[Task]:
        """Получение задач пользователя"""
        conditions = ["($1 = ANY(assignee_ids) OR creator_id = $1)"]
        params = [user_id]
        param_idx = 2

        if task_type:
            conditions.append(f"type = ${param_idx}")
            params.append(task_type.value)
            param_idx += 1

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        if project_id:
            conditions.append(f"project_id = ${param_idx}")
            params.append(project_id)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, title, description, type, status, priority, creator_id, assignee_ids,
                   project_id, group_id, chat_id, due_date, estimated_hours, actual_hours,
                   tags, labels, parent_task_id, subtasks, dependencies, attachments,
                   metadata, created_at, updated_at, completed_at
            FROM tasks
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        tasks = []
        for row in rows:
            task = Task(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                type=TaskType(row['type']),
                status=TaskStatus(row['status']),
                priority=TaskPriority(row['priority']),
                creator_id=row['creator_id'],
                assignee_ids=row['assignee_ids'] or [],
                project_id=row['project_id'],
                group_id=row['group_id'],
                chat_id=row['chat_id'],
                due_date=row['due_date'],
                estimated_hours=row['estimated_hours'],
                actual_hours=row['actual_hours'],
                tags=row['tags'] or [],
                labels=[TaskLabel(label) for label in row['labels']] if row['labels'] else [],
                parent_task_id=row['parent_task_id'],
                subtasks=row['subtasks'] or [],
                dependencies=row['dependencies'] or [],
                attachments=row['attachments'] or [],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                completed_at=row['completed_at']
            )
            tasks.append(task)

        return tasks

    async def get_project_tasks(self, project_id: str, status: Optional[TaskStatus] = None,
                              assignee_id: Optional[int] = None,
                              limit: int = 50, offset: int = 0) -> List[Task]:
        """Получение задач проекта"""
        conditions = ["project_id = $1"]
        params = [project_id]
        param_idx = 2

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        if assignee_id:
            conditions.append(f"$param_idx = ANY(assignee_ids)")
            params.append(assignee_id)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, title, description, type, status, priority, creator_id, assignee_ids,
                   project_id, group_id, chat_id, due_date, estimated_hours, actual_hours,
                   tags, labels, parent_task_id, subtasks, dependencies, attachments,
                   metadata, created_at, updated_at, completed_at
            FROM tasks
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        tasks = []
        for row in rows:
            task = Task(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                type=TaskType(row['type']),
                status=TaskStatus(row['status']),
                priority=TaskPriority(row['priority']),
                creator_id=row['creator_id'],
                assignee_ids=row['assignee_ids'] or [],
                project_id=row['project_id'],
                group_id=row['group_id'],
                chat_id=row['chat_id'],
                due_date=row['due_date'],
                estimated_hours=row['estimated_hours'],
                actual_hours=row['actual_hours'],
                tags=row['tags'] or [],
                labels=[TaskLabel(label) for label in row['labels']] if row['labels'] else [],
                parent_task_id=row['parent_task_id'],
                subtasks=row['subtasks'] or [],
                dependencies=row['dependencies'] or [],
                attachments=row['attachments'] or [],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                completed_at=row['completed_at']
            )
            tasks.append(task)

        return tasks

    async def get_user_projects(self, user_id: int, status: Optional[ProjectStatus] = None,
                              limit: int = 50, offset: int = 0) -> List[Project]:
        """Получение проектов пользователя"""
        conditions = ["$1 = ANY(SELECT jsonb_array_elements_text(->'user_id'::text) FROM members) OR owner_id = $1"]
        params = [user_id]
        param_idx = 2

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, name, description, owner_id, members, status, start_date,
                   end_date, budget, spent_budget, tags, metadata, created_at, updated_at, completed_at
            FROM projects
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        projects = []
        for row in rows:
            project = Project(
                id=row['id'],
                name=row['name'],
                description=row['description'],
                owner_id=row['owner_id'],
                members=json.loads(row['members']) if row['members'] else [],
                status=ProjectStatus(row['status']),
                start_date=row['start_date'],
                end_date=row['end_date'],
                budget=row['budget'],
                spent_budget=row['spent_budget'],
                tags=row['tags'] or [],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                completed_at=row['completed_at']
            )
            projects.append(project)

        return projects

    async def _update_project_task_stats(self, project_id: str):
        """Обновление статистики задач проекта"""
        async with db_pool.acquire() as conn:
            # Подсчитываем задачи по статусам
            status_counts = await conn.fetch(
                """
                SELECT status, COUNT(*) as count
                FROM tasks WHERE project_id = $1
                GROUP BY status
                """,
                project_id
            )

            # Подсчитываем общее количество задач
            total_tasks = await conn.fetchval(
                "SELECT COUNT(*) FROM tasks WHERE project_id = $1",
                project_id
            )

            # Подсчитываем выполненные задачи
            completed_tasks = await conn.fetchval(
                "SELECT COUNT(*) FROM tasks WHERE project_id = $1 AND status = 'done'",
                project_id
            )

            # Рассчитываем прогресс
            progress = (completed_tasks or 0) / (total_tasks or 1) * 100

            # Обновляем статистику в проекте
            await conn.execute(
                """
                UPDATE projects SET 
                    metadata = metadata || $2::jsonb,
                    updated_at = $3
                WHERE id = $1
                """,
                project_id,
                json.dumps({
                    'task_stats': {
                        'total': total_tasks or 0,
                        'completed': completed_tasks or 0,
                        'progress_percent': progress,
                        'by_status': {row['status']: row['count'] for row in status_counts}
                    }
                }),
                datetime.utcnow()
            )

        # Обновляем в кэше
        project = await self.get_project(project_id)
        if project:
            await self._cache_project(project)

    async def add_comment_to_task(self, task_id: str, user_id: int, content: str,
                                parent_comment_id: Optional[str] = None) -> Optional[str]:
        """Добавление комментария к задаче"""
        task = await self.get_task(task_id)
        if not task:
            return None

        # Проверяем права на комментирование
        if not await self._can_comment_task(task, user_id):
            return None

        comment_id = str(uuid.uuid4())

        comment = TaskComment(
            id=comment_id,
            task_id=task_id,
            user_id=user_id,
            content=content,
            parent_comment_id=parent_comment_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем комментарий в базу данных
        await self._save_task_comment(comment)

        # Увеличиваем счетчик комментариев в задаче
        await self._increment_task_comment_count(task_id)

        # Уведомляем заинтересованные стороны
        await self._notify_task_commented(task, comment)

        # Создаем запись активности
        await self._log_activity(user_id, "task_commented", {
            "task_id": task_id,
            "comment_id": comment_id
        })

        return comment_id

    async def _save_task_comment(self, comment: TaskComment):
        """Сохранение комментария к задаче в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO task_comments (
                    id, task_id, user_id, content, parent_comment_id, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                comment.id, comment.task_id, comment.user_id, comment.content,
                comment.parent_comment_id, comment.created_at, comment.updated_at
            )

    async def _increment_task_comment_count(self, task_id: str):
        """Увеличение счетчика комментариев в задаче"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE tasks SET metadata = metadata || $2::jsonb, updated_at = $3
                WHERE id = $1
                """,
                task_id,
                json.dumps({'comments_count': await self._get_task_comment_count(task_id) + 1}),
                datetime.utcnow()
            )

    async def _get_task_comment_count(self, task_id: str) -> int:
        """Получение количества комментариев к задаче"""
        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM task_comments WHERE task_id = $1",
                task_id
            )
        return count or 0

    async def _can_comment_task(self, task: Task, user_id: int) -> bool:
        """Проверка прав на комментирование задачи"""
        # Проверяем, является ли пользователь создателем или исполнителем задачи
        if task.creator_id == user_id or user_id in task.assignee_ids:
            return True

        # Проверяем, является ли пользователь участником проекта
        if task.project_id:
            project = await self.get_project(task.project_id)
            if project and any(member['user_id'] == user_id for member in project.members):
                return True

        return False

    async def _notify_task_commented(self, task: Task, comment: TaskComment):
        """Уведомление о комментировании задачи"""
        notification = {
            'type': 'task_commented',
            'task': {
                'id': task.id,
                'title': task.title
            },
            'comment': {
                'id': comment.id,
                'user_id': comment.user_id,
                'content': comment.content[:50] + '...' if len(comment.content) > 50 else comment.content
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        # Уведомляем создателя и исполнителей задачи
        all_relevant_users = [task.creator_id] + task.assignee_ids
        for user_id in set(all_relevant_users):
            await redis_client.publish(f"user:{user_id}:tasks", json.dumps(notification))

        # Если задача связана с проектом, уведомляем участников проекта
        if task.project_id:
            project = await self.get_project(task.project_id)
            if project:
                for member in project.members:
                    await redis_client.publish(f"user:{member['user_id']}:projects", json.dumps(notification))

    async def add_attachment_to_task(self, task_id: str, file_id: str, user_id: int) -> bool:
        """Добавление вложения к задаче"""
        task = await self.get_task(task_id)
        if not task:
            return False

        # Проверяем права на добавление вложения
        if not await self._can_modify_task(task, user_id):
            return False

        attachment = {
            'id': file_id,
            'added_by': user_id,
            'added_at': datetime.utcnow().isoformat()
        }

        task.attachments.append(attachment)
        task.updated_at = datetime.utcnow()

        # Обновляем в базе данных
        await self._update_task_attachments_in_db(task)

        # Обновляем в кэше
        await self._cache_task(task)

        # Создаем запись активности
        await self._log_activity(user_id, "task_attachment_added", {
            "task_id": task_id,
            "file_id": file_id
        })

        return True

    async def _update_task_attachments_in_db(self, task: Task):
        """Обновление вложений задачи в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE tasks SET attachments = $2, updated_at = $3 WHERE id = $1",
                task.id, task.attachments, task.updated_at
            )

    async def _can_modify_task(self, task: Task, user_id: int) -> bool:
        """Проверка прав на изменение задачи"""
        # Проверяем, является ли пользователь создателем или исполнителем задачи
        if task.creator_id == user_id or user_id in task.assignee_ids:
            return True

        # Проверяем, является ли пользователь администратором проекта
        if task.project_id:
            return await self._is_project_admin(task.project_id, user_id)

        return False

    async def _is_project_admin(self, project_id: str, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором проекта"""
        project = await self.get_project(project_id)
        if not project:
            return False

        for member in project.members:
            if member['user_id'] == user_id and member['role'] in ['owner', 'admin']:
                return True

        return False

    async def _is_group_admin(self, group_id: str, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором группы"""
        # В реальной системе здесь будет проверка в таблице участников группы
        return False

    async def get_task_statistics(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики задач пользователя"""
        async with db_pool.acquire() as conn:
            # Общая статистика
            total_tasks = await conn.fetchval(
                "SELECT COUNT(*) FROM tasks WHERE $1 = ANY(assignee_ids) OR creator_id = $1",
                user_id
            )
            
            completed_tasks = await conn.fetchval(
                "SELECT COUNT(*) FROM tasks WHERE ($1 = ANY(assignee_ids) OR creator_id = $1) AND status = 'done'",
                user_id
            )
            
            overdue_tasks = await conn.fetchval(
                """
                SELECT COUNT(*) FROM tasks 
                WHERE ($1 = ANY(assignee_ids) OR creator_id = $1) 
                  AND status != 'done' AND due_date < NOW()
                """,
                user_id
            )
            
            # Статистика по приоритетам
            priority_stats = await conn.fetch(
                """
                SELECT priority, COUNT(*) as count
                FROM tasks WHERE $1 = ANY(assignee_ids) OR creator_id = $1
                GROUP BY priority
                """,
                user_id
            )
            
            # Статистика по статусам
            status_stats = await conn.fetch(
                """
                SELECT status, COUNT(*) as count
                FROM tasks WHERE $1 = ANY(assignee_ids) OR creator_id = $1
                GROUP BY status
                """,
                user_id
            )

        stats = {
            'total_tasks': total_tasks or 0,
            'completed_tasks': completed_tasks or 0,
            'overdue_tasks': overdue_tasks or 0,
            'completion_rate': (completed_tasks or 0) / (total_tasks or 1) * 100,
            'overdue_rate': (overdue_tasks or 0) / (total_tasks or 1) * 100,
            'priority_breakdown': {
                row['priority']: row['count'] for row in priority_stats
            },
            'status_breakdown': {
                row['status']: row['count'] for row in status_stats
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        return stats

    async def get_project_statistics(self, project_id: str) -> Dict[str, Any]:
        """Получение статистики проекта"""
        project = await self.get_project(project_id)
        if not project:
            return {}

        async with db_pool.acquire() as conn:
            # Статистика задач проекта
            task_stats = await conn.fetch(
                """
                SELECT status, COUNT(*) as count, AVG(extract(epoch from (completed_at - created_at))/3600) as avg_completion_time_hours
                FROM tasks WHERE project_id = $1
                GROUP BY status
                """,
                project_id
            )
            
            # Статистика участников
            member_stats = await conn.fetch(
                """
                SELECT assignee_ids, COUNT(*) as task_count
                FROM tasks WHERE project_id = $1 AND status = 'done'
                GROUP BY assignee_ids
                """
            )

        stats = {
            'project_id': project_id,
            'project_name': project.name,
            'total_tasks': sum(row['count'] for row in task_stats),
            'completed_tasks': next((row['count'] for row in task_stats if row['status'] == 'done'), 0),
            'in_progress_tasks': next((row['count'] for row in task_stats if row['status'] == 'in_progress'), 0),
            'todo_tasks': next((row['count'] for row in task_stats if row['status'] == 'todo'), 0),
            'completion_rate': next((row['count'] for row in task_stats if row['status'] == 'done'), 0) / sum(row['count'] for row in task_stats) * 100 if task_stats else 0,
            'avg_completion_time_hours': next((row['avg_completion_time_hours'] for row in task_stats if row['status'] == 'done'), 0),
            'member_task_distribution': [
                {
                    'member_ids': row['assignee_ids'],
                    'completed_tasks': row['task_count']
                }
                for row in member_stats
            ],
            'timestamp': datetime.utcnow().isoformat()
        }

        return stats

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
task_project_enhancement_service = TaskProjectEnhancementService()
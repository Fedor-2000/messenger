# server/app/tasks/task_manager.py
import asyncio
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import uuid
from datetime import datetime, timedelta
import asyncpg

class TaskPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    OVERDUE = "overdue"

class TaskType(Enum):
    PERSONAL = "personal"
    GROUP = "group"
    PROJECT = "project"
    CHAT = "chat"

@dataclass
class Task:
    id: str
    title: str
    description: str
    assignee_id: int
    creator_id: int
    due_date: Optional[datetime]
    priority: TaskPriority
    status: TaskStatus
    task_type: TaskType
    chat_id: Optional[str] = None
    group_id: Optional[str] = None
    project_id: Optional[str] = None
    created_at: datetime = None
    completed_at: Optional[datetime] = None
    estimated_hours: Optional[float] = None
    actual_hours: Optional[float] = None
    tags: List[str] = None
    attachments: List[Dict[str, Any]] = None
    subtasks: List[str] = None  # IDs of subtasks
    parent_task: Optional[str] = None  # ID of parent task

class TaskManager:
    """Менеджер задач для интеграции с чатами"""
    
    def __init__(self, db_pool, redis_client):
        self.db_pool = db_pool
        self.redis = redis_client
        self.task_cache = {}  # Кэш задач
        self.user_task_lists = {}  # Списки задач пользователей
        self.chat_task_lists = {}  # Списки задач чатов
    
    async def create_task(self, title: str, description: str, assignee_id: int, 
                         creator_id: int, task_type: TaskType, 
                         due_date: Optional[datetime] = None,
                         priority: TaskPriority = TaskPriority.MEDIUM,
                         chat_id: Optional[str] = None,
                         group_id: Optional[str] = None,
                         project_id: Optional[str] = None,
                         estimated_hours: Optional[float] = None,
                         tags: Optional[List[str]] = None) -> str:
        """Создание новой задачи"""
        task_id = str(uuid.uuid4())
        
        task = Task(
            id=task_id,
            title=title,
            description=description,
            assignee_id=assignee_id,
            creator_id=creator_id,
            due_date=due_date,
            priority=priority,
            status=TaskStatus.PENDING,
            task_type=task_type,
            chat_id=chat_id,
            group_id=group_id,
            project_id=project_id,
            created_at=datetime.utcnow(),
            estimated_hours=estimated_hours,
            tags=tags or [],
            attachments=[],
            subtasks=[],
            parent_task=None
        )
        
        # Сохраняем задачу в базу данных
        await self._save_task_to_db(task)
        
        # Добавляем в кэш
        self.task_cache[task_id] = task
        
        # Уведомляем заинтересованные стороны
        await self._notify_task_created(task)
        
        return task_id
    
    async def _save_task_to_db(self, task: Task):
        """Сохранение задачи в базу данных"""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO tasks (
                    id, title, description, assignee_id, creator_id, 
                    due_date, priority, status, task_type, chat_id, 
                    group_id, project_id, created_at, estimated_hours, tags
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                """,
                task.id, task.title, task.description, task.assignee_id,
                task.creator_id, task.due_date, task.priority.value,
                task.status.value, task.task_type.value, task.chat_id,
                task.group_id, task.project_id, task.created_at,
                task.estimated_hours, task.tags
            )
    
    async def get_task(self, task_id: str) -> Optional[Task]:
        """Получение задачи по ID"""
        # Сначала проверяем кэш
        if task_id in self.task_cache:
            return self.task_cache[task_id]
        
        # Затем базу данных
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, title, description, assignee_id, creator_id, 
                       due_date, priority, status, task_type, chat_id, 
                       group_id, project_id, created_at, completed_at,
                       estimated_hours, actual_hours, tags, attachments, 
                       subtasks, parent_task
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
            assignee_id=row['assignee_id'],
            creator_id=row['creator_id'],
            due_date=row['due_date'],
            priority=TaskPriority(row['priority']),
            status=TaskStatus(row['status']),
            task_type=TaskType(row['task_type']),
            chat_id=row['chat_id'],
            group_id=row['group_id'],
            project_id=row['project_id'],
            created_at=row['created_at'],
            completed_at=row['completed_at'],
            estimated_hours=row['estimated_hours'],
            actual_hours=row['actual_hours'],
            tags=row['tags'] or [],
            attachments=row['attachments'] or [],
            subtasks=row['subtasks'] or [],
            parent_task=row['parent_task']
        )
        
        # Кэшируем задачу
        self.task_cache[task_id] = task
        
        return task
    
    async def update_task(self, task_id: str, **updates) -> bool:
        """Обновление задачи"""
        task = await self.get_task(task_id)
        if not task:
            return False
        
        # Обновляем поля задачи
        for field, value in updates.items():
            if hasattr(task, field):
                if field == 'priority' and isinstance(value, str):
                    setattr(task, field, TaskPriority(value))
                elif field == 'status' and isinstance(value, str):
                    setattr(task, field, TaskStatus(value))
                elif field == 'task_type' and isinstance(value, str):
                    setattr(task, field, TaskType(value))
                else:
                    setattr(task, field, value)
        
        # Обновляем время завершения, если статус изменился на "completed"
        if 'status' in updates and updates['status'] == TaskStatus.COMPLETED.value:
            task.completed_at = datetime.utcnow()
        
        # Сохраняем в базу данных
        await self._update_task_in_db(task)
        
        # Обновляем кэш
        self.task_cache[task_id] = task
        
        # Уведомляем заинтересованные стороны
        await self._notify_task_updated(task)
        
        return True
    
    async def _update_task_in_db(self, task: Task):
        """Обновление задачи в базе данных"""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE tasks SET
                    title = $2, description = $3, assignee_id = $4,
                    due_date = $5, priority = $6, status = $7,
                    completed_at = $8, actual_hours = $9, tags = $10
                WHERE id = $1
                """,
                task.id, task.title, task.description, task.assignee_id,
                task.due_date, task.priority.value, task.status.value,
                task.completed_at, task.actual_hours, task.tags
            )
    
    async def delete_task(self, task_id: str) -> bool:
        """Удаление задачи"""
        task = await self.get_task(task_id)
        if not task:
            return False
        
        # Удаляем из базы данных
        async with self.db_pool.acquire() as conn:
            await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)
        
        # Удаляем из кэша
        if task_id in self.task_cache:
            del self.task_cache[task_id]
        
        # Уведомляем заинтересованные стороны
        await self._notify_task_deleted(task)
        
        return True
    
    async def assign_task(self, task_id: str, assignee_id: int) -> bool:
        """Назначение задачи пользователю"""
        return await self.update_task(task_id, assignee_id=assignee_id)
    
    async def complete_task(self, task_id: str) -> bool:
        """Отметка задачи как выполненной"""
        return await self.update_task(task_id, status=TaskStatus.COMPLETED.value)
    
    async def cancel_task(self, task_id: str) -> bool:
        """Отмена задачи"""
        return await self.update_task(task_id, status=TaskStatus.CANCELLED.value)
    
    async def get_user_tasks(self, user_id: int, status: Optional[TaskStatus] = None, 
                           limit: int = 50, offset: int = 0) -> List[Task]:
        """Получение задач пользователя"""
        conditions = ["assignee_id = $1 OR creator_id = $1"]
        params = [user_id]
        param_idx = 2
        
        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1
        
        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT id, title, description, assignee_id, creator_id, 
                   due_date, priority, status, task_type, chat_id, 
                   group_id, project_id, created_at, completed_at,
                   estimated_hours, actual_hours, tags, attachments, 
                   subtasks, parent_task
            FROM tasks
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        
        params.extend([limit, offset])
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        tasks = []
        for row in rows:
            task = Task(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                assignee_id=row['assignee_id'],
                creator_id=row['creator_id'],
                due_date=row['due_date'],
                priority=TaskPriority(row['priority']),
                status=TaskStatus(row['status']),
                task_type=TaskType(row['task_type']),
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                created_at=row['created_at'],
                completed_at=row['completed_at'],
                estimated_hours=row['estimated_hours'],
                actual_hours=row['actual_hours'],
                tags=row['tags'] or [],
                attachments=row['attachments'] or [],
                subtasks=row['subtasks'] or [],
                parent_task=row['parent_task']
            )
            tasks.append(task)
        
        return tasks
    
    async def get_chat_tasks(self, chat_id: str, status: Optional[TaskStatus] = None) -> List[Task]:
        """Получение задач чата"""
        conditions = ["chat_id = $1"]
        params = [chat_id]
        param_idx = 2
        
        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1
        
        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT id, title, description, assignee_id, creator_id, 
                   due_date, priority, status, task_type, chat_id, 
                   group_id, project_id, created_at, completed_at,
                   estimated_hours, actual_hours, tags, attachments, 
                   subtasks, parent_task
            FROM tasks
            WHERE {where_clause}
            ORDER BY created_at DESC
        """
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        tasks = []
        for row in rows:
            task = Task(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                assignee_id=row['assignee_id'],
                creator_id=row['creator_id'],
                due_date=row['due_date'],
                priority=TaskPriority(row['priority']),
                status=TaskStatus(row['status']),
                task_type=TaskType(row['task_type']),
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                created_at=row['created_at'],
                completed_at=row['completed_at'],
                estimated_hours=row['estimated_hours'],
                actual_hours=row['actual_hours'],
                tags=row['tags'] or [],
                attachments=row['attachments'] or [],
                subtasks=row['subtasks'] or [],
                parent_task=row['parent_task']
            )
            tasks.append(task)
        
        return tasks
    
    async def create_subtask(self, parent_task_id: str, title: str, description: str, 
                           assignee_id: int, creator_id: int) -> Optional[str]:
        """Создание подзадачи"""
        parent_task = await self.get_task(parent_task_id)
        if not parent_task:
            return None
        
        # Создаем подзадачу с теми же параметрами, что и родительская задача
        subtask_id = await self.create_task(
            title=title,
            description=description,
            assignee_id=assignee_id,
            creator_id=creator_id,
            task_type=parent_task.task_type,
            due_date=parent_task.due_date,  # Наследуем срок
            priority=parent_task.priority,  # Наследуем приоритет
            chat_id=parent_task.chat_id,
            group_id=parent_task.group_id,
            project_id=parent_task.project_id,
            estimated_hours=None  # Не наследуем оценку времени
        )
        
        if subtask_id:
            # Добавляем подзадачу к родительской задаче
            parent_task.subtasks.append(subtask_id)
            await self._update_task_in_db(parent_task)
            self.task_cache[parent_task_id] = parent_task
            
            # Обновляем статус родительской задачи, если все подзадачи выполнены
            await self._update_parent_task_status(parent_task_id)
        
        return subtask_id
    
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
        all_completed = all(subtask.status == TaskStatus.COMPLETED for subtask in subtasks)
        any_cancelled = any(subtask.status == TaskStatus.CANCELLED for subtask in subtasks)
        any_in_progress = any(subtask.status == TaskStatus.IN_PROGRESS for subtask in subtasks)
        
        new_status = None
        if all_completed:
            new_status = TaskStatus.COMPLETED
        elif any_cancelled:
            new_status = TaskStatus.CANCELLED
        elif any_in_progress:
            new_status = TaskStatus.IN_PROGRESS
        else:
            new_status = TaskStatus.PENDING
        
        if new_status and parent_task.status != new_status:
            await self.update_task(parent_task_id, status=new_status.value)
    
    async def _notify_task_created(self, task: Task):
        """Уведомление о создании задачи"""
        notification = {
            'type': 'task_created',
            'task': self._task_to_dict(task),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Отправляем уведомление назначенному пользователю
        await self._send_notification_to_user(task.assignee_id, notification)
        
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
        await self._send_notification_to_user(task.assignee_id, notification)
        await self._send_notification_to_user(task.creator_id, notification)
        
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
        await self._send_notification_to_user(task.assignee_id, notification)
        await self._send_notification_to_user(task.creator_id, notification)
        
        # Если задача связана с чатом, отправляем в чат
        if task.chat_id:
            await self._send_notification_to_chat(task.chat_id, notification)
    
    async def _send_notification_to_user(self, user_id: int, notification: Dict[str, Any]):
        """Отправка уведомления пользователю"""
        channel = f"user:{user_id}:tasks"
        await self.redis.publish(channel, json.dumps(notification))
    
    async def _send_notification_to_chat(self, chat_id: str, notification: Dict[str, Any]):
        """Отправка уведомления в чат"""
        channel = f"chat:{chat_id}:tasks"
        await self.redis.publish(channel, json.dumps(notification))
    
    def _task_to_dict(self, task: Task) -> Dict[str, Any]:
        """Конвертация задачи в словарь для отправки"""
        return {
            'id': task.id,
            'title': task.title,
            'description': task.description,
            'assignee_id': task.assignee_id,
            'creator_id': task.creator_id,
            'due_date': task.due_date.isoformat() if task.due_date else None,
            'priority': task.priority.value,
            'status': task.status.value,
            'task_type': task.task_type.value,
            'chat_id': task.chat_id,
            'group_id': task.group_id,
            'project_id': task.project_id,
            'created_at': task.created_at.isoformat() if task.created_at else None,
            'completed_at': task.completed_at.isoformat() if task.completed_at else None,
            'estimated_hours': task.estimated_hours,
            'actual_hours': task.actual_hours,
            'tags': task.tags,
            'subtasks_count': len(task.subtasks) if task.subtasks else 0
        }
    
    async def get_overdue_tasks(self) -> List[Task]:
        """Получение просроченных задач"""
        now = datetime.utcnow()
        query = """
            SELECT id, title, description, assignee_id, creator_id, 
                   due_date, priority, status, task_type, chat_id, 
                   group_id, project_id, created_at, completed_at,
                   estimated_hours, actual_hours, tags, attachments, 
                   subtasks, parent_task
            FROM tasks
            WHERE due_date < $1 AND status = $2
            ORDER BY due_date ASC
        """
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, now, TaskStatus.PENDING.value)
        
        tasks = []
        for row in rows:
            task = Task(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                assignee_id=row['assignee_id'],
                creator_id=row['creator_id'],
                due_date=row['due_date'],
                priority=TaskPriority(row['priority']),
                status=TaskStatus(row['status']),
                task_type=TaskType(row['task_type']),
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                created_at=row['created_at'],
                completed_at=row['completed_at'],
                estimated_hours=row['estimated_hours'],
                actual_hours=row['actual_hours'],
                tags=row['tags'] or [],
                attachments=row['attachments'] or [],
                subtasks=row['subtasks'] or [],
                parent_task=row['parent_task']
            )
            tasks.append(task)
        
        return tasks
    
    async def get_tasks_by_priority(self, user_id: int, priority: TaskPriority) -> List[Task]:
        """Получение задач по приоритету"""
        query = """
            SELECT id, title, description, assignee_id, creator_id, 
                   due_date, priority, status, task_type, chat_id, 
                   group_id, project_id, created_at, completed_at,
                   estimated_hours, actual_hours, tags, attachments, 
                   subtasks, parent_task
            FROM tasks
            WHERE (assignee_id = $1 OR creator_id = $1) AND priority = $2
            ORDER BY created_at DESC
        """
        
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, priority.value)
        
        tasks = []
        for row in rows:
            task = Task(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                assignee_id=row['assignee_id'],
                creator_id=row['creator_id'],
                due_date=row['due_date'],
                priority=TaskPriority(row['priority']),
                status=TaskStatus(row['status']),
                task_type=TaskType(row['task_type']),
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                created_at=row['created_at'],
                completed_at=row['completed_at'],
                estimated_hours=row['estimated_hours'],
                actual_hours=row['actual_hours'],
                tags=row['tags'] or [],
                attachments=row['attachments'] or [],
                subtasks=row['subtasks'] or [],
                parent_task=row['parent_task']
            )
            tasks.append(task)
        
        return tasks

# Глобальный экземпляр для использования в приложении
task_manager = TaskManager(None, None)  # Будет инициализирован в основном приложении
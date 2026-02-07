"""
Improved modular architecture for the hybrid messenger application.

This module implements a modular, scalable architecture with clear separation of concerns,
dependency injection, and improved maintainability.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Protocol
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
import uuid
from datetime import datetime

from aiohttp import web
import asyncpg
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class Component(ABC):
    """Base class for all components."""
    
    @abstractmethod
    async def initialize(self):
        """Initialize the component."""
        raise NotImplementedError

    @abstractmethod
    async def shutdown(self):
        """Shutdown the component."""
        raise NotImplementedError


class DatabaseInterface(Protocol):
    """Protocol for database operations."""
    
    async def acquire(self) -> asyncpg.Connection:
        """Acquire a database connection."""
        ...


class RedisInterface(Protocol):
    """Protocol for Redis operations."""
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis."""
        ...
    
    async def set(self, key: str, value: str, ex: Optional[int] = None):
        """Set value in Redis."""
        ...
    
    async def publish(self, channel: str, message: str):
        """Publish message to Redis channel."""
        ...


@dataclass
class AppConfig:
    """Application configuration."""
    db_url: str = "postgresql://messenger:password@localhost:5432/messenger"
    redis_url: str = "redis://localhost:6379"
    jwt_secret: str = "secret"
    message_encryption_key: str = "key"
    tcp_host: str = "0.0.0.0"
    tcp_port: int = 8888
    http_host: str = "0.0.0.0"
    http_port: int = 8080
    log_level: str = "INFO"


class DatabaseManager(Component):
    """Manages database connections and operations."""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None
    
    async def initialize(self):
        """Initialize database connection pool."""
        logger.info("Initializing database connection pool...")
        self.pool = await asyncpg.create_pool(
            self.config.db_url,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        logger.info("Database connection pool initialized.")
    
    async def shutdown(self):
        """Shutdown database connection pool."""
        if self.pool:
            logger.info("Closing database connection pool...")
            await self.pool.close()
            logger.info("Database connection pool closed.")
    
    def get_pool(self) -> asyncpg.Pool:
        """Get the database pool."""
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        return self.pool


class RedisManager(Component):
    """Manages Redis connections and operations."""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.client: Optional[redis.Redis] = None
    
    async def initialize(self):
        """Initialize Redis connection."""
        logger.info("Initializing Redis connection...")
        self.client = redis.from_url(
            self.config.redis_url,
            decode_responses=True,
            password=None  # Add password if needed
        )
        logger.info("Redis connection initialized.")
    
    async def shutdown(self):
        """Shutdown Redis connection."""
        if self.client:
            logger.info("Closing Redis connection...")
            await self.client.close()
            logger.info("Redis connection closed.")
    
    def get_client(self) -> redis.Redis:
        """Get the Redis client."""
        if not self.client:
            raise RuntimeError("Redis client not initialized")
        return self.client


class SecurityService(Component):
    """Provides security-related services."""
    
    def __init__(self, db_manager: DatabaseManager, redis_manager: RedisManager):
        self.db_manager = db_manager
        self.redis_manager = redis_manager
    
    async def initialize(self):
        """Initialize security service."""
        logger.info("Initializing security service...")
        # Initialize security-related configurations
        logger.info("Security service initialized.")
    
    async def shutdown(self):
        """Shutdown security service."""
        logger.info("Shutting down security service...")
    
    async def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate user."""
        db_pool = self.db_manager.get_pool()
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT id, username, password_hash FROM users WHERE username = $1",
                username
            )
            if user:
                # Verify password (implementation depends on your hashing method)
                # Return user data after successful authentication
                return {
                    'id': user['id'],
                    'username': user['username']
                }
        return None


class MessageService(Component):
    """Handles message-related operations."""
    
    def __init__(self, 
                 db_manager: DatabaseManager, 
                 redis_manager: RedisManager,
                 security_service: SecurityService):
        self.db_manager = db_manager
        self.redis_manager = redis_manager
        self.security_service = security_service
        self.active_connections: Dict[str, Any] = {}  # Connection tracking
    
    async def initialize(self):
        """Initialize message service."""
        logger.info("Initializing message service...")
        logger.info("Message service initialized.")
    
    async def shutdown(self):
        """Shutdown message service."""
        logger.info("Shutting down message service...")
    
    async def send_message(self, chat_id: str, sender_id: int, content: str):
        """Send a message to a chat."""
        db_pool = self.db_manager.get_pool()
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO messages (chat_id, sender_id, content, message_type, timestamp) 
                VALUES ($1, $2, $3, 'text', $4)
                """,
                chat_id, sender_id, content, datetime.utcnow()
            )
        
        # Publish to Redis for real-time delivery
        redis_client = self.redis_manager.get_client()
        message_data = {
            'type': 'new_message',
            'chat_id': chat_id,
            'sender_id': sender_id,
            'content': content,
            'timestamp': datetime.utcnow().isoformat()
        }
        await redis_client.publish(f"chat:{chat_id}", str(message_data))


class UserService(Component):
    """Handles user-related operations."""
    
    def __init__(self, db_manager: DatabaseManager, redis_manager: RedisManager):
        self.db_manager = db_manager
        self.redis_manager = redis_manager
    
    async def initialize(self):
        """Initialize user service."""
        logger.info("Initializing user service...")
        logger.info("User service initialized.")
    
    async def shutdown(self):
        """Shutdown user service."""
        logger.info("Shutting down user service...")
    
    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        db_pool = self.db_manager.get_pool()
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT id, username, avatar FROM users WHERE id = $1",
                user_id
            )
            if user:
                return {
                    'id': user['id'],
                    'username': user['username'],
                    'avatar': user['avatar']
                }
        return None
    
    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username."""
        db_pool = self.db_manager.get_pool()
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT id, username, avatar FROM users WHERE username = $1",
                username
            )
            if user:
                return {
                    'id': user['id'],
                    'username': user['username'],
                    'avatar': user['avatar']
                }
        return None


class ChatService(Component):
    """Handles chat-related operations."""
    
    def __init__(self, 
                 db_manager: DatabaseManager, 
                 redis_manager: RedisManager,
                 user_service: UserService):
        self.db_manager = db_manager
        self.redis_manager = redis_manager
        self.user_service = user_service
    
    async def initialize(self):
        """Initialize chat service."""
        logger.info("Initializing chat service...")
        logger.info("Chat service initialized.")
    
    async def shutdown(self):
        """Shutdown chat service."""
        logger.info("Shutting down chat service...")
    
    async def create_private_chat(self, user1_id: int, user2_id: int) -> str:
        """Create a private chat between two users."""
        chat_id = f"private_{min(user1_id, user2_id)}_{max(user1_id, user2_id)}"
        
        db_pool = self.db_manager.get_pool()
        async with db_pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO chats (id, type, participants) 
                VALUES ($1, 'private', ARRAY[$2, $3])
                ON CONFLICT (id) DO NOTHING
                ''',
                chat_id, user1_id, user2_id
            )
        
        return chat_id
    
    async def get_chat_participants(self, chat_id: str) -> List[int]:
        """Get participants of a chat."""
        db_pool = self.db_manager.get_pool()
        async with db_pool.acquire() as conn:
            chat = await conn.fetchrow(
                "SELECT participants FROM chats WHERE id = $1",
                chat_id
            )
            return chat['participants'] if chat else []


class GameService(Component):
    """Handles game-related operations."""
    
    def __init__(self, 
                 db_manager: DatabaseManager, 
                 redis_manager: RedisManager,
                 user_service: UserService):
        self.db_manager = db_manager
        self.redis_manager = redis_manager
        self.user_service = user_service
        self.active_games: Dict[str, Any] = {}
    
    async def initialize(self):
        """Initialize game service."""
        logger.info("Initializing game service...")
        logger.info("Game service initialized.")
    
    async def shutdown(self):
        """Shutdown game service."""
        logger.info("Shutting down game service...")
        # End all active games
        for game_id in list(self.active_games.keys()):
            await self.end_game(game_id)
    
    async def create_game_session(self, game_type: str, player_ids: List[int]) -> str:
        """Create a new game session."""
        game_id = str(uuid.uuid4())
        
        # Store game session
        self.active_games[game_id] = {
            'type': game_type,
            'players': player_ids,
            'status': 'waiting',
            'created_at': datetime.utcnow()
        }
        
        # Save to database
        db_pool = self.db_manager.get_pool()
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO game_sessions (id, game_type, players, status, created_at) 
                VALUES ($1, $2, $3, $4, $5)
                """,
                game_id, game_type, player_ids, 'waiting', datetime.utcnow()
            )
        
        return game_id
    
    async def end_game(self, game_id: str):
        """End a game session."""
        if game_id in self.active_games:
            del self.active_games[game_id]


class TaskService(Component):
    """Handles task-related operations."""
    
    def __init__(self, 
                 db_manager: DatabaseManager, 
                 redis_manager: RedisManager,
                 user_service: UserService):
        self.db_manager = db_manager
        self.redis_manager = redis_manager
        self.user_service = user_service
    
    async def initialize(self):
        """Initialize task service."""
        logger.info("Initializing task service...")
        logger.info("Task service initialized.")
    
    async def shutdown(self):
        """Shutdown task service."""
        logger.info("Shutting down task service...")
    
    async def create_task(self, title: str, description: str, assignee_id: int, 
                         creator_id: int, chat_id: Optional[str] = None) -> str:
        """Create a new task."""
        task_id = str(uuid.uuid4())
        
        db_pool = self.db_manager.get_pool()
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO tasks (
                    id, title, description, assignee_id, creator_id, 
                    status, chat_id, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                task_id, title, description, assignee_id, creator_id,
                'pending', chat_id, datetime.utcnow()
            )
        
        # Notify assignee
        redis_client = self.redis_manager.get_client()
        notification = {
            'type': 'task_assigned',
            'task_id': task_id,
            'title': title,
            'assignee_id': assignee_id
        }
        await redis_client.publish(f"user:{assignee_id}:tasks", str(notification))
        
        return task_id


class CalendarService(Component):
    """Handles calendar-related operations."""
    
    def __init__(self, 
                 db_manager: DatabaseManager, 
                 redis_manager: RedisManager,
                 user_service: UserService):
        self.db_manager = db_manager
        self.redis_manager = redis_manager
        self.user_service = user_service
    
    async def initialize(self):
        """Initialize calendar service."""
        logger.info("Initializing calendar service...")
        logger.info("Calendar service initialized.")
    
    async def shutdown(self):
        """Shutdown calendar service."""
        logger.info("Shutting down calendar service...")
    
    async def create_event(self, title: str, description: str, start_time: datetime, 
                          end_time: datetime, creator_id: int, 
                          attendees: List[int]) -> str:
        """Create a new calendar event."""
        event_id = str(uuid.uuid4())
        
        db_pool = self.db_manager.get_pool()
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO calendar_events (
                    id, title, description, start_time, end_time, 
                    creator_id, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                event_id, title, description, start_time, end_time, 
                creator_id, datetime.utcnow()
            )
            
            # Add attendees
            for attendee_id in attendees:
                await conn.execute(
                    "INSERT INTO event_attendees (event_id, user_id) VALUES ($1, $2)",
                    event_id, attendee_id
                )
        
        # Notify attendees
        redis_client = self.redis_manager.get_client()
        for attendee_id in attendees:
            notification = {
                'type': 'calendar_event_created',
                'event_id': event_id,
                'title': title,
                'start_time': start_time.isoformat(),
                'attendee_id': attendee_id
            }
            await redis_client.publish(f"user:{attendee_id}:calendar", str(notification))
        
        return event_id


class AnalyticsService(Component):
    """Handles analytics operations."""
    
    def __init__(self, 
                 db_manager: DatabaseManager, 
                 redis_manager: RedisManager):
        self.db_manager = db_manager
        self.redis_manager = redis_manager
    
    async def initialize(self):
        """Initialize analytics service."""
        logger.info("Initializing analytics service...")
        logger.info("Analytics service initialized.")
    
    async def shutdown(self):
        """Shutdown analytics service."""
        logger.info("Shutting down analytics service...")
    
    async def track_event(self, user_id: int, event_type: str, properties: Dict[str, Any]):
        """Track an analytics event."""
        # Log the analytics event
        logger.info(f"Analytics event: {event_type} for user {user_id} with props {properties}")
        
        # Store analytics event in dedicated table
        db_pool = self.db_manager.get_pool()
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO analytics_events (user_id, event_type, properties, timestamp) 
                VALUES ($1, $2, $3, $4)
                """,
                user_id, event_type, properties, datetime.utcnow()
            )


class Application:
    """Main application class that manages all services."""
    
    def __init__(self, config: AppConfig):
        self.config = config
        
        # Managers
        self.db_manager = DatabaseManager(config)
        self.redis_manager = RedisManager(config)
        
        # Services
        self.security_service = SecurityService(self.db_manager, self.redis_manager)
        self.user_service = UserService(self.db_manager, self.redis_manager)
        self.chat_service = ChatService(self.db_manager, self.redis_manager, self.user_service)
        self.message_service = MessageService(self.db_manager, self.redis_manager, self.security_service)
        self.game_service = GameService(self.db_manager, self.redis_manager, self.user_service)
        self.task_service = TaskService(self.db_manager, self.redis_manager, self.user_service)
        self.calendar_service = CalendarService(self.db_manager, self.redis_manager, self.user_service)
        self.analytics_service = AnalyticsService(self.db_manager, self.redis_manager)
        
        self.components: List[Component] = [
            self.db_manager,
            self.redis_manager,
            self.security_service,
            self.user_service,
            self.chat_service,
            self.message_service,
            self.game_service,
            self.task_service,
            self.calendar_service,
            self.analytics_service
        ]
    
    async def initialize(self):
        """Initialize all components."""
        logger.info("Initializing application...")
        for component in self.components:
            await component.initialize()
        logger.info("Application initialized.")
    
    async def shutdown(self):
        """Shutdown all components."""
        logger.info("Shutting down application...")
        for component in reversed(self.components):
            await component.shutdown()
        logger.info("Application shut down.")
    
    def get_web_app(self) -> web.Application:
        """Get the aiohttp web application."""
        app = web.Application()
        
        # Add routes here
        app.router.add_get('/health', self.health_check)
        
        return app
    
    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({'status': 'healthy'})


@asynccontextmanager
async def lifespan(app: web.Application, application: Application):
    """Application lifespan manager."""
    await application.initialize()
    yield
    await application.shutdown()


async def create_application(config: AppConfig) -> Application:
    """Create and return the application instance."""
    application = Application(config)
    return application


async def main():
    """Main entry point."""
    config = AppConfig()
    
    # Create application
    application = await create_application(config)
    
    # Initialize
    await application.initialize()
    
    # Create web app
    web_app = application.get_web_app()
    
    # Add lifespan
    web_app.cleanup_ctx.append(lambda app: lifespan(app, application))
    
    # Run the application
    logger.info(f"Starting server on {config.http_host}:{config.http_port}")
    await web._run_app(web_app, host=config.http_host, port=config.http_port)


if __name__ == '__main__':
    asyncio.run(main())
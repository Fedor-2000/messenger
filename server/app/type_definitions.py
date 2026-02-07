"""
Type definitions for the hybrid messenger application.

This module contains all type definitions, dataclasses, enums and protocols
used throughout the application to ensure consistent typing and better IDE support.
"""

from typing import Dict, List, Optional, Union, Any, Callable, Awaitable, Protocol
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
import uuid


# Enums
class MessageType(Enum):
    """Types of messages that can be sent."""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FILE = "file"
    SYSTEM = "system"
    REACTION = "reaction"
    EDITED = "edited"
    DELETED = "deleted"


class ChatType(Enum):
    """Types of chats."""
    PRIVATE = "private"
    GROUP = "group"
    CHANNEL = "channel"


class TaskStatus(Enum):
    """Status of tasks."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    OVERDUE = "overdue"


class TaskPriority(Enum):
    """Priority levels for tasks."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class EventPrivacy(Enum):
    """Privacy levels for calendar events."""
    PUBLIC = "public"
    PRIVATE = "private"
    CONFIDENTIAL = "confidential"


class OnlineStatus(Enum):
    """User online status."""
    ONLINE = "online"
    AWAY = "away"
    BUSY = "busy"
    OFFLINE = "offline"
    INVISIBLE = "invisible"


class GameType(Enum):
    """Types of games."""
    TRIVIA = "trivia"
    TICTACTOE = "tic_tac_toe"
    HANGMAN = "hangman"
    WORD_SEARCH = "word_search"
    PUZZLE = "puzzle"


class MediaStreamType(Enum):
    """Types of media streams."""
    AUDIO = "audio"
    VIDEO = "video"
    SCREEN_SHARE = "screen_share"


class CallStatus(Enum):
    """Status of calls."""
    INITIATED = "initiated"
    RINGING = "ringing"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    ENDED = "ended"
    MISSED = "missed"


# Dataclasses
@dataclass
class User:
    """Represents a user in the system."""
    id: int
    username: str
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None
    bio: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    online_status: OnlineStatus = OnlineStatus.OFFLINE
    is_active: bool = True
    preferences: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Chat:
    """Represents a chat room."""
    id: str
    type: ChatType
    name: Optional[str] = None
    description: Optional[str] = None
    creator_id: Optional[int] = None
    participants: List[int] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_message: Optional[str] = None
    last_activity: datetime = field(default_factory=datetime.utcnow)
    unread_count: int = 0
    avatar: Optional[str] = None
    is_archived: bool = False


@dataclass
class Message:
    """Represents a message in a chat."""
    id: str
    chat_id: str
    sender_id: int
    content: str
    message_type: MessageType
    timestamp: datetime = field(default_factory=datetime.utcnow)
    reply_to: Optional[str] = None
    edited: bool = False
    edited_at: Optional[datetime] = None
    reactions: Optional[Dict[str, List[int]]] = None  # emoji -> list of user_ids who reacted
    mentions: Optional[List[int]] = None  # list of mentioned user_ids
    file_info: Optional[Dict[str, Any]] = None  # for file/image messages
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None


@dataclass
class Task:
    """Represents a task."""
    id: str
    title: str
    description: str
    assignee_id: int
    creator_id: int
    due_date: Optional[datetime] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    task_type: str = "personal"  # personal, group, project, chat
    chat_id: Optional[str] = None
    group_id: Optional[str] = None
    project_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    estimated_hours: Optional[float] = None
    actual_hours: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    subtasks: List[str] = field(default_factory=list)  # IDs of subtasks
    parent_task: Optional[str] = None  # ID of parent task


@dataclass
class CalendarEvent:
    """Represents a calendar event."""
    id: str
    title: str
    description: str
    start_time: datetime
    end_time: datetime
    timezone: str = "UTC"
    creator_id: int
    event_type: str = "custom"
    privacy: EventPrivacy = EventPrivacy.PRIVATE
    location: Optional[str] = None
    recurrence_pattern: Optional[str] = None
    recurrence_end: Optional[datetime] = None
    reminder_minutes: Optional[int] = 15
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    chat_id: Optional[str] = None
    attendees: List[int] = field(default_factory=list)
    is_allday: bool = False


@dataclass
class GameSession:
    """Represents a game session."""
    id: str
    game_type: GameType
    players: List[int]
    status: str = "waiting"  # waiting, playing, finished
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    winner_id: Optional[int] = None
    game_data: Dict[str, Any] = field(default_factory=dict)
    current_turn: int = 0


@dataclass
class CallSession:
    """Represents a voice/video call session."""
    session_id: str
    caller_id: int
    callee_id: int
    media_types: List[MediaStreamType] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    status: CallStatus = CallStatus.INITIATED
    duration: Optional[int] = None  # in seconds
    participants: List[int] = field(default_factory=list)


@dataclass
class Notification:
    """Represents a notification."""
    id: str
    user_id: int
    title: str
    message: str
    type: str = "info"  # info, warning, error, success
    created_at: datetime = field(default_factory=datetime.utcnow)
    read: bool = False
    priority: int = 1  # 1-5, 5 highest
    data: Optional[Dict[str, Any]] = None


@dataclass
class FileUpload:
    """Represents an uploaded file."""
    id: str
    original_name: str
    stored_name: str
    size: int
    mime_type: str
    uploader_id: int
    uploaded_at: datetime = field(default_factory=datetime.utcnow)
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
    is_encrypted: bool = False


@dataclass
class AnalyticsEvent:
    """Represents an analytics event."""
    id: str
    user_id: int
    event_type: str
    properties: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    session_id: str
    source: str = "client"  # client, server, api


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
    enable_https: bool = False
    ssl_cert_path: Optional[str] = None
    ssl_key_path: Optional[str] = None
    max_upload_size: int = 10 * 1024 * 1024  # 10MB
    rate_limit_requests: int = 100
    rate_limit_window: int = 60  # seconds
    session_timeout: int = 3600  # 1 hour


# Protocols (interfaces)
class DatabaseInterface(Protocol):
    """Protocol for database operations."""
    
    async def acquire(self) -> Any:  # asyncpg.Connection
        """Acquire a database connection."""
        raise NotImplementedError
    
    async def fetch(self, query: str, *args) -> List[Dict[str, Any]]:
        """Execute a SELECT query."""
        raise NotImplementedError
    
    async def fetchrow(self, query: str, *args) -> Optional[Dict[str, Any]]:
        """Execute a SELECT query and return a single row."""
        raise NotImplementedError
    
    async def execute(self, query: str, *args) -> str:
        """Execute a query."""
        raise NotImplementedError


class RedisInterface(Protocol):
    """Protocol for Redis operations."""
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis."""
        raise NotImplementedError

    async def set(self, key: str, value: str, ex: Optional[int] = None):
        """Set value in Redis."""
        raise NotImplementedError

    async def publish(self, channel: str, message: str):
        """Publish message to Redis channel."""
        raise NotImplementedError
    
    async def hgetall(self, key: str) -> Dict[str, str]:
        """Get all fields and values in a hash."""
        raise NotImplementedError

    async def hset(self, key: str, field: str, value: str):
        """Set field in hash."""
        raise NotImplementedError


class MessageHandler(Protocol):
    """Protocol for message handlers."""
    
    async def handle_message(self, message: Message) -> Optional[Dict[str, Any]]:
        """Handle an incoming message."""
        raise NotImplementedError


class AuthenticationProvider(Protocol):
    """Protocol for authentication providers."""
    
    async def authenticate(self, username: str, password: str) -> Optional[User]:
        """Authenticate a user."""
        raise NotImplementedError

    async def create_session(self, user_id: int) -> str:
        """Create a session for a user."""
        raise NotImplementedError

    async def validate_token(self, token: str) -> Optional[User]:
        """Validate an authentication token."""
        raise NotImplementedError


class EncryptionProvider(Protocol):
    """Protocol for encryption providers."""
    
    def encrypt(self, data: str) -> str:
        """Encrypt data."""
        raise NotImplementedError

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt data."""
        raise NotImplementedError


class StorageProvider(Protocol):
    """Protocol for storage providers."""
    
    async def save_file(self, file_data: bytes, filename: str) -> str:
        """Save a file and return its identifier."""
        raise NotImplementedError

    async def get_file(self, file_id: str) -> Optional[bytes]:
        """Retrieve a file by its identifier."""
        raise NotImplementedError


# Type aliases
UserId = int
ChatId = str
MessageId = str
TaskId = str
EventId = str
GameId = str
CallId = str
NotificationId = str
FileId = str
AnalyticsId = str
SessionId = str
Token = str
IpAddress = str
Port = int
StatusCode = int
Headers = Dict[str, str]
QueryParams = Dict[str, str]
RequestBody = Union[Dict[str, Any], str, bytes]
ResponseBody = Union[Dict[str, Any], str, bytes]
WebSocketConnection = Any
TcpConnection = Any
HttpRequest = Any
HttpResponse = Any
Middleware = Callable[[Any], Awaitable[Any]]
ErrorHandler = Callable[[Exception], Any]
RouteHandler = Callable[[Any], Awaitable[Any]]
BackgroundTask = Callable[[], Awaitable[None]]
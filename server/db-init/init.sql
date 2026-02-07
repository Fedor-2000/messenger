-- server/db-init/init.sql
-- Инициализация базы данных для мессенджера с дополнительными компонентами

-- Таблицы для основного функционала
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    avatar VARCHAR(255) DEFAULT '',
    bio TEXT,
    last_seen TIMESTAMP DEFAULT NOW(),
    online_status VARCHAR(20) DEFAULT 'offline'
);

CREATE TABLE IF NOT EXISTS chats (
    id VARCHAR(100) PRIMARY KEY,
    type VARCHAR(20) NOT NULL,
    name VARCHAR(100),
    description TEXT,
    creator_id INTEGER REFERENCES users(id),
    participants INTEGER[],
    created_at TIMESTAMP DEFAULT NOW(),
    last_message TEXT,
    last_activity TIMESTAMP DEFAULT NOW(),
    unread_count INTEGER DEFAULT 0,
    avatar VARCHAR(255) DEFAULT ''
);

CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    chat_id VARCHAR(100) REFERENCES chats(id),
    sender_id INTEGER REFERENCES users(id),
    content TEXT NOT NULL,
    message_type VARCHAR(20) DEFAULT 'text',
    timestamp TIMESTAMP DEFAULT NOW(),
    reply_to VARCHAR(50),
    edited BOOLEAN DEFAULT FALSE,
    edited_at TIMESTAMP,
    deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,
    mentions INTEGER[],
    reactions JSONB
);

CREATE TABLE IF NOT EXISTS files (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    stored_name VARCHAR(255) NOT NULL,
    uploader_id INTEGER REFERENCES users(id),
    size BIGINT,
    mime_type VARCHAR(100),
    uploaded_at TIMESTAMP DEFAULT NOW()
);

-- Таблицы для WebRTC
CREATE TABLE IF NOT EXISTS call_sessions (
    session_id VARCHAR(100) PRIMARY KEY,
    caller_id INTEGER REFERENCES users(id),
    callee_id INTEGER REFERENCES users(id),
    media_types TEXT[],
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'initiated',
    duration INTEGER  -- в секундах
);

-- Таблицы для задач
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(100) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    assignee_id INTEGER REFERENCES users(id),
    creator_id INTEGER REFERENCES users(id),
    due_date TIMESTAMP,
    priority VARCHAR(20) DEFAULT 'medium',
    status VARCHAR(20) DEFAULT 'pending',
    task_type VARCHAR(20) DEFAULT 'personal',
    chat_id VARCHAR(100),
    group_id VARCHAR(100),
    project_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    estimated_hours DECIMAL(5,2),
    actual_hours DECIMAL(5,2),
    tags TEXT[],
    attachments JSONB,
    subtasks TEXT[],
    parent_task VARCHAR(100)
);

-- Таблицы для календаря
CREATE TABLE IF NOT EXISTS calendar_events (
    id VARCHAR(100) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    timezone VARCHAR(50) DEFAULT 'UTC',
    creator_id INTEGER REFERENCES users(id),
    event_type VARCHAR(20) DEFAULT 'custom',
    privacy VARCHAR(20) DEFAULT 'private',
    location VARCHAR(255),
    recurrence_pattern VARCHAR(20),
    recurrence_end TIMESTAMP,
    reminder_minutes INTEGER DEFAULT 15,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    chat_id VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS event_attendees (
    event_id VARCHAR(100) REFERENCES calendar_events(id),
    user_id INTEGER REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'pending',
    PRIMARY KEY (event_id, user_id)
);

-- Таблицы для уведомлений
CREATE TABLE IF NOT EXISTS notifications (
    id VARCHAR(100) PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    type VARCHAR(20) DEFAULT 'info',
    created_at TIMESTAMP DEFAULT NOW(),
    read BOOLEAN DEFAULT FALSE,
    priority INTEGER DEFAULT 1
);

-- Таблицы для игровой статистики
CREATE TABLE IF NOT EXISTS game_sessions (
    id VARCHAR(100) PRIMARY KEY,
    game_type VARCHAR(50) NOT NULL,
    players INTEGER[],
    winner_id INTEGER REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'playing',
    created_at TIMESTAMP DEFAULT NOW(),
    finished_at TIMESTAMP,
    game_data JSONB
);

CREATE TABLE IF NOT EXISTS user_game_stats (
    user_id INTEGER REFERENCES users(id),
    game_type VARCHAR(50) NOT NULL,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    draws INTEGER DEFAULT 0,
    total_games INTEGER DEFAULT 0,
    rating DECIMAL(5,2) DEFAULT 1000.00,
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, game_type)
);

-- Таблица для хранения ключей шифрования пользователей
CREATE TABLE IF NOT EXISTS user_encryption_keys (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    public_key TEXT NOT NULL,
    private_key_encrypted TEXT NOT NULL,  -- Зашифрованный приватный ключ
    key_algorithm VARCHAR(20) DEFAULT 'RSA-2048',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Таблица для логирования тестовых SMS
CREATE TABLE IF NOT EXISTS sms_test_log (
    id SERIAL PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    sent_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'sent',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Индексы для оптимизации запросов
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_messages_sender_id ON messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen);
CREATE INDEX IF NOT EXISTS idx_chats_last_activity ON chats(last_activity);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee_id ON tasks(assignee_id);
CREATE INDEX IF NOT EXISTS idx_tasks_creator_id ON tasks(creator_id);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_calendar_events_start_time ON calendar_events(start_time);
CREATE INDEX IF NOT EXISTS idx_calendar_events_creator_id ON calendar_events(creator_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(read);
CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at);
CREATE INDEX IF NOT EXISTS idx_call_sessions_started_at ON call_sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_call_sessions_status ON call_sessions(status);
CREATE INDEX IF NOT EXISTS idx_user_encryption_keys_user_id ON user_encryption_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_sms_test_log_sent_at ON sms_test_log(sent_at);
CREATE INDEX IF NOT EXISTS idx_sms_test_log_phone_number ON sms_test_log(phone_number);
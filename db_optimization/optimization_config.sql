# Database Optimization Configuration
# File: db_optimization/optimization_config.sql

-- =============================================
-- ОПТИМИЗАЦИЯ БАЗЫ ДАННЫХ ДЛЯ МЕССЕНДЖЕРА
-- =============================================

-- 1. СОЗДАНИЕ ИНДЕКСОВ

-- Индексы для таблицы пользователей
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);

-- Индексы для таблицы чатов
CREATE INDEX IF NOT EXISTS idx_chats_type ON chats(type);
CREATE INDEX IF NOT EXISTS idx_chats_creator_id ON chats(creator_id);
CREATE INDEX IF NOT EXISTS idx_chats_last_activity ON chats(last_activity);
CREATE INDEX IF NOT EXISTS idx_chats_participants ON chats USING GIN(participants); -- Для массивов

-- Индексы для таблицы сообщений
CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_messages_sender_id ON messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_chat_timestamp ON messages(chat_id, timestamp DESC); -- Для получения истории

-- Индексы для таблицы файлов
CREATE INDEX IF NOT EXISTS idx_files_uploader_id ON files(uploader_id);
CREATE INDEX IF NOT EXISTS idx_files_chat_id ON files(chat_id);
CREATE INDEX IF NOT EXISTS idx_files_uploaded_at ON files(uploaded_at);

-- Индексы для таблицы уведомлений
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_sent ON notifications(sent);
CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at);
CREATE INDEX IF NOT EXISTS idx_notifications_user_created ON notifications(user_id, created_at DESC); -- Для получения уведомлений пользователя

-- Индексы для таблицы голосований
CREATE INDEX IF NOT EXISTS idx_polls_chat_id ON polls(chat_id);
CREATE INDEX IF NOT EXISTS idx_polls_creator_id ON polls(creator_id);
CREATE INDEX IF NOT EXISTS idx_polls_created_at ON polls(created_at);

-- 2. ПАРАМЕТРЫ ПРОИЗВОДИТЕЛЬНОСТИ PostgreSQL

-- Увеличение размера разделяемой памяти
ALTER SYSTEM SET shared_buffers = '256MB'; -- Рекомендуется 25% от RAM

-- Увеличение размера буфера WAL
ALTER SYSTEM SET wal_buffers = '16MB';

-- Увеличение эффективности работы с кэшем
ALTER SYSTEM SET effective_cache_size = '1GB';

-- Увеличение числа одновременных подключений
ALTER SYSTEM SET max_connections = 200;

-- Увеличение числа рабочих процессов
ALTER SYSTEM SET max_worker_processes = 4;
ALTER SYSTEM SET max_parallel_workers_per_gather = 2;
ALTER SYSTEM SET max_parallel_workers = 4;

-- Настройка времени автовакуума
ALTER SYSTEM SET autovacuum_vacuum_scale_factor = 0.1; -- Вакуум при 10% изменений
ALTER SYSTEM SET autovacuum_analyze_scale_factor = 0.05; -- Анализ при 5% изменений
ALTER SYSTEM SET autovacuum_vacuum_threshold = 1000; -- Минимум 1000 строк
ALTER SYSTEM SET autovacuum_analyze_threshold = 500; -- Минимум 500 строк

-- 3. СОЗДАНИЕ ПРЕДСТАВЛЕНИЙ ДЛЯ ЧАСТОГО ЗАПРОСА

-- Представление для получения информации о чате с последним сообщением
CREATE OR REPLACE VIEW chat_with_last_message AS
SELECT 
    c.id,
    c.type,
    c.name,
    c.creator_id,
    c.participants,
    c.created_at,
    c.last_message,
    c.last_activity,
    c.unread_count,
    m.content as last_message_content,
    m.sender_id as last_message_sender_id,
    u.username as last_message_sender_username,
    m.timestamp as last_message_timestamp
FROM chats c
LEFT JOIN messages m ON c.last_message = m.id
LEFT JOIN users u ON m.sender_id = u.id;

-- Представление для получения активных пользователей
CREATE OR REPLACE VIEW active_users AS
SELECT 
    u.id,
    u.username,
    u.avatar,
    u.created_at,
    MAX(m.timestamp) as last_activity
FROM users u
LEFT JOIN messages m ON u.id = m.sender_id
GROUP BY u.id, u.username, u.avatar, u.created_at
HAVING MAX(m.timestamp) > NOW() - INTERVAL '30 days' OR u.created_at > NOW() - INTERVAL '30 days'
ORDER BY last_activity DESC;

-- 4. СОЗДАНИЕ ФУНКЦИЙ ДЛЯ ОПТИМИЗАЦИИ ЗАПРОСОВ

-- Функция для получения истории чата с пагинацией
CREATE OR REPLACE FUNCTION get_chat_history(
    p_chat_id VARCHAR(100),
    p_limit INTEGER DEFAULT 50,
    p_offset INTEGER DEFAULT 0
) RETURNS TABLE (
    id INTEGER,
    sender_id INTEGER,
    username VARCHAR(50),
    content TEXT,
    message_type VARCHAR(20),
    timestamp TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        m.id,
        m.sender_id,
        u.username,
        m.content,
        m.message_type,
        m.timestamp
    FROM messages m
    JOIN users u ON m.sender_id = u.id
    WHERE m.chat_id = p_chat_id
    ORDER BY m.timestamp DESC
    LIMIT p_limit OFFSET p_offset;
END;
$$ LANGUAGE plpgsql;

-- Функция для получения чатов пользователя
CREATE OR REPLACE FUNCTION get_user_chats(
    p_user_id INTEGER,
    p_limit INTEGER DEFAULT 50,
    p_offset INTEGER DEFAULT 0
) RETURNS TABLE (
    id VARCHAR(100),
    type VARCHAR(20),
    name VARCHAR(100),
    creator_id INTEGER,
    participants INTEGER[],
    created_at TIMESTAMP,
    last_message TEXT,
    last_activity TIMESTAMP,
    unread_count INTEGER,
    last_message_content TEXT,
    last_message_sender_username VARCHAR(50),
    last_message_timestamp TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id,
        c.type,
        c.name,
        c.creator_id,
        c.participants,
        c.created_at,
        c.last_message,
        c.last_activity,
        c.unread_count,
        clm.last_message_content,
        clm.last_message_sender_username,
        clm.last_message_timestamp
    FROM chats c
    LEFT JOIN chat_with_last_message clm ON c.id = clm.id
    WHERE p_user_id = ANY(c.participants)
    ORDER BY c.last_activity DESC
    LIMIT p_limit OFFSET p_offset;
END;
$$ LANGUAGE plpgsql;

-- 5. СОЗДАНИЕ ТРИГГЕРОВ ДЛЯ ОПТИМИЗАЦИИ

-- Триггер для обновления времени последней активности в чате при добавлении сообщения
CREATE OR REPLACE FUNCTION update_chat_last_activity()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE chats 
    SET 
        last_activity = NEW.timestamp,
        last_message = NEW.id
    WHERE id = NEW.chat_id;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_chat_last_activity ON messages;
CREATE TRIGGER trigger_update_chat_last_activity
    AFTER INSERT ON messages
    FOR EACH ROW
    EXECUTE FUNCTION update_chat_last_activity();

-- 6. СОЗДАНИЕ ЧАСТИЦ ДЛЯ БОЛЬШИХ ТАБЛИЦ

-- Создание секционированной таблицы сообщений по месяцам
CREATE TABLE IF NOT EXISTS messages_partitioned (
    id SERIAL,
    chat_id VARCHAR(100) NOT NULL,
    sender_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    message_type VARCHAR(20) DEFAULT 'text',
    timestamp TIMESTAMP DEFAULT NOW()
) PARTITION BY RANGE (timestamp);

-- Создание секций для текущего и следующих месяцев
DO $$ 
DECLARE
    create_month DATE := DATE_TRUNC('month', CURRENT_DATE);
    end_month DATE := DATE_TRUNC('month', CURRENT_DATE + INTERVAL '12 months');
    partition_name TEXT;
    partition_range_start DATE;
    partition_range_end DATE;
BEGIN
    WHILE create_month <= end_month LOOP
        partition_name := 'messages_' || TO_CHAR(create_month, 'YYYY_MM');
        partition_range_start := create_month;
        partition_range_end := create_month + INTERVAL '1 month';
        
        EXECUTE '
            CREATE TABLE IF NOT EXISTS ' || partition_name || ' PARTITION OF messages_partitioned
            FOR VALUES FROM (''' || partition_range_start || ''') TO (''' || partition_range_end || ''');
        ';
        
        -- Создание индексов для секции
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_' || partition_name || '_chat_timestamp ON ' || partition_name || '(chat_id, timestamp DESC);';
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_' || partition_name || '_sender ON ' || partition_name || '(sender_id);';
        
        create_month := create_month + INTERVAL '1 month';
    END LOOP;
END $$;

-- 7. СОЗДАНИЕ СТАТИСТИКИ ДЛЯ ОПТИМИЗАТОРА ЗАПРОСОВ

-- Создание расширенной статистики для анализа корреляции
CREATE STATISTICS IF NOT EXISTS user_chat_stats (dependencies) ON creator_id, participants FROM chats;
CREATE STATISTICS IF NOT EXISTS message_content_stats (mcv) ON chat_id, sender_id FROM messages;

-- 8. КОНФИГУРАЦИЯ ПУЛА КОННЕКШЕНОВ

-- Настройка PgBouncer (если используется)
-- pool_mode = transaction
-- default_pool_size = 25
-- max_client_conn = 1000

-- 9. РЕКОМЕНДАЦИИ ПО ШАРДИНГУ

/*
Для дальнейшего масштабирования рекомендуется реализовать шардинг:

1. Горизонтальное разделение по пользователям:
   - Шард 1: пользователи с id 1-100000
   - Шард 2: пользователи с id 100001-200000
   и т.д.

2. Или шардинг по чатам:
   - Каждый крупный чат на отдельном шарде
   - Общие системные данные на отдельном шарде

3. Использование Citus Data или других решений для автоматического шардинга
*/

-- 10. РЕКОМЕНДАЦИИ ПО РЕПЛИКАЦИИ

/*
Для обеспечения высокой доступности рекомендуется настроить:
1. Streaming replication (горячая реплика)
2. Logical replication (для отдельных таблиц)
3. Настройка автоматического переключения (failover) с помощью Patroni или аналогов
*/

-- Применение изменений
SELECT pg_reload_conf();
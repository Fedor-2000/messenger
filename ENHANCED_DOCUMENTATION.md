# Расширенная документация проекта: Гибридный мессенджер

## Обзор

Этот проект представляет собой гибридный мессенджер с серверной частью на Python и клиентами на C++/Qt и мобильных платформах. Проект включает в себя расширенный функционал, включая шифрование end-to-end, двухфакторную аутентификацию, масштабируемую архитектуру и дополнительные сервисы.

## Архитектура

### Серверная часть

**Технологии:**
- Python 3.11
- aiohttp для HTTP/WebSocket
- asyncio для асинхронности
- asyncpg для PostgreSQL
- redis-py для Redis
- PyJWT для аутентификации
- bcrypt для хеширования паролей
- cryptography для шифрования сообщений
- aiokafka для масштабируемости
- aiocache для кэширования

**Компоненты:**
- `main.py` - основной серверный код
- `advanced_encryption.py` - модуль расширенного шифрования
- `advanced_auth.py` - модуль расширенной аутентификации
- `performance_optimizer.py` - модуль оптимизации производительности
- `enhanced_features.py` - модуль расширенных возможностей
- `scalability_manager.py` - менеджер масштабируемости
- `additional_services.py` - дополнительные сервисы

### Клиентская часть

**Технологии:**
- C++17
- Qt6 для GUI
- Boost.Asio для сетевых операций
- nlohmann/json для работы с JSON
- OpenSSL для шифрования

**Компоненты:**
- `mainwindow.cpp/h` - главное окно приложения
- `messagelistmodel.cpp/h` - модель данных для списка сообщений
- `settings.cpp/h` - управление настройками
- `enhanced_ui_features.cpp/h` - расширенные возможности UI
- `mainwindow.ui` - дизайн интерфейса

## Безопасность

### Шифрование

#### Основное шифрование
- **AES-256-GCM** для аутентифицированного шифрования
- **PBKDF2** для генерации ключей из паролей
- **SHA-256** для хеширования мастер-ключа
- **Salt** для предотвращения атак rainbow table

#### End-to-End шифрование
- Реализация сквозного шифрования для приватных сообщений
- Использование симметричных ключей для упрощения (в реальном приложении - ассиметричные)
- Возможность шифрования сообщений для конкретных получателей

#### Аутентификация
- **JWT-токены** с временем жизни 15 минут для access токенов
- **Refresh токены** с временем жизни 30 дней
- **Хеширование паролей** с помощью bcrypt (12 раундов)
- **Двухфакторная аутентификация** (SMS, Email, Authenticator app)
- **Блокировка аккаунтов** после 5 неудачных попыток
- **Сессии** с хранением в Redis и базе данных

### Защита
- **Рейт-лимитер** для предотвращения DDoS-атак
- **Валидация всех входных данных**
- **Санитизация пользовательского ввода**
- **SQL-инъекция защита** через подготовленные выражения
- **XSS защита** через экранирование вывода

## Функциональность

### Основные возможности
- Поддержка TCP и WebSocket соединений
- Приватные и групповые чаты
- Передача файлов (изображения, документы, аудио, видео)
- История сообщений с пагинацией
- Упоминания пользователей (@username)
- Уведомления

### Расширенные возможности
- **Форматирование текста** (Markdown, жирный, курсив, код)
- **Эмодзи и стикеры**
- **Цитирование сообщений**
- **Редактирование и удаление сообщений**
- **Ответы на конкретные сообщения**
- **Реакции на сообщения** (лайки, смайлы)
- **Поиск по сообщениям**
- **Фильтрация по дате, пользователю, типу**
- **Индикаторы набора текста**
- **Сохранение черновиков**
- **Автодополнение упоминаний**
- **Горячие клавиши**

### Групповая функциональность
- Создание и управление группами
- Роли участников (администратор, модератор, участник)
- Приглашения в группы
- Приватные каналы внутри групп
- Разграничение прав (отправка сообщений, редактирование, удаление)

### Медиа функции
- Поддержка изображений, видео, аудио
- Предпросмотр изображений
- Галерея медиафайлов
- Поддержка голосовых сообщений
- Просмотр документов

## Производительность

### Оптимизация базы данных
- Подготовленные выражения для часто используемых запросов
- Индексы для часто используемых полей
- Connection pooling с оптимизированными настройками
- Массовая вставка данных
- Пагинация с эффективными запросами

### Оптимизация сети
- Компрессия данных при передаче
- Использование Protocol Buffers (в будущем)
- Оптимизация WebSocket соединений
- Load balancing между серверами

### Оптимизация клиентов
- Lazy loading сообщений
- Кэширование данных на клиенте
- Оптимизация UI рендеринга
- Анимации с аппаратным ускорением

### Кэширование
- LRU кэш в памяти для часто запрашиваемых данных
- Redis кэш для долгосрочного хранения
- Кэширование результатов запросов
- Кэширование результатов шифрования

## Масштабируемость

### Архитектурные улучшения
- Микросервисная архитектура
- Message queues (Kafka) для асинхронной обработки
- Service discovery
- Kubernetes orchestration

### Горизонтальное масштабирование
- Балансировка нагрузки через HAProxy/Nginx
- Кластеризация баз данных (PostgreSQL streaming replication)
- Кластеризация Redis
- CDN для статических файлов

### Автомасштабирование
- Мониторинг метрик (CPU, Memory, Requests/sec)
- Автоматическое масштабирование на основе нагрузки
- Health checks для проверки состояния сервисов
- Circuit breaker для отказоустойчивости

## Клиенты

### Qt-клиент
- Полнофункциональный десктопный клиент
- Поддержка тем (светлая/темная)
- Горячие клавиши
- Уведомления
- Индикаторы статуса пользователей
- Эмодзи панель
- Форматирование текста

### Мобильный клиент
- Кроссплатформенное приложение (iOS/Android)
- Поддержка push-уведомлений
- Offline режим
- Camera integration
- Contacts sync
- Biometric authentication

## Дополнительные сервисы

### Уведомления
- Push-уведомления
- Email-уведомления
- Внутренние уведомления
- Настройка приоритетов
- Режим "не беспокоить"

### Аналитика
- Отслеживание событий пользователей
- Метрики вовлеченности
- DAU/WAU/MAU статистика
- Поведенческий анализ

### Модерация
- Автоматическая модерация текста
- Модерация изображений
- Спам-фильтр
- Блокировка пользователей
- Жалобы пользователей

### Перевод
- Автоматический перевод сообщений
- Определение языка
- Поддержка множества языков

### ИИ-сервисы
- Анализ тональности сообщений
- Генерация умных ответов
- Краткое содержание длинных сообщений
- Обнаружение спама с помощью ИИ

## Инфраструктура

### Docker
- Контейнеризация всех компонентов
- Docker Compose для оркестрации
- Автоматическая сборка образов
- Multi-stage builds для оптимизации

### Мониторинг
- Prometheus для сбора метрик
- Grafana для визуализации
- Alertmanager для уведомлений
- ELK stack для логирования
- Health checks

### Резервное копирование
- Регулярное резервное копирование базы данных
- Хранение резервных копий в S3
- Восстановление из резервных копий
- Проверка целостности резервных копий

## CI/CD

### Pipeline
- Автоматические тесты (unit, integration)
- Проверка безопасности (Trivy)
- Статический анализ кода
- Форматирование кода
- Типизация (mypy)
- Линтинг (flake8, cppcheck)

### Деплой
- Автоматический деплой на staging
- Ручной деплой на production
- Blue-green deployment
- Canary releases
- Rollback в случае ошибок

### Тестирование
- Unit-тесты для бизнес-логики
- Интеграционные тесты для API
- Нагрузочное тестирование
- Тестирование безопасности

## API

### WebSocket API

#### Подключение
```
ws://localhost:8080/ws
```

#### Типы сообщений

**Аутентификация:**
```json
{
  "type": "auth",
  "username": "user123",
  "password": "password123",
  "two_factor_token": "optional_2fa_token"
}
```

**Ответ при успешной аутентификации:**
```json
{
  "type": "auth_success",
  "access_token": "jwt-access-token",
  "refresh_token": "jwt-refresh-token",
  "user_id": 123,
  "username": "user123",
  "expires_in": 900
}
```

**Отправка сообщения:**
```json
{
  "type": "message",
  "access_token": "jwt-access-token",
  "chat_id": "general",
  "content": "Привет, мир!",
  "message_type": "text",
  "reply_to": "optional_message_id",
  "mentions": [456, 789]
}
```

**Получение сообщения:**
```json
{
  "type": "new_message",
  "chat_id": "general",
  "message": {
    "id": "msg123",
    "sender_id": 123,
    "content": "Привет, мир!",
    "message_type": "text",
    "timestamp": "2023-12-01T10:00:00Z",
    "reply_to": "optional_message_id",
    "mentions": [456, 789]
  }
}
```

### REST API

#### Регистрация
```
POST /api/v1/register
Content-Type: application/json

{
  "username": "newuser",
  "password": "password123",
  "email": "user@example.com",
  "phone": "+1234567890"
}
```

#### Вход
```
POST /api/v1/login
Content-Type: application/json

{
  "username": "user123",
  "password": "password123"
}
```

#### Отправка сообщения
```
POST /api/v1/chats/{chat_id}/messages
Authorization: Bearer jwt-access-token
Content-Type: application/json

{
  "content": "Привет, мир!",
  "message_type": "text",
  "reply_to": "optional_message_id",
  "encrypt_for_recipients": false
}
```

#### Получение истории
```
GET /api/v1/chats/{chat_id}/messages?page=1&limit=50
Authorization: Bearer jwt-access-token
```

## База данных

### Структура таблиц

#### users
- id: SERIAL PRIMARY KEY
- username: VARCHAR(50) UNIQUE NOT NULL
- password_hash: VARCHAR(255)
- email: VARCHAR(100)
- phone: VARCHAR(20)
- auth_level: VARCHAR(20) DEFAULT 'basic'
- two_factor_enabled: BOOLEAN DEFAULT FALSE
- two_factor_method: VARCHAR(20)
- two_factor_secret: VARCHAR(255)
- created_at: TIMESTAMP DEFAULT NOW()
- last_seen: TIMESTAMP
- online_status: VARCHAR(20) DEFAULT 'offline'
- avatar: VARCHAR(255) DEFAULT ''
- bio: TEXT

#### chats
- id: VARCHAR(100) PRIMARY KEY
- type: VARCHAR(20) NOT NULL (private/group/channel)
- name: VARCHAR(100)
- description: TEXT
- creator_id: INTEGER REFERENCES users(id)
- participants: INTEGER[]
- admins: INTEGER[]
- created_at: TIMESTAMP DEFAULT NOW()
- updated_at: TIMESTAMP DEFAULT NOW()
- last_message: TEXT
- last_activity: TIMESTAMP DEFAULT NOW()
- unread_count: INTEGER DEFAULT 0
- avatar: VARCHAR(255)

#### messages
- id: VARCHAR(50) PRIMARY KEY
- chat_id: VARCHAR(100) REFERENCES chats(id)
- sender_id: INTEGER REFERENCES users(id)
- content: TEXT NOT NULL
- message_type: VARCHAR(20) DEFAULT 'text'
- timestamp: TIMESTAMP DEFAULT NOW()
- reply_to: VARCHAR(50) REFERENCES messages(id)
- edited: BOOLEAN DEFAULT FALSE
- edited_at: TIMESTAMP
- deleted: BOOLEAN DEFAULT FALSE
- deleted_at: TIMESTAMP
- mentions: INTEGER[]

#### message_reactions
- id: SERIAL PRIMARY KEY
- message_id: VARCHAR(50) REFERENCES messages(id)
- user_id: INTEGER REFERENCES users(id)
- emoji: VARCHAR(10) NOT NULL
- created_at: TIMESTAMP DEFAULT NOW()

#### user_sessions
- id: SERIAL PRIMARY KEY
- user_id: INTEGER REFERENCES users(id)
- session_id: VARCHAR(255) UNIQUE NOT NULL
- ip_address: VARCHAR(45)
- user_agent: TEXT
- created_at: TIMESTAMP DEFAULT NOW()
- expires_at: TIMESTAMP NOT NULL
- last_activity: TIMESTAMP DEFAULT NOW()
- revoked: BOOLEAN DEFAULT FALSE

#### analytics_events
- id: VARCHAR(50) PRIMARY KEY
- user_id: INTEGER REFERENCES users(id)
- event_type: VARCHAR(50) NOT NULL
- properties: JSONB
- timestamp: TIMESTAMP DEFAULT NOW()
- session_id: VARCHAR(50)

#### notifications
- id: VARCHAR(50) PRIMARY KEY
- user_id: INTEGER REFERENCES users(id)
- title: VARCHAR(255) NOT NULL
- message: TEXT NOT NULL
- type: VARCHAR(20) DEFAULT 'info'
- created_at: TIMESTAMP DEFAULT NOW()
- read: BOOLEAN DEFAULT FALSE
- priority: INTEGER DEFAULT 1

#### refresh_tokens
- id: SERIAL PRIMARY KEY
- user_id: INTEGER REFERENCES users(id)
- token: VARCHAR(255) UNIQUE NOT NULL
- expires_at: TIMESTAMP NOT NULL
- revoked: BOOLEAN DEFAULT FALSE
- created_at: TIMESTAMP DEFAULT NOW()

#### group_permissions
- id: SERIAL PRIMARY KEY
- group_id: VARCHAR(100) REFERENCES chats(id)
- user_id: INTEGER REFERENCES users(id)
- permission: VARCHAR(50) NOT NULL
- granted_at: TIMESTAMP DEFAULT NOW()
- granted_by: INTEGER REFERENCES users(id)

## Тестирование

### Unit-тесты
- Тестирование бизнес-логики
- Тестирование безопасности
- Тестирование валидации
- Тестирование шифрования

### Интеграционные тесты
- Тестирование API
- Тестирование базы данных
- Тестирование сетевых соединений
- Тестирование Redis

### Нагрузочное тестирование
- Тестирование производительности
- Тестирование масштабируемости
- Тестирование отказоустойчивости

## Развертывание

### Локальное развертывание
1. Установить Docker и Docker Compose
2. Скопировать .env.example в .env
3. Настроить переменные окружения
4. Запустить `docker-compose up -d`

### Облачное развертывание
1. Настроить DNS-записи
2. Настроить SSL-сертификаты
3. Обновить .env с production-значениями
4. Запустить на сервере с Kubernetes или Docker Swarm

## Лицензия

Проект распространяется под MIT-лицензией.

## Поддержка

Для получения поддержки:
- Создайте issue в репозитории
- Обратитесь в службу поддержки
- Посетите наш форум разработчиков
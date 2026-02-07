# Инструкция по запуску мессенджера

## Требования

- Docker (версия 20.10 или выше)
- Docker Compose (версия 2.0 или выше)
- Git
- Python 3.10+
- Flutter SDK (для мобильного клиента)
- Android SDK (для сборки APK)

## Установка и запуск

### 1. Клонирование репозитория

```bash
git clone https://github.com/yourusername/messenger-project.git
cd messenger-project
```

### 2. Настройка конфигурации

Скопируйте пример файла конфигурации:

```bash
cp .env.example .env
```

Отредактируйте файл `.env`, установив свои значения:

```bash
JWT_SECRET=your-super-secret-jwt-key-change-it
MESSAGE_ENCRYPTION_KEY=your-message-encryption-key
POSTGRES_PASSWORD=your-secure-password
REDIS_PASSWORD=your-secure-redis-password
GRAFANA_PASSWORD=your-secure-grafana-password
DOMAIN=localhost
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
TWILIO_ACCOUNT_SID=your-twilio-account-sid
TWILIO_AUTH_TOKEN=your-twilio-auth-token
TWILIO_PHONE_NUMBER=+1234567890
AWS_ACCESS_KEY_ID=your-aws-access-key-id
AWS_SECRET_ACCESS_KEY=your-aws-secret-access-key
AWS_REGION=us-east-1
FCM_SERVER_KEY=your-firebase-server-key
APNS_CERT_PATH=path/to/apns/cert.pem
APNS_KEY_PATH=path/to/apns/key.pem
APNS_TOPIC=com.yourcompany.messenger
APNS_TEAM_ID=your-team-id
APNS_KEY_ID=your-key-id
```

### 3. Установка зависимостей

#### Установка Python зависимостей (если запускаете локально):
```bash
cd server
pip install -r requirements.txt
```

#### Установка Flutter зависимостей (для мобильного клиента):
```bash
cd mobile_client
flutter pub get
```

### 4. Запуск проекта

#### Вариант 1: Использование Docker Compose (рекомендуется)

```bash
docker-compose up -d
```

#### Вариант 2: Использование скрипта

```bash
./scripts/start-messenger.sh
```

#### Вариант 3: Локальный запуск сервера (для разработки)

```bash
cd server
python -m app.main
```

### 5. Проверка запуска

Проверьте статус сервисов:

```bash
docker-compose ps
```

Должны быть запущены все сервисы: `messenger-server`, `db`, `redis`, `nginx`, `prometheus`, `grafana`, `webrtc-signaling`, `notification-service`, `auth-service`, `calendar-service`, `task-service`, `game-service`, `call-service`, `file-service`, `analytics-service`.

## Доступ к сервисам

После запуска проект будет доступен по следующим адресам:

- **Основной мессенджер**: http://localhost
- **TCP-порт для C++ клиентов**: localhost:8888
- **WebSocket/HTTP API**: localhost:8080
- **Grafana (мониторинг)**: http://localhost:3000
- **Prometheus**: http://localhost:9090
- **Adminer (администрирование БД)**: http://localhost:8081
- **API документация**: http://localhost:8080/docs
- **WebSocket endpoint**: ws://localhost:8080/ws

## Остановка проекта

Для остановки всех сервисов выполните:

```bash
docker-compose down
```

## Перезапуск проекта

Для перезапуска проекта:

```bash
docker-compose down
docker-compose up -d
```

## Обновление проекта

Для обновления до последней версии:

```bash
git pull origin main
docker-compose build --no-cache
docker-compose up -d
```

## Проверка логов

Для просмотра логов конкретного сервиса:

```bash
# Логи сервера
docker-compose logs -f messenger-server

# Логи базы данных
docker-compose logs -f db

# Логи Redis
docker-compose logs -f redis

# Логи всех сервисов
docker-compose logs -f
```

## Удаление данных

Для полного удаления всех данных (включая базу данных):

```bash
docker-compose down -v
```

Предупреждение: эта команда удалит все данные, включая сообщения, пользователей, задачи и события календаря!

## Запуск тестов

Для запуска юнит-тестов:

```bash
cd server
python -m pytest tests/unit/ -v
```

Для запуска всех тестов:

```bash
cd server
python -m pytest tests/ -v
```

Для запуска с измерением покрытия:

```bash
python -m pytest tests/ --cov=app --cov-report=html
```

## Разработка

### Сборка отдельных компонентов

#### Сервер

Сервер находится в папке `server/` и использует Python 3.10+.

Для локального запуска сервера:

```bash
cd server
python -m app.main
```

#### Qt-клиент

Qt-клиент находится в папке `client-qt/` и использует Qt6.

Для локальной сборки Qt-клиента:

```bash
cd client-qt
mkdir build
cd build
cmake ..
make
```

#### Мобильный клиент

Мобильный клиент находится в папке `mobile_client/` и использует Flutter.

Для запуска мобильного клиента:

```bash
cd mobile_client
flutter run
```

Для сборки APK:

```bash
flutter build apk --release
```

### Запуск отдельных сервисов

Все сервисы могут быть запущены отдельно:

```bash
# Запуск только сервера
docker-compose up messenger-server

# Запуск сервера и базы данных
docker-compose up messenger-server db

# Запуск всех сервисов
docker-compose up -d
```

## Безопасность

Проект включает в себя следующие меры безопасности:

- JWT-аутентификация для всех запросов
- Двухфакторная аутентификация (2FA) с использованием TOTP
- Шифрование сообщений при передаче и хранении (AES-256-GCM)
- Защита от DDoS-атак через улучшенный рейт-лимитер
- Валидация всех входных данных
- Использование SSL/TLS для шифрования соединений
- Сквозное шифрование для приватных сообщений
- Проверка подлинности устройств через device fingerprinting
- Защита от повторного использования токенов через JWT ID (jti)

## Мониторинг

Система включает в себя:

- Prometheus для сбора метрик производительности
- Grafana для визуализации метрик
- Встроенные логи в каждом сервисе
- Метрики производительности (запросы, задержки, соединения)
- Мониторинг здоровья сервисов
- Система алертов при аномалиях

## Конфигурация внешних сервисов

Для полноценной работы приложения необходимо настроить:

### Email уведомления
- SMTP сервер (Gmail, SendGrid, Mailgun)
- Учетные данные в `.env` файле

### SMS уведомления
- Twilio или AWS SNS учетные данные
- Телефонный номер отправителя

### Push-уведомления
- Firebase Cloud Messaging (FCM) для Android
- Apple Push Notification Service (APNs) для iOS

## Возможные проблемы и решения

### Проблема: Порт уже используется

Если вы получаете ошибку "port is already allocated", проверьте, не запущены ли другие сервисы на тех же портах.

### Проблема: Недостаточно прав

Если возникают проблемы с доступом к Docker, убедитесь, что ваш пользователь добавлен в группу docker:

```bash
sudo usermod -aG docker $USER
```

После этого перезайдите в систему.

### Проблема: Сервис не запускается

Проверьте логи сервиса:

```bash
docker-compose logs <service-name>
```

### Проблема: Ошибки при отправке email/SMS

Убедитесь, что вы настроили учетные данные для внешних сервисов в файле `.env`.

## Структура проекта

```
messenger-project/
├── server/                 # Серверная часть на Python
│   ├── app/               # Основной код сервера
│   │   ├── webrtc/        # WebRTC сигнализация
│   │   ├── games/         # Игровые сервисы
│   │   ├── tasks/         # Система задач
│   │   ├── analytics/     # Аналитика чатов
│   │   ├── calendar/      # Интеграция с календарем
│   │   ├── advanced_auth.py  # Улучшенная аутентификация
│   │   ├── advanced_encryption.py  # Улучшенное шифрование
│   │   ├── advanced_security.py  # Улучшенная безопасность
│   │   ├── performance_optimizations.py  # Оптимизации производительности
│   │   ├── scalability_manager.py  # Менеджер масштабирования
│   │   └── main.py        # Главный серверный файл
│   ├── tests/             # Тесты
│   │   ├── unit/          # Модульные тесты
│   │   └── integration/   # Интеграционные тесты
│   ├── db-init/           # Скрипты инициализации БД
│   ├── Dockerfile         # Dockerfile для сервера
│   └── requirements.txt   # Зависимости Python
├── client-qt/             # Qt-клиент на C++
├── mobile_client/         # Мобильный клиент на Flutter
├── services/              # Микросервисы
│   ├── auth_service/      # Сервис аутентификации
│   ├── chat_service/      # Сервис чатов
│   ├── notification_service/  # Сервис уведомлений
│   ├── task_service/      # Сервис задач
│   ├── calendar_service/  # Сервис календаря
│   ├── game_service/      # Сервис игр
│   ├── call_service/      # Сервис звонков
│   ├── file_service/      # Сервис файлов
│   └── analytics_service/ # Сервис аналитики
├── caching/               # Система кэширования
├── nginx/                 # Конфигурация Nginx
├── prometheus/            # Конфигурация Prometheus
├── grafana/               # Конфигурация Grafana
├── scripts/               # Скрипты для запуска и обслуживания
├── docker-compose.yml     # Основная конфигурация Docker Compose
├── .env                   # Файл конфигурации
├── .env.example          # Пример файла конфигурации
├── RUNNING_INSTRUCTIONS.md # Инструкция по запуску
├── DOCUMENTATION.md       # Полная документация
├── DOCUMENTATION_FULL.md  # Расширенная документация
├── CODE_QUALITY_GUIDELINES.md # Руководство по качеству кода
├── SECURITY.md            # Документация по безопасности
└── README.md             # Основная документация
```

## Запуск в продакшене

Для запуска в продакшене:

1. Обновите все учетные данные в `.env` файле
2. Настройте SSL-сертификаты
3. Убедитесь, что все внешние сервисы (email, SMS, push) настроены
4. Запустите с помощью:
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```

## Масштабирование

Для масштабирования приложения:

1. Используйте Redis для хранения сессий (позволяет использовать несколько экземпляров сервера)
2. Настройте балансировщик нагрузки
3. Используйте PostgreSQL в режиме репликации
4. Добавьте дополнительные экземпляры сервисов:
   ```bash
   docker-compose up --scale messenger-server=3
   ```
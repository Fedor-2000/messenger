FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем инструменты анализа качества кода
RUN pip install \
    black==23.10.1 \
    isort==5.12.0 \
    flake8==6.0.0 \
    mypy==1.7.1 \
    bandit==1.7.5 \
    pytest==7.4.3 \
    pytest-asyncio==0.21.1

# Копируем исходный код
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY pyproject.toml ./
COPY mypy.ini ./

# Создаем пользователя для безопасности
RUN useradd -m -u 1000 messenger && chown -R messenger:messenger /app
USER messenger

# Открываем порты
EXPOSE 8888  # TCP для C++ клиентов
EXPOSE 8080  # HTTP/WebSocket для web

# Запускаем сервер
CMD ["python", "-u", "app/main.py"]
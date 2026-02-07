#!/bin/bash
# scripts/start-messenger.sh

set -e

echo "=== Запуск мессенджера ==="

# Проверяем, установлены ли Docker и Docker Compose
if ! command -v docker &> /dev/null; then
    echo "Docker не установлен. Пожалуйста, установите Docker."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "Docker Compose не установлен. Пожалуйста, установите Docker Compose."
    exit 1
fi

# Проверяем наличие .env файла
if [ ! -f .env ]; then
    echo "Файл .env не найден. Копируем .env.example..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "Файл .env создан из .env.example. Пожалуйста, настройте его перед запуском."
        exit 1
    else
        echo "Файл .env.example также отсутствует. Создайте .env файл вручную."
        exit 1
    fi
fi

echo "Запускаем сервисы..."
docker-compose up -d

echo "Ожидаем запуска сервисов..."
sleep 10

echo "Проверяем статус сервисов..."
docker-compose ps

echo ""
echo "=== Мессенджер запущен ==="
echo "Сервер доступен:"
echo "  - TCP (для C++ клиентов): localhost:8888"
echo "  - WebSocket/HTTP (для веб-клиентов): localhost:8080"
echo "  - Веб-интерфейс: http://localhost"
echo "  - Grafana (мониторинг): http://localhost:3000"
echo "  - Prometheus: http://localhost:9090"
echo ""
echo "Для остановки используйте: docker-compose down"
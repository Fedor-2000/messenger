#!/bin/bash
# scripts/run_code_quality.sh

set -e

echo "=== Запуск проверки качества кода ==="

# Проверяем, установлены ли инструменты
if ! command -v python &> /dev/null; then
    echo "Python не установлен"
    exit 1
fi

if ! command -v black &> /dev/null; then
    echo "Black не установлен. Установите с помощью: pip install black"
    exit 1
fi

if ! command -v isort &> /dev/null; then
    echo "isort не установлен. Установите с помощью: pip install isort"
    exit 1
fi

if ! command -v flake8 &> /dev/null; then
    echo "flake8 не установлен. Установите с помощью: pip install flake8"
    exit 1
fi

if ! command -v mypy &> /dev/null; then
    echo "mypy не установлен. Установите с помощью: pip install mypy"
    exit 1
fi

if ! command -vm bandit &> /dev/null; then
    echo "bandit не установлен. Установите с помощью: pip install bandit"
    exit 1
fi

echo "1. Запуск форматирования с помощью black..."
black --config pyproject.toml server/

echo "2. Сортировка импортов с помощью isort..."
isort --settings-path pyproject.toml server/

echo "3. Проверка стиля кода с помощью flake8..."
flake8 --config .flake8 server/

echo "4. Проверка типов с помощью mypy..."
mypy --config-file mypy.ini server/

echo "5. Проверка безопасности с помощью bandit..."
bandit -c pyproject.toml -r server/

echo "6. Запуск тестов с покрытием кода..."
python -m pytest tests/ -v --cov=app --cov-report=html --cov-report=term-missing

echo ""
echo "=== Проверка качества кода завершена ==="
echo "Форматирование и анализ завершены успешно!"
echo ""
echo "Отчеты о покрытии кода доступны в директории htmlcov/"
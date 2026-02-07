#!/bin/bash
# mobile_client/build_apk.sh

set -e

echo "=== Сборка APK для мессенджера ==="

# Проверяем, установлены ли необходимые инструменты
if ! command -v flutter &> /dev/null; then
    echo "Flutter не установлен. Пожалуйста, установите Flutter."
    exit 1
fi

if ! command -v adb &> /dev/null; then
    echo "ADB не установлен. Убедитесь, что Android SDK установлен и добавлен в PATH."
    exit 1
fi

echo "Проверка конфигурации Flutter..."
flutter doctor

echo "Установка зависимостей..."
flutter pub get

echo "Анализ кода..."
flutter analyze

echo "Запуск тестов (если есть)..."
flutter test || echo "Тесты не найдены или произошли ошибки"

echo "Сборка релизного APK..."
flutter build apk --release

echo ""
echo "=== Сборка завершена ==="
echo "APK файл расположен по пути:"
echo "  $(pwd)/build/app/outputs/flutter-apk/app-release.apk"
echo ""
echo "Размер файла:"
ls -lh build/app/outputs/flutter-apk/app-release.apk

echo ""
echo "Для установки на устройство выполните:"
echo "  adb install build/app/outputs/flutter-apk/app-release.apk"
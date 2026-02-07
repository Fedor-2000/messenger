# Инструкция по установке Android SDK и сборке APK

## Установка Android SDK

### 1. Установка Java Development Kit (JDK)

Перед установкой Android SDK убедитесь, что у вас установлен JDK 8 или выше:

```bash
# Для Ubuntu/Debian
sudo apt update
sudo apt install openjdk-11-jdk

# Для CentOS/RHEL/Fedora
sudo dnf install java-11-openjdk-devel

# Проверка версии Java
java -version
javac -version
```

### 2. Установка Android SDK

#### Вариант 1: Установка через Android Studio (рекомендуется)

1. Скачайте Android Studio с официального сайта: https://developer.android.com/studio
2. Установите Android Studio, следуя инструкциям установщика
3. Запустите Android Studio и завершите первоначальную настройку
4. Установите Android SDK, SDK Platform-Tools и SDK Build-Tools через SDK Manager

#### Вариант 2: Установка Android SDK Command Line Tools

```bash
# Создайте директорию для Android SDK
mkdir -p ~/android-sdk

# Скачайте Command Line Tools (проверьте последнюю версию на сайте)
cd ~/android-sdk
wget https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip
unzip commandlinetools-linux-9477386_latest.zip

# Создайте структуру директорий
mkdir -p cmdline-tools/latest
mv ~/android-sdk/cmdline-tools/* ~/android-sdk/cmdline-tools/latest/

# Установите SDK
export ANDROID_HOME=~/android-sdk
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools

# Примите лицензии
sdkmanager --licenses
```

### 3. Установка Flutter

```bash
# Скачайте Flutter
cd ~
wget https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_3.13.0-stable.tar.xz
tar xf flutter_linux_3.13.0-stable.tar.xz

# Добавьте Flutter в PATH
export PATH="$PATH:`pwd`/flutter/bin"

# Проверьте установку
flutter doctor
```

### 4. Настройка переменных окружения

Добавьте следующие строки в ваш `~/.bashrc` или `~/.zshrc`:

```bash
export ANDROID_HOME=~/android-sdk
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools
export PATH="$PATH:~/flutter/bin"
```

Затем примените изменения:

```bash
source ~/.bashrc  # или source ~/.zshrc
```

## Сборка APK файла

### 1. Перейдите в директорию мобильного клиента

```bash
cd /path/to/messenger-project/mobile_client
```

### 2. Установите зависимости Flutter

```bash
flutter pub get
```

### 3. Проверьте конфигурацию

```bash
flutter doctor
```

Убедитесь, что все компоненты отмечены галочками.

### 4. Запустите проверку проекта

```bash
flutter analyze
```

### 5. Запустите тесты (если есть)

```bash
flutter test
```

### 6. Создайте релизный APK

```bash
flutter build apk --release
```

APK файл будет создан в директории:
```
build/app/outputs/flutter-apk/app-release.apk
```

### 7. Альтернативные варианты сборки

#### Сборка для конкретной архитектуры:
```bash
# Только для arm64-v8a
flutter build apk --release --target-platform android-arm64

# Для нескольких архитектур
flutter build apk --split-per-abi
```

#### Сборка с подписью (для публикации):
```bash
# Сгенерируйте ключ
keytool -genkey -v -keystore ~/upload-keystore.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload

# Добавьте информацию о ключе в android/key.properties
storeFile=~/upload-keystore.jks
storePassword=<пароль_от_кеystore>
keyPassword=<пароль_от_ключа>
keyAlias=upload

# Соберите подписанный APK
flutter build apk --release
```

## Установка APK на устройство

### 1. Включите режим разработчика и USB-отладку на устройстве

### 2. Подключите устройство по USB

### 3. Установите APK

```bash
adb install build/app/outputs/flutter-apk/app-release.apk
```

## Альтернатива: Использование Docker для сборки

Если вы не хотите устанавливать Android SDK локально, вы можете использовать Docker:

```dockerfile
# Dockerfile для сборки Android
FROM cirrusci/flutter:stable

RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    openjdk-11-jdk

# Установка Android SDK
ENV ANDROID_HOME=/android-sdk
ENV PATH=${PATH}:${ANDROID_HOME}/cmdline-tools/latest/bin:${ANDROID_HOME}/platform-tools

RUN mkdir -p ${ANDROID_HOME}/cmdline-tools/latest
WORKDIR /tmp
RUN wget https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip
RUN unzip commandlinetools-linux-9477386_latest.zip -d ${ANDROID_HOME}/cmdline-tools/latest/ && \
    mv ${ANDROID_HOME}/cmdline-tools/latest/cmdline-tools/* ${ANDROID_HOME}/cmdline-tools/latest/

# Применение лицензий
RUN yes | sdkmanager --licenses

WORKDIR /app
COPY . .

RUN flutter pub get
RUN flutter build apk --release

# APK будет находиться в /app/build/app/outputs/flutter-apk/
```

Для сборки в Docker:
```bash
docker build -t messenger-android-builder .
docker run --rm -v $(pwd)/output:/app/build/app/outputs/flutter-apk messenger-android-builder
```

## Завершение

После выполнения этих шагов у вас будет готовый к установке APK-файл мессенджера, который можно установить на любое Android-устройство.
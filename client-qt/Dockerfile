# Dockerfile.client-qt
FROM ubuntu:22.04

# Установка зависимостей для Qt6
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    qt6-base-dev \
    qt6-base-dev-tools \
    libqt6core6 \
    libqt6widgets6 \
    libqt6network6 \
    libqt6concurrent6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем исходный код клиента
COPY client-qt/ ./

# Создаем директорию сборки
RUN mkdir build && cd build && \
    cmake .. && \
    make -j$(nproc)

# Запускаем клиент
CMD ["./build/MessengerClient"]
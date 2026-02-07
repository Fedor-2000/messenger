cmake_minimum_required(VERSION 3.16)
project(MessengerClient VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Qt6 REQUIRED COMPONENTS Core Widgets Network Concurrent LinguistTools Svg)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

# UI файлы
set(UI_FILES
    ui/mainwindow.ui
    ui/mainwindow_modern.ui
)

# Ресурсы
qt_add_resources(QT_RESOURCES
    resources/resources.qrc
)

# Трансляции
set(TS_FILES
    translations/en_US.ts
)

qt_create_translation(QM_FILES ${CMAKE_SOURCE_DIR} ${TS_FILES})

# Исходные файлы
set(SOURCES
    src/main.cpp
    src/mainwindow.cpp
    src/messagelistmodel.cpp
    src/messagelistdelegate.cpp
    src/settings.cpp
    src/enhanced_ui_features.cpp
)

set(HEADERS
    src/mainwindow.h
    src/messagelistmodel.h
    src/messagelistdelegate.h
    src/settings.h
    src/enhanced_ui_features.h
)

add_executable(${PROJECT_NAME} ${SOURCES} ${HEADERS} ${UI_FILES} ${QT_RESOURCES} ${QM_FILES})

target_link_libraries(${PROJECT_NAME} Qt6::Core Qt6::Widgets Qt6::Network Qt6::Concurrent Qt6::Svg)

# Установка
install(TARGETS ${PROJECT_NAME} DESTINATION bin)
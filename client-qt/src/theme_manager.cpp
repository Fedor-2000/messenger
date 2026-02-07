# client-qt/src/theme_manager.cpp
#include "theme_manager.h"
#include <QFile>
#include <QDir>
#include <QStandardPaths>
#include <QApplication>
#include <QPalette>
#include <QStyleFactory>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QColor>
#include <QFont>
#include <QDebug>
#include <QSettings>

ThemeManager::ThemeManager(QObject *parent)
    : QObject(parent)
    , m_currentTheme("default")
    , m_themeDirectory("")
    , m_isInitialized(false)
{
    initializeThemeSystem();
}

void ThemeManager::initializeThemeSystem()
{
    // Устанавливаем директорию для тем
    m_themeDirectory = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation) + "/themes/";
    QDir().mkpath(m_themeDirectory);
    
    // Загружаем встроенные темы
    loadBuiltInThemes();
    
    // Загружаем пользовательские темы
    loadCustomThemes();
    
    // Загружаем сохраненную тему
    loadSavedTheme();
    
    m_isInitialized = true;
}

void ThemeManager::loadBuiltInThemes()
{
    // Создаем встроенные темы
    createBuiltInDarkTheme();
    createBuiltInLightTheme();
    createBuiltInBlueTheme();
    createBuiltInGreenTheme();
    createBuiltInPurpleTheme();
}

void ThemeManager::createBuiltInDarkTheme()
{
    Theme darkTheme;
    darkTheme.name = "Dark";
    darkTheme.displayName = "Темная тема";
    darkTheme.author = "System";
    darkTheme.version = "1.0";
    darkTheme.description = "Темная тема с контрастными цветами";
    
    // Цвета темной темы
    darkTheme.colors["window"] = "#1e1e1e";
    darkTheme.colors["windowText"] = "#ffffff";
    darkTheme.colors["base"] = "#252526";
    darkTheme.colors["alternateBase"] = "#2d2d2d";
    darkTheme.colors["text"] = "#ffffff";
    darkTheme.colors["button"] = "#3c3c3c";
    darkTheme.colors["buttonText"] = "#ffffff";
    darkTheme.colors["brightText"] = "#ffffff";
    darkTheme.colors["highlight"] = "#0078d4";
    darkTheme.colors["highlightedText"] = "#ffffff";
    darkTheme.colors["tooltipBase"] = "#2d2d2d";
    darkTheme.colors["tooltipText"] = "#ffffff";
    darkTheme.colors["link"] = "#4daafc";
    darkTheme.colors["linkVisited"] = "#a46ede";
    
    // Шрифты
    darkTheme.fonts["default"] = QFont("Segoe UI", 9);
    darkTheme.fonts["header"] = QFont("Segoe UI", 12, QFont::Bold);
    darkTheme.fonts["monospace"] = QFont("Consolas", 10);
    
    // Прочие параметры
    darkTheme.parameters["borderRadius"] = "4px";
    darkTheme.parameters["shadowIntensity"] = "0.3";
    darkTheme.parameters["opacity"] = "1.0";
    
    m_themes["dark"] = darkTheme;
}

void ThemeManager::createBuiltInLightTheme()
{
    Theme lightTheme;
    lightTheme.name = "Light";
    lightTheme.displayName = "Светлая тема";
    lightTheme.author = "System";
    lightTheme.version = "1.0";
    lightTheme.description = "Светлая тема с мягкими цветами";
    
    // Цвета светлой темы
    lightTheme.colors["window"] = "#ffffff";
    lightTheme.colors["windowText"] = "#000000";
    lightTheme.colors["base"] = "#f3f3f3";
    lightTheme.colors["alternateBase"] = "#fafafa";
    lightTheme.colors["text"] = "#000000";
    lightTheme.colors["button"] = "#e0e0e0";
    lightTheme.colors["buttonText"] = "#000000";
    lightTheme.colors["brightText"] = "#ffffff";
    lightTheme.colors["highlight"] = "#0078d4";
    lightTheme.colors["highlightedText"] = "#ffffff";
    lightTheme.colors["tooltipBase"] = "#ffffe1";
    lightTheme.colors["tooltipText"] = "#000000";
    lightTheme.colors["link"] = "#0066cc";
    lightTheme.colors["linkVisited"] = "#800080";
    
    // Шрифты
    lightTheme.fonts["default"] = QFont("Segoe UI", 9);
    lightTheme.fonts["header"] = QFont("Segoe UI", 12, QFont::Bold);
    lightTheme.fonts["monospace"] = QFont("Consolas", 10);
    
    // Прочие параметры
    lightTheme.parameters["borderRadius"] = "4px";
    lightTheme.parameters["shadowIntensity"] = "0.1";
    lightTheme.parameters["opacity"] = "1.0";
    
    m_themes["light"] = lightTheme;
}

void ThemeManager::createBuiltInBlueTheme()
{
    Theme blueTheme;
    blueTheme.name = "Blue";
    blueTheme.displayName = "Синяя тема";
    blueTheme.author = "System";
    blueTheme.version = "1.0";
    blueTheme.description = "Синяя тема с акцентами";
    
    // Цвета синей темы
    blueTheme.colors["window"] = "#e6f3ff";
    blueTheme.colors["windowText"] = "#003366";
    blueTheme.colors["base"] = "#ffffff";
    blueTheme.colors["alternateBase"] = "#f0f8ff";
    blueTheme.colors["text"] = "#003366";
    blueTheme.colors["button"] = "#4daafc";
    blueTheme.colors["buttonText"] = "#ffffff";
    blueTheme.colors["brightText"] = "#ffffff";
    blueTheme.colors["highlight"] = "#0078d4";
    blueTheme.colors["highlightedText"] = "#ffffff";
    blueTheme.colors["tooltipBase"] = "#ffffe1";
    blueTheme.colors["tooltipText"] = "#000000";
    blueTheme.colors["link"] = "#0066cc";
    blueTheme.colors["linkVisited"] = "#800080";
    
    // Шрифты
    blueTheme.fonts["default"] = QFont("Segoe UI", 9);
    blueTheme.fonts["header"] = QFont("Segoe UI", 12, QFont::Bold);
    blueTheme.fonts["monospace"] = QFont("Consolas", 10);
    
    // Прочие параметры
    blueTheme.parameters["borderRadius"] = "8px";
    blueTheme.parameters["shadowIntensity"] = "0.2";
    blueTheme.parameters["opacity"] = "1.0";
    
    m_themes["blue"] = blueTheme;
}

void ThemeManager::createBuiltInGreenTheme()
{
    Theme greenTheme;
    greenTheme.name = "Green";
    greenTheme.displayName = "Зеленая тема";
    greenTheme.author = "System";
    greenTheme.version = "1.0";
    greenTheme.description = "Зеленая тема с природными тонами";
    
    // Цвета зеленой темы
    greenTheme.colors["window"] = "#f0f7f0";
    greenTheme.colors["windowText"] = "#2e7d32";
    greenTheme.colors["base"] = "#ffffff";
    greenTheme.colors["alternateBase"] = "#f5fbf5";
    greenTheme.colors["text"] = "#2e7d32";
    greenTheme.colors["button"] = "#4caf50";
    greenTheme.colors["buttonText"] = "#ffffff";
    greenTheme.colors["brightText"] = "#ffffff";
    greenTheme.colors["highlight"] = "#4caf50";
    greenTheme.colors["highlightedText"] = "#ffffff";
    greenTheme.colors["tooltipBase"] = "#e8f5e9";
    greenTheme.colors["tooltipText"] = "#1b5e20";
    greenTheme.colors["link"] = "#388e3c";
    greenTheme.colors["linkVisited"] = "#1b5e20";
    
    // Шрифты
    greenTheme.fonts["default"] = QFont("Segoe UI", 9);
    greenTheme.fonts["header"] = QFont("Segoe UI", 12, QFont::Bold);
    greenTheme.fonts["monospace"] = QFont("Consolas", 10);
    
    // Прочие параметры
    greenTheme.parameters["borderRadius"] = "6px";
    greenTheme.parameters["shadowIntensity"] = "0.15";
    greenTheme.parameters["opacity"] = "1.0";
    
    m_themes["green"] = greenTheme;
}

void ThemeManager::createBuiltInPurpleTheme()
{
    Theme purpleTheme;
    purpleTheme.name = "Purple";
    purpleTheme.displayName = "Фиолетовая тема";
    purpleTheme.author = "System";
    purpleTheme.version = "1.0";
    purpleTheme.description = "Фиолетовая тема с таинственными тонами";
    
    // Цвета фиолетовой темы
    purpleTheme.colors["window"] = "#f3e5f5";
    purpleTheme.colors["windowText"] = "#7b1fa2";
    purpleTheme.colors["base"] = "#ffffff";
    purpleTheme.colors["alternateBase"] = "#fae8ff";
    purpleTheme.colors["text"] = "#7b1fa2";
    purpleTheme.colors["button"] = "#9c27b0";
    purpleTheme.colors["buttonText"] = "#ffffff";
    purpleTheme.colors["brightText"] = "#ffffff";
    purpleTheme.colors["highlight"] = "#9c27b0";
    purpleTheme.colors["highlightedText"] = "#ffffff";
    purpleTheme.colors["tooltipBase"] = "#f3e5f5";
    purpleTheme.colors["tooltipText"] = "#4a148c";
    purpleTheme.colors["link"] = "#7b1fa2";
    purpleTheme.colors["linkVisited"] = "#4a148c";
    
    // Шрифты
    purpleTheme.fonts["default"] = QFont("Segoe UI", 9);
    purpleTheme.fonts["header"] = QFont("Segoe UI", 12, QFont::Bold);
    purpleTheme.fonts["monospace"] = QFont("Consolas", 10);
    
    // Прочие параметры
    purpleTheme.parameters["borderRadius"] = "10px";
    purpleTheme.parameters["shadowIntensity"] = "0.25";
    purpleTheme.parameters["opacity"] = "1.0";
    
    m_themes["purple"] = purpleTheme;
}

void ThemeManager::loadCustomThemes()
{
    QDir themesDir(m_themeDirectory);
    QStringList themeFiles = themesDir.entryList(QStringList() << "*.json", QDir::Files);
    
    for (const QString &fileName : themeFiles) {
        QString filePath = m_themeDirectory + fileName;
        loadCustomThemeFromFile(filePath);
    }
}

bool ThemeManager::loadCustomThemeFromFile(const QString &filePath)
{
    QFile file(filePath);
    if (!file.open(QIODevice::ReadOnly)) {
        qWarning() << "Could not open theme file:" << filePath;
        return false;
    }
    
    QByteArray data = file.readAll();
    QJsonParseError error;
    QJsonDocument doc = QJsonDocument::fromJson(data, &error);
    
    if (error.error != QJsonParseError::NoError) {
        qWarning() << "Error parsing theme file:" << error.errorString();
        return false;
    }
    
    if (!doc.isObject()) {
        qWarning() << "Theme file is not a valid JSON object";
        return false;
    }
    
    QJsonObject obj = doc.object();
    
    // Проверяем обязательные поля
    if (!obj.contains("name") || !obj.contains("colors")) {
        qWarning() << "Theme file missing required fields";
        return false;
    }
    
    Theme customTheme;
    customTheme.name = obj["name"].toString();
    customTheme.displayName = obj["displayName"].toString(customTheme.name);
    customTheme.author = obj["author"].toString("Unknown");
    customTheme.version = obj["version"].toString("1.0");
    customTheme.description = obj["description"].toString("");
    
    // Загружаем цвета
    QJsonObject colorsObj = obj["colors"].toObject();
    for (auto it = colorsObj.begin(); it != colorsObj.end(); ++it) {
        customTheme.colors[it.key()] = it.value().toString();
    }
    
    // Загружаем шрифты (если есть)
    QJsonObject fontsObj = obj["fonts"].toObject();
    for (auto it = fontsObj.begin(); it != fontsObj.end(); ++it) {
        QJsonObject fontData = it.value().toObject();
        QFont font;
        font.setFamily(fontData["family"].toString("Segoe UI"));
        font.setPointSize(fontData["pointSize"].toInt(9));
        font.setBold(fontData["bold"].toBool(false));
        font.setItalic(fontData["italic"].toBool(false));
        customTheme.fonts[it.key()] = font;
    }
    
    // Загружаем параметры (если есть)
    QJsonObject paramsObj = obj["parameters"].toObject();
    for (auto it = paramsObj.begin(); it != paramsObj.end(); ++it) {
        customTheme.parameters[it.key()] = it.value().toString();
    }
    
    // Добавляем тему в список
    m_themes[customTheme.name.toLower()] = customTheme;
    
    return true;
}

void ThemeManager::loadSavedTheme()
{
    QSettings settings;
    QString savedTheme = settings.value("appearance/theme", "dark").toString();
    
    if (m_themes.contains(savedTheme.toLower())) {
        setCurrentTheme(savedTheme);
    } else {
        setCurrentTheme("dark"); // тема по умолчанию
    }
}

bool ThemeManager::setCurrentTheme(const QString &themeName)
{
    QString lowerThemeName = themeName.toLower();
    
    if (!m_themes.contains(lowerThemeName)) {
        qWarning() << "Theme not found:" << themeName;
        return false;
    }
    
    m_currentTheme = lowerThemeName;
    
    // Применяем тему
    applyCurrentTheme();
    
    // Сохраняем выбор темы
    QSettings settings;
    settings.setValue("appearance/theme", themeName);
    
    emit themeChanged(themeName);
    
    return true;
}

void ThemeManager::applyCurrentTheme()
{
    if (!m_isInitialized) {
        return;
    }
    
    const Theme &theme = m_themes[m_currentTheme];
    
    // Создаем QPalette на основе цветов темы
    QPalette palette;
    
    // Устанавливаем цвета
    if (theme.colors.contains("window")) {
        palette.setColor(QPalette::Window, QColor(theme.colors["window"]));
    }
    if (theme.colors.contains("windowText")) {
        palette.setColor(QPalette::WindowText, QColor(theme.colors["windowText"]));
    }
    if (theme.colors.contains("base")) {
        palette.setColor(QPalette::Base, QColor(theme.colors["base"]));
    }
    if (theme.colors.contains("alternateBase")) {
        palette.setColor(QPalette::AlternateBase, QColor(theme.colors["alternateBase"]));
    }
    if (theme.colors.contains("text")) {
        palette.setColor(QPalette::Text, QColor(theme.colors["text"]));
    }
    if (theme.colors.contains("button")) {
        palette.setColor(QPalette::Button, QColor(theme.colors["button"]));
    }
    if (theme.colors.contains("buttonText")) {
        palette.setColor(QPalette::ButtonText, QColor(theme.colors["buttonText"]));
    }
    if (theme.colors.contains("brightText")) {
        palette.setColor(QPalette::BrightText, QColor(theme.colors["brightText"]));
    }
    if (theme.colors.contains("highlight")) {
        palette.setColor(QPalette::Highlight, QColor(theme.colors["highlight"]));
    }
    if (theme.colors.contains("highlightedText")) {
        palette.setColor(QPalette::HighlightedText, QColor(theme.colors["highlightedText"]));
    }
    if (theme.colors.contains("tooltipBase")) {
        palette.setColor(QPalette::ToolTipBase, QColor(theme.colors["tooltipBase"]));
    }
    if (theme.colors.contains("tooltipText")) {
        palette.setColor(QPalette::ToolTipText, QColor(theme.colors["tooltipText"]));
    }
    if (theme.colors.contains("link")) {
        palette.setColor(QPalette::Link, QColor(theme.colors["link"]));
    }
    if (theme.colors.contains("linkVisited")) {
        palette.setColor(QPalette::LinkVisited, QColor(theme.colors["linkVisited"]));
    }
    
    // Применяем палитру к приложению
    qApp->setPalette(palette);
    
    // Устанавливаем шрифт по умолчанию
    if (theme.fonts.contains("default")) {
        qApp->setFont(theme.fonts["default"]);
    }
    
    // Генерируем CSS стили на основе темы
    QString cssStyles = generateCSSFromTheme(theme);
    
    // Применяем стили к приложению
    qApp->setStyleSheet(cssStyles);
}

QString ThemeManager::generateCSSFromTheme(const Theme &theme)
{
    QString css = "";
    
    // Основные стили
    css += QString("QMainWindow { background-color: %1; color: %2; }\n")
           .arg(theme.colors.value("window", "#ffffff"))
           .arg(theme.colors.value("windowText", "#000000"));
    
    css += QString("QWidget { background-color: %1; color: %2; }\n")
           .arg(theme.colors.value("window", "#ffffff"))
           .arg(theme.colors.value("windowText", "#000000"));
    
    // Стили для чата
    css += QString("QListView { background-color: %1; color: %2; border: 1px solid %3; border-radius: %4; }\n")
           .arg(theme.colors.value("base", "#f0f0f0"))
           .arg(theme.colors.value("text", "#000000"))
           .arg(theme.colors.value("button", "#d0d0d0"))
           .arg(theme.parameters.value("borderRadius", "4px"));
    
    // Стили для поля ввода
    css += QString("QLineEdit { background-color: %1; color: %2; border: 1px solid %3; border-radius: %4; padding: 5px; }\n")
           .arg(theme.colors.value("base", "#ffffff"))
           .arg(theme.colors.value("text", "#000000"))
           .arg(theme.colors.value("button", "#c0c0c0"))
           .arg(theme.parameters.value("borderRadius", "4px"));
    
    // Стили для кнопок
    css += QString("QPushButton { background-color: %1; color: %2; border: none; border-radius: %3; padding: 8px 16px; font-weight: 500; }\n")
           .arg(theme.colors.value("button", "#0078d4"))
           .arg(theme.colors.value("buttonText", "#ffffff"))
           .arg(theme.parameters.value("borderRadius", "4px"));
    
    css += QString("QPushButton:hover { background-color: %1; }\n")
           .arg(lighterColor(theme.colors.value("button", "#0078d4"), 1.2));
    
    css += QString("QPushButton:pressed { background-color: %1; }\n")
           .arg(darkerColor(theme.colors.value("button", "#0078d4"), 1.2));
    
    css += QString("QPushButton:disabled { background-color: %1; color: %2; }\n")
           .arg(theme.colors.value("alternateBase", "#e0e0e0"))
           .arg(theme.colors.value("text", "#808080"));
    
    // Стили для вкладок
    css += QString("QTabWidget::pane { border: none; background-color: %1; border-radius: %2; }\n")
           .arg(theme.colors.value("window", "#ffffff"))
           .arg(theme.parameters.value("borderRadius", "4px"));
    
    css += QString("QTabBar::tab { background-color: %1; color: %2; padding: 10px 20px; margin-right: 2px; border-top-left-radius: %3; border-top-right-radius: %3; font-weight: 500; }\n")
           .arg(theme.colors.value("button", "#e0e0e0"))
           .arg(theme.colors.value("buttonText", "#000000"))
           .arg(theme.parameters.value("borderRadius", "4px"));
    
    css += QString("QTabBar::tab:selected { background-color: %1; color: %2; border-bottom: 3px solid %3; }\n")
           .arg(theme.colors.value("window", "#ffffff"))
           .arg(theme.colors.value("windowText", "#000000"))
           .arg(theme.colors.value("highlight", "#0078d4"));
    
    css += QString("QTabBar::tab:hover:!selected { background-color: %1; }\n")
           .arg(lighterColor(theme.colors.value("button", "#e0e0e0"), 1.1));
    
    // Стили для полосы прокрутки
    css += QString("QScrollBar:vertical { background: %1; width: 12px; border-radius: 6px; }\n")
           .arg(theme.colors.value("alternateBase", "#f0f0f0"));
    
    css += QString("QScrollBar::handle:vertical { background: %1; border-radius: 6px; min-height: 20px; }\n")
           .arg(darkerColor(theme.colors.value("button", "#c0c0c0"), 1.1));
    
    css += QString("QScrollBar::handle:vertical:hover { background: %1; }\n")
           .arg(darkerColor(theme.colors.value("button", "#c0c0c0"), 1.3));
    
    // Стили для статус бара
    css += QString("QStatusBar { background-color: %1; color: %2; border-top: 1px solid %3; }\n")
           .arg(darkerColor(theme.colors.value("window", "#ffffff"), 1.1))
           .arg(theme.colors.value("text", "#000000"))
           .arg(theme.colors.value("button", "#d0d0d0"));
    
    // Стили для меню
    css += QString("QMenuBar { background-color: %1; color: %2; border-bottom: 1px solid %3; }\n")
           .arg(darkerColor(theme.colors.value("window", "#ffffff"), 1.05))
           .arg(theme.colors.value("windowText", "#000000"))
           .arg(theme.colors.value("button", "#d0d0d0"));
    
    css += QString("QMenuBar::item { background: transparent; padding: 4px 8px; }\n");
    css += QString("QMenuBar::item:selected { background: %1; }\n")
           .arg(lighterColor(theme.colors.value("button", "#e0e0e0"), 1.2));
    css += QString("QMenuBar::item:pressed { background: %1; color: %2; }\n")
           .arg(theme.colors.value("highlight", "#0078d4"))
           .arg(theme.colors.value("highlightedText", "#ffffff"));
    
    // Стили для чекбоксов
    css += QString("QCheckBox { spacing: 8px; color: %1; }\n")
           .arg(theme.colors.value("windowText", "#000000"));
    
    css += QString("QCheckBox::indicator { width: 18px; height: 18px; }\n");
    css += QString("QCheckBox::indicator:unchecked { border: 2px solid %1; background-color: %2; border-radius: 3px; }\n")
           .arg(theme.colors.value("button", "#c0c0c0"))
           .arg(theme.colors.value("base", "#ffffff"));
    css += QString("QCheckBox::indicator:checked { border: 2px solid %1; background-color: %1; border-radius: 3px; }\n")
           .arg(theme.colors.value("highlight", "#0078d4"));
    
    // Стили для радиокнопок
    css += QString("QRadioButton { spacing: 8px; color: %1; }\n")
           .arg(theme.colors.value("windowText", "#000000"));
    
    css += QString("QRadioButton::indicator { width: 18px; height: 18px; }\n");
    css += QString("QRadioButton::indicator:unchecked { border: 2px solid %1; background-color: %2; border-radius: 9px; }\n")
           .arg(theme.colors.value("button", "#c0c0c0"))
           .arg(theme.colors.value("base", "#ffffff"));
    css += QString("QRadioButton::indicator:checked { border: 2px solid %1; background-color: %1; border-radius: 9px; }\n")
           .arg(theme.colors.value("highlight", "#0078d4"));
    
    // Стили для спинбокса
    css += QString("QSpinBox { background-color: %1; color: %2; border: 1px solid %3; border-radius: 4px; padding: 4px; }\n")
           .arg(theme.colors.value("base", "#ffffff"))
           .arg(theme.colors.value("text", "#000000"))
           .arg(theme.colors.value("button", "#c0c0c0"));
    
    // Стили для группбокса
    css += QString("QGroupBox { border: 1px solid %1; border-radius: %2; margin-top: 1ex; font-weight: bold; color: %3; }\n")
           .arg(theme.colors.value("button", "#c0c0c0"))
           .arg(theme.parameters.value("borderRadius", "4px"))
           .arg(theme.colors.value("windowText", "#000000"));
    
    css += QString("QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top center; padding: 0 3px; }\n");
    
    // Стили для прогрессбара
    css += QString("QProgressBar { border: 1px solid %1; border-radius: 4px; text-align: center; color: %2; background-color: %3; }\n")
           .arg(theme.colors.value("button", "#c0c0c0"))
           .arg(theme.colors.value("windowText", "#000000"))
           .arg(theme.colors.value("alternateBase", "#f0f0f0"));
    
    css += QString("QProgressBar::chunk { background-color: %1; border-radius: 3px; }\n")
           .arg(theme.colors.value("highlight", "#0078d4"));
    
    // Стили для тултипа
    css += QString("QToolTip { background-color: %1; color: %2; border: 1px solid %3; border-radius: 4px; padding: 5px; opacity: 230; }\n")
           .arg(theme.colors.value("tooltipBase", "#ffffe1"))
           .arg(theme.colors.value("tooltipText", "#000000"))
           .arg(theme.colors.value("button", "#c0c0c0"));
    
    // Стили для заголовка
    css += QString("QHeaderView::section { background-color: %1; color: %2; padding: 4px; border: 1px solid %3; font-weight: bold; }\n")
           .arg(theme.colors.value("button", "#e0e0e0"))
           .arg(theme.colors.value("buttonText", "#000000"))
           .arg(theme.colors.value("window", "#ffffff"));
    
    return css;
}

QString ThemeManager::lighterColor(const QString &color, qreal factor)
{
    QColor c(color);
    c = c.lighter(factor * 100);
    return c.name();
}

QString ThemeManager::darkerColor(const QString &color, qreal factor)
{
    QColor c(color);
    c = c.darker(factor * 100);
    return c.name();
}

QStringList ThemeManager::getAvailableThemes() const
{
    QStringList themes;
    for (const auto &themePair : m_themes.asKeyValueRange()) {
        themes << themePair.first;
    }
    return themes;
}

QString ThemeManager::getCurrentTheme() const
{
    return m_currentTheme;
}

Theme ThemeManager::getTheme(const QString &themeName) const
{
    QString lowerName = themeName.toLower();
    if (m_themes.contains(lowerName)) {
        return m_themes[lowerName];
    }
    return Theme(); // возвращаем пустую тему, если не найдена
}

bool ThemeManager::createCustomTheme(const QString &name, const QString &displayName, 
                                   const QString &author, const QString &description,
                                   const QMap<QString, QString> &colors,
                                   const QMap<QString, QFont> &fonts,
                                   const QMap<QString, QString> &parameters)
{
    Theme newTheme;
    newTheme.name = name;
    newTheme.displayName = displayName;
    newTheme.author = author;
    newTheme.version = "1.0";
    newTheme.description = description;
    newTheme.colors = colors;
    newTheme.fonts = fonts;
    newTheme.parameters = parameters;
    
    m_themes[name.toLower()] = newTheme;
    
    // Сохраняем тему в файл
    return saveThemeToFile(newTheme, m_themeDirectory + name + ".json");
}

bool ThemeManager::saveThemeToFile(const Theme &theme, const QString &filePath)
{
    QJsonObject obj;
    obj["name"] = theme.name;
    obj["displayName"] = theme.displayName;
    obj["author"] = theme.author;
    obj["version"] = theme.version;
    obj["description"] = theme.description;
    
    // Сохраняем цвета
    QJsonObject colorsObj;
    for (auto it = theme.colors.constBegin(); it != theme.colors.constEnd(); ++it) {
        colorsObj[it.key()] = it.value();
    }
    obj["colors"] = colorsObj;
    
    // Сохраняем шрифты
    QJsonObject fontsObj;
    for (auto it = theme.fonts.constBegin(); it != theme.fonts.constEnd(); ++it) {
        QJsonObject fontData;
        fontData["family"] = it.value().family();
        fontData["pointSize"] = it.value().pointSize();
        fontData["bold"] = it.value().bold();
        fontData["italic"] = it.value().italic();
        fontsObj[it.key()] = fontData;
    }
    obj["fonts"] = fontsObj;
    
    // Сохраняем параметры
    QJsonObject paramsObj;
    for (auto it = theme.parameters.constBegin(); it != theme.parameters.constEnd(); ++it) {
        paramsObj[it.key()] = it.value();
    }
    obj["parameters"] = paramsObj;
    
    QJsonDocument doc(obj);
    
    QFile file(filePath);
    if (!file.open(QIODevice::WriteOnly)) {
        qWarning() << "Could not save theme to file:" << filePath;
        return false;
    }
    
    file.write(doc.toJson());
    
    return true;
}

bool ThemeManager::deleteCustomTheme(const QString &themeName)
{
    QString lowerName = themeName.toLower();
    
    if (!m_themes.contains(lowerName)) {
        return false;
    }
    
    // Не позволяем удалять встроенные темы
    if (lowerName == "dark" || lowerName == "light" || lowerName == "blue" || 
        lowerName == "green" || lowerName == "purple") {
        return false;
    }
    
    // Удаляем файл темы
    QString filePath = m_themeDirectory + themeName + ".json";
    QFile::remove(filePath);
    
    // Удаляем из памяти
    m_themes.remove(lowerName);
    
    return true;
}

void ThemeManager::resetToDefault()
{
    // Сбрасываем к встроенным темам
    m_themes.clear();
    loadBuiltInThemes();
    
    // Возвращаемся к темной теме по умолчанию
    setCurrentTheme("dark");
    
    // Удаляем все пользовательские темы из директории
    QDir themesDir(m_themeDirectory);
    QStringList themeFiles = themesDir.entryList(QStringList() << "*.json", QDir::Files);
    
    for (const QString &fileName : themeFiles) {
        themesDir.remove(fileName);
    }
}
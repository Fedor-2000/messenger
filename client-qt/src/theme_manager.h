// client-qt/src/theme_manager.h
#ifndef THEME_MANAGER_H
#define THEME_MANAGER_H

#include <QObject>
#include <QMap>
#include <QFont>
#include <QColor>
#include <QDateTime>
#include <QMetaType>

struct Theme {
    QString name;
    QString displayName;
    QString author;
    QString version;
    QString description;
    QMap<QString, QString> colors;
    QMap<QString, QFont> fonts;
    QMap<QString, QString> parameters;  // Дополнительные параметры (радиусы, прозрачность и т.д.)
    QDateTime created_at;
    QDateTime updated_at;
    
    Theme() : created_at(QDateTime::currentDateTime()), updated_at(QDateTime::currentDateTime()) {}
};

class ThemeManager : public QObject
{
    Q_OBJECT

public:
    explicit ThemeManager(QObject *parent = nullptr);

    // Управление темами
    bool setCurrentTheme(const QString &themeName);
    QString getCurrentTheme() const;
    QStringList getAvailableThemes() const;
    Theme getTheme(const QString &themeName) const;

    // Создание и удаление тем
    bool createCustomTheme(const QString &name, const QString &displayName,
                          const QString &author, const QString &description,
                          const QMap<QString, QString> &colors,
                          const QMap<QString, QFont> &fonts,
                          const QMap<QString, QString> &parameters);
    bool deleteCustomTheme(const QString &themeName);
    void resetToDefault();

    // Управление системой тем
    void initializeThemeSystem();

signals:
    void themeChanged(const QString &themeName);

private slots:
    void applyCurrentTheme();

private:
    // Загрузка тем
    void loadBuiltInThemes();
    void loadCustomThemes();
    void loadSavedTheme();

    // Создание встроенных тем
    void createBuiltInDarkTheme();
    void createBuiltInLightTheme();
    void createBuiltInBlueTheme();
    void createBuiltInGreenTheme();
    void createBuiltInPurpleTheme();

    // Работа с файлами тем
    bool loadCustomThemeFromFile(const QString &filePath);
    bool saveThemeToFile(const Theme &theme, const QString &filePath);

    // Применение темы
    QString generateCSSFromTheme(const Theme &theme);

    // Вспомогательные функции
    QString lighterColor(const QString &color, qreal factor = 1.1);
    QString darkerColor(const QString &color, qreal factor = 1.1);

    // Данные
    QString m_currentTheme;
    QMap<QString, Theme> m_themes;
    QString m_themeDirectory;
    bool m_isInitialized;
};

Q_DECLARE_METATYPE(Theme)

#endif // THEME_MANAGER_H
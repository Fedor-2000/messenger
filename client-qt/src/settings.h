#ifndef SETTINGS_H
#define SETTINGS_H

#include <QObject>
#include <QSettings>
#include <QScopedPointer>

class Settings : public QObject
{
    Q_OBJECT

    Q_PROPERTY(QString username READ username WRITE setUsername NOTIFY usernameChanged)
    Q_PROPERTY(QString serverHost READ serverHost WRITE setServerHost NOTIFY serverHostChanged)
    Q_PROPERTY(int serverPort READ serverPort WRITE setServerPort NOTIFY serverPortChanged)
    Q_PROPERTY(bool useWebSocket READ useWebSocket WRITE setUseWebSocket NOTIFY useWebSocketChanged)
    Q_PROPERTY(bool useSsl READ useSsl WRITE setUseSsl NOTIFY useSslChanged)
    Q_PROPERTY(bool notificationsEnabled READ notificationsEnabled WRITE setNotificationsEnabled NOTIFY notificationsEnabledChanged)
    Q_PROPERTY(bool soundEnabled READ soundEnabled WRITE setSoundEnabled NOTIFY soundEnabledChanged)
    Q_PROPERTY(QString theme READ theme WRITE setTheme NOTIFY themeChanged)
    Q_PROPERTY(bool autoReconnect READ autoReconnect WRITE setAutoReconnect NOTIFY autoReconnectChanged)

public:
    explicit Settings(QObject *parent = nullptr);
    
    // Геттеры
    QString username() const;
    QString serverHost() const;
    int serverPort() const;
    bool useWebSocket() const;
    bool useSsl() const;
    bool notificationsEnabled() const;
    bool soundEnabled() const;
    QString theme() const;
    bool autoReconnect() const;
    
    // Сеттеры
    void setUsername(const QString &username);
    void setServerHost(const QString &host);
    void setServerPort(int port);
    void setUseWebSocket(bool use);
    void setUseSsl(bool use);
    void setNotificationsEnabled(bool enabled);
    void setSoundEnabled(bool enabled);
    void setTheme(const QString &theme);
    void setAutoReconnect(bool enabled);

signals:
    void usernameChanged(const QString &username);
    void serverHostChanged(const QString &host);
    void serverPortChanged(int port);
    void useWebSocketChanged(bool use);
    void useSslChanged(bool use);
    void notificationsEnabledChanged(bool enabled);
    void soundEnabledChanged(bool enabled);
    void themeChanged(const QString &theme);
    void autoReconnectChanged(bool enabled);
    void settingsChanged(const QString &key, const QVariant &value);

private:
    QScopedPointer<QSettings> m_settings;
    
    // Кэшированные значения для оптимизации
    mutable QString m_cachedUsername;
    mutable QString m_cachedServerHost;
    mutable int m_cachedServerPort;
    mutable bool m_cachedUseWebSocket;
    mutable bool m_cachedUseSsl;
    mutable bool m_cachedNotificationsEnabled;
    mutable bool m_cachedSoundEnabled;
    mutable QString m_cachedTheme;
    mutable bool m_cachedAutoReconnect;
    mutable bool m_cacheValid;
    
    void invalidateCache();
};

#endif // SETTINGS_H
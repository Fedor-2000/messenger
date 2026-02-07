#include "settings.h"
#include <QStandardPaths>
#include <QDir>

Settings::Settings(QObject *parent)
    : QObject(parent)
    , m_settings(new QSettings(
        QStandardPaths::writableLocation(QStandardPaths::ConfigLocation) + 
        QDir::separator() + "messenger-client.ini", 
        QSettings::IniFormat, 
        this))
    , m_cacheValid(false)
{
}

void Settings::invalidateCache()
{
    m_cacheValid = false;
}

QString Settings::username() const
{
    if (!m_cacheValid) {
        m_cachedUsername = m_settings->value("user/username", "").toString();
        m_cacheValid = true;
    }
    return m_cachedUsername;
}

void Settings::setUsername(const QString &username)
{
    if (this->username() != username) {
        m_settings->setValue("user/username", username);
        m_cachedUsername = username;
        emit usernameChanged(username);
        emit settingsChanged("user/username", username);
    }
}

QString Settings::serverHost() const
{
    if (!m_cacheValid) {
        m_cachedServerHost = m_settings->value("network/serverHost", "localhost").toString();
        m_cacheValid = true;
    }
    return m_cachedServerHost;
}

void Settings::setServerHost(const QString &host)
{
    if (serverHost() != host) {
        m_settings->setValue("network/serverHost", host);
        m_cachedServerHost = host;
        m_cacheValid = false; // Сброс кэша
        emit serverHostChanged(host);
        emit settingsChanged("network/serverHost", host);
    }
}

int Settings::serverPort() const
{
    if (!m_cacheValid) {
        m_cachedServerPort = m_settings->value("network/serverPort", 8080).toInt();
        m_cacheValid = true;
    }
    return m_cachedServerPort;
}

void Settings::setServerPort(int port)
{
    if (serverPort() != port) {
        m_settings->setValue("network/serverPort", port);
        m_cachedServerPort = port;
        m_cacheValid = false;
        emit serverPortChanged(port);
        emit settingsChanged("network/serverPort", port);
    }
}

bool Settings::useWebSocket() const
{
    if (!m_cacheValid) {
        m_cachedUseWebSocket = m_settings->value("network/useWebSocket", false).toBool();
        m_cacheValid = true;
    }
    return m_cachedUseWebSocket;
}

void Settings::setUseWebSocket(bool use)
{
    if (useWebSocket() != use) {
        m_settings->setValue("network/useWebSocket", use);
        m_cachedUseWebSocket = use;
        m_cacheValid = false;
        emit useWebSocketChanged(use);
        emit settingsChanged("network/useWebSocket", use);
    }
}

bool Settings::useSsl() const
{
    if (!m_cacheValid) {
        m_cachedUseSsl = m_settings->value("network/useSsl", false).toBool();
        m_cacheValid = true;
    }
    return m_cachedUseSsl;
}

void Settings::setUseSsl(bool use)
{
    if (useSsl() != use) {
        m_settings->setValue("network/useSsl", use);
        m_cachedUseSsl = use;
        m_cacheValid = false;
        emit useSslChanged(use);
        emit settingsChanged("network/useSsl", use);
    }
}

bool Settings::notificationsEnabled() const
{
    if (!m_cacheValid) {
        m_cachedNotificationsEnabled = m_settings->value("notifications/enabled", true).toBool();
        m_cacheValid = true;
    }
    return m_cachedNotificationsEnabled;
}

void Settings::setNotificationsEnabled(bool enabled)
{
    if (notificationsEnabled() != enabled) {
        m_settings->setValue("notifications/enabled", enabled);
        m_cachedNotificationsEnabled = enabled;
        m_cacheValid = false;
        emit notificationsEnabledChanged(enabled);
        emit settingsChanged("notifications/enabled", enabled);
    }
}

bool Settings::soundEnabled() const
{
    if (!m_cacheValid) {
        m_cachedSoundEnabled = m_settings->value("notifications/sound", true).toBool();
        m_cacheValid = true;
    }
    return m_cachedSoundEnabled;
}

void Settings::setSoundEnabled(bool enabled)
{
    if (soundEnabled() != enabled) {
        m_settings->setValue("notifications/sound", enabled);
        m_cachedSoundEnabled = enabled;
        m_cacheValid = false;
        emit soundEnabledChanged(enabled);
        emit settingsChanged("notifications/sound", enabled);
    }
}

QString Settings::theme() const
{
    if (!m_cacheValid) {
        m_cachedTheme = m_settings->value("appearance/theme", "default").toString();
        m_cacheValid = true;
    }
    return m_cachedTheme;
}

void Settings::setTheme(const QString &theme)
{
    if (this->theme() != theme) {
        m_settings->setValue("appearance/theme", theme);
        m_cachedTheme = theme;
        m_cacheValid = false;
        emit themeChanged(theme);
        emit settingsChanged("appearance/theme", theme);
    }
}

bool Settings::autoReconnect() const
{
    if (!m_cacheValid) {
        m_cachedAutoReconnect = m_settings->value("connection/autoReconnect", true).toBool();
        m_cacheValid = true;
    }
    return m_cachedAutoReconnect;
}

void Settings::setAutoReconnect(bool enabled)
{
    if (autoReconnect() != enabled) {
        m_settings->setValue("connection/autoReconnect", enabled);
        m_cachedAutoReconnect = enabled;
        m_cacheValid = false;
        emit autoReconnectChanged(enabled);
        emit settingsChanged("connection/autoReconnect", enabled);
    }
}
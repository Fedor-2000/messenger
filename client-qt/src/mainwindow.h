#ifndef MAINWINDOW_H
#define MAINWINDOW_H

#include <QMainWindow>
#include <QTcpSocket>
#include <QWebSocket>
#include <QStandardItemModel>
#include <QStyledItemDelegate>
#include <QTimer>
#include <QSettings>
#include <QSystemTrayIcon>
#include <QMenu>
#include <QAction>
#include <QCloseEvent>
#include <QMessageBox>
#include <QProgressBar>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QTextEdit>
#include <QListView>
#include <QSplitter>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QFormLayout>
#include <QGroupBox>
#include <QTabWidget>
#include <QCheckBox>
#include <QRadioButton>
#include <QSpinBox>
#include <QComboBox>
#include <QDateTime>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QSslConfiguration>
#include <QSslSocket>

#include "messagelistmodel.h"
#include "settings.h"

QT_BEGIN_NAMESPACE
namespace Ui { class MainWindow; }
QT_END_NAMESPACE

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    MainWindow(QWidget *parent = nullptr);
    ~MainWindow();

protected:
    void closeEvent(QCloseEvent *event) override;

private slots:
    void connectToServer();
    void disconnectFromServer();
    void sendMessage();
    void onSocketConnected();
    void onSocketDisconnected();
    void onSocketError(QAbstractSocket::SocketError error);
    void onSocketReadyRead();
    void onWebSocketConnected();
    void onWebSocketDisconnected();
    void onWebSocketError(QAbstractSocket::SocketError error);
    void onWebSocketTextMessageReceived(const QString &message);
    void toggleConnection();
    void showTrayMenu();
    void trayActivated(QSystemTrayIcon::ActivationReason reason);
    void showSettingsDialog();
    void applySettings();
    void updateStatusBar();
    void onSendMessageButtonClicked();
    void onInputReturnPressed();
    void onUsernameChanged(const QString &username);
    void onServerAddressChanged(const QString &address);
    void onPortChanged(int port);
    void onUseSslChanged(bool useSsl);
    void toggleEmojiPanel();
    void toggleStickerPanel();

private:
    void setupUI();
    void setupConnections();
    void setupTrayIcon();
    void setupStatusBar();
    void setupEmojiPanel();
    void setupStickerPanel();
    void loadSettings();
    void saveSettings();
    void updateConnectionState();
    void addMessageToChat(const QString &user, const QString &text, const QDateTime &timestamp, bool isOwn = false);
    void showError(const QString &error);
    void showNotification(const QString &title, const QString &message);
    void sendAuthRequest();
    void sendHeartbeat();
    void applyTheme(const QString &themeName);
    void insertEmoji(const QString &emoji);
    void insertSticker(const QString &sticker);
    void openAttachmentDialog();

    Ui::MainWindow *ui;
    QTcpSocket *tcpSocket;
    QWebSocket *webSocket;
    MessageListModel *chatModel;
    Settings *appSettings;

    QSystemTrayIcon *trayIcon;
    QMenu *trayMenu;
    QAction *connectAction;
    QAction *disconnectAction;
    QAction *quitAction;
    QAction *settingsAction;

    QLabel *statusLabel;
    QLabel *connectionStatusLabel;
    QProgressBar *progressBar;

    QTimer *heartbeatTimer;
    QTimer *reconnectTimer;

    // Дополнительные компоненты
    QWidget *emojiPanel;
    QWidget *stickerPanel;

    QString currentUsername;
    QString currentServer;
    int currentPort;
    bool useWebSocket;
    bool isConnected;
    int reconnectAttempts;

    // Настройки
    bool notificationsEnabled;
    bool soundEnabled;
    QString theme;
};

#endif // MAINWINDOW_H
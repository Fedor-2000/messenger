#include "mainwindow.h"
#include "./ui_mainwindow.h"
#include <QMessageBox>
#include <QInputDialog>
#include <QFileDialog>
#include <QStandardPaths>
#include <QDesktopServices>
#include <QUrl>
#include <QApplication>
#include <QStyle>
#include <QTimer>
#include <QDateTime>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QSslConfiguration>
#include <QSslSocket>

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
    , ui(new Ui::MainWindow)
    , tcpSocket(new QTcpSocket(this))
    , webSocket(new QWebSocket())
    , chatModel(new MessageListModel(this))
    , appSettings(new Settings(this))
    , trayIcon(nullptr)
    , trayMenu(nullptr)
    , connectAction(nullptr)
    , disconnectAction(nullptr)
    , quitAction(nullptr)
    , settingsAction(nullptr)
    , statusLabel(nullptr)
    , connectionStatusLabel(nullptr)
    , progressBar(nullptr)
    , heartbeatTimer(new QTimer(this))
    , reconnectTimer(new QTimer(this))
    , emojiPanel(nullptr)
    , stickerPanel(nullptr)
    , currentUsername("")
    , currentServer("localhost")
    , currentPort(8080)
    , useWebSocket(false)
    , isConnected(false)
    , reconnectAttempts(0)
    , notificationsEnabled(true)
    , soundEnabled(true)
    , theme("dark")
{
    ui->setupUi(this);

    setupUI();
    setupConnections();
    setupTrayIcon();
    setupStatusBar();
    setupEmojiPanel();
    setupStickerPanel();
    loadSettings();

    // Инициализация таймеров
    heartbeatTimer->setInterval(30000); // 30 секунд
    connect(heartbeatTimer, &QTimer::timeout, this, &MainWindow::sendHeartbeat);

    reconnectTimer->setSingleShot(true);
    reconnectTimer->setInterval(5000); // 5 секунд
    connect(reconnectTimer, &QTimer::timeout, this, &MainWindow::connectToServer);

    // Загрузка стиля
    applyTheme(theme);

    // Обновление состояния интерфейса
    updateConnectionState();
}

MainWindow::~MainWindow()
{
    if (isConnected) {
        disconnectFromServer();
    }
    delete ui;
}

void MainWindow::setupUI()
{
    // Установка модели для списка сообщений
    ui->chatView->setModel(chatModel);

    // Настройка поля ввода сообщения
    ui->messageInput->setPlaceholderText(tr("Введите сообщение..."));

    // Настройка списка пользователей (если будет реализован)
    ui->contactsList->setVisible(true); // Теперь видимо

    // Установка заголовка окна
    setWindowTitle(tr("Мессенджер - ") + appSettings->serverHost() + ":" + QString::number(appSettings->serverPort()));

    // Настройка кнопок
    connect(ui->sendButton, &QPushButton::clicked, this, &MainWindow::onSendMessageButtonClicked);
    connect(ui->emojiButton, &QPushButton::clicked, this, &MainWindow::toggleEmojiPanel);
    connect(ui->stickerButton, &QPushButton::clicked, this, &MainWindow::toggleStickerPanel);
    connect(ui->attachButton, &QPushButton::clicked, this, &MainWindow::openAttachmentDialog);

    // Настройка поля ввода сообщения
    connect(ui->messageInput, &QLineEdit::returnPressed, this, &MainWindow::onInputReturnPressed);
}

void MainWindow::applyTheme(const QString &themeName)
{
    QString themeFile;
    if (themeName == "dark") {
        themeFile = ":/styles/modern-dark.qss";
    } else if (themeName == "light") {
        themeFile = ":/styles/modern-light.qss";
    } else {
        themeFile = ":/styles/modern-dark.qss"; // тема по умолчанию
    }

    QFile file(themeFile);
    if (file.open(QFile::ReadOnly | QFile::Text)) {
        setStyleSheet(file.readAll());
    }
}

void MainWindow::setupEmojiPanel()
{
    emojiPanel = new QWidget(this);
    emojiPanel->setWindowFlags(Qt::Popup);
    emojiPanel->setFixedSize(350, 400);

    QVBoxLayout *layout = new QVBoxLayout(emojiPanel);

    // Создаем сетку эмодзи
    QGridLayout *emojiGrid = new QGridLayout();
    emojiGrid->setSpacing(5);

    // Базовые эмодзи
    QStringList emojis = {"😀", "😂", "😍", "🥰", "😎", "🤩", "🥳", "😭", "😡", "🤯",
                          "👍", "👎", "👏", "🙌", "👌", "✌️", "🤞", "🤟", "🤘", "🤙",
                          "👋", "💪", "🦾", "❤️", "💖", "💘", "💝", "💓", "💞", "💕",
                          "🔥", "⭐", "✨", "🎉", "🎁", "🎈", "🎂", "🍰", "🍕", "🍔"};

    int rows = 8;
    int cols = 5;

    for (int i = 0; i < emojis.size() && i < rows * cols; ++i) {
        int row = i / cols;
        int col = i % cols;

        QPushButton *emojiBtn = new QPushButton(emojis[i]);
        emojiBtn->setFixedSize(50, 50);
        emojiBtn->setStyleSheet(R"(
            QPushButton {
                font-size: 24px;
                border: none;
                border-radius: 8px;
                background-color: transparent;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
                border: 1px solid #cccccc;
            }
        )");

        connect(emojiBtn, &QPushButton::clicked, this, [this, emoji = emojis[i]]() {
            insertEmoji(emoji);
        });

        emojiGrid->addWidget(emojiBtn, row, col);
    }

    layout->addLayout(emojiGrid);

    // Добавляем кнопку закрытия
    QPushButton *closeBtn = new QPushButton(tr("Закрыть"));
    connect(closeBtn, &QPushButton::clicked, emojiPanel, &QWidget::hide);
    layout->addWidget(closeBtn);

    emojiPanel->hide();
}

void MainWindow::setupStickerPanel()
{
    stickerPanel = new QWidget(this);
    stickerPanel->setWindowFlags(Qt::Popup);
    stickerPanel->setFixedSize(400, 300);

    QVBoxLayout *layout = new QVBoxLayout(stickerPanel);

    // Заголовок
    QLabel *titleLabel = new QLabel(tr("Стикерпак"));
    titleLabel->setAlignment(Qt::AlignCenter);
    titleLabel->setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;");
    layout->addWidget(titleLabel);

    // Создаем сетку стикеров
    QGridLayout *stickerGrid = new QGridLayout();
    stickerGrid->setSpacing(10);

    // Используем стандартные эмодзи как "стикеры" для демонстрации
    QStringList stickers = {"👻", "❤️", "⭐", "🔥", "👍", "👏", "🎉", "💯"};

    int rows = 2;
    int cols = 4;

    for (int i = 0; i < stickers.size() && i < rows * cols; ++i) {
        int row = i / cols;
        int col = i % cols;

        QPushButton *stickerBtn = new QPushButton(stickers[i]);
        stickerBtn->setFixedSize(70, 70);
        stickerBtn->setStyleSheet(R"(
            QPushButton {
                font-size: 32px;
                border: 2px solid transparent;
                border-radius: 12px;
                background-color: transparent;
            }
            QPushButton:hover {
                border: 2px solid #0078d4;
                background-color: #f0f8ff;
            }
        )");

        connect(stickerBtn, &QPushButton::clicked, this, [this, sticker = stickers[i]]() {
            insertSticker(sticker);
        });

        stickerGrid->addWidget(stickerBtn, row, col);
    }

    layout->addLayout(stickerGrid);

    // Добавляем кнопку закрытия
    QPushButton *closeBtn = new QPushButton(tr("Закрыть"));
    connect(closeBtn, &QPushButton::clicked, stickerPanel, &QWidget::hide);
    layout->addWidget(closeBtn);

    stickerPanel->hide();
}

void MainWindow::insertEmoji(const QString &emoji)
{
    ui->messageInput->insert(emoji);
    ui->messageInput->setFocus();
}

void MainWindow::insertSticker(const QString &sticker)
{
    // Отправляем стикер как сообщение
    QString message = QString(":%1:").arg(sticker);

    QJsonObject jsonMsg;
    jsonMsg["type"] = "message";
    jsonMsg["user"] = currentUsername;
    jsonMsg["text"] = message;
    jsonMsg["timestamp"] = QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs);
    jsonMsg["message_type"] = "sticker";

    QString jsonString = QJsonDocument(jsonMsg).toJson(QJsonDocument::Compact);

    if (useWebSocket) {
        webSocket->sendTextMessage(jsonString);
    } else {
        tcpSocket->write(jsonString.toUtf8() + "\n");
    }

    // Добавление сообщения в чат как собственное
    addMessageToChat(currentUsername, message, QDateTime::currentDateTime(), true);

    // Закрываем панель стикеров
    if (stickerPanel->isVisible()) {
        stickerPanel->hide();
    }
}

void MainWindow::toggleEmojiPanel()
{
    if (emojiPanel->isVisible()) {
        emojiPanel->hide();
    } else {
        // Позиционируем панель рядом с полем ввода
        QPoint pos = ui->messageInput->mapToGlobal(QPoint(0, -emojiPanel->height()));
        emojiPanel->move(pos);
        emojiPanel->show();
    }
}

void MainWindow::toggleStickerPanel()
{
    if (stickerPanel->isVisible()) {
        stickerPanel->hide();
    } else {
        // Позиционируем панель рядом с полем ввода
        QPoint pos = ui->messageInput->mapToGlobal(QPoint(0, -stickerPanel->height()));
        stickerPanel->move(pos);
        stickerPanel->show();
    }
}

void MainWindow::openAttachmentDialog()
{
    QString fileName = QFileDialog::getOpenFileName(this, tr("Выберите файл"), "",
        tr("Изображения (*.png *.xpm *.jpg *.jpeg);;Документы (*.pdf *.doc *.docx *.txt);;Все файлы (*)"));

    if (!fileName.isEmpty()) {
        // Здесь должна быть реализация отправки файла
        // Пока просто показываем сообщение
        QMessageBox::information(this, tr("Файл выбран"),
            tr("Файл: %1 будет отправлен").arg(QFileInfo(fileName).fileName()));
    }
}

void MainWindow::setupConnections()
{
    // Подключения для TCP сокета
    connect(tcpSocket, &QTcpSocket::connected, this, &MainWindow::onSocketConnected);
    connect(tcpSocket, &QTcpSocket::disconnected, this, &MainWindow::onSocketDisconnected);
    connect(tcpSocket, QOverload<QAbstractSocket::SocketError>::of(&QAbstractSocket::error),
            this, &MainWindow::onSocketError);
    connect(tcpSocket, &QTcpSocket::readyRead, this, &MainWindow::onSocketReadyRead);
    
    // Подключения для WebSocket
    connect(webSocket, &QWebSocket::connected, this, &MainWindow::onWebSocketConnected);
    connect(webSocket, &QWebSocket::disconnected, this, &MainWindow::onWebSocketDisconnected);
    connect(webSocket, QOverload<QAbstractSocket::SocketError>::of(&QWebSocket::error),
            this, &MainWindow::onWebSocketError);
    connect(webSocket, &QWebSocket::textMessageReceived,
            this, &MainWindow::onWebSocketTextMessageReceived);
    
    // Подключения для кнопок
    connect(ui->connectButton, &QPushButton::clicked, this, &MainWindow::toggleConnection);
    connect(ui->sendButton, &QPushButton::clicked, this, &MainWindow::onSendMessageButtonClicked);
    
    // Подключение сигнала нажатия Enter в поле ввода
    connect(ui->messageInput, &QLineEdit::returnPressed, this, &MainWindow::onInputReturnPressed);
    
    // Подключения для настроек
    connect(appSettings, &Settings::usernameChanged, this, &MainWindow::onUsernameChanged);
    connect(appSettings, &Settings::serverHostChanged, this, &MainWindow::onServerAddressChanged);
    connect(appSettings, &Settings::serverPortChanged, this, &MainWindow::onPortChanged);
    connect(appSettings, &Settings::useSslChanged, this, &MainWindow::onUseSslChanged);
}

void MainWindow::setupTrayIcon()
{
    if (!QSystemTrayIcon::isSystemTrayAvailable()) {
        qWarning() << "Системный трей недоступен!";
        return;
    }
    
    trayIcon = new QSystemTrayIcon(this);
    trayIcon->setIcon(QIcon(":/icons/messenger.png")); // Предполагается наличие иконки
    trayIcon->setToolTip(tr("Мессенджер"));
    
    trayMenu = new QMenu(this);
    
    connectAction = new QAction(tr("Подключиться"), this);
    disconnectAction = new QAction(tr("Отключиться"), this);
    settingsAction = new QAction(tr("Настройки"), this);
    quitAction = new QAction(tr("Выход"), this);
    
    connect(connectAction, &QAction::triggered, this, &MainWindow::connectToServer);
    connect(disconnectAction, &QAction::triggered, this, &MainWindow::disconnectFromServer);
    connect(settingsAction, &QAction::triggered, this, &MainWindow::showSettingsDialog);
    connect(quitAction, &QAction::triggered, qApp, &QApplication::quit);
    
    trayMenu->addAction(connectAction);
    trayMenu->addAction(disconnectAction);
    trayMenu->addSeparator();
    trayMenu->addAction(settingsAction);
    trayMenu->addSeparator();
    trayMenu->addAction(quitAction);
    
    trayIcon->setContextMenu(trayMenu);
    
    connect(trayIcon, &QSystemTrayIcon::activated, this, &MainWindow::trayActivated);
    
    trayIcon->show();
}

void MainWindow::setupStatusBar()
{
    statusLabel = new QLabel(tr("Готов"));
    connectionStatusLabel = new QLabel(tr("Отключен"));
    progressBar = new QProgressBar();
    progressBar->setVisible(false);
    
    statusBar()->addWidget(statusLabel);
    statusBar()->addPermanentWidget(connectionStatusLabel);
    statusBar()->addPermanentWidget(progressBar);
}

void MainWindow::loadSettings()
{
    currentUsername = appSettings->username();
    currentServer = appSettings->serverHost();
    currentPort = appSettings->serverPort();
    useWebSocket = appSettings->useWebSocket();
    notificationsEnabled = appSettings->notificationsEnabled();
    soundEnabled = appSettings->soundEnabled();
    theme = appSettings->theme();
    
    // Обновление UI
    ui->usernameEdit->setText(currentUsername);
    ui->serverEdit->setText(currentServer);
    ui->portSpinBox->setValue(currentPort);
    ui->protocolCombo->setCurrentIndex(useWebSocket ? 1 : 0);
    ui->sslCheckBox->setChecked(appSettings->useSsl());
    ui->notificationsCheckBox->setChecked(notificationsEnabled);
    ui->soundCheckBox->setChecked(soundEnabled);
}

void MainWindow::saveSettings()
{
    appSettings->setUsername(currentUsername);
    appSettings->setServerHost(currentServer);
    appSettings->setServerPort(currentPort);
    appSettings->setUseWebSocket(useWebSocket);
    appSettings->setUseSsl(ui->sslCheckBox->isChecked());
    appSettings->setNotificationsEnabled(ui->notificationsCheckBox->isChecked());
    appSettings->setSoundEnabled(ui->soundCheckBox->isChecked());
    appSettings->setTheme(theme);
}

void MainWindow::connectToServer()
{
    if (currentUsername.isEmpty()) {
        currentUsername = QInputDialog::getText(this, tr("Имя пользователя"), tr("Введите ваше имя:"));
        if (currentUsername.isEmpty()) {
            showError(tr("Имя пользователя обязательно!"));
            return;
        }
        appSettings->setUsername(currentUsername);
    }
    
    isConnected = false;
    updateConnectionState();
    
    if (useWebSocket) {
        QString scheme = appSettings->useSsl() ? "wss://" : "ws://";
        QString url = QString("%1%2:%3/ws").arg(scheme, currentServer, QString::number(currentPort));
        webSocket->open(QUrl(url));
    } else {
        tcpSocket->connectToHost(currentServer, currentPort);
        
        if (appSettings->useSsl()) {
            // Настройка SSL для TCP сокета
            QSslSocket *sslSocket = qobject_cast<QSslSocket*>(tcpSocket);
            if (sslSocket) {
                sslSocket->connectToHostEncrypted(currentServer, currentPort);
            }
        }
    }
    
    statusLabel->setText(tr("Подключение..."));
}

void MainWindow::disconnectFromServer()
{
    heartbeatTimer->stop();
    
    if (useWebSocket) {
        webSocket->close();
    } else {
        tcpSocket->disconnectFromHost();
    }
    
    isConnected = false;
    updateConnectionState();
    statusLabel->setText(tr("Отключен"));
}

void MainWindow::toggleConnection()
{
    if (isConnected) {
        disconnectFromServer();
    } else {
        connectToServer();
    }
}

void MainWindow::sendMessage()
{
    QString message = ui->messageInput->text().trimmed();
    if (message.isEmpty()) {
        return;
    }
    
    QJsonObject jsonMsg;
    jsonMsg["type"] = "message";
    jsonMsg["user"] = currentUsername;
    jsonMsg["text"] = message;
    jsonMsg["timestamp"] = QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs);
    
    QString jsonString = QJsonDocument(jsonMsg).toJson(QJsonDocument::Compact);
    
    if (useWebSocket) {
        webSocket->sendTextMessage(jsonString);
    } else {
        tcpSocket->write(jsonString.toUtf8() + "\n");
    }
    
    // Добавление сообщения в чат как собственное
    addMessageToChat(currentUsername, message, QDateTime::currentDateTime(), true);
    
    // Очистка поля ввода
    ui->messageInput->clear();
}

void MainWindow::onSendMessageButtonClicked()
{
    sendMessage();
}

void MainWindow::onInputReturnPressed()
{
    sendMessage();
}

void MainWindow::onSocketConnected()
{
    statusLabel->setText(tr("Подключен к серверу"));
    isConnected = true;
    updateConnectionState();
    
    // Отправка запроса аутентификации
    sendAuthRequest();
    
    // Запуск таймера для проверки соединения
    heartbeatTimer->start();
    
    // Добавление системного сообщения
    addMessageToChat(tr("Система"), tr("Подключено к серверу"), QDateTime::currentDateTime(), false);
}

void MainWindow::onSocketDisconnected()
{
    statusLabel->setText(tr("Отключен от сервера"));
    isConnected = false;
    updateConnectionState();
    heartbeatTimer->stop();
    
    addMessageToChat(tr("Система"), tr("Соединение потеряно"), QDateTime::currentDateTime(), false);
    
    // Попытка переподключения
    if (appSettings->autoReconnect() && reconnectAttempts < 5) {
        reconnectAttempts++;
        statusLabel->setText(tr("Попытка переподключения... (%1)").arg(reconnectAttempts));
        reconnectTimer->start();
    }
}

void MainWindow::onSocketError(QAbstractSocket::SocketError error)
{
    QString errorMsg;
    switch (error) {
    case QAbstractSocket::ConnectionRefusedError:
        errorMsg = tr("Сервер отклонил соединение");
        break;
    case QAbstractSocket::RemoteHostClosedError:
        errorMsg = tr("Сервер закрыл соединение");
        break;
    case QAbstractSocket::HostNotFoundError:
        errorMsg = tr("Сервер не найден");
        break;
    case QAbstractSocket::SocketTimeoutError:
        errorMsg = tr("Таймаут соединения");
        break;
    default:
        errorMsg = tcpSocket->errorString();
        break;
    }
    
    showError(errorMsg);
    statusLabel->setText(tr("Ошибка: %1").arg(errorMsg));
}

void MainWindow::onSocketReadyRead()
{
    while (tcpSocket->canReadLine()) {
        QByteArray line = tcpSocket->readLine();
        QString messageStr = QString::fromUtf8(line).trimmed();
        
        QJsonDocument doc = QJsonDocument::fromJson(messageStr.toUtf8());
        if (!doc.isNull()) {
            QJsonObject jsonObj = doc.object();
            handleIncomingMessage(jsonObj);
        }
    }
}

void MainWindow::onWebSocketConnected()
{
    statusLabel->setText(tr("Подключен к серверу (WebSocket)"));
    isConnected = true;
    updateConnectionState();
    
    // Отправка запроса аутентификации
    sendAuthRequest();
    
    // Запуск таймера для проверки соединения
    heartbeatTimer->start();
    
    // Добавление системного сообщения
    addMessageToChat(tr("Система"), tr("Подключено к серверу (WebSocket)"), QDateTime::currentDateTime(), false);
}

void MainWindow::onWebSocketDisconnected()
{
    statusLabel->setText(tr("WebSocket отключен"));
    isConnected = false;
    updateConnectionState();
    heartbeatTimer->stop();
    
    addMessageToChat(tr("Система"), tr("WebSocket соединение потеряно"), QDateTime::currentDateTime(), false);
    
    // Попытка переподключения
    if (appSettings->autoReconnect() && reconnectAttempts < 5) {
        reconnectAttempts++;
        statusLabel->setText(tr("Попытка переподключения... (%1)").arg(reconnectAttempts));
        reconnectTimer->start();
    }
}

void MainWindow::onWebSocketError(QAbstractSocket::SocketError error)
{
    QString errorMsg = webSocket->errorString();
    showError(tr("WebSocket ошибка: %1").arg(errorMsg));
    statusLabel->setText(tr("WebSocket ошибка: %1").arg(errorMsg));
}

void MainWindow::onWebSocketTextMessageReceived(const QString &message)
{
    QJsonDocument doc = QJsonDocument::fromJson(message.toUtf8());
    if (!doc.isNull()) {
        QJsonObject jsonObj = doc.object();
        handleIncomingMessage(jsonObj);
    }
}

void MainWindow::handleIncomingMessage(const QJsonObject &jsonObj)
{
    QString type = jsonObj["type"].toString();
    
    if (type == "new_message" || type == "history_message") {
        QString user = jsonObj["user"].toString();
        QString text = jsonObj["text"].toString();
        QString timestampStr = jsonObj["timestamp"].toString();
        
        QDateTime timestamp = QDateTime::fromString(timestampStr, Qt::ISODateWithMs);
        if (!timestamp.isValid()) {
            timestamp = QDateTime::currentDateTime();
        }
        
        addMessageToChat(user, text, timestamp, user == currentUsername);
        
        // Показ уведомления
        if (notificationsEnabled && user != currentUsername) {
            showNotification(tr("Новое сообщение от %1").arg(user), text);
        }
    } else if (type == "auth_success") {
        statusLabel->setText(tr("Аутентификация успешна"));
        reconnectAttempts = 0; // Сброс попыток переподключения после успешной аутентификации
    } else if (type == "auth_error") {
        QString errorMsg = jsonObj["message"].toString();
        showError(tr("Ошибка аутентификации: %1").arg(errorMsg));
    } else if (type == "error") {
        QString errorMsg = jsonObj["message"].toString();
        showError(tr("Ошибка от сервера: %1").arg(errorMsg));
    } else if (type == "rate_limit_exceeded") {
        QString errorMsg = jsonObj["message"].toString();
        showError(tr("Превышен лимит запросов: %1").arg(errorMsg));
    }
}

void MainWindow::addMessageToChat(const QString &user, const QString &text, const QDateTime &timestamp, bool isOwn)
{
    MessageItem item;
    item.user = user;
    item.text = text;
    item.timestamp = timestamp;
    item.isOwn = isOwn;
    
    chatModel->addMessage(item);
    
    // Прокрутка к последнему сообщению
    QModelIndex lastIndex = chatModel->index(chatModel->rowCount() - 1, 0);
    ui->chatView->scrollTo(lastIndex, QAbstractItemView::PositionAtBottom);
}

void MainWindow::sendAuthRequest()
{
    QJsonObject authMsg;
    authMsg["type"] = "auth";
    authMsg["username"] = currentUsername;
    authMsg["password"] = "temp_password"; // В реальном приложении нужно запрашивать пароль
    
    QString authString = QJsonDocument(authMsg).toJson(QJsonDocument::Compact);
    
    if (useWebSocket) {
        webSocket->sendTextMessage(authString);
    } else {
        tcpSocket->write(authString.toUtf8() + "\n");
    }
}

void MainWindow::sendHeartbeat()
{
    if (isConnected) {
        QJsonObject heartbeatMsg;
        heartbeatMsg["type"] = "heartbeat";
        heartbeatMsg["timestamp"] = QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs);
        
        QString heartbeatString = QJsonDocument(heartbeatMsg).toJson(QJsonDocument::Compact);
        
        if (useWebSocket) {
            webSocket->sendTextMessage(heartbeatString);
        } else {
            tcpSocket->write(heartbeatString.toUtf8() + "\n");
        }
    }
}

void MainWindow::updateConnectionState()
{
    bool connected = isConnected;
    
    // Обновление текста кнопки подключения
    if (connected) {
        ui->connectButton->setText(tr("Отключиться"));
        ui->connectButton->setStyleSheet("QPushButton { background-color: #f44336; color: white; }");
        connectionStatusLabel->setText(tr("Подключен"));
    } else {
        ui->connectButton->setText(tr("Подключиться"));
        ui->connectButton->setStyleSheet("");
        connectionStatusLabel->setText(tr("Отключен"));
    }
    
    // Обновление доступности элементов управления
    ui->messageInput->setEnabled(connected);
    ui->sendButton->setEnabled(connected);
    ui->usernameEdit->setEnabled(!connected);
    ui->serverEdit->setEnabled(!connected);
    ui->portSpinBox->setEnabled(!connected);
    ui->protocolCombo->setEnabled(!connected);
    ui->sslCheckBox->setEnabled(!connected);
    
    // Обновление действий в трее
    if (trayIcon) {
        connectAction->setEnabled(!connected);
        disconnectAction->setEnabled(connected);
    }
}

void MainWindow::showError(const QString &error)
{
    QMessageBox::critical(this, tr("Ошибка"), error);
    statusLabel->setText(tr("Ошибка: %1").arg(error));
}

void MainWindow::showNotification(const QString &title, const QString &message)
{
    if (notificationsEnabled && trayIcon) {
        trayIcon->showMessage(title, message, QSystemTrayIcon::Information, 5000);
    }
}

void MainWindow::showTrayMenu()
{
    if (trayMenu) {
        trayMenu->popup(QCursor::pos());
    }
}

void MainWindow::trayActivated(QSystemTrayIcon::ActivationReason reason)
{
    switch (reason) {
    case QSystemTrayIcon::Trigger:
        if (isMinimized()) {
            showNormal();
            raise();
            activateWindow();
        } else {
            showMinimized();
        }
        break;
    case QSystemTrayIcon::DoubleClick:
        showNormal();
        raise();
        activateWindow();
        break;
    default:
        break;
    }
}

void MainWindow::showSettingsDialog()
{
    // Здесь будет вызов диалога настроек
    // Для упрощения в этом примере просто показываем вкладку настроек
    if (ui->tabWidget->indexOf(ui->settingsTab) != -1) {
        ui->tabWidget->setCurrentWidget(ui->settingsTab);
    }
}

void MainWindow::applySettings()
{
    // Применение настроек из интерфейса
    currentUsername = ui->usernameEdit->text();
    currentServer = ui->serverEdit->text();
    currentPort = ui->portSpinBox->value();
    useWebSocket = ui->protocolCombo->currentIndex() == 1; // 0 - TCP, 1 - WebSocket
    
    // Сохранение настроек
    saveSettings();
    
    // Обновление заголовка окна
    setWindowTitle(tr("Мессенджер - ") + currentServer + ":" + QString::number(currentPort));
}

void MainWindow::onUsernameChanged(const QString &username)
{
    currentUsername = username;
}

void MainWindow::onServerAddressChanged(const QString &address)
{
    currentServer = address;
}

void MainWindow::onPortChanged(int port)
{
    currentPort = port;
}

void MainWindow::onUseSslChanged(bool useSsl)
{
    Q_UNUSED(useSsl);
    // Переподключение при изменении SSL настроек
    if (isConnected) {
        disconnectFromServer();
        QTimer::singleShot(1000, this, &MainWindow::connectToServer);
    }
}

void MainWindow::closeEvent(QCloseEvent *event)
{
    if (trayIcon && trayIcon->isVisible()) {
        hide();
        event->ignore();
    } else {
        if (isConnected) {
            disconnectFromServer();
        }
        event->accept();
    }
}

void MainWindow::updateStatusBar()
{
    // Обновление информации в строке состояния
    QString info = tr("Пользователей онлайн: %1 | Сообщений: %2")
                       .arg(chatModel->onlineUsersCount())
                       .arg(chatModel->messageCount());
    statusLabel->setText(info);
}
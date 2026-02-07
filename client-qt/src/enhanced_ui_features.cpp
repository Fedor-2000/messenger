# client-qt/src/enhanced_ui_features.cpp
#include "enhanced_ui_features.h"
#include <QTextEdit>
#include <QTextBrowser>
#include <QScrollBar>
#include <QCompleter>
#include <QStringListModel>
#include <QShortcut>
#include <QKeyEvent>
#include <QTimer>
#include <QMovie>
#include <QLabel>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QGridLayout>
#include <QPushButton>
#include <QLineEdit>
#include <QListWidget>
#include <QListWidgetItem>
#include <QPainter>
#include <QStyleOptionViewItem>
#include <QStyledItemDelegate>
#include <QPropertyAnimation>
#include <QEasingCurve>
#include <QGraphicsOpacityEffect>
#include <QDesktopServices>
#include <QUrl>
#include <QDir>
#include <QStandardPaths>
#include <QSettings>
#include <QApplication>
#include <QPalette>
#include <QFontDatabase>
#include <QMessageBox>
#include <QInputDialog>
#include <QColorDialog>
#include <QFontDialog>
#include <QFileDialog>
#include <QMimeData>
#include <QDragEnterEvent>
#include <QDropEvent>
#include <QDrag>
#include <QDragMoveEvent>
#include <QTimerEvent>
#include <QWheelEvent>
#include <QMouseEvent>
#include <QHoverEvent>
#include <QPaintEvent>
#include <QResizeEvent>
#include <QShowEvent>
#include <QHideEvent>
#include <QFocusEvent>
#include <QContextMenuEvent>
#include <QAction>
#include <QMenu>
#include <QMenuBar>
#include <QToolBar>
#include <QStatusBar>
#include <QDockWidget>
#include <QSplitter>
#include <QTabWidget>
#include <QTabBar>
#include <QProgressBar>
#include <QSlider>
#include <QSpinBox>
#include <QDoubleSpinBox>
#include <QCheckBox>
#include <QRadioButton>
#include <QGroupBox>
#include <QFormLayout>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QGridLayout>
#include <QStackedLayout>
#include <QScrollArea>
#include <QFrame>
#include <QLabel>
#include <QLineEdit>
#include <QTextEdit>
#include <QPlainTextEdit>
#include <QTextBrowser>
#include <QListWidget>
#include <QTreeWidget>
#include <QTableWidget>
#include <QComboBox>
#include <QFontComboBox>
#include <QCalendarWidget>
#include <QTimeEdit>
#include <QDateEdit>
#include <QDateTimeEdit>
#include <QSpinBox>
#include <QDoubleSpinBox>
#include <QProgressBar>
#include <QSlider>
#include <QDial>
#include <QScrollBar>
#include <QScroller>
#include <QScrollerProperties>

EnhancedUIFeatures::EnhancedUIFeatures(QObject *parent)
    : QObject(parent)
    , m_autoCompleteEnabled(true)
    , m_shortcutsEnabled(true)
    , m_animationsEnabled(true)
    , m_themesEnabled(true)
    , m_mentionSuggestionsEnabled(true)
    , m_messageFormattingEnabled(true)
    , m_dragAndDropEnabled(true)
    , m_tooltipsEnabled(true)
    , m_statusIndicatorsEnabled(true)
    , m_searchAsITypeEnabled(true)
    , m_autoSaveDraftsEnabled(true)
    , m_typingIndicatorsEnabled(true)
{
    initializeFeatures();
}

void EnhancedUIFeatures::initializeFeatures()
{
    setupAutoComplete();
    setupShortcuts();
    setupAnimations();
    setupThemes();
    setupMentionSuggestions();
    setupMessageFormatting();
    setupDragAndDrop();
    setupTooltips();
    setupStatusIndicators();
    setupSearchAsIType();
    setupAutoSaveDrafts();
    setupTypingIndicators();
}

void EnhancedUIFeatures::setupAutoComplete()
{
    if (!m_autoCompleteEnabled) return;

    // Создаем список слов для автодополнения
    QStringList autoCompleteWords;
    autoCompleteWords << "hello" << "world" << "messenger" << "chat" << "message"
                     << "user" << "group" << "private" << "public" << "online"
                     << "offline" << "away" << "busy" << "available";

    m_autoCompleteModel = new QStringListModel(autoCompleteWords, this);
    m_autoCompleter = new QCompleter(m_autoCompleteModel, this);
    m_autoCompleter->setCaseSensitivity(Qt::CaseInsensitive);
    m_autoCompleter->setCompletionMode(QCompleter::PopupCompletion);
}

void EnhancedUIFeatures::setupShortcuts()
{
    if (!m_shortcutsEnabled) return;

    // Создаем горячие клавиши
    m_shortcuts["send_message"] = new QShortcut(QKeySequence("Ctrl+Return"), nullptr);
    m_shortcuts["send_message"]->setContext(Qt::ApplicationShortcut);
    
    m_shortcuts["new_line"] = new QShortcut(QKeySequence("Shift+Return"), nullptr);
    m_shortcuts["new_line"]->setContext(Context::ApplicationShortcut);
    
    m_shortcuts["search"] = new QShortcut(QKeySequence("Ctrl+F"), nullptr);
    m_shortcuts["search"]->setContext(Qt::ApplicationShortcut);
    
    m_shortcuts["next_chat"] = new QShortcut(QKeySequence("Ctrl+Tab"), nullptr);
    m_shortcuts["next_chat"]->setContext(Qt::ApplicationShortcut);
    
    m_shortcuts["prev_chat"] = new QShortcut(QKeySequence("Ctrl+Shift+Tab"), nullptr);
    m_shortcuts["prev_chat"]->setContext(Qt::ApplicationShortcut);
    
    m_shortcuts["emoji_panel"] = new QShortcut(QKeySequence("Ctrl+E"), nullptr);
    m_shortcuts["emoji_panel"]->setContext(Qt::ApplicationShortcut);
    
    // Подключаем сигналы
    connect(m_shortcuts["send_message"], &QShortcut::activated, this, &EnhancedUIFeatures::onSendMessageShortcut);
    connect(m_shortcuts["search"], &QShortcut::activated, this, &EnhancedUIFeatures::onSearchShortcut);
    connect(m_shortcuts["emoji_panel"], &QShortcut::activated, this, &EnhancedUIFeatures::onEmojiPanelShortcut);
}

void EnhancedUIFeatures::setupAnimations()
{
    if (!m_animationsEnabled) return;

    // Устанавливаем параметры анимаций
    m_animationDuration = 300; // ms
    m_easingCurve = QEasingCurve::OutCubic;
}

void EnhancedUIFeatures::setupThemes()
{
    if (!m_themesEnabled) return;

    // Загружаем встроенные темы
    m_builtinThemes["light"] = ":/themes/light.qss";
    m_builtinThemes["dark"] = ":/themes/dark.qss";
    m_builtinThemes["blue"] = ":/themes/blue.qss";
    m_builtinThemes["green"] = ":/themes/green.qss";
    m_builtinThemes["purple"] = ":/themes/purple.qss";

    // Загружаем пользовательские темы
    loadCustomThemes();
}

void EnhancedUIFeatures::setupMentionSuggestions()
{
    if (!m_mentionSuggestionsEnabled) return;

    // Создаем модель для автодополнения упоминаний
    m_mentionModel = new QStringListModel(this);
    m_mentionCompleter = new QCompleter(m_mentionModel, this);
    m_mentionCompleter->setCaseSensitivity(Qt::CaseInsensitive);
    m_mentionCompleter->setCompletionMode(QCompleter::InlineCompletion);
    m_mentionCompleter->setWidget(nullptr); // Будет устанавливаться для конкретного виджета
}

void EnhancedUIFeatures::setupMessageFormatting()
{
    if (!m_messageFormattingEnabled) return;

    // Инициализируем форматирование текста
    m_formattingActions["bold"] = new QAction(QIcon(":/icons/bold.png"), tr("Bold"), this);
    m_formattingActions["italic"] = new QAction(QIcon(":/icons/italic.png"), tr("Italic"), this);
    m_formattingActions["underline"] = new QAction(QIcon(":/icons/underline.png"), tr("Underline"), this);
    m_formattingActions["strikethrough"] = new QAction(QIcon(":/icons/strikethrough.png"), tr("Strikethrough"), this);
    m_formattingActions["code"] = new QAction(QIcon(":/icons/code.png"), tr("Code"), this);
    m_formattingActions["link"] = new QAction(QIcon(":/icons/link.png"), tr("Link"), this);
    m_formattingActions["quote"] = new QAction(QIcon(":/icons/quote.png"), tr("Quote"), this);

    // Устанавливаем сочетания клавиш
    m_formattingActions["bold"]->setShortcut(QKeySequence("Ctrl+B"));
    m_formattingActions["italic"]->setShortcut(QKeySequence("Ctrl+I"));
    m_formattingActions["underline"]->setShortcut(QKeySequence("Ctrl+U"));
    m_formattingActions["code"]->setShortcut(QKeySequence("Ctrl+K"));

    // Подключаем сигналы
    connect(m_formattingActions["bold"], &QAction::triggered, this, &EnhancedUIFeatures::applyBoldFormat);
    connect(m_formattingActions["italic"], &QAction::triggered, this, &EnhancedUIFeatures::applyItalicFormat);
    connect(m_formattingActions["underline"], &QAction::triggered, this, &EnhancedUIFeatures::applyUnderlineFormat);
    connect(m_formattingActions["strikethrough"], &QAction::triggered, this, &EnhancedUIFeatures::applyStrikeThroughFormat);
    connect(m_formattingActions["code"], &QAction::triggered, this, &EnhancedUIFeatures::applyCodeFormat);
    connect(m_formattingActions["link"], &QAction::triggered, this, &EnhancedUIFeatures::applyLinkFormat);
    connect(m_formattingActions["quote"], &QAction::triggered, this, &EnhancedUIFeatures::applyQuoteFormat);
}

void EnhancedUIFeatures::setupDragAndDrop()
{
    if (!m_dragAndDropEnabled) return;

    // Устанавливаем параметры Drag & Drop
    m_dragPixmapSize = QSize(100, 100);
    m_dropIndicatorColor = QColor(0, 120, 215);
    m_acceptableMimeTypes << "text/plain" << "text/html" << "application/x-qabstractitemmodeldatalist";
}

void EnhancedUIFeatures::setupTooltips()
{
    if (!m_tooltipsEnabled) return;

    // Устанавливаем параметры всплывающих подсказок
    m_tooltipDelay = 500; // ms
    m_tooltipDuration = 5000; // ms
    m_tooltipStyle = "QToolTip { background-color: #2a2a2a; color: white; border: 1px solid #555; border-radius: 4px; padding: 4px; }";
}

void EnhancedUIFeatures::setupStatusIndicators()
{
    if (!m_statusIndicatorsEnabled) return;

    // Инициализируем индикаторы статуса
    m_statusIcons["online"] = QIcon(":/icons/status_online.png");
    m_statusIcons["away"] = QIcon(":/icons/status_away.png");
    m_statusIcons["busy"] = QIcon(":/icons/status_busy.png");
    m_statusIcons["offline"] = QIcon(":/icons/status_offline.png");
    m_statusIcons["invisible"] = QIcon(":/icons/status_invisible.png");
}

void EnhancedUIFeatures::setupSearchAsIType()
{
    if (!m_searchAsITypeEnabled) return;

    // Устанавливаем параметры поиска по мере ввода
    m_searchDelay = 300; // ms
    m_searchMinimumChars = 2;
    m_searchCaseSensitive = false;
}

void EnhancedUIFeatures::setupAutoSaveDrafts()
{
    if (!m_autoSaveDraftsEnabled) return;

    // Устанавливаем параметры автосохранения черновиков
    m_draftSaveInterval = 30000; // 30 seconds
    m_maxDrafts = 10;
    m_draftsPath = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation) + "/drafts/";

    QDir().mkpath(m_draftsPath);
}

void EnhancedUIFeatures::setupTypingIndicators()
{
    if (!m_typingIndicatorsEnabled) return;

    // Устанавливаем параметры индикаторов набора текста
    m_typingIndicatorTimeout = 5000; // 5 seconds
    m_typingIndicatorStyle = "color: #888; font-style: italic;";
}

void EnhancedUIFeatures::applyTheme(const QString &themeName)
{
    if (m_themesEnabled && m_builtinThemes.contains(themeName)) {
        QFile themeFile(m_builtinThemes[themeName]);
        if (themeFile.open(QFile::ReadOnly | QFile::Text)) {
            QString stylesheet = themeFile.readAll();
            qApp->setStyleSheet(stylesheet);
            
            // Сохраняем выбранную тему
            QSettings settings;
            settings.setValue("appearance/theme", themeName);
            
            emit themeChanged(themeName);
        }
    }
}

void EnhancedUIFeatures::enableAutoCompleteFor(QLineEdit *lineEdit)
{
    if (m_autoCompleteEnabled && m_autoCompleter) {
        m_autoCompleter->setWidget(lineEdit);
    }
}

void EnhancedUIFeatures::enableAutoCompleteFor(QTextEdit *textEdit)
{
    if (m_autoCompleteEnabled && m_autoCompleter) {
        // Для QTextEdit нужно создать специальный обработчик
        connect(textEdit, &QTextEdit::textChanged, this, [this, textEdit]() {
            // Проверяем, был ли введен символ, который может триггерить автодополнение
            QTextCursor cursor = textEdit->textCursor();
            QString text = textEdit->toPlainText();
            int pos = cursor.position();
            
            if (pos > 0 && text[pos-1] == '@') {
                // Показываем автодополнение для упоминаний
                showMentionSuggestions(textEdit, pos-1);
            }
        });
    }
}

void EnhancedUIFeatures::showMentionSuggestions(QTextEdit *textEdit, int position)
{
    if (!m_mentionSuggestionsEnabled || !m_mentionCompleter) return;

    // Получаем список пользователей в чате
    QStringList users = getCurrentChatUsers(); // В реальном приложении получать из модели
    
    m_mentionModel->setStringList(users);
    m_mentionCompleter->setWidget(textEdit);
    
    // Показываем автодополнение
    QTextCursor cursor = textEdit->textCursor();
    cursor.setPosition(position);
    textEdit->setTextCursor(cursor);
    
    m_mentionCompleter->complete();
}

void EnhancedUIFeatures::applyBoldFormat()
{
    if (!m_messageFormattingEnabled) return;
    
    QTextEdit *currentTextEdit = getCurrentTextEdit(); // В реальном приложении получать активный редактор
    if (currentTextEdit) {
        QTextCharFormat format;
        format.setFontWeight(QFont::Bold);
        currentTextEdit->mergeCurrentCharFormat(format);
    }
}

void EnhancedUIFeatures::applyItalicFormat()
{
    if (!m_messageFormattingEnabled) return;
    
    QTextEdit *currentTextEdit = getCurrentTextEdit();
    if (currentTextEdit) {
        QTextCharFormat format;
        format.setFontItalic(true);
        currentTextEdit->mergeCurrentCharFormat(format);
    }
}

void EnhancedUIFeatures::applyUnderlineFormat()
{
    if (!m_messageFormattingEnabled) return;
    
    QTextEdit *currentTextEdit = getCurrentTextEdit();
    if (currentTextEdit) {
        QTextCharFormat format;
        format.setFontUnderline(true);
        currentTextEdit->mergeCurrentCharFormat(format);
    }
}

void EnhancedUIFeatures::applyCodeFormat()
{
    if (!m_messageFormattingEnabled) return;
    
    QTextEdit *currentTextEdit = getCurrentTextEdit();
    if (currentTextEdit) {
        QTextCharFormat format;
        format.setFontFamily("Courier New");
        format.setBackground(QColor("#f0f0f0"));
        format.setForeground(QColor("#d63333"));
        currentTextEdit->mergeCurrentCharFormat(format);
    }
}

void EnhancedUIFeatures::animateWidget(QWidget *widget, AnimationType type)
{
    if (!m_animationsEnabled) return;

    switch (type) {
    case FadeIn:
        animateFadeIn(widget);
        break;
    case FadeOut:
        animateFadeOut(widget);
        break;
    case SlideIn:
        animateSlideIn(widget);
        break;
    case SlideOut:
        animateSlideOut(widget);
        break;
    case Bounce:
        animateBounce(widget);
        break;
    }
}

void EnhancedUIFeatures::animateFadeIn(QWidget *widget)
{
    QGraphicsOpacityEffect *effect = new QGraphicsOpacityEffect(widget);
    widget->setGraphicsEffect(effect);

    QPropertyAnimation *animation = new QPropertyAnimation(effect, "opacity");
    animation->setDuration(m_animationDuration);
    animation->setStartValue(0);
    animation->setEndValue(1);
    animation->setEasingCurve(m_easingCurve);

    connect(animation, &QPropertyAnimation::finished, effect, &QGraphicsOpacityEffect::deleteLater);
    animation->start(QPropertyAnimation::DeleteWhenStopped);
}

void EnhancedUIFeatures::animateFadeOut(QWidget *widget)
{
    QGraphicsOpacityEffect *effect = widget->graphicsEffect();
    if (!effect) {
        effect = new QGraphicsOpacityEffect(widget);
        widget->setGraphicsEffect(effect);
    }

    QPropertyAnimation *animation = new QPropertyAnimation(effect, "opacity");
    animation->setDuration(m_animationDuration);
    animation->setStartValue(1);
    animation->setEndValue(0);
    animation->setEasingCurve(m_easingCurve);

    connect(animation, &QPropertyAnimation::finished, [widget, effect]() {
        widget->hide();
        effect->deleteLater();
    });
    animation->start(QPropertyAnimation::DeleteWhenStopped);
}

void EnhancedUIFeatures::animateSlideIn(QWidget *widget)
{
    // Анимация появления сбоку
    QPoint startPos = widget->pos();
    startPos.setX(startPos.x() - widget->width());

    QPropertyAnimation *animation = new QPropertyAnimation(widget, "pos");
    animation->setDuration(m_animationDuration);
    animation->setStartValue(startPos);
    animation->setEndValue(widget->pos());
    animation->setEasingCurve(m_easingCurve);

    widget->show();
    animation->start(QPropertyAnimation::DeleteWhenStopped);
}

void EnhancedUIFeatures::animateBounce(QWidget *widget)
{
    QPropertyAnimation *animation = new QPropertyAnimation(widget, "geometry");
    QRect originalGeometry = widget->geometry();
    
    // Создаем анимацию с прыжками
    animation->setDuration(m_animationDuration * 2);
    animation->setKeyValueAt(0.0, originalGeometry);
    animation->setKeyValueAt(0.3, originalGeometry.adjusted(-5, -5, 5, 5));
    animation->setKeyValueAt(0.6, originalGeometry.adjusted(3, 3, -3, -3));
    animation->setKeyValueAt(1.0, originalGeometry);
    animation->setEasingCurve(QEasingCurve::OutBounce);

    animation->start(QPropertyAnimation::DeleteWhenStopped);
}

void EnhancedUIFeatures::showNotification(const QString &title, const QString &message, NotificationType type)
{
    // Показываем улучшенное уведомление
    QMessageBox msgBox;
    
    switch (type) {
    case Info:
        msgBox.setIcon(QMessageBox::Information);
        break;
    case Warning:
        msgBox.setIcon(QMessageBox::Warning);
        break;
    case Error:
        msgBox.setIcon(QMessageBox::Critical);
        break;
    case Success:
        msgBox.setIcon(QMessageBox::Information);
        break;
    }
    
    msgBox.setWindowTitle(title);
    msgBox.setText(message);
    msgBox.setStandardButtons(QMessageBox::Ok);
    msgBox.setDefaultButton(QMessageBox::Ok);
    
    // Добавляем таймер для авто-скрытия (если нужно)
    QTimer::singleShot(5000, &msgBox, &QMessageBox::accept);
    
    msgBox.exec();
}

void EnhancedUIFeatures::loadCustomThemes()
{
    // Загружаем пользовательские темы из директории
    QString themesPath = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation) + "/themes/";
    QDir themesDir(themesPath);
    
    if (themesDir.exists()) {
        QStringList themeFiles = themesDir.entryList(QStringList() << "*.qss", QDir::Files);
        for (const QString &file : themeFiles) {
            QString themeName = file.left(file.length() - 4); // Убираем .qss
            m_customThemes[themeName] = themesPath + file;
        }
    }
}

QStringList EnhancedUIFeatures::getCurrentChatUsers()
{
    // В реальном приложении возвращать список пользователей текущего чата
    return QStringList() << "user1" << "user2" << "user3" << "admin";
}

QTextEdit *EnhancedUIFeatures::getCurrentTextEdit()
{
    // В реальном приложении возвращать текущий активный текстовый редактор
    return nullptr;
}

void EnhancedUIFeatures::onSendMessageShortcut()
{
    emit sendMessageRequested();
}

void EnhancedUIFeatures::onSearchShortcut()
{
    emit searchRequested();
}

void EnhancedUIFeatures::onEmojiPanelShortcut()
{
    emit emojiPanelRequested();
}

// EmojiPanel.cpp
EmojiPanel::EmojiPanel(QWidget *parent)
    : QWidget(parent)
    , m_gridLayout(nullptr)
    , m_searchBox(nullptr)
    , m_categoryTabs(nullptr)
{
    setupUI();
    loadEmojis();
    setupConnections();
}

void EmojiPanel::setupUI()
{
    setWindowFlags(Qt::Popup);
    setFixedSize(350, 400);
    
    QVBoxLayout *mainLayout = new QVBoxLayout(this);
    
    // Панель поиска
    m_searchBox = new QLineEdit(this);
    m_searchBox->setPlaceholderText(tr("Search emojis..."));
    m_searchBox->setClearButtonEnabled(true);
    
    // Табы категорий
    m_categoryTabs = new QTabWidget(this);
    m_categoryTabs->setTabPosition(QTabWidget::South);
    
    // Создаем вкладки для категорий
    setupCategories();
    
    mainLayout->addWidget(m_searchBox);
    mainLayout->addWidget(m_categoryTabs);
    
    // Устанавливаем стили
    setStyleSheet(R"(
        QWidget {
            background-color: #ffffff;
            border: 1px solid #cccccc;
            border-radius: 8px;
        }
        QLineEdit {
            padding: 8px;
            border: 1px solid #dddddd;
            border-radius: 4px;
            margin: 5px;
        }
        QTabWidget::pane {
            border: none;
            background: transparent;
        }
        QTabBar::tab {
            background: #f0f0f0;
            border: 1px solid #ddd;
            border-bottom: none;
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }
        QTabBar::tab:selected {
            background: #ffffff;
            border-bottom: 2px solid #0078d4;
        }
    )");
}

void EmojiPanel::setupCategories()
{
    // Создаем вкладки для различных категорий эмодзи
    QStringList categories = {"Smileys", "People", "Nature", "Food", "Travel", "Objects", "Symbols", "Flags"};
    
    for (const QString &category : categories) {
        QWidget *categoryWidget = new QWidget(this);
        QGridLayout *gridLayout = new QGridLayout(categoryWidget);
        gridLayout->setSpacing(2);
        gridLayout->setContentsMargins(5, 5, 5, 5);
        
        // Заполняем эмодзи для категории (в реальном приложении - из базы данных)
        populateCategory(category, gridLayout);
        
        m_categoryTabs->addTab(categoryWidget, category);
    }
}

void EmojiPanel::populateCategory(const QString &category, QGridLayout *layout)
{
    // В реальном приложении загружать эмодзи из базы данных или файла
    QStringList emojis;
    
    if (category == "Smileys") {
        emojis << "😀" << "😃" << "😄" << "😁" << "😆" << "😅" << "🤣" << "😂" << "🙂" << "🙃" << "😉" << "😊";
    } else if (category == "People") {
        emojis << "👋" << "🤚" << "🖐" << "✋" << "🖖" << "👌" << "🤏" << "✌️" << "🤞" << "🤟" << "🤘" << "🤙";
    } else if (category == "Nature") {
        emojis << "🐶" << "🐱" << "🐭" << "🐹" << "🐰" << "🦊" << "🐻" << "🐼" << "🐨" << "🐯" << "🦁" << "🐮";
    } else if (category == "Food") {
        emojis << "🍏" << "🍎" << "🍐" << "🍊" << "🍋" << "🍌" << "🍉" << "🍇" << "🍓" << "🍈" << "🍒" << "🍑";
    } else if (category == "Travel") {
        emojis << "🚗" << "🚕" << "🚙" << "🚌" << "🚎" << "🏎" << "🚓" << "🚑" << "🚒" << "🚐" << "🛻" << "🚚";
    } else if (category == "Objects") {
        emojis << "⌚" << "📱" << "📲" << "💻" << "⌨️" << "🖥" << "🖨" << "🖱" << "🖲" << "🕹" << "🗜" << "💽";
    } else if (category == "Symbols") {
        emojis << "❤️" << "🧡" << "💛" << "💚" << "💙" << "💜" << "🖤" << "🤍" << "🤎" << "💔" << "❣️" << "💕";
    } else if (category == "Flags") {
        emojis << "🏳️" << "🏴" << "🏁" << "🚩" << "🏳️‍🌈" << "🏴‍☠️" << "🇺🇸" << "🇷🇺" << "🇨🇳" << "🇯🇵" << "🇰🇷" << "🇩🇪";
    }
    
    int rows = 4;
    int cols = 6;
    int index = 0;
    
    for (const QString &emoji : emojis) {
        if (index >= rows * cols) break;
        
        int row = index / cols;
        int col = index % cols;
        
        QPushButton *emojiBtn = new QPushButton(emoji, this);
        emojiBtn->setFixedSize(40, 40);
        emojiBtn->setStyleSheet(R"(
            QPushButton {
                font-size: 20px;
                border: none;
                border-radius: 4px;
                background-color: transparent;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
            }
            QPushButton:pressed {
                background-color: #e0e0e0;
            }
        )");
        
        connect(emojiBtn, &QPushButton::clicked, this, [this, emoji]() {
            emit emojiSelected(emoji);
        });
        
        layout->addWidget(emojiBtn, row, col);
        index++;
    }
}

void EmojiPanel::loadEmojis()
{
    // В реальном приложении загружать эмодзи из файла или базы данных
}

void EmojiPanel::setupConnections()
{
    connect(m_searchBox, &QLineEdit::textChanged, this, &EmojiPanel::filterEmojis);
}

void EmojiPanel::filterEmojis(const QString &filter)
{
    // Фильтрация эмодзи по поисковому запросу
    // В реальном приложении реализовать фильтрацию
}

void EmojiPanel::showAt(const QPoint &pos)
{
    move(pos);
    show();
}

// MessageFormatter.cpp
MessageFormatter::MessageFormatter(QObject *parent)
    : QObject(parent)
{
    initializePatterns();
}

void MessageFormatter::initializePatterns()
{
    // Регулярные выражения для форматирования
    m_patterns["bold"] = QRegularExpression("\\*\\*(.*?)\\*\\*");
    m_patterns["italic"] = QRegularExpression("\\*(.*?)\\*");
    m_patterns["code"] = QRegularExpression("`([^`]*)`");
    m_patterns["code_block"] = QRegularExpression("```(?:([a-zA-Z]+)\\n)?([\\s\\S]*?)```");
    m_patterns["link"] = QRegularExpression("\\[([^\\]]+)\\]\\(([^\\)]+)\\)");
    m_patterns["mention"] = QRegularExpression("@(\\w+)");
    m_patterns["hashtag"] = QRegularExpression("#(\\w+)");
    m_patterns["strikethrough"] = QRegularExpression("~~(.*?)~~");
    m_patterns["quote"] = QRegularExpression("^> (.*)$", QRegularExpression::MultilineOption);
}

QString MessageFormatter::formatMessage(const QString &rawMessage)
{
    QString formatted = rawMessage;
    
    // Применяем форматирование в порядке приоритета
    formatted = formatCodeBlocks(formatted);
    formatted = formatCodeSpans(formatted);
    formatted = formatBold(formatted);
    formatted = formatItalic(formatted);
    formatted = formatStrikethrough(formatted);
    formatted = formatLinks(formatted);
    formatted = formatMentions(formatted);
    formatted = formatHashtags(formatted);
    formatted = formatQuotes(formatted);
    
    return formatted;
}

QString MessageFormatter::formatBold(const QString &text)
{
    QString result = text;
    QRegularExpressionMatchIterator it = m_patterns["bold"].globalMatch(result);
    
    int offset = 0;
    while (it.hasNext()) {
        QRegularExpressionMatch match = it.next();
        QString content = match.captured(1);
        QString replacement = QString("<b>%1</b>").arg(content);
        
        result.replace(match.capturedStart() + offset, match.capturedLength(), replacement);
        offset += replacement.length() - match.capturedLength();
    }
    
    return result;
}

QString MessageFormatter::formatItalic(const QString &text)
{
    QString result = text;
    QRegularExpressionMatchIterator it = m_patterns["italic"].globalMatch(result);
    
    int offset = 0;
    while (it.hasNext()) {
        QRegularExpressionMatch match = it.next();
        QString content = match.captured(1);
        QString replacement = QString("<i>%1</i>").arg(content);
        
        result.replace(match.capturedStart() + offset, match.capturedLength(), replacement);
        offset += replacement.length() - match.capturedLength();
    }
    
    return result;
}

QString MessageFormatter::formatCodeSpans(const QString &text)
{
    QString result = text;
    QRegularExpressionMatchIterator it = m_patterns["code"].globalMatch(result);
    
    int offset = 0;
    while (it.hasNext()) {
        QRegularExpressionMatch match = it.next();
        QString content = match.captured(1);
        QString replacement = QString("<code style=\"background-color:#f4f4f4; padding:2px 4px; border-radius:3px; font-family:'Courier New',monospace;\">%1</code>").arg(content);
        
        result.replace(match.capturedStart() + offset, match.capturedLength(), replacement);
        offset += replacement.length() - match.capturedLength();
    }
    
    return result;
}

QString MessageFormatter::formatLinks(const QString &text)
{
    QString result = text;
    QRegularExpressionMatchIterator it = m_patterns["link"].globalMatch(result);
    
    int offset = 0;
    while (it.hasNext()) {
        QRegularExpressionMatch match = it.next();
        QString linkText = match.captured(1);
        QString linkUrl = match.captured(2);
        QString replacement = QString("<a href=\"%2\" style=\"color:#0078d4; text-decoration:underline;\">%1</a>").arg(linkText, linkUrl);
        
        result.replace(match.capturedStart() + offset, match.capturedLength(), replacement);
        offset += replacement.length() - match.capturedLength();
    }
    
    return result;
}

QString MessageFormatter::formatMentions(const QString &text)
{
    QString result = text;
    QRegularExpressionMatchIterator it = m_patterns["mention"].globalMatch(result);
    
    int offset = 0;
    while (it.hasNext()) {
        QRegularExpressionMatch match = it.next();
        QString username = match.captured(1);
        QString replacement = QString("<span style=\"color:#0078d4; font-weight:bold;\">@%1</span>").arg(username);
        
        result.replace(match.capturedStart() + offset, match.capturedLength(), replacement);
        offset += replacement.length() - match.capturedLength();
    }
    
    return result;
}

QString MessageFormatter::formatHashtags(const QString &text)
{
    QString result = text;
    QRegularExpressionMatchIterator it = m_patterns["hashtag"].globalMatch(result);
    
    int offset = 0;
    while (it.hasNext()) {
        QRegularExpressionMatch match = it.next();
        QString hashtag = match.captured(1);
        QString replacement = QString("<a href=\"hashtag://%1\" style=\"color:#0078d4; text-decoration:none;\">#%1</a>").arg(hashtag);
        
        result.replace(match.capturedStart() + offset, match.capturedLength(), replacement);
        offset += replacement.length() - match.capturedLength();
    }
    
    return result;
}

QString MessageFormatter::formatStrikethrough(const QString &text)
{
    QString result = text;
    QRegularExpressionMatchIterator it = m_patterns["strikethrough"].globalMatch(result);
    
    int offset = 0;
    while (it.hasNext()) {
        QRegularExpressionMatch match = it.next();
        QString content = match.captured(1);
        QString replacement = QString("<s>%1</s>").arg(content);
        
        result.replace(match.capturedStart() + offset, match.capturedLength(), replacement);
        offset += replacement.length() - match.capturedLength();
    }
    
    return result;
}

QString MessageFormatter::formatQuotes(const QString &text)
{
    QString result = text;
    QRegularExpressionMatchIterator it = m_patterns["quote"].globalMatch(result);
    
    int offset = 0;
    while (it.hasNext()) {
        QRegularExpressionMatch match = it.next();
        QString quoteText = match.captured(1);
        QString replacement = QString("<blockquote style=\"margin:10px 0; padding:8px 12px; border-left:3px solid #0078d4; background-color:#f9f9f9;\">%1</blockquote>").arg(quoteText);
        
        result.replace(match.capturedStart() + offset, match.capturedLength(), replacement);
        offset += replacement.length() - match.capturedLength();
    }
    
    return result;
}

QString MessageFormatter::formatCodeBlocks(const QString &text)
{
    QString result = text;
    QRegularExpressionMatchIterator it = m_patterns["code_block"].globalMatch(result);
    
    int offset = 0;
    while (it.hasNext()) {
        QRegularExpressionMatch match = it.next();
        QString lang = match.captured(1); // Может быть пустым
        QString code = match.captured(2);
        
        QString languageClass = lang.isEmpty() ? "" : QString(" class=\"language-%1\"").arg(lang);
        QString replacement = QString("<pre><code%1 style=\"display:block; padding:12px; background-color:#f4f4f4; border-radius:4px; font-family:'Courier New',monospace; overflow-x:auto;\">%2</code></pre>")
                                   .arg(languageClass, code.toHtmlEscaped());
        
        result.replace(match.capturedStart() + offset, match.capturedLength(), replacement);
        offset += replacement.length() - match.capturedLength();
    }
    
    return result;
}
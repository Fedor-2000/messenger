// client-qt/src/enhanced_ui_features.h
#ifndef ENHANCED_UI_FEATURES_H
#define ENHANCED_UI_FEATURES_H

#include <QObject>
#include <QMap>
#include <QHash>
#include <QList>
#include <QString>
#include <QStringList>
#include <QIcon>
#include <QCompleter>
#include <QStringListModel>
#include <QAction>
#include <QShortcut>
#include <QEasingCurve>
#include <QPropertyAnimation>
#include <QTextCharFormat>
#include <QRegularExpression>
#include <QTextEdit>
#include <QLineEdit>
#include <QTabWidget>
#include <QGridLayout>
#include <QPushButton>
#include <QLabel>
#include <QTimer>

class EnhancedUIFeatures : public QObject
{
    Q_OBJECT

public:
    enum AnimationType {
        FadeIn,
        FadeOut,
        SlideIn,
        SlideOut,
        Bounce
    };

    enum NotificationType {
        Info,
        Warning,
        Error,
        Success
    };

    explicit EnhancedUIFeatures(QObject *parent = nullptr);

    // Управление возможностями
    void setAutoCompleteEnabled(bool enabled) { m_autoCompleteEnabled = enabled; }
    void setShortcutsEnabled(bool enabled) { m_shortcutsEnabled = enabled; }
    void setAnimationsEnabled(bool enabled) { m_animationsEnabled = enabled; }
    void setThemesEnabled(bool enabled) { m_themesEnabled = enabled; }
    void setMentionSuggestionsEnabled(bool enabled) { m_mentionSuggestionsEnabled = enabled; }
    void setMessageFormattingEnabled(bool enabled) { m_messageFormattingEnabled = enabled; }
    void setDragAndDropEnabled(bool enabled) { m_dragAndDropEnabled = enabled; }
    void setTooltipsEnabled(bool enabled) { m_tooltipsEnabled = enabled; }
    void setStatusIndicatorsEnabled(bool enabled) { m_statusIndicatorsEnabled = enabled; }
    void setSearchAsITypeEnabled(bool enabled) { m_searchAsITypeEnabled = enabled; }
    void setAutoSaveDraftsEnabled(bool enabled) { m_autoSaveDraftsEnabled = enabled; }
    void setTypingIndicatorsEnabled(bool enabled) { m_typingIndicatorsEnabled = enabled; }

    bool isAutoCompleteEnabled() const { return m_autoCompleteEnabled; }
    bool isShortcutsEnabled() const { return m_shortcutsEnabled; }
    bool isAnimationsEnabled() const { return m_animationsEnabled; }
    bool isThemesEnabled() const { return m_themesEnabled; }
    bool isMentionSuggestionsEnabled() const { return m_mentionSuggestionsEnabled; }
    bool isMessageFormattingEnabled() const { return m_messageFormattingEnabled; }
    bool isDragAndDropEnabled() const { return m_dragAndDropEnabled; }
    bool isTooltipsEnabled() const { return m_tooltipsEnabled; }
    bool isStatusIndicatorsEnabled() const { return m_statusIndicatorsEnabled; }
    bool isSearchAsITypeEnabled() const { return m_searchAsITypeEnabled; }
    bool isAutoSaveDraftsEnabled() const { return m_autoSaveDraftsEnabled; }
    bool isTypingIndicatorsEnabled() const { return m_typingIndicatorsEnabled; }

    // Функции для работы с темами
    void applyTheme(const QString &themeName);
    QStringList getAvailableThemes() const { return m_builtinThemes.keys() + m_customThemes.keys(); }

    // Функции для автодополнения
    void enableAutoCompleteFor(QLineEdit *lineEdit);
    void enableAutoCompleteFor(QTextEdit *textEdit);

    // Функции для форматирования сообщений
    void applyBoldFormat();
    void applyItalicFormat();
    void applyUnderlineFormat();
    void applyStrikeThroughFormat() { /* реализация */ }
    void applyCodeFormat();
    void applyLinkFormat() { /* реализация */ }
    void applyQuoteFormat() { /* реализация */ }

    // Функции для анимаций
    void animateWidget(QWidget *widget, AnimationType type);
    void animateFadeIn(QWidget *widget);
    void animateFadeOut(QWidget *widget);
    void animateSlideIn(QWidget *widget);
    void animateSlideOut(QWidget *widget) { /* реализация */ }
    void animateBounce(QWidget *widget);

    // Функции для уведомлений
    void showNotification(const QString &title, const QString &message, NotificationType type = Info);

    // Функции для индикаторов статуса
    QIcon getStatusIcon(const QString &status) const { return m_statusIcons.value(status, QIcon()); }

    // Функции для поиска
    void setSearchCaseSensitive(bool sensitive) { m_searchCaseSensitive = sensitive; }

    // Функции для черновиков
    void saveDraft(const QString &chatId, const QString &text);
    QString loadDraft(const QString &chatId) const;

    // Функции для индикаторов набора текста
    void showTypingIndicator(const QString &userId, bool show = true);

signals:
    void themeChanged(const QString &themeName);
    void sendMessageRequested();
    void searchRequested();
    void emojiPanelRequested();
    void messageFormatted(const QString &formattedText);

private slots:
    void onSendMessageShortcut();
    void onSearchShortcut();
    void onEmojiPanelShortcut();

private:
    void initializeFeatures();
    void setupAutoComplete();
    void setupShortcuts();
    void setupAnimations();
    void setupThemes();
    void setupMentionSuggestions();
    void setupMessageFormatting();
    void setupDragAndDrop();
    void setupTooltips();
    void setupStatusIndicators();
    void setupSearchAsIType();
    void setupAutoSaveDrafts();
    void setupTypingIndicators();
    void loadCustomThemes();
    QStringList getCurrentChatUsers();
    QTextEdit *getCurrentTextEdit();
    void showMentionSuggestions(QTextEdit *textEdit, int position);

    // Настройки возможностей
    bool m_autoCompleteEnabled;
    bool m_shortcutsEnabled;
    bool m_animationsEnabled;
    bool m_themesEnabled;
    bool m_mentionSuggestionsEnabled;
    bool m_messageFormattingEnabled;
    bool m_dragAndDropEnabled;
    bool m_tooltipsEnabled;
    bool m_statusIndicatorsEnabled;
    bool m_searchAsITypeEnabled;
    bool m_autoSaveDraftsEnabled;
    bool m_typingIndicatorsEnabled;

    // Компоненты автодополнения
    QStringListModel *m_autoCompleteModel;
    QCompleter *m_autoCompleter;

    // Компоненты горячих клавиш
    QMap<QString, QShortcut*> m_shortcuts;

    // Параметры анимаций
    int m_animationDuration;
    QEasingCurve m_easingCurve;

    // Темы
    QMap<QString, QString> m_builtinThemes;
    QMap<QString, QString> m_customThemes;

    // Компоненты упоминаний
    QStringListModel *m_mentionModel;
    QCompleter *m_mentionCompleter;

    // Компоненты форматирования
    QMap<QString, QAction*> m_formattingActions;

    // Параметры Drag & Drop
    QSize m_dragPixmapSize;
    QColor m_dropIndicatorColor;
    QStringList m_acceptableMimeTypes;

    // Параметры всплывающих подсказок
    int m_tooltipDelay;
    int m_tooltipDuration;
    QString m_tooltipStyle;

    // Иконки статусов
    QMap<QString, QIcon> m_statusIcons;

    // Параметры поиска
    int m_searchDelay;
    int m_searchMinimumChars;
    bool m_searchCaseSensitive;

    // Параметры автосохранения
    int m_draftSaveInterval;
    int m_maxDrafts;
    QString m_draftsPath;

    // Параметры индикаторов набора текста
    int m_typingIndicatorTimeout;
    QString m_typingIndicatorStyle;
};

// EmojiPanel.h
class EmojiPanel : public QWidget
{
    Q_OBJECT

public:
    explicit EmojiPanel(QWidget *parent = nullptr);

    void showAt(const QPoint &pos);

signals:
    void emojiSelected(const QString &emoji);

private slots:
    void filterEmojis(const QString &filter);

private:
    void setupUI();
    void setupCategories();
    void populateCategory(const QString &category, QGridLayout *layout);
    void loadEmojis();
    void setupConnections();

    QGridLayout *m_gridLayout;
    QLineEdit *m_searchBox;
    QTabWidget *m_categoryTabs;
};

// MessageFormatter.h
class MessageFormatter : public QObject
{
    Q_OBJECT

public:
    explicit MessageFormatter(QObject *parent = nullptr);

    QString formatMessage(const QString &rawMessage);

    // Отдельные функции форматирования
    QString formatBold(const QString &text);
    QString formatItalic(const QString &text);
    QString formatCodeSpans(const QString &text);
    QString formatLinks(const QString &text);
    QString formatMentions(const QString &text);
    QString formatHashtags(const QString &text);
    QString formatStrikethrough(const QString &text);
    QString formatQuotes(const QString &text);
    QString formatCodeBlocks(const QString &text);

private:
    void initializePatterns();

    QMap<QString, QRegularExpression> m_patterns;
};

#endif // ENHANCED_UI_FEATURES_H
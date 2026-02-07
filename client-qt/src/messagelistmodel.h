#ifndef MESSAGELISTMODEL_H
#define MESSAGELISTMODEL_H

#include <QAbstractListModel>
#include <QDateTime>
#include <QList>
#include <QColor>

struct MessageItem {
    QString user;
    QString text;
    QDateTime timestamp;
    bool isOwn;
};

class MessageListModel : public QAbstractListModel
{
    Q_OBJECT

public:
    explicit MessageListModel(QObject *parent = nullptr);

    // Basic functionality:
    int rowCount(const QModelIndex &parent = QModelIndex()) const override;

    QVariant data(const QModelIndex &index, int role = Qt::DisplayRole) const override;
    bool setData(const QModelIndex &index, const QVariant &value, int role = Qt::EditRole) override;
    
    Qt::ItemFlags flags(const QModelIndex& index) const override;
    
    // Добавление сообщения
    void addMessage(const MessageItem &item);
    
    // Получение количества сообщений
    int messageCount() const { return messages.size(); }
    
    // Получение количества онлайн пользователей (условно)
    int onlineUsersCount() const { return 10; } // Заглушка

private:
    QList<MessageItem> messages;
};

#endif // MESSAGELISTMODEL_H
#include "messagelistmodel.h"
#include <QFont>
#include <QBrush>

MessageListModel::MessageListModel(QObject *parent)
    : QAbstractListModel(parent)
{
}

int MessageListModel::rowCount(const QModelIndex &parent) const
{
    // For list models only the root node (an invalid parent) should return the list's size. For all
    // other (valid) parents, rowCount() should return 0 so that it does not become a tree model.
    if (parent.isValid())
        return 0;

    return messages.size();
}

QVariant MessageListModel::data(const QModelIndex &index, int role) const
{
    if (!index.isValid() || index.row() >= messages.size())
        return QVariant();

    const MessageItem &item = messages[index.row()];
    
    switch (role) {
    case Qt::DisplayRole:
        return QString("[%1] %2: %3").arg(
            item.timestamp.toString("hh:mm:ss"),
            item.user,
            item.text
        );
    case Qt::ToolTipRole:
        return QString("От: %1\nВремя: %2\nСообщение: %3")
            .arg(item.user)
            .arg(item.timestamp.toString("dd.MM.yyyy hh:mm:ss"))
            .arg(item.text);
    case Qt::ForegroundRole:
        if (item.isOwn) {
            return QColor(0, 100, 0); // Темно-зеленый для своих сообщений
        } else {
            return QColor(0, 0, 0); // Черный для чужих сообщений
        }
    case Qt::FontRole: {
        QFont font;
        if (item.isOwn) {
            font.setItalic(true);
        }
        return font;
    }
    case Qt::UserRole:
        // Возвращаем структуру целиком для использования в делегате
        return QVariant::fromValue(item);
    default:
        return QVariant();
    }
}

bool MessageListModel::setData(const QModelIndex &index, const QVariant &value, int role)
{
    if (!index.isValid() || index.row() >= messages.size())
        return false;

    MessageItem &item = messages[index.row()];

    switch (role) {
    case Qt::EditRole:
    case Qt::DisplayRole: {
        QStringList parts = value.toString().split(": ");
        if (parts.size() >= 2) {
            item.user = parts[0];
            item.text = parts[1];
        } else {
            item.text = value.toString();
        }
        break;
    }
    case Qt::UserRole: {
        // Предполагаем, что value содержит MessageItem
        if (value.canConvert<MessageItem>()) {
            item = value.value<MessageItem>();
        }
        break;
    }
    default:
        return false;
    }

    emit dataChanged(index, index, QVector<int>() << role);
    return true;
}

Qt::ItemFlags MessageListModel::flags(const QModelIndex& index) const
{
    if (!index.isValid())
        return Qt::NoItemFlags;

    return Qt::ItemIsEnabled | Qt::ItemIsSelectable;
}

void MessageListModel::addMessage(const MessageItem &item)
{
    beginInsertRows(QModelIndex(), messages.size(), messages.size());
    messages.append(item);
    endInsertRows();
}
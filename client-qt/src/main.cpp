#include <QApplication>
#include <QLocale>
#include <QTranslator>
#include <QSslSocket>
#include "mainwindow.h"

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    
    // Установка информации о приложении
    app.setApplicationName("Messenger Client");
    app.setApplicationVersion("1.0.0");
    app.setOrganizationName("Messenger Project");
    
    // Проверка поддержки SSL
    if (!QSslSocket::supportsSsl()) {
        qWarning() << "SSL не поддерживается!";
    }
    
    // Установка перевода
    QTranslator translator;
    const QStringList uiLanguages = QLocale::system().uiLanguages();
    for (const QString &locale : uiLanguages) {
        const QString baseName = "en_US";
        if (translator.load(":/translations/" + baseName + ".qm")) {
            app.installTranslator(&translator);
            break;
        }
    }
    
    MainWindow w;
    w.show();
    
    return app.exec();
}
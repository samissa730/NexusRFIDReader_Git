# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'settings.ui'
##
## Created by: Qt User Interface Compiler version 6.9.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QSizePolicy,
    QVBoxLayout, QWidget)
import ui.pl_rc

class Ui_SettingsScreen(object):
    def setupUi(self, SettingsScreen):
        if not SettingsScreen.objectName():
            SettingsScreen.setObjectName(u"SettingsScreen")
        SettingsScreen.resize(800, 480)
        SettingsScreen.setMinimumSize(QSize(790, 420))
        SettingsScreen.setStyleSheet(u"")
        self.verticalLayout_20 = QVBoxLayout(SettingsScreen)
        self.verticalLayout_20.setSpacing(0)
        self.verticalLayout_20.setObjectName(u"verticalLayout_20")
        self.verticalLayout_20.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.horizontalLayout_13 = QHBoxLayout()
        self.horizontalLayout_13.setObjectName(u"horizontalLayout_13")
        self.label_24 = QLabel(SettingsScreen)
        self.label_24.setObjectName(u"label_24")
        font = QFont()
        font.setFamilies([u"Gilroy"])
        font.setPointSize(14)
        font.setBold(True)
        self.label_24.setFont(font)
        self.label_24.setStyleSheet(u"color: #ffffff;")
        self.label_24.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.horizontalLayout_13.addWidget(self.label_24)


        self.verticalLayout.addLayout(self.horizontalLayout_13)


        self.verticalLayout_20.addLayout(self.verticalLayout)


        self.retranslateUi(SettingsScreen)

        QMetaObject.connectSlotsByName(SettingsScreen)
    # setupUi

    def retranslateUi(self, SettingsScreen):
        SettingsScreen.setWindowTitle(QCoreApplication.translate("SettingsScreen", u"Settings", None))
        self.label_24.setText(QCoreApplication.translate("SettingsScreen", u"Settings", None))
    # retranslateUi


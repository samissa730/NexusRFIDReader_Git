import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit
from screens.base import BaseScreen
from ui.screens.ui_settings import Ui_SettingsScreen


class SettingsScreen(BaseScreen):

    sig_result = Signal(bool)

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.ui = Ui_SettingsScreen()
        self.ui.setupUi(self)

import threading
import time
from functools import partial

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QLineEdit
from utils.common import get_serial
from screens.base import BaseScreen
from ui.screens.ui_overview import Ui_OverviewScreen
from utils.logger import logger


class OverviewScreen(BaseScreen):
    sig_data = Signal(list)

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.ui = Ui_OverviewScreen()
        self.ui.setupUi(self)
        self.ui.device_id.setText(get_serial())
        logger.info("Overview initialized successfully")

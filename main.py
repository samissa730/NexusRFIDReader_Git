import sys
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile

if __name__ == "__main__":
    app = QApplication(sys.argv)

    loader = QUiLoader()
    ui_file = QFile("ui/main.ui")
    ui_file.open(QFile.ReadOnly)
    window = loader.load(ui_file)
    ui_file.close()

    window.show()
    sys.exit(app.exec())


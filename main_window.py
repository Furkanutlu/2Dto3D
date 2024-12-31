from PyQt5.QtWidgets import QMainWindow, QStackedWidget
from cube_3d_widget import Cube3DWidget
from entry_screen import EntryScreen
from main_screen import MainScreen

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Görüntüleme")
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.entry_screen = EntryScreen(self)
        self.cube_widget = Cube3DWidget()
        self.main_screen = MainScreen(self, self.cube_widget)
        self.stack.addWidget(self.entry_screen)
        self.stack.addWidget(self.main_screen)
        self.stack.setCurrentIndex(0)
        self.resize(800, 600)

    def go_entry_screen(self):
        self.stack.setCurrentIndex(0)

    def go_main_screen(self):
        self.stack.setCurrentIndex(1)
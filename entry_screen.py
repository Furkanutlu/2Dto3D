from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QToolButton, QWidget,
    QPushButton, QFileDialog, QColorDialog, QStackedWidget, QDialog, QLabel,
    QComboBox, QDialogButtonBox
)
from PyQt5.QtGui import QIcon, QColor
from PyQt5.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt5.QtOpenGL import QGLWidget
from OpenGL.GL import *
from OpenGL.GLU import gluPerspective, gluNewQuadric, gluCylinder

import sys
import numpy as np
import os

class EntryScreen(QWidget):

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        # Load icons only if they exist to prevent errors
        cube_icon_path = "Images/3d-cube.png"
        upload_icon_path = "Images/upload.png"

        cube_icon = QIcon(cube_icon_path) if os.path.exists(cube_icon_path) else QIcon.fromTheme("cube")
        upload_icon = QIcon(upload_icon_path) if os.path.exists(upload_icon_path) else QIcon.fromTheme("document-open")

        self.cube_button = QPushButton("Küp Göster")
        self.cube_button.setIcon(cube_icon)
        self.cube_button.clicked.connect(self.show_cube)

        self.upload_button = QPushButton("OBJ Yükle")
        self.upload_button.setIcon(upload_icon)
        self.upload_button.clicked.connect(self.upload_obj)

        layout.addWidget(self.cube_button)
        layout.addWidget(self.upload_button)
        self.setLayout(layout)

    def show_cube(self):
        self.main_window.cube_widget.add_cube()
        self.main_window.go_main_screen()

    def upload_obj(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "OBJ Dosyası Seç", "", "OBJ Files (*.obj)")
        if file_name:
            self.main_window.cube_widget.clear_scene()
            self.main_window.cube_widget.load_obj(file_name)
            self.main_window.go_main_screen()

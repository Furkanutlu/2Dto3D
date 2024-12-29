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
class AddObjectDialog(QDialog):
    """
    Dialog to select the type of object to add or to load a custom OBJ file.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Object")
        self.setModal(True)
        self.selected_option = None
        self.obj_file_path = None

        layout = QVBoxLayout()

        # Dropdown to select object type
        self.combo = QComboBox()
        self.combo.addItems(["Cube", "Load OBJ"])
        layout.addWidget(QLabel("Select Object Type:"))
        layout.addWidget(self.combo)

        # Button to browse OBJ files, initially hidden
        self.browse_button = QPushButton("Browse OBJ File")
        self.browse_button.clicked.connect(self.browse_obj_file)
        self.browse_button.setVisible(False)
        layout.addWidget(self.browse_button)

        # Connect the dropdown selection to show/hide browse button
        self.combo.currentTextChanged.connect(self.on_selection_change)

        # OK and Cancel buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def on_selection_change(self, text):
        if text == "Load OBJ":
            self.browse_button.setVisible(True)
        else:
            self.browse_button.setVisible(False)

    def browse_obj_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select OBJ File", "", "OBJ Files (*.obj)")
        if file_name:
            self.obj_file_path = file_name

    def get_selection(self):
        return self.combo.currentText(), self.obj_file_path
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
from add_object_dialog import AddObjectDialog

import sys
import numpy as np
import os
from repeat_button import RepeatButton

class MainScreen(QWidget):
    def __init__(self, main_window, cube_widget):
        super().__init__()
        self.main_window = main_window
        self.cube_widget = cube_widget

        self.active_style = """
            QToolButton {
                background-color: #b0c4de;
                border: 1px solid #666;
                border-radius: 5px;
                margin: 5px;
                padding: 10px;
            }
            QToolButton:hover {
                background-color: #a0b4ce;
            }
        """
        self.inactive_style = """
            QToolButton {
                background-color: #ffffff;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin: 5px;
                padding: 10px;
            }
            QToolButton:hover {
                background-color: #e0e0e0;
            }
        """

        self.tool_buttons = {}
        self.tool_bar = QWidget()
        self.tool_bar_layout = QVBoxLayout(self.tool_bar)
        self.tool_bar.setFixedWidth(100)
        self.tool_bar.setStyleSheet("background-color: #f0f0f0; border-right: 1px solid #ccc;")

        # Icons list
        icons = [
            {"icon": "Images/cursor.png", "tooltip": "Cursor"},
            {"icon": "Images/circle-of-two-clockwise-arrows-rotation.png", "tooltip": "Rotate"},
            {"icon": "Images/expand-arrows.png", "tooltip": "Move"},
            {"icon": "Images/resize.png", "tooltip": "resize"},  # "resize" butonunu geri ekledik
            {"icon": "Images/transparency.png", "tooltip": "Transparency"},  # Yeni Transparency butonu
            {"icon": "Images/color-wheel.png", "tooltip": "Background Color"},
            {"icon": "Images/scissors.png", "tooltip": "Cut"},
            {"icon": "Images/delete.png", "tooltip": "Objeyi Sil"},  # Delete button
            {"icon": "Images/back.png", "tooltip": "Undo"},
            {"icon": "Images/redo-arrow.png", "tooltip": "Redo"},
            {"icon": "Images/add-object.png", "tooltip": "Add Object"},  # Add Object button
            {"icon": "Images/home.png", "tooltip": "Giriş Ekranına Dön"}
        ]

        for item in icons:
            icon_path = item["icon"]
            tooltip = item["tooltip"]
            if tooltip in ["Undo", "Redo"]:
                # Use RepeatButton for Undo and Redo
                button = RepeatButton(initial_interval=500, min_interval=100, acceleration=0.8)
                if os.path.exists(icon_path):
                    button.setIcon(QIcon(icon_path))
                else:
                    # Fallback to a default icon if not found
                    default_icon = QIcon.fromTheme("edit-undo") if tooltip == "Undo" else QIcon.fromTheme("edit-redo")
                    button.setIcon(default_icon)
                button.setToolTip(tooltip)
                button.setStyleSheet(self.inactive_style)
                if tooltip == "Undo":
                    button.repeat_signal.connect(self.cube_widget.undo)
                elif tooltip == "Redo":
                    button.repeat_signal.connect(self.cube_widget.redo)
            else:
                # Use regular QToolButton for other tools
                button = QToolButton()
                if os.path.exists(icon_path):
                    button.setIcon(QIcon(icon_path))
                else:
                    # Fallback to a default icon based on tooltip
                    if tooltip == "Cursor":
                        default_icon = QIcon.fromTheme("cursor-arrow")
                    elif tooltip == "Rotate":
                        default_icon = QIcon.fromTheme("object-rotate-right")
                    elif tooltip == "Move":
                        default_icon = QIcon.fromTheme("transform-move")
                    elif tooltip == "resize":
                        default_icon = QIcon.fromTheme("transform-scale")  # Ölçeklendirme için uygun bir tema ikonu
                    elif tooltip == "Transparency":
                        default_icon = QIcon.fromTheme("view-transparency")  # Transparency için uygun bir tema ikonu
                    elif tooltip == "Background Color":
                        default_icon = QIcon.fromTheme("color-picker")
                    elif tooltip == "Cut":
                        default_icon = QIcon.fromTheme("edit-cut")
                    elif tooltip == "Objeyi Sil":
                        default_icon = QIcon.fromTheme("edit-delete")
                    elif tooltip == "Add Object":
                        default_icon = QIcon.fromTheme("list-add")
                    elif tooltip == "Giriş Ekranına Dön":
                        default_icon = QIcon.fromTheme("go-home")
                    else:
                        default_icon = QIcon()
                    button.setIcon(default_icon)
                button.setToolTip(tooltip)
                button.setStyleSheet(self.inactive_style)
                if tooltip in ["Cursor", "Rotate", "Move", "resize", "Cut", "Transparency"]:
                    button.clicked.connect(lambda checked, tool=tooltip: self.activate_tool(tool))
                elif tooltip == "Background Color":
                    button.clicked.connect(self.cube_widget.set_background_color)
                elif tooltip == "Add Object":
                    button.clicked.connect(self.add_object)
                elif tooltip == "Giriş Ekranına Dön":
                    button.clicked.connect(self.main_window.go_entry_screen)
                elif tooltip == "Objeyi Sil":
                    button.clicked.connect(self.cube_widget.delete_selected_object)

            self.tool_buttons[tooltip] = button
            self.tool_bar_layout.addWidget(button)

        self.tool_bar_layout.addStretch()  # Push buttons to the top

        main_layout = QHBoxLayout(self)
        main_layout.addWidget(self.tool_bar)
        main_layout.addWidget(self.cube_widget)
        self.setLayout(main_layout)

    def activate_tool(self, tool):
        # Update button styles
        for ttip, btn in self.tool_buttons.items():
            if ttip in ["Cursor", "Rotate", "Move", "resize", "Cut", "Transparency"]:
                if ttip == tool:
                    btn.setStyleSheet(self.active_style)
                else:
                    btn.setStyleSheet(self.inactive_style)

        # Set the transformation mode
        if tool == "Cursor":
            self.cube_widget.set_mode(None)
        elif tool == "Rotate":
            self.cube_widget.set_mode("rotate")
        elif tool == "Move":
            self.cube_widget.set_mode("move")
        elif tool == "resize":
            self.cube_widget.set_mode("resize")  # "resize" modunu ayarla
        elif tool == "Cut":
            self.cube_widget.set_mode("cut")
        elif tool == "Transparency":
            self.cube_widget.set_mode("transparency")  # Yeni "transparency" modunu ayarla

    def add_object(self):
        """
        Open the AddObjectDialog to allow users to add a Cube or load an OBJ file.
        """
        dialog = AddObjectDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            selected_type, obj_file = dialog.get_selection()
            if selected_type == "Cube":
                self.cube_widget.add_cube()
            elif selected_type == "Load OBJ" and obj_file:
                self.cube_widget.load_obj(obj_file)
            self.main_window.go_main_screen()
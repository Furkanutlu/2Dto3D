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

class RepeatButton(QToolButton):
    """
    A QToolButton subclass that emits a signal repeatedly while pressed,
    with acceleration over time.
    """
    repeat_signal = pyqtSignal()

    def __init__(self, parent=None, initial_interval=500, min_interval=50, acceleration=0.9):
        super().__init__(parent)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.emit_repeat)
        self.initial_interval = initial_interval  # Initial delay in ms
        self.min_interval = min_interval          # Minimum interval in ms
        self.acceleration = acceleration          # Factor to decrease interval
        self.current_interval = initial_interval

    def emit_repeat(self):
        self.repeat_signal.emit()
        # Calculate the next interval with acceleration
        self.current_interval = max(int(self.current_interval * self.acceleration), self.min_interval)
        self.timer.setInterval(self.current_interval)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.repeat_signal.emit()  # Emit immediately on press
            self.current_interval = self.initial_interval
            self.timer.start(self.current_interval)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.timer.stop()
        super().mouseReleaseEvent(event)
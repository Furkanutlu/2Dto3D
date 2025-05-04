from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton
from PyQt5.QtCore import pyqtSignal

class LoadingDialog(QDialog):
    cancel_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Yükleniyor')
        self.setModal(True)
        layout = QVBoxLayout()
        self.label = QLabel('3D model oluşturuluyor, lütfen bekleyin.')
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.cancel_btn = QPushButton('İptal')
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        layout.addWidget(self.label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.cancel_btn)
        self.setLayout(layout)

    def update_progress(self, value):
        self.progress_bar.setValue(value)

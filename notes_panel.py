from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QSizePolicy
from PyQt5.QtCore import Qt


class NotesPanel(QWidget):
    """Kullanıcı serbest metin notları tutulur (proje genelinde)."""
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedWidth(180)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self.title = QLabel("▾ Notlar")
        self.title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title.setStyleSheet("background:#dddddd;font-weight:bold;")
        self.title.mousePressEvent = self._toggle

        self.text = QTextEdit()
        self.text.setPlaceholderText("Proje ile ilgili notlarınızı yazın…")

        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.title); lay.addWidget(self.text)

        self._collapsed = False

    # ——————————————————————————————
    def _toggle(self, *_):
        self._collapsed = not self._collapsed
        self.text.setVisible(not self._collapsed)
        self.title.setText(("▾ " if not self._collapsed else "▸ ") + "Notlar")

        if self._collapsed:
            self.setMaximumHeight(self.title.sizeHint().height())
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        else:
            self.setMaximumHeight(16777215)
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self.parent().updateGeometry()
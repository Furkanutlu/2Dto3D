from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QComboBox, QLabel, QPushButton,
    QFileDialog, QDialogButtonBox
)
class AddObjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Object")
        self.setModal(True)
        self.obj_file_path = None

        layout = QVBoxLayout()
        self.combo = QComboBox()
        self.combo.addItems(["Load OBJ"])          # sadece OBJ yükleme
        layout.addWidget(QLabel("Select Object Type:"))
        layout.addWidget(self.combo)

        self.browse_button = QPushButton("Browse OBJ File")
        self.browse_button.clicked.connect(self.browse_obj_file)
        layout.addWidget(self.browse_button)       # daima görünür

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def browse_obj_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select OBJ File", "", "OBJ Files (*.obj)")
        if file_name:
            self.obj_file_path = file_name

    def get_selection(self):
        # Seçim artık daima "Load OBJ"
        return "Load OBJ", self.obj_file_path
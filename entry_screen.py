from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QFileDialog, QLabel, QDialog,
    QLineEdit, QDialogButtonBox, QComboBox, QSpinBox, QDoubleSpinBox,
    QHBoxLayout, QMessageBox
)
from PyQt5.QtGui import QPixmap, QFont, QIcon
from PyQt5.QtCore import Qt, QSize
import os
import cv2
import numpy as np

from loading_dialog import LoadingDialog
from model_generation_worker import ModelGenerationWorker


class EntryScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("3D Modelleme Uygulamasına Hoş Geldiniz")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)

        logo = QLabel()
        logo.setPixmap(QPixmap("Icons/main_image.png").scaled(200, 200, Qt.KeepAspectRatio))
        logo.setAlignment(Qt.AlignCenter)

        btn_font = QFont("Arial", 14, QFont.Bold)
        icon_size = QSize(64, 64)

        self.upload_button = QPushButton("OBJ Yükle")
        self.upload_button.setFont(btn_font)
        self.upload_button.setIconSize(icon_size)
        self.upload_button.setIcon(QIcon("Icons/upload.png"))
        self.upload_button.clicked.connect(self.upload_obj)

        self.create_button = QPushButton("Obje Oluştur")
        self.create_button.setFont(btn_font)
        self.create_button.setIconSize(icon_size)
        self.create_button.setIcon(QIcon("Icons/create.png"))
        self.create_button.clicked.connect(self.create_obj)

        layout.addWidget(title)
        layout.addWidget(logo)
        layout.addWidget(self.upload_button)
        layout.addWidget(self.create_button)
        self.setLayout(layout)

    # --------------------------------------------------------- OBJ yükleme
    def upload_obj(self):
        fn, _ = QFileDialog.getOpenFileName(self, "OBJ Dosyası Seç", "", "OBJ Files (*.obj)")
        if fn:
            self.main_window.cube_widget.clear_scene()
            self.main_window.cube_widget.load_obj(fn)
            self.main_window.go_main_screen()

    # --------------------------------------------------------- OBJ oluşturma
    def create_obj(self):
        dlg = ObjCreationDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return

        folder = dlg.get_slice_folder()
        name   = dlg.get_output_name().strip()
        if not folder or not name:
            QMessageBox.warning(self, "Eksik Bilgi", "Klasör ve dosya adı boş olamaz.")
            return

        output_path = os.path.join(folder, f"{name}.obj")
        if os.path.exists(output_path):
            QMessageBox.warning(self, "Dosya Zaten Var",
                                f"'{name}.obj' adlı bir model zaten mevcut.\n"
                                "Lütfen farklı bir isim girin.")
            return

        self.start_loading_screen(
            slice_folder = folder,
            output_path  = output_path,
            noise_method = dlg.get_noise_reduction_method(),
            scale_factor = dlg.get_scale_factor(),
            z_increment  = dlg.get_z_increment(),
            threshold    = dlg.get_threshold(),
            resolution   = dlg.get_resolution()
        )

    # --------------------------------------------------------- İş parçacığını başlat
    def start_loading_screen(self, slice_folder, output_path, noise_method,
                             scale_factor, z_increment, threshold, resolution):
        self.loading_dialog = LoadingDialog(self)
        self.worker = ModelGenerationWorker(
            slice_folder, output_path,
            scale_factor=scale_factor,
            z_increment=z_increment,
            threshold=threshold,
            resolution=resolution,
            noise_method=noise_method
        )
        self.worker.progress_signal.connect(self.loading_dialog.update_progress)
        self.worker.finished_signal.connect(self.on_generation_finished)
        self.loading_dialog.cancel_requested.connect(self.worker.stop)
        self.loading_dialog.cancel_requested.connect(self.loading_dialog.close)
        self.worker.start()
        self.loading_dialog.exec_()

    # --------------------------------------------------------- Tamamlandığında
    def on_generation_finished(self, output_path: str):
        self.loading_dialog.close()
        if output_path:
            QMessageBox.information(self, "İşlem Tamamlandı",
                                    f"‘{os.path.basename(output_path)}’ modeli başarıyla oluşturuldu.")
        else:
            QMessageBox.warning(self, "İşlem İptal",
                                "Model oluşturulamadı veya işlem iptal edildi.")

# ==================================================================== DİYALOG
class ObjCreationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Obje Oluştur")
        self.slice_folder = None

        vbox = QVBoxLayout(self)

        # --- klasör seçimi
        self.slice_label = QLabel("Dilim klasörünü seçin:")
        self.browse_btn  = QPushButton("Göz At")
        self.browse_btn.clicked.connect(self.browse_folder)
        vbox.addWidget(self.slice_label)
        vbox.addWidget(self.browse_btn)

        # --- dosya adı
        self.name_label = QLabel("Oluşturulacak OBJ dosyası adı:")
        self.name_edit  = QLineEdit()
        vbox.addWidget(self.name_label)
        vbox.addWidget(self.name_edit)

        # --- gürültü azaltma
        self.noise_combo = QComboBox()
        self.noise_combo.addItems(["Yok", "Medyan Blur", "Gauss Blur", "Bilateral"])
        vbox.addWidget(QLabel("Gürültü Azaltma:"))
        vbox.addWidget(self.noise_combo)

        # --- scale & z‐increment
        self.scale_spin = QDoubleSpinBox(); self.scale_spin.setRange(0.001, 10); self.scale_spin.setValue(0.1); self.scale_spin.setDecimals(3)
        self.zinc_spin  = QDoubleSpinBox(); self.zinc_spin .setRange(0.001, 10); self.zinc_spin .setValue(0.1); self.zinc_spin .setDecimals(3)
        vbox.addWidget(QLabel("Scale Factor:"));       vbox.addWidget(self.scale_spin)
        vbox.addWidget(QLabel("Z Increment:"));        vbox.addWidget(self.zinc_spin)

        # --- threshold
        self.th_spin = QSpinBox(); self.th_spin.setRange(0, 255); self.th_spin.setValue(100)
        vbox.addWidget(QLabel("Threshold (0-255):")); vbox.addWidget(self.th_spin)

        # --- çözünürlük
        res_row = QHBoxLayout()
        self.res_w = QSpinBox(); self.res_w.setRange(4, 4096); self.res_w.setValue(256)
        self.res_h = QSpinBox(); self.res_h.setRange(4, 4096); self.res_h.setValue(256)
        res_row.addWidget(self.res_w); res_row.addWidget(QLabel("x")); res_row.addWidget(self.res_h)
        vbox.addWidget(QLabel("Yeniden Ölçekleme (WxH):")); vbox.addLayout(res_row)

        # --- OK / Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        vbox.addWidget(buttons)

    # ----------------------------------------------------- klasör seç
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Dilim Klasörü Seç")
        if not folder:
            return
        png_files = [f for f in os.listdir(folder) if f.lower().endswith(".png")]
        pixels = []
        for fn in png_files:
            g = cv2.imread(os.path.join(folder, fn), cv2.IMREAD_GRAYSCALE)
            if g is not None:
                g = cv2.resize(g, (self.res_w.value(), self.res_h.value()), interpolation=cv2.INTER_AREA)
                pixels.append(g.flatten())
        if pixels:
            flat = np.concatenate(pixels, dtype=np.uint8)
            thr, _ = cv2.threshold(flat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            self.th_spin.setValue(int(thr))
            self.slice_label.setText(f"Klasör: {folder}  (Otsu={int(thr)})")
        else:
            self.slice_label.setText(f"Klasör: {folder}")
        self.slice_folder = folder

    # ----------------------------- getter yardımcıları
    def get_slice_folder(self):          return self.slice_folder
    def get_output_name(self):           return self.name_edit.text()
    def get_noise_reduction_method(self):return self.noise_combo.currentText()
    def get_scale_factor(self):          return self.scale_spin.value()
    def get_z_increment(self):           return self.zinc_spin.value()
    def get_threshold(self):             return self.th_spin.value()
    def get_resolution(self):            return (self.res_w.value(), self.res_h.value())

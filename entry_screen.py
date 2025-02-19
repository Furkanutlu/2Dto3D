from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QFileDialog, QLabel, QProgressBar,
    QDialog, QLineEdit, QDialogButtonBox, QComboBox, QSpinBox, QDoubleSpinBox,
    QHBoxLayout
)
from PyQt5.QtGui import QPixmap, QFont, QIcon
from PyQt5.QtCore import Qt, QSize, QThread, pyqtSignal
import os
import numpy as np
import open3d as o3d
import cv2
from skimage import measure

class EntryScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        font = QFont("Arial", 14, QFont.Bold)
        icon_size = 64
        self.cube_button = QPushButton("Küp Göster")
        self.cube_button.setFont(font)
        self.cube_button.setIconSize(QSize(icon_size, icon_size))
        self.cube_button.setIcon(QIcon("Icons/cube.png"))
        self.cube_button.clicked.connect(self.show_cube)
        self.upload_button = QPushButton("OBJ Yükle")
        self.upload_button.setFont(font)
        self.upload_button.setIconSize(QSize(icon_size, icon_size))
        self.upload_button.setIcon(QIcon("Icons/upload.png"))
        self.upload_button.clicked.connect(self.upload_obj)
        self.create_obj_button = QPushButton("Obje Oluştur")
        self.create_obj_button.setFont(font)
        self.create_obj_button.setIconSize(QSize(icon_size, icon_size))
        self.create_obj_button.setIcon(QIcon("Icons/create.png"))
        self.create_obj_button.clicked.connect(self.create_obj)
        self.title_label = QLabel("3D Modelleme Uygulamasına Hoş Geldiniz")
        self.title_label.setFont(QFont("Arial", 18, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.image_label = QLabel()
        pixmap = QPixmap("Icons/main_image.png")
        pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio)
        self.image_label.setPixmap(pixmap)
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)
        layout.addWidget(self.image_label)
        layout.addWidget(self.cube_button)
        layout.addWidget(self.upload_button)
        layout.addWidget(self.create_obj_button)
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

    def create_obj(self):
        dialog = ObjCreationDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            slice_folder = dialog.get_slice_folder()
            output_name = dialog.get_output_name()
            noise_method = dialog.get_noise_reduction_method()
            scale_factor = dialog.get_scale_factor()
            z_inc = dialog.get_z_increment()
            threshold = dialog.get_threshold()
            resolution = dialog.get_resolution()
            if slice_folder and output_name:
                output_path = os.path.join(slice_folder, f"{output_name}.obj")
                self.start_loading_screen(slice_folder, output_path, noise_method, scale_factor, z_inc, threshold, resolution)

    def start_loading_screen(self, slice_folder, output_path, noise_method, scale_factor, z_increment, threshold, resolution):
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
        self.worker.finished_signal.connect(self.on_model_generation_finished)
        self.worker.start()
        self.loading_dialog.exec_()

    def on_model_generation_finished(self, output_path):
        self.loading_dialog.close()
        print(f"3D model başarıyla kaydedildi: {output_path}")

class ObjCreationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Obje Oluştur")
        self.setModal(True)
        self.slice_folder = None
        self.output_name = None
        layout = QVBoxLayout()
        self.slice_label = QLabel("Dilimlerin olduğu klasörü seçin:")
        self.browse_button = QPushButton("Gözat")
        self.browse_button.clicked.connect(self.browse_folder)
        layout.addWidget(self.slice_label)
        layout.addWidget(self.browse_button)
        self.name_label = QLabel("Oluşturulacak OBJ dosyasının adı:")
        self.name_input = QLineEdit()
        layout.addWidget(self.name_label)
        layout.addWidget(self.name_input)
        self.noise_label = QLabel("Gürültü Azaltma Yöntemi:")
        self.noise_combo = QComboBox()
        self.noise_combo.addItems(["Yok", "Medyan Bulanıklaştırma", "Gauss Bulanıklaştırma", "Bilateral Filtre"])
        layout.addWidget(self.noise_label)
        layout.addWidget(self.noise_combo)
        self.scale_label = QLabel("Ölçek Faktörü (scale_factor):")
        self.scale_input = QDoubleSpinBox()
        self.scale_input.setValue(0.1)
        self.scale_input.setDecimals(3)
        self.scale_input.setSingleStep(0.1)
        layout.addWidget(self.scale_label)
        layout.addWidget(self.scale_input)
        self.zinc_label = QLabel("Dilimler arası mesafe (z_increment):")
        self.zinc_input = QDoubleSpinBox()
        self.zinc_input.setValue(0.1)
        self.zinc_input.setDecimals(3)
        self.zinc_input.setSingleStep(0.1)
        layout.addWidget(self.zinc_label)
        layout.addWidget(self.zinc_input)
        self.th_label = QLabel("Eşik Değeri (threshold 0-255):")
        self.th_input = QSpinBox()
        self.th_input.setRange(0, 255)
        self.th_input.setValue(100)
        layout.addWidget(self.th_label)
        layout.addWidget(self.th_input)
        self.res_label = QLabel("Görüntü Çözünürlüğü (Genişlik x Yükseklik):")
        res_layout = QHBoxLayout()
        self.res_w_input = QSpinBox()
        self.res_h_input = QSpinBox()
        self.res_w_input.setRange(1, 2048)
        self.res_h_input.setRange(1, 2048)
        self.res_w_input.setValue(256)
        self.res_h_input.setValue(256)
        res_layout.addWidget(self.res_w_input)
        res_layout.addWidget(QLabel("x"))
        res_layout.addWidget(self.res_h_input)
        layout.addWidget(self.res_label)
        layout.addLayout(res_layout)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Dilim Klasörünü Seç")
        if folder:
            self.slice_folder = folder
            self.slice_label.setText(f"Klasör: {folder}")

    def get_slice_folder(self):
        return self.slice_folder

    def get_output_name(self):
        return self.name_input.text()

    def get_noise_reduction_method(self):
        return self.noise_combo.currentText()

    def get_scale_factor(self):
        return float(self.scale_input.value())

    def get_z_increment(self):
        return float(self.zinc_input.value())

    def get_threshold(self):
        return int(self.th_input.value())

    def get_resolution(self):
        return (self.res_w_input.value(), self.res_h_input.value())

class LoadingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Yükleniyor")
        self.setModal(True)
        layout = QVBoxLayout()
        self.label = QLabel("3D model oluşturuluyor, lütfen bekleyin...")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.label)
        layout.addWidget(self.progress_bar)
        self.setLayout(layout)

    def update_progress(self, value):
        self.progress_bar.setValue(value)

class ModelGenerationWorker(QThread):
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(str)

    def __init__(
        self, slice_folder, output_path,
        scale_factor=0.1, z_increment=0.1, threshold=100, resolution=(256, 256),
        noise_method="Yok"
    ):
        super().__init__()
        self.slice_folder = slice_folder
        self.output_path = output_path
        self.scale_factor = scale_factor
        self.z_increment = z_increment
        self.threshold = threshold
        self.resolution = resolution
        self.noise_method = noise_method

    def run(self):
        try:
            slice_files = sorted(os.listdir(self.slice_folder))
            slices = []
            total_steps = len(slice_files) + 1
            step = 0
            for slice_file in slice_files:
                if slice_file.lower().endswith(".png"):
                    img_path = os.path.join(self.slice_folder, slice_file)
                    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                    if img is None:
                        continue
                    if self.noise_method == "Medyan Bulanıklaştırma":
                        img = cv2.medianBlur(img, 3)
                    elif self.noise_method == "Gauss Bulanıklaştırma":
                        img = cv2.GaussianBlur(img, (3, 3), 0)
                    elif self.noise_method == "Bilateral Filtre":
                        img = cv2.bilateralFilter(img, 5, 75, 75)
                    img = cv2.resize(img, self.resolution)
                    slices.append(img)
                    step += 1
                    progress = int(step / total_steps * 100)
                    self.progress_signal.emit(progress)
            volume = np.stack(slices, axis=-1).astype(np.float32)
            volume /= 255.0
            level = self.threshold / 255.0
            verts, faces, normals, values = measure.marching_cubes(volume, level=level)
            with open(self.output_path, "w") as f:
                for v in verts:
                    x = v[0] * self.scale_factor
                    y = v[1] * self.scale_factor
                    z = v[2] * self.z_increment
                    f.write(f"v {x} {y} {z}\n")
                for face in faces:
                    f1, f2, f3 = face + 1
                    f.write(f"f {f1} {f2} {f3}\n")
            self.progress_signal.emit(100)
            self.finished_signal.emit(self.output_path)
        except Exception as e:
            print(f"HATA: {e}")
            self.finished_signal.emit("")

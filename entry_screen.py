from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QFileDialog, QLabel, QProgressBar, QDialog, QLineEdit, QDialogButtonBox
)
from PyQt5.QtGui import QPixmap, QFont, QIcon
from PyQt5.QtCore import Qt, QSize, QThread, pyqtSignal
import os
import numpy as np
import open3d as o3d
import cv2
from skimage import measure
from skimage.measure import marching_cubes

class EntryScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        # Yazı ve ikon boyutları
        font = QFont("Arial", 14, QFont.Bold)
        icon_size = 64  # px

        # Küp Göster Butonu
        self.cube_button = QPushButton("Küp Göster")
        self.cube_button.setFont(font)
        self.cube_button.setIconSize(QSize(icon_size, icon_size))
        self.cube_button.setIcon(QIcon("Icons/cube.png"))  # Doğru bir ikon yolu belirtin
        self.cube_button.clicked.connect(self.show_cube)

        # OBJ Yükle Butonu
        self.upload_button = QPushButton("OBJ Yükle")
        self.upload_button.setFont(font)
        self.upload_button.setIconSize(QSize(icon_size, icon_size))
        self.upload_button.setIcon(QIcon("Icons/upload.png"))  # Doğru bir ikon yolu belirtin
        self.upload_button.clicked.connect(self.upload_obj)

        # Obje Oluştur Butonu
        self.create_obj_button = QPushButton("Obje Oluştur")
        self.create_obj_button.setFont(font)
        self.create_obj_button.setIconSize(QSize(icon_size, icon_size))
        self.create_obj_button.setIcon(QIcon("Icons/create.png"))  # Doğru bir ikon yolu belirtin
        self.create_obj_button.clicked.connect(self.create_obj)

        # Giriş ekranı başlığı
        self.title_label = QLabel("3D Modelleme Uygulamasına Hoş Geldiniz")
        self.title_label.setFont(QFont("Arial", 18, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)

        # Resim ekleme
        self.image_label = QLabel()
        pixmap = QPixmap("Icons/main_image.png")  # Ana ekran görseli
        pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio)  # Görseli yeniden boyutlandır
        self.image_label.setPixmap(pixmap)
        self.image_label.setAlignment(Qt.AlignCenter)

        # Layout'a bileşenleri ekle
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

            if slice_folder and output_name:
                output_path = os.path.join(slice_folder, f"{output_name}.obj")
                self.start_loading_screen(slice_folder, output_path)

    def start_loading_screen(self, slice_folder, output_path):
        # Yükleniyor ekranını başlat
        self.loading_dialog = LoadingDialog(self)
        self.worker = ModelGenerationWorker(slice_folder, output_path)

        # İşçi sinyalleri
        self.worker.progress_signal.connect(self.loading_dialog.update_progress)
        self.worker.finished_signal.connect(self.on_model_generation_finished)

        # Loading ekranını göster ve işlemi başlat
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

        # Dilim klasörü seçimi
        self.slice_label = QLabel("Dilimlerin olduğu klasörü seçin:")
        self.browse_button = QPushButton("Gözat")
        self.browse_button.clicked.connect(self.browse_folder)
        layout.addWidget(self.slice_label)
        layout.addWidget(self.browse_button)

        # Çıktı dosya adı girişi
        self.name_label = QLabel("Oluşturulacak OBJ dosyasının adı:")
        self.name_input = QLineEdit()
        layout.addWidget(self.name_label)
        layout.addWidget(self.name_input)

        # Onay ve İptal butonları
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

    def __init__(self, slice_folder, output_path, scale_factor=0.001, z_increment=0.5, threshold=150, resolution=(16, 16)):
        super().__init__()
        self.slice_folder = slice_folder
        self.output_path = output_path
        self.scale_factor = scale_factor
        self.z_increment = z_increment
        self.threshold = threshold
        self.resolution = resolution

    def run(self):
        try:
            slice_files = sorted(os.listdir(self.slice_folder))
            print(f"Tespit edilen dilimler: {slice_files}")

            slices = []
            total_steps = len(slice_files) + 1  # Resim yükleme + marching cubes
            step = 0

            for slice_file in slice_files:
                img_path = os.path.join(self.slice_folder, slice_file)
                print(f"Dilim işleniyor: {img_path}")

                img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                if img is None:
                    print(f"HATA: Resim yüklenemedi: {img_path}")
                    continue

                img = cv2.resize(img, self.resolution)  # Çözünürlüğü artır
                slices.append(img)

                step += 1
                progress = int(step / total_steps * 100)
                self.progress_signal.emit(progress)

            # Hacimsel veri oluştur ve normalize et
            volume = np.stack(slices, axis=-1) / 255.0  # 0-1 aralığına normalize et

            # Marching Cubes algoritmasını uygula
            verts, faces, normals, values = measure.marching_cubes(volume, level=self.threshold / 255.0)

            # OBJ dosyasına yaz
            with open(self.output_path, "w") as f:
                for v in verts:
                    f.write(f"v {v[0] * self.scale_factor} {v[1] * self.scale_factor} {v[2] * self.z_increment}\n")
                for face in faces:
                    f.write(f"f {face[0] + 1} {face[1] + 1} {face[2] + 1}\n")

            print(f"OBJ dosyası başarıyla kaydedildi: {self.output_path}")
            self.progress_signal.emit(100)
            self.finished_signal.emit(self.output_path)

        except Exception as e:
            print(f"HATA: {e}")
            self.finished_signal.emit("")  # Hata durumunda boş sinyal gönder


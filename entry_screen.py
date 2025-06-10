# entry_screen.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QFileDialog, QLabel, QDialog,
    QLineEdit, QDialogButtonBox, QComboBox, QSpinBox, QDoubleSpinBox,
    QHBoxLayout, QMessageBox
)
from PyQt5.QtGui import QPixmap, QFont, QIcon
from PyQt5.QtCore import Qt, QSize
import os, cv2, numpy as np

from loading_dialog          import LoadingDialog
from model_generation_worker import ModelGenerationWorker


# =================================================================== ANA EKRAN
class EntryScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

        # Ana layout – dikey olarak ortalanmış
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # Başlık
        title = QLabel("3D Modelleme Uygulamasına Hoş Geldiniz")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)

        # Logo
        logo = QLabel()
        logo.setPixmap(
            QPixmap("Icons/main_image.png").scaled(200, 200, Qt.KeepAspectRatio)
        )
        logo.setAlignment(Qt.AlignCenter)

        btn_font  = QFont("Arial", 14, QFont.Bold)
        icon_size = QSize(64, 64)

        # “OBJ Yükle” düğmesi
        self.upload_button = QPushButton("OBJ Yükle")
        self.upload_button.setFont(btn_font)
        self.upload_button.setIconSize(icon_size)
        self.upload_button.setIcon(QIcon("Icons/upload.png"))
        self.upload_button.clicked.connect(self.upload_obj)

        # “Obje Oluştur” düğmesi
        self.create_button = QPushButton("Obje Oluştur")
        self.create_button.setFont(btn_font)
        self.create_button.setIconSize(icon_size)
        self.create_button.setIcon(QIcon("Icons/create.png"))
        self.create_button.clicked.connect(self.create_obj)

        # Hepsini layout’a ekle
        for w in (title, logo, self.upload_button, self.create_button):
            layout.addWidget(w)


    # -------------------------------------------------------- “OBJ Yükle” işlemi
    def upload_obj(self):
        fn, _ = QFileDialog.getOpenFileName(
            self, "OBJ Dosyası Seç", "", "OBJ Files (*.obj)"
        )
        if not fn:
            return

        # Sahneyi temizle ve seçilen objeyi yükle
        self.main_window.cube_widget.clear_scene()
        mesh = self.main_window.cube_widget.load_obj(fn)

        # Yüklenen mesh bir nokta bulutuysa, başlangıç point_size’ı uygulamak
        # (Varsayılan olarak 5.0 piksel atıyoruz; isterseniz burada değiştirin)
        if mesh and mesh.draw_mode == GL_POINTS:
            mesh.point_size = 5.0
            self.main_window.cube_widget.update()

        # Henüz hiçbir mesh seçili değil → menüde “Nokta Boyutu” pasif olsun
        self.main_window.cube_widget.selected_index = -1
        self.main_window.cube_widget.selection_changed.emit(-1)

        # Eğer yüklenen mesh noktabilimi ise onu seçili yapıp menüyü aktif edelim
        if mesh and mesh.draw_mode == GL_POINTS:
            idx = self.main_window.cube_widget.meshes.index(mesh)
            self.main_window.cube_widget.selected_index = idx
            self.main_window.cube_widget.selection_changed.emit(idx)

        # Ana ekrana geçiş
        self.main_window.go_main_screen()


    # -------------------------------------------------------- “Obje Oluştur” işlemi
    def create_obj(self):
        # Örneğin DICOM’dan okuyabileceğiniz “slice thickness (mm)” değerini buraya verin.
        # Eğer DICOM yoksa, sabit 0.5 mm ya da uygun gördüğünüz başka bir değer yazabilirsiniz.
        default_slice_thickness = 0.5

        dlg = ObjCreationDialog(self, default_scale_mm=default_slice_thickness)
        if dlg.exec_() != QDialog.Accepted:
            return

        folder = dlg.get_slice_folder()
        name   = dlg.get_output_name().strip()
        if not folder or not name:
            QMessageBox.warning(self, "Eksik Bilgi",
                                "Klasör ve dosya adı boş olamaz.")
            return

        output_path = os.path.join(folder, f"{name}.obj")
        if os.path.exists(output_path):
            QMessageBox.warning(
                self,
                "Dosya Zaten Var",
                f"'{name}.obj' adlı bir model zaten mevcut.\n"
                "Lütfen farklı bir isim girin."
            )
            return

        # İş parçacığını başlatırken “point_size” değerini de aktaracağız
        self.start_loading_screen(
            slice_folder = folder,
            output_path  = output_path,
            noise_method = dlg.get_noise_reduction_method(),
            scale_factor = dlg.get_scale_factor(),
            z_increment  = dlg.get_z_increment(),
            threshold    = dlg.get_threshold(),
            resolution   = dlg.get_resolution(),
            render_mode  = dlg.get_render_mode(),
            point_size   = dlg.get_point_size()
        )


    # -------------------------------------------------------- İş parçacığını başlat
    def start_loading_screen(self, slice_folder, output_path, noise_method,
                             scale_factor, z_increment, threshold, resolution,
                             render_mode, point_size):
        """
        render_mode: "mesh" veya "point"
        point_size:  Nokta bulutu modu ise glPointSize için kullanılacak değer (px)
        """
        self.loading_dialog = LoadingDialog(self)
        self.worker = ModelGenerationWorker(
            slice_folder, output_path,
            scale_factor=scale_factor,
            z_increment=z_increment,
            threshold=threshold,
            resolution=resolution,
            noise_method=noise_method,
            render_mode=render_mode,
            point_size=point_size
        )
        self.worker.progress_signal.connect(self.loading_dialog.update_progress)
        self.worker.finished_signal.connect(self.on_generation_finished)
        self.loading_dialog.cancel_requested.connect(self.worker.stop)
        self.loading_dialog.cancel_requested.connect(self.loading_dialog.close)
        self.worker.start()
        self.loading_dialog.exec_()


    # -------------------------------------------------------- İşlem tamamlandığında
    def on_generation_finished(self, output_path: str):
        self.loading_dialog.close()
        if output_path:
            QMessageBox.information(
                self,
                "İşlem Tamamlandı",
                f"‘{os.path.basename(output_path)}’ modeli başarıyla oluşturuldu."
            )
            # Oluşan objeyi sahneye yükle ve gerekli ayarları yap
            self.main_window.cube_widget.clear_scene()
            mesh = self.main_window.cube_widget.load_obj(output_path)

            # Eğer nokta bulutu ise point_size’ı atayalım
            if mesh and mesh.draw_mode == GL_POINTS:
                mesh.point_size = self.worker.point_size
                self.main_window.cube_widget.update()

            # Seçimi “o mesh” olarak yapalım, böylece menü aktifleşsin
            if mesh and mesh.draw_mode == GL_POINTS:
                idx = self.main_window.cube_widget.meshes.index(mesh)
                self.main_window.cube_widget.selected_index = idx
                self.main_window.cube_widget.selection_changed.emit(idx)
            else:
                # Mesh moduysa, hiçbir nokta seçili değil demektir
                self.main_window.cube_widget.selected_index = -1
                self.main_window.cube_widget.selection_changed.emit(-1)

            self.main_window.go_main_screen()
        else:
            QMessageBox.warning(self, "İşlem İptal",
                                "Model oluşturulamadı veya işlem iptal edildi.")



# ================================================================ DİYALOG
class ObjCreationDialog(QDialog):
    def __init__(self, parent=None, default_scale_mm: float = 0.1):
        """
        default_scale_mm: Her bir dilimin gerçek kalınlığı (mm) olarak dışarıdan verilir.
                          Eğer verilmezse 0.1 mm kullanılır.
        """
        super().__init__(parent)
        self.setWindowTitle("Obje Oluştur")
        self.slice_folder = None

        vbox = QVBoxLayout(self)

        # --- model tipi (EN ÜSTTE)
        self.render_combo = QComboBox()
        self.render_combo.addItems(["Yüzey (Mesh)", "Nokta Bulutu"])
        vbox.addWidget(QLabel("Model Tipi:"))
        vbox.addWidget(self.render_combo)

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
        self.noise_label = QLabel("Gürültü Azaltma:")
        self.noise_combo = QComboBox()
        self.noise_combo.addItems(["Yok", "Medyan Blur", "Gauss Blur", "Bilateral"])
        vbox.addWidget(self.noise_label)
        vbox.addWidget(self.noise_combo)

        # --- scale & z-increment
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.001, 100.0)   # mm cinsinden geniş bir aralık
        self.scale_spin.setDecimals(3)
        self.scale_spin.setSingleStep(0.1)
        self.scale_spin.setValue(default_scale_mm)

        self.zinc_spin  = QDoubleSpinBox()
        self.zinc_spin.setRange(0.001, 100.0)
        self.zinc_spin.setDecimals(3)
        self.zinc_spin.setSingleStep(0.1)
        self.zinc_spin.setValue(default_scale_mm)

        vbox.addWidget(QLabel("Scale Factor (mm / pixel):"))
        vbox.addWidget(self.scale_spin)
        vbox.addWidget(QLabel("Z Increment (mm / slice):"))
        vbox.addWidget(self.zinc_spin)

        # --- point size (sadece Nokta Bulutu modunda)
        self.ps_label = QLabel("Point Size (px):")
        self.ps_spin  = QDoubleSpinBox()
        self.ps_spin.setRange(1.0, 100.0)  # 1–100 piksel aralığı
        self.ps_spin.setDecimals(1)
        self.ps_spin.setSingleStep(1.0)
        self.ps_spin.setValue(5.0)         # Varsayılan 5.0 px
        vbox.addWidget(self.ps_label)
        vbox.addWidget(self.ps_spin)

        # --- threshold (Otsu veya manuel eşiği ancak yalnızca Mesh modunda)
        self.th_label = QLabel("Threshold (0–255):")
        self.th_spin  = QSpinBox()
        self.th_spin.setRange(0, 255)
        self.th_spin.setValue(100)
        vbox.addWidget(self.th_label)
        vbox.addWidget(self.th_spin)

        # --- çözünürlük (RGB dilimlerinin yeniden boyutu WxH)
        res_row = QHBoxLayout()
        self.res_w = QSpinBox()
        self.res_w.setRange(4, 4096)
        self.res_w.setValue(256)

        self.res_h = QSpinBox()
        self.res_h.setRange(4, 4096)
        self.res_h.setValue(256)

        res_row.addWidget(self.res_w)
        res_row.addWidget(QLabel("x"))
        res_row.addWidget(self.res_h)

        self.res_label = QLabel("Yeniden Ölçekleme (WxH):")
        vbox.addWidget(self.res_label)
        vbox.addLayout(res_row)

        # --- OK / Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        vbox.addWidget(buttons)

        # ───────────────────────────────────────────────────────────────────
        # Model Tipi değişince, ilgili alanları gizle/göster:
        self.render_combo.currentIndexChanged.connect(self._update_fields_visibility)
        # İlk açılışta “Mesh” seçili olduğu varsayılı olarak düşünülür:
        self._update_fields_visibility(self.render_combo.currentIndex())


    def _update_fields_visibility(self, index: int):
        """
        index == 0 ('Yüzey (Mesh)')   → Gürültü Azaltma + Threshold görünür,
                                      Point Size gizli.
        index == 1 ('Nokta Bulutu')   → Gürültü Azaltma + Threshold gizli,
                                      Point Size görünür.
        """
        is_mesh = (index == 0)

        # Gürültü Azaltma (label + combo) yalnızca Mesh modunda
        self.noise_label.setVisible(is_mesh)
        self.noise_combo.setVisible(is_mesh)

        # Threshold (label + spinbox) yalnızca Mesh modunda
        self.th_label.setVisible(is_mesh)
        self.th_spin.setVisible(is_mesh)

        # Point Size (label + spinbox) yalnızca Nokta Bulutu modunda
        self.ps_label.setVisible(not is_mesh)
        self.ps_spin.setVisible(not is_mesh)

        # Eğer isterseniz, çözünürlük (WxH) bilgisini de yalnızca Mesh’te gösterip nokta modunda gizleyebilirsiniz:
        # self.res_label.setVisible(is_mesh)
        # self.res_w.setVisible(is_mesh)
        # self.res_h.setVisible(is_mesh)


    # ------------------------------------------------ klasör seç (Otsu hesaplaması sadece Mesh için)
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Dilim Klasörü Seç")
        if not folder:
            return

        # Eğer “Mesh” modu seçiliyse (index == 0), Otsu eşik hesaplaması yap:
        if self.render_combo.currentIndex() == 0:
            png_files = [f for f in os.listdir(folder) if f.lower().endswith(".png")]
            pixels = []
            for fn in png_files:
                g = cv2.imread(os.path.join(folder, fn), cv2.IMREAD_GRAYSCALE)
                if g is not None:
                    # Eşik hesaplaması öncesi yeniden ölçekle (WxH)
                    g = cv2.resize(
                        g,
                        (self.res_w.value(), self.res_h.value()),
                        interpolation=cv2.INTER_AREA
                    )
                    pixels.append(g.flatten())

            if pixels:
                flat = np.concatenate(pixels, dtype=np.uint8)
                thr, _ = cv2.threshold(
                    flat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
                )
                # Otsu sonucunu “Threshold” etiketi yanına yaz:
                self.th_label.setText(f"Threshold (0–255) [Otsu={int(thr)}]:")
                self.th_spin.setValue(int(thr))
                self.slice_label.setText(f"Klasör: {folder}")
            else:
                self.th_label.setText("Threshold (0–255):")
                self.slice_label.setText(f"Klasör: {folder}")
        else:
            # Nokta Bulutu modunda Otsu yapılmaz, sadece klasör bilgisini göster:
            self.slice_label.setText(f"Klasör: {folder}")

        self.slice_folder = folder


    # ----------------------------- getter’lar
    def get_slice_folder(self):
        return self.slice_folder

    def get_output_name(self):
        return self.name_edit.text()

    def get_noise_reduction_method(self):
        return self.noise_combo.currentText()

    def get_scale_factor(self):
        return self.scale_spin.value()

    def get_z_increment(self):
        return self.zinc_spin.value()

    def get_threshold(self):
        return self.th_spin.value()

    def get_resolution(self):
        return (self.res_w.value(), self.res_h.value())

    def get_render_mode(self) -> str:
        # index == 1 ise Nokta Bulutu, yoksa Mesh
        return "point" if self.render_combo.currentIndex() == 1 else "mesh"

    def get_point_size(self) -> float:
        """
        Nokta Bulutu modu seçildiyse bu değer glPointSize için kullanılır.
        Mesh modunda çağrılsa bile spinbox’ta görünen değeri döner (kullanılmaz).
        """
        return self.ps_spin.value()

# main_window.py

import os
import json
import numpy as np
from PyQt5.QtWidgets import (
    QMainWindow, QStackedWidget,
    QInputDialog, QMessageBox, QFileDialog,
    QAction, QActionGroup, QColorDialog, qApp
)
from PyQt5.QtCore import Qt
from OpenGL.GL import (
    glGenBuffers, glBindBuffer, glBufferData,
    GL_ARRAY_BUFFER, GL_STATIC_DRAW
)
from mesh import Mesh
from cube_3d_widget import Cube3DWidget
from entry_screen import EntryScreen
from main_screen import MainScreen
from PyQt5.QtWidgets import QToolTip
from PyQt5.QtGui     import QCursor

def export_mesh(mesh: Mesh, filepath: str) -> None:
    """
    Basit OBJ exporter: mesh.vertices ve mesh.indices kullanarak OBJ dosyası oluşturur.
    """
    with open(filepath, 'w') as f:
        f.write(f"# OBJ file for {mesh.name}\n")
        for v in mesh.vertices:
            f.write(f"v {v[0]} {v[1]} {v[2]}\n")
        for face in mesh.indices.reshape(-1, 3):
            f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Görüntüleme")
        self.resize(800, 600)

        # Proje yönetimi
        self.project_dir = None
        self.current_project = None
        self.next_color_id = 1

        # Stack & ekranlar
        self.stack = QStackedWidget()
        self.entry_screen = EntryScreen(self)
        self.cube_widget = Cube3DWidget()
        self.main_screen = MainScreen(self, self.cube_widget)
        self.stack.addWidget(self.entry_screen)  # index 0
        self.stack.addWidget(self.main_screen)   # index 1
        self.setCentralWidget(self.stack)

        # Menü & aksiyonlar
        self.statusBar()
        self.create_menu()

        # Ekran değişimine göre aksiyon durumu
        self.stack.currentChanged.connect(self.update_actions)
        # Başlangıçta doğru durumu ayarla
        self.update_actions(self.stack.currentIndex())

    def create_menu(self):
        """Menü çubuğuna Dosya ve Ayarlar menülerini ekler ve aksiyonları oluşturur."""
        menubar = self.menuBar()

        # Dosya menüsü
        file_menu = menubar.addMenu("Dosya")

        self.new_act = QAction("Yeni Proje...", self)
        self.new_act.triggered.connect(self.new_project)
        file_menu.addAction(self.new_act)

        self.open_act = QAction("Projeyi Aç...", self)
        self.open_act.triggered.connect(self.open_project)
        file_menu.addAction(self.open_act)

        self.save_act = QAction("Projeyi Kaydet", self)
        self.save_act.triggered.connect(self.save_project)
        file_menu.addAction(self.save_act)

        self.close_act = QAction("Projeyi Kapat", self)
        self.close_act.triggered.connect(self.close_project)
        file_menu.addAction(self.close_act)

        # Ayarlar menüsü
        settings_menu = menubar.addMenu("Ayarlar")

        # Tema rengi
        theme_act = QAction("Tema", self)
        theme_act.triggered.connect(self.change_theme)
        settings_menu.addAction(theme_act)

        # Eksen göster/gizle
        self.axis_act = QAction("Eksen Göster", self, checkable=True)
        self.axis_act.setChecked(True)
        self.axis_act.hovered.connect(lambda: QToolTip.showText(
            QCursor.pos(),
            "X ekseni → kırmızı\nY ekseni → yeşil\nZ ekseni → mavi"
        ))
        self.axis_act.triggered.connect(
            lambda checked: self.cube_widget.set_axis_visible(checked)
        )
        settings_menu.addAction(self.axis_act)

        # Eksen Uzunluğu…
        axis_size_act = QAction("Eksen Uzunluğu…", self)
        axis_size_act.triggered.connect(self.adjust_axis_length)
        settings_menu.addAction(axis_size_act)
        # Grid Modu Alt-Menüsü
        grid_mode_menu = settings_menu.addMenu("Grid Modu")
        grid_group = QActionGroup(self)

        self.grid_all_act = QAction("Tüm Planlar (3D)", self, checkable=True)
        self.grid_xy_act = QAction("XY Düzlemi", self, checkable=True)
        self.grid_xz_act = QAction("XZ Düzlemi", self, checkable=True)
        self.grid_yz_act = QAction("YZ Düzlemi", self, checkable=True)
        self.grid_none_act = QAction("Kapalı", self, checkable=True)
        # Hepsini grupla ve menüye ekle
        for act in (
                self.grid_all_act,
                self.grid_xy_act,
                self.grid_xz_act,
                self.grid_yz_act,
                self.grid_none_act
        ):
            grid_group.addAction(act)
            grid_mode_menu.addAction(act)

        # Varsayılanı işaretle
        self.grid_all_act.setChecked(True)

        # Bağlantıları yap
        self.grid_all_act.triggered.connect(lambda: self.cube_widget.set_grid_mode('all'))
        self.grid_xy_act.triggered.connect(lambda: self.cube_widget.set_grid_mode('xy'))
        self.grid_xz_act.triggered.connect(lambda: self.cube_widget.set_grid_mode('xz'))
        self.grid_yz_act.triggered.connect(lambda: self.cube_widget.set_grid_mode('yz'))
        self.grid_none_act.triggered.connect(self._disable_grid)



        # “Grid Boyutu…” eylemi
        grid_size_act = QAction("Grid Boyutu…", self)
        grid_size_act.triggered.connect(self.adjust_grid_size)
        settings_menu.addAction(grid_size_act)
        # Menü öğeleri için renk şeması: etkin = siyah, devre dışı = gri
        style = """
            QMenu::item:enabled { color: black; }
            QMenu::item:disabled { color: grey; }
        """
        file_menu.setStyleSheet(style)
        settings_menu.setStyleSheet(style)

    def adjust_axis_length(self):
        """
        Kullanıcıdan ondalık bir değer alıp eksen uzunluğunu ayarlar.
        """
        val, ok = QInputDialog.getDouble(
            self, "Eksen Uzunluğu",
            "Eksen boyu (birim):",
            self.cube_widget.axis_length,
            0.1, 100.0, 2
        )
        if not ok:
            return
        self.cube_widget.set_axis_length(val)
        QMessageBox.information(
            self, "Eksen Ayarlandı",
            f"Eksen uzunluğu {val} birim olarak ayarlandı."
        )
    def _set_grid(self, mode: str):
        """Seçilen düzlem moduna geç ve grid’i aç."""
        # grid toggle düğmesini de senkronize edelim
        self.cube_widget.set_grid_visible(True)
        self.cube_widget.set_grid_mode(mode)

    def _disable_grid(self):
        """Grid’leri tamamen kapat."""
        self.cube_widget.set_grid_visible(False)

    def adjust_grid_size(self):
        """
        Kullanıcıdan bir ondalık değer alıp grid aralığını günceller.
        """
        # Mevcut aralığı al, 0.1–100 arasında 2 ondalık hassasiyetle sor
        val, ok = QInputDialog.getDouble(
            self, "Grid Boyutu",
            "Grid aralığı (birim):",
            self.cube_widget._grid_spacing,
            0.1, 100.0, 2
        )
        if not ok:
            return
        # Hem spacing hem de half_count orantılı güncellenebilir,
        # burada yalnızca spacing’i ayarlıyoruz:
        self.cube_widget.set_grid_spacing(val)
        QMessageBox.information(
            self, "Grid Ayarlandı",
            f"Yeni grid aralığı: {val}"
        )
    def update_actions(self, index: int):
        """
        Giriş ekranı (index 0) veya ana ekran (index 1) durumuna göre
        hangi aksiyonların aktif/devre dışı olacağını ayarlar.
        """
        if index == 0:
            self.new_act.setEnabled(True)
            self.open_act.setEnabled(True)
            self.save_act.setEnabled(False)
            self.close_act.setEnabled(False)
        else:
            self.new_act.setEnabled(False)
            self.open_act.setEnabled(False)
            self.save_act.setEnabled(True)
            self.close_act.setEnabled(True)

    def new_project(self):
        """Yeni proje oluştur ve sahneyi temizle."""
        name, ok = QInputDialog.getText(self, "Yeni Proje", "Proje Adı:")
        if not ok or not name.strip():
            return
        base = r"C:\Users\mfurk\2Dto3D"
        proj_dir = os.path.join(base, name)
        if os.path.exists(proj_dir):
            QMessageBox.warning(self, "Hata", f"\"{name}\" adlı proje zaten var.")
            return
        os.makedirs(proj_dir, exist_ok=True)

        self.current_project = name
        self.project_dir = proj_dir
        self.stack.setCurrentIndex(1)
        self.cube_widget.meshes.clear()
        self.cube_widget.selected_mesh = None
        self.cube_widget.scene_changed.emit()

        if self.cube_widget.selected_mesh:
            mesh = self.cube_widget.selected_mesh
            export_mesh(mesh, os.path.join(proj_dir, f"{mesh.name}.obj"))

        self.write_scene_manifest()
        QMessageBox.information(self, "Yeni Proje", f"Proje oluşturuldu: {proj_dir}")

    def write_scene_manifest(self):
        """Mevcut sahnedeki tüm mesh'leri OBJ ve scene.json olarak kaydeder."""
        if not self.project_dir:
            return
        manifest = {"meshes": []}
        for m in self.cube_widget.meshes:
            filepath = os.path.join(self.project_dir, f"{m.name}.obj")
            export_mesh(m, filepath)

            colors = m.colors.tolist() if getattr(m, 'colors', None) else None
            manifest["meshes"].append({
                "name": m.name,
                "file": f"{m.name}.obj",
                "transform": {
                    "pos": m.translation.tolist(),
                    "rot": m.rotation.tolist(),
                    "scale": m.scale
                },
                "material": {
                    "color": m.color,
                    "transparent": m.transparent
                },
                "colors": colors
            })

        with open(os.path.join(self.project_dir, "scene.json"), "w") as f:
            json.dump(manifest, f, indent=2)

    def save_project(self):
        """Projeyi kaydet (OBJ + manifest)."""
        if not self.project_dir:
            QMessageBox.warning(self, "Hata", "Önce proje oluşturun veya açın.")
            return
        self.write_scene_manifest()
        QMessageBox.information(self, "Kaydedildi", "Proje kaydedildi.")

    def open_project(self):
        """Var olan projeyi aç ve sahneyi yükle."""
        proj_dir = QFileDialog.getExistingDirectory(
            self, "Proje Klasörü Seç", r"C:\Users\mfurk\2Dto3D"
        )
        if not proj_dir:
            return
        scene_path = os.path.join(proj_dir, "scene.json")
        if not os.path.isfile(scene_path):
            QMessageBox.critical(self, "Hata", "scene.json bulunamadı.")
            return

        with open(scene_path, "r") as f:
            manifest = json.load(f)

        self.stack.setCurrentIndex(1)
        self.cube_widget.meshes.clear()
        self.cube_widget.selected_mesh = None

        for entry in manifest["meshes"]:
            filepath = os.path.join(proj_dir, entry["file"])
            if not os.path.isfile(filepath):
                QMessageBox.warning(self, "Eksik Dosya",
                                    f"{entry['file']} bulunamadı, atlanıyor.")
                continue

            mesh = self.load_mesh_from_file(filepath)
            mesh.name        = entry["name"]
            mesh.translation = np.array(entry["transform"]["pos"])
            mesh.rotation    = np.array(entry["transform"]["rot"])
            mesh.scale       = entry["transform"]["scale"]
            mesh.color       = entry["material"]["color"]
            mesh.transparent = entry["material"]["transparent"]

            if entry.get("colors") is not None:
                cols = np.array(entry["colors"], dtype=np.float32)
                mesh.colors = cols
                if not getattr(mesh, "vbo_c", None):
                    mesh.vbo_c = glGenBuffers(1)
                glBindBuffer(GL_ARRAY_BUFFER, mesh.vbo_c)
                glBufferData(GL_ARRAY_BUFFER, cols.nbytes, cols, GL_STATIC_DRAW)

            self.cube_widget.meshes.append(mesh)

        self.project_dir     = proj_dir
        self.current_project = os.path.basename(proj_dir)
        self.cube_widget.scene_changed.emit()
        QMessageBox.information(self, "Proje Açıldı",
                                f"{self.current_project} yüklendi.")

    def close_project(self):
        """Projeyi kaydetmeden kapat ve giriş ekranına dön."""
        if not self.project_dir:
            return
        self.project_dir = None
        self.current_project = None
        self.stack.setCurrentIndex(0)
        self.cube_widget.meshes.clear()
        self.cube_widget.selected_mesh = None
        QMessageBox.information(self, "Proje Kapatıldı",
                                "Mevcut proje kaydedilmeden kapatıldı.")

    def change_theme(self):
        """Tema rengini QColorDialog ile seç ve uygulama stilini güncelle."""
        color = QColorDialog.getColor()
        if color.isValid():
            qApp.setStyleSheet(f"QMainWindow {{ background-color: {color.name()}; }}")
            QMessageBox.information(self, "Tema Değiştirildi",
                                    f"Tema rengi {color.name()} olarak ayarlandı.")

    def load_mesh_from_file(self, filepath: str) -> Mesh:
        """OBJ dosyasından Mesh üretir (v ve f satırlarını okur)."""
        verts, faces = [], []
        with open(filepath, "r") as f:
            for line in f:
                if line.startswith("v "):
                    parts = line.split()[1:]
                    verts.append([float(p) for p in parts])
                elif line.startswith("f "):
                    parts = line.split()[1:]
                    idxs = [int(p.split("/")[0]) - 1 for p in parts]
                    faces.append(idxs)

        verts_arr = np.array(verts, dtype=np.float32)
        inds_arr = np.array(faces, dtype=np.uint32).flatten()
        mesh = Mesh(verts_arr, inds_arr,
                    mesh_name=os.path.splitext(os.path.basename(filepath))[0])
        mesh.id = self.next_color_id
        self.next_color_id += 1
        return mesh

    def go_entry_screen(self):
        """Giriş ekranına dön."""
        self.stack.setCurrentIndex(0)

    def go_main_screen(self):
        """Ana ekrana dön."""
        self.stack.setCurrentIndex(1)

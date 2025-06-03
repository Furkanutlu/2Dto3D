# main_window.py

import os
import json
import numpy as np
from PyQt5.QtWidgets import (
    QMainWindow, QStackedWidget,
    QInputDialog, QMessageBox, QFileDialog,
    QAction, QActionGroup, QColorDialog, qApp,
    QToolTip
)
from PyQt5.QtGui     import QCursor
from PyQt5.QtCore    import Qt, pyqtSignal
from OpenGL.GL import (
    glGenBuffers, glBindBuffer, glBufferData,
    GL_ARRAY_BUFFER, GL_STATIC_DRAW, GL_POINTS
)

from mesh            import Mesh
from cube_3d_widget  import Cube3DWidget
from entry_screen    import EntryScreen
from main_screen     import MainScreen


def export_mesh(mesh: Mesh, filepath: str) -> None:
    """
    Basit OBJ exporter: mesh.vertices ve mesh.indices kullanarak OBJ dosyası oluşturur.
    """
    with open(filepath, 'w') as f:
        f.write(f"# OBJ file for {mesh.name}\n")
        for v in mesh.vertices:
            f.write(f"v {v[0]} {v[1]} {v[2]}\n")
        for face in mesh.indices.reshape(-1, 3):
            # OBJ indeksi 1-bazlı olduğu için +1
            f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")


class MainWindow(QMainWindow):
    BASE_TITLE = "3D Studio"
    theme_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(self.BASE_TITLE)
        self.resize(800, 600)

        # Proje yönetimi
        self.project_dir = None
        self.current_project = None
        self.next_color_id = 1

        # Stack & ekranlar
        self.stack = QStackedWidget()
        self.entry_screen = EntryScreen(self)
        self.cube_widget  = Cube3DWidget()
        self.main_screen  = MainScreen(self, self.cube_widget)

        self.stack.addWidget(self.entry_screen)  # index 0
        self.stack.addWidget(self.main_screen)   # index 1
        self.setCentralWidget(self.stack)

        # Menü & aksiyonlar
        self.statusBar()
        self.create_menu()

        # **Burada on_selection_changed metodu yoksa hata alırsınız**
        self.cube_widget.selection_changed.connect(self.on_selection_changed)

        # Ekran değişimine göre aksiyon durumu
        self.stack.currentChanged.connect(self.update_actions)
        # Başlangıçta doğru durumu ayarla
        self.update_actions(self.stack.currentIndex())


    def create_menu(self):
        """Menü çubuğuna Dosya ve Ayarlar menülerini ekler ve aksiyonları oluşturur."""
        menubar = self.menuBar()

        # ---------------------------------------------------------------
        # Dosya menüsü
        file_menu = menubar.addMenu("Dosya")

        self.new_act   = QAction("Yeni Proje...", self)
        self.new_act.triggered.connect(self.new_project)
        file_menu.addAction(self.new_act)

        self.open_act  = QAction("Projeyi Aç...", self)
        self.open_act.triggered.connect(self.open_project)
        file_menu.addAction(self.open_act)

        self.save_act  = QAction("Projeyi Kaydet", self)
        self.save_act.triggered.connect(self.save_project)
        file_menu.addAction(self.save_act)

        self.close_act = QAction("Projeyi Kapat", self)
        self.close_act.triggered.connect(self.close_project)
        file_menu.addAction(self.close_act)

        # ---------------------------------------------------------------
        # Ayarlar menüsü
        settings_menu = menubar.addMenu("Ayarlar")

        # Tema rengi
        theme_menu = settings_menu.addMenu("Tema")
        theme_group = QActionGroup(self)

        self.light_theme_act = QAction("Light Mode", self, checkable=True)
        self.dark_theme_act = QAction("Dark Mode", self, checkable=True)

        # Add themes to group and menu
        for act in (self.light_theme_act, self.dark_theme_act):
            theme_group.addAction(act)
            theme_menu.addAction(act)

        # Set default theme
        self.light_theme_act.setChecked(True)
        self.apply_theme("light")

        # Connect theme actions
        self.light_theme_act.triggered.connect(lambda: self.apply_theme("light"))
        self.dark_theme_act.triggered.connect(lambda: self.apply_theme("dark"))

        # Eksen göster/gizle
        self.axis_act = QAction("Eksen Göster", self, checkable=True)
        self.axis_act.setChecked(False)
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

        self.grid_all_act  = QAction("Tüm Planlar (3D)", self, checkable=True)
        self.grid_xy_act   = QAction("XY Düzlemi", self, checkable=True)
        self.grid_xz_act   = QAction("XZ Düzlemi", self, checkable=True)
        self.grid_yz_act   = QAction("YZ Düzlemi", self, checkable=True)
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

        # Varsayılan “Kapalı”
        self.grid_none_act.setChecked(True)

        # Bağlantıları yap
        self.grid_all_act.triggered.connect(lambda: self.cube_widget.set_grid_mode('all'))
        self.grid_xy_act.triggered.connect(lambda: self.cube_widget.set_grid_mode('xy'))
        self.grid_xz_act.triggered.connect(lambda: self.cube_widget.set_grid_mode('xz'))
        self.grid_yz_act.triggered.connect(lambda: self.cube_widget.set_grid_mode('yz'))
        self.grid_none_act.triggered.connect(self._disable_grid)

        # Grid Boyutu…
        grid_size_act = QAction("Grid Boyutu…", self)
        grid_size_act.triggered.connect(self.adjust_grid_size)
        settings_menu.addAction(grid_size_act)

        # ---------------------------
        # “Nokta Boyutu…” eylemi
        self.action_point_size = QAction("Nokta Boyutu...", self)
        self.action_point_size.setEnabled(False)  # Başlangıçta pasif
        self.action_point_size.triggered.connect(self.on_change_point_size)
        settings_menu.addAction(self.action_point_size)

        # Renk şeması (aktif/devre dışı öğeler için)
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


    def _disable_grid(self):
        """Grid'leri tamamen kapat."""
        self.cube_widget.set_grid_visible(False)


    def adjust_grid_size(self):
        """
        Kullanıcıdan bir ondalık değer alıp grid aralığını günceller.
        """
        val, ok = QInputDialog.getDouble(
            self, "Grid Boyutu",
            "Grid aralığı (birim):",
            self.cube_widget._grid_spacing,
            0.1, 100.0, 2
        )
        if not ok:
            return
        # Sadece spacing'i ayarlıyoruz:
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
            # Entry ekranındayken “Nokta Boyutu” menüsünü pasif kıl
            self.action_point_size.setEnabled(False)
        else:
            self.new_act.setEnabled(False)
            self.open_act.setEnabled(False)
            self.save_act.setEnabled(True)
            self.close_act.setEnabled(True)
            # Ana ekrana geçince, seçili obje durumuna göre “Nokta Boyutu” menüsünü güncelle
            self._update_point_size_menu()


    def new_project(self):
        """Yeni proje oluştur ve sahneyi temizle."""
        name, ok = QInputDialog.getText(self, "Yeni Proje", "Proje Adı:")
        if not ok or not name.strip():
            return

        # Get desktop path
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")

        # Proje dizinini seçtir
        proj_dir = QFileDialog.getExistingDirectory(
            self,
            "Proje Konumunu Seçin",
            desktop,
            QFileDialog.ShowDirsOnly
        )
        if not proj_dir:
            return

        # Proje klasörünü oluştur
        proj_dir = os.path.join(proj_dir, name)
        if os.path.exists(proj_dir):
            QMessageBox.warning(self, "Hata", f"\"{name}\" adlı proje zaten var.")
            return
        os.makedirs(proj_dir, exist_ok=True)

        self.current_project = name
        self.project_dir     = proj_dir
        self.stack.setCurrentIndex(1)  # Cube ekranına geç
        self.cube_widget.meshes.clear()
        self.cube_widget.selected_mesh = None

        # Arkaplan rengini varsayılan beyaz yap
        default_bg = (1.0, 1.0, 1.0, 1.0)
        self.cube_widget.bg_color = default_bg
        self.cube_widget.update()
        self.cube_widget.scene_changed.emit()

        if self.cube_widget.selected_mesh:
            mesh = self.cube_widget.selected_mesh
            export_mesh(mesh, os.path.join(proj_dir, f"{mesh.name}.obj"))

        self.write_scene_manifest()
        self.setWindowTitle(f"3D Studio – {name}")
        QMessageBox.information(self, "Yeni Proje", f"Proje oluşturuldu: {proj_dir}")
        self.main_screen.notes_panel.text.clear()


    def write_scene_manifest(self):
        """Mevcut sahnedeki tüm mesh'leri OBJ ve scene.json olarak kaydeder."""
        if not self.project_dir:
            return
        manifest = {
            "meshes": [],
            "notes": self.main_screen.notes_panel.text.toPlainText(),
            "bg_color": list(self.cube_widget.bg_color)
        }
        for m in self.cube_widget.meshes:
            filepath = os.path.join(self.project_dir, f"{m.name}.obj")
            export_mesh(m, filepath)

            cols_attr = getattr(m, 'colors', None)
            colors = cols_attr.tolist() if cols_attr is not None else None
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
        if not self.project_dir:
            QMessageBox.warning(self, "Hata", "Önce proje oluşturun veya açın.")
            return
        self.write_scene_manifest()
        self.setWindowTitle(f"{self.BASE_TITLE} – {self.current_project}")
        QMessageBox.information(self, "Kaydedildi", "Proje kaydedildi.")


    def open_project(self):
        """Var olan projeyi aç ve sahneyi yükle."""
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        proj_dir = QFileDialog.getExistingDirectory(
            self, "Proje Klasörü Seç", desktop
        )
        if not proj_dir:
            return
        scene_path = os.path.join(proj_dir, "scene.json")
        if not os.path.isfile(scene_path):
            QMessageBox.critical(self, "Hata", "scene.json bulunamadı.")
            return

        with open(scene_path, "r") as f:
            manifest = json.load(f)

        notes_edit = self.main_screen.notes_panel.text
        notes_edit.blockSignals(True)
        notes_edit.setPlainText(manifest.get("notes", ""))
        notes_edit.blockSignals(False)

        bg = manifest.get("bg_color", [1.0, 1.0, 1.0, 1.0])
        self.cube_widget.bg_color = tuple(bg)
        self.cube_widget.update()

        self.stack.setCurrentIndex(1)  # Cube ekranına geç
        self.cube_widget.meshes.clear()
        self.cube_widget.selected_mesh = None

        for entry in manifest["meshes"]:
            filepath = os.path.join(proj_dir, entry["file"])
            if not os.path.isfile(filepath):
                QMessageBox.warning(self, "Eksik Dosya",
                                    f"{entry['file']} bulunamadı, atlanıyor.")
                continue

            mesh = self.load_mesh_from_file(filepath)
            mesh.name = entry["name"]
            mesh.translation = np.array(entry["transform"]["pos"])
            mesh.rotation = np.array(entry["transform"]["rot"])
            mesh.scale = entry["transform"]["scale"]
            mesh.color = entry["material"]["color"]
            mesh.transparent = entry["material"]["transparent"]


            mesh.id = self.cube_widget.next_color_id
            self.cube_widget.next_color_id += 1

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
        proj_name = os.path.basename(proj_dir)
        self.setWindowTitle(f"3D Studio – {proj_name}")
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
        self.setWindowTitle(self.BASE_TITLE)
        QMessageBox.information(self, "Proje Kapatıldı",
                                "Mevcut proje kaydedilmeden kapatıldı.")
        self.main_screen.notes_panel.text.clear()

    def apply_theme(self, theme: str):
        """Apply the selected theme to the application."""
        if theme == "light":
            qApp.setStyleSheet("QMainWindow { background-color: #FFFFFF; }")
        elif theme == "dark":
            qApp.setStyleSheet("QMainWindow { background-color: #121212; }")

        # Emit theme changed signal
        self.theme_changed.emit(theme)
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
        inds_arr  = np.array(faces, dtype=np.uint32).flatten()
        mesh = Mesh(verts_arr, inds_arr,
                    mesh_name=os.path.splitext(os.path.basename(filepath))[0])
        mesh.id = self.next_color_id
        self.next_color_id += 1
        return mesh


    def go_entry_screen(self):
        """Giriş ekranına dön."""
        self.stack.setCurrentIndex(0)
        # Entry ekranındayken “Nokta Boyutu” menüsünü pasif kıl:
        self.action_point_size.setEnabled(False)


    def go_main_screen(self):
        """Ana ekrana (3D sahne) dön."""
        self.stack.setCurrentIndex(1)
        # Ana ekrana geçince, seçili obje durumuna göre “Nokta Boyutu” menüsünü güncelle:
        self._update_point_size_menu()


    def _update_point_size_menu(self):
        """
        Cube3DWidget üzerinde seçili bir nokta bulutu varsa menüyü aktif et,
        aksi halde pasif yap.
        """
        idx = self.cube_widget.get_selected_index()
        # Önce geçerli bir index aralığında mı kontrol et
        if idx < 0 or idx >= len(self.cube_widget.meshes):
            self.action_point_size.setEnabled(False)
            return

        mesh = self.cube_widget.meshes[idx]
        if mesh.draw_mode == GL_POINTS:
            self.action_point_size.setEnabled(True)
        else:
            self.action_point_size.setEnabled(False)


    def on_selection_changed(self, mesh_index: int):
        """
        Kullanıcı sahnede seçim değiştirdiğinde tetiklenir:
         - mesh_index == -1 → hiçbir mesh seçili değil
         - mesh_index >= 0  → self.cube_widget.meshes[mesh_index] geçerli bir mesh

        Bu metotta “seçili mesh bir nokta bulutu mu?” kontrolü yapıp
        “Ayarlar → Nokta Boyutu…” menüsünü aktif/pasif yapıyoruz.
        """
        # 1) Eğer index geçersizse, menüyü pasif yap ve çık
        if mesh_index < 0 or mesh_index >= len(self.cube_widget.meshes):
            self.action_point_size.setEnabled(False)
            return

        # 2) Geçerli bir index varsa, mesh’i al ve draw_mode’ına bak
        mesh = self.cube_widget.meshes[mesh_index]
        if mesh.draw_mode == GL_POINTS:
            # Seçili obje bir nokta bulutuysa menüyü aktif et
            self.action_point_size.setEnabled(True)
        else:
            # Değilse kapat
            self.action_point_size.setEnabled(False)

    def on_change_point_size(self):
        mesh_index = self.cube_widget.get_selected_index()
        if mesh_index < 0 or mesh_index >= len(self.cube_widget.meshes):
            return  # seçim yok

        mesh = self.cube_widget.meshes[mesh_index]
        if mesh.draw_mode != GL_POINTS:
            QMessageBox.warning(self, "Geçersiz İşlem",
                                "Seçili obje bir nokta bulutu değil.")
            return

        current_size = getattr(mesh, "point_size", 1.0)
        new_size, ok = QInputDialog.getDouble(
            self, "Nokta Boyutu Değiştir",
            "Yeni nokta boyutu (piksel):",
            current_size, 1.0, 100.0, 1
        )
        if not ok or new_size == current_size:
            return

        self.cube_widget.save_state()  # ← **Undo kaydı eklendi**
        mesh.point_size = new_size
        self.cube_widget.update()



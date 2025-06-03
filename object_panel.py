from PyQt5.QtWidgets import QWidget, QListWidget, QVBoxLayout, QLabel, QSizePolicy
from PyQt5.QtCore    import Qt


class ObjectPanel(QWidget):
    """
    Sağ kenarda açılıp-kapanan listede sahnedeki bütün Mesh’ler görünür.
    Satıra tıklandığında obje seçilir; aynı satıra yeniden tıklayınca seçim kalkar.
    """
    def __init__(self, cube_widget, parent=None):
        super().__init__(parent)
        self.cube_widget = cube_widget

        # panel ölçüsü
        self.setFixedWidth(180)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        # başlık (tıklanarak aç/kapa)
        self.title = QLabel("▾ Objeler")
        self.title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title.setStyleSheet("background:#dddddd;font-weight:bold;")
        self.title.mousePressEvent = self._toggle

        # liste
        self.list = QListWidget()
        self.list.itemClicked.connect(self._click_item)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.title)
        lay.addWidget(self.list)

        # cube_widget sinyallerine bağlan
        cube_widget.scene_changed.connect(self._refresh)
        cube_widget.selection_changed.connect(self._mark)

        self._collapsed = False
        self._refresh()

    # ------------------------------------------------------------
    def _toggle(self, *_):
        """Paneli aç / kapa: içerik gizle + yükseklik ayarı."""
        self._collapsed = not self._collapsed
        self.list.setVisible(not self._collapsed)
        self.title.setText(("▾ " if not self._collapsed else "▸ ") + "Objeler")

        if self._collapsed:                                 # yalnızca başlık kadar yüksek
            self.setMaximumHeight(self.title.sizeHint().height())
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        else:                                               # serbestçe uzasın
            self.setMaximumHeight(16777215)                 # Qt “sonsuz” değeri
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self.parent().updateGeometry()
    # ------------------------------------------------------------
    def _refresh(self):
        """Sahnedeki Mesh’leri listeye yeniden doldurur."""
        self.list.clear()
        for m in self.cube_widget.meshes:
            prefix = "✓ " if m == self.cube_widget.selected_mesh else ""
            self.list.addItem(prefix + m.name)

    # ------------------------------------------------------------
    def _mark(self, mesh_id: int):
        """Seçilen mesh değiştiğinde ✓ işaretini güncelle."""
        for row, m in enumerate(self.cube_widget.meshes):
            prefix = "✓ " if row == mesh_id else ""
            self.list.item(row).setText(prefix + m.name)

    # ------------------------------------------------------------
    def _click_item(self, item):
        # Tıklanan satırın dizinini al
        idx = self.list.row(item)

        if idx == self.cube_widget.selected_index:
            # Aynı öğeye yeniden tıklandı → seçimi kaldır
            self.cube_widget.selected_mesh = None
            self.cube_widget.selected_index = -1
            self.cube_widget.selection_changed.emit(-1)
        else:
            # Yeni öğe seçildi
            self.cube_widget.selected_mesh = self.cube_widget.meshes[idx]
            self.cube_widget.selected_index = idx
            self.cube_widget.selection_changed.emit(idx)

        # Görünümü ve listeyi yenile
        self.cube_widget.update()
        self._refresh()


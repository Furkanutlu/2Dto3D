from __future__ import annotations
"""
Inspector panel — editable transform with spin‑boxes and “–” placeholder.
Her değer değişikliğinde **Cube3DWidget.save_state()** çağırarak Undo/Redo’ya
kaydedilir.
"""

from typing import Sequence, Optional
import numpy as np
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QFormLayout,
    QDoubleSpinBox,
    QSizePolicy,
)

__all__ = ["InspectorPanel"]

_DEG2RAD = np.pi / 180.0
_RAD2DEG = 180.0 / np.pi
_INF     = 16777215
_BLANK   = -1e12   # sentinel value shown as “–”


class InspectorPanel(QWidget):
    """Collapsible, live‑updating, editable transform panel with spin‑boxes."""

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def __init__(self, cube_widget: QWidget, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.cube_widget = cube_widget
        self._collapsed = False

        # ------------------------------------------------ panel gövdesi
        self.setFixedWidth(180)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setStyleSheet("background-color: white;")  # Set white background
        root = QVBoxLayout(self);
        root.setContentsMargins(0, 0, 0, 0);
        root.setSpacing(0)

        self.title = QLabel("▾ Inspector")
        self.title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title.setStyleSheet("background:#dddddd;font-weight:bold;padding:2px;")
        self.title.mousePressEvent = self._toggle  # type: ignore
        root.addWidget(self.title)

        # ---------- Form gövdesi --------------------------------------
        self.form_widget = QWidget();
        root.addWidget(self.form_widget)
        form = QFormLayout(self.form_widget);
        form.setContentsMargins(4, 4, 4, 4);
        form.setSpacing(2)

        # --- Triangle etiketi (YENİ) ----------------------------------
        self.tri_label = QLabel("–")
        form.addRow("Triangle (⊿):", self.tri_label)
        # --- Point etiketi (YENİ) ----------------------------------
        self.pt_label = QLabel("–")  # <── EK
        form.addRow("Point (•):", self.pt_label)  # <── EK

        # Helper → spin-box üretir
        def _spin(tag: str, dec: int, step: float) -> QDoubleSpinBox:
            sb = QDoubleSpinBox();
            sb.setDecimals(dec);
            sb.setSingleStep(step)
            sb.setRange(_BLANK, 1e9);
            sb.setSpecialValueText("–")
            sb.setButtonSymbols(QDoubleSpinBox.UpDownArrows)
            sb.valueChanged.connect(lambda _v, t=tag, s=sb: self._value_changed(t, s))
            return sb

        # Konum
        self.pos_x = _spin("pos_x", 3, 0.10);
        self.pos_y = _spin("pos_y", 3, 0.10);
        self.pos_z = _spin("pos_z", 3, 0.10)
        # Rotasyon
        self.rot_x = _spin("rot_x", 2, 1.0);
        self.rot_y = _spin("rot_y", 2, 1.0);
        self.rot_z = _spin("rot_z", 2, 1.0)
        # Ölçek
        self.scl_x = _spin("scl_x", 3, 0.05);
        self.scl_y = _spin("scl_y", 3, 0.05);
        self.scl_z = _spin("scl_z", 3, 0.05)

        for label, widget in (
                ("Konum X:", self.pos_x), ("Konum Y:", self.pos_y), ("Konum Z:", self.pos_z),
                ("Rotasyon X:", self.rot_x), ("Rotasyon Y:", self.rot_y), ("Rotasyon Z:", self.rot_z),
                ("Ölçek X:", self.scl_x), ("Ölçek Y:", self.scl_y), ("Ölçek Z:", self.scl_z),
        ):
            form.addRow(label, widget)

        # --- CubeWidget sinyalleri -----------------------------------
        if hasattr(cube_widget, "selection_changed"):
            cube_widget.selection_changed.connect(self._refresh)  # type: ignore
        if hasattr(cube_widget, "scene_changed"):
            cube_widget.scene_changed.connect(self._refresh)  # type: ignore

        # Periyodik tazeleme (10 Hz)
        self._timer = QTimer(self);
        self._timer.timeout.connect(self._refresh);
        self._timer.start(100)
        self._refresh()
    # ------------------------------------------------------------------
    # Collapse / expand
    # ------------------------------------------------------------------
    def _toggle(self, *_):
        self._collapsed = not self._collapsed
        self.form_widget.setVisible(not self._collapsed)
        self.title.setText(("▾ " if not self._collapsed else "▸ ") + "Inspector")

        if self._collapsed:                              # only header height
            self.setMaximumHeight(self.title.sizeHint().height())
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        else:                                            # free to grow
            self.setMaximumHeight(_INF)
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)

        if self.parent():
            self.parent().updateGeometry()

    # ------------------------------------------------------------------
    # Spin‑box callback → apply to mesh & save undo snapshot
    # ------------------------------------------------------------------
    def _value_changed(self, tag: str, sb: QDoubleSpinBox):
        # Ignore placeholder “–”
        if sb.value() == _BLANK:
            return

        mesh = getattr(self.cube_widget, "selected_mesh", None)
        if mesh is None:
            return

        # --- 1) Save previous state before mutating anything ---------
        self.cube_widget.save_state()

        axis = "xyz".index(tag[-1])

        def _get(sp: QDoubleSpinBox) -> float:
            return sp.value() if sp.value() != _BLANK else 0.0

        # ---------------- position ----------------
        if tag.startswith("pos_"):
            pos = [_get(self.pos_x), _get(self.pos_y), _get(self.pos_z)]
            pos[axis] = sb.value()
            mesh.translation = pos                      # type: ignore[attr-defined]

        # ---------------- scale -------------------
        elif tag.startswith("scl_"):
            scl = [_get(self.scl_x), _get(self.scl_y), _get(self.scl_z)]
            scl[axis] = max(sb.value(), 1e-6)
            mesh.scale = scl                            # type: ignore[attr-defined]

        # --------------- rotation (Euler deg) ------
        elif tag.startswith("rot_"):
            rot_deg = [_get(self.rot_x), _get(self.rot_y), _get(self.rot_z)]
            rot_deg[axis] = sb.value()
            rx, ry, rz = (d * _DEG2RAD for d in rot_deg)

            cx, sx = np.cos(rx), np.sin(rx)
            cy, sy = np.cos(ry), np.sin(ry)
            cz, sz = np.cos(rz), np.sin(rz)

            Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
            Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
            Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])

            M = np.identity(4, np.float32)
            M[:3, :3] = Rz @ Ry @ Rx
            mesh.rotation = M

        # Redraw & refresh fields
        self.cube_widget.update()
        self._refresh()

    # ------------------------------------------------------------------
    # Live refresh helper
    # ------------------------------------------------------------------
    def _refresh(self, *_):
        mesh = getattr(self.cube_widget, "selected_mesh", None)
        has_sel = mesh is not None

        # ---------- Spin-box’ların enable durumu ----------------------
        for sp in (
                self.pos_x, self.pos_y, self.pos_z,
                self.rot_x, self.rot_y, self.rot_z,
                self.scl_x, self.scl_y, self.scl_z,
        ):
            sp.setEnabled(has_sel)

        # --------- Seçim yoksa tüm alanlara “–” -----------------------
        if not has_sel:
            self.tri_label.setText("–")  # ⊿ etiketi
            self.pt_label.setText("–")
            for sp in (
                    self.pos_x, self.pos_y, self.pos_z,
                    self.rot_x, self.rot_y, self.rot_z,
                    self.scl_x, self.scl_y, self.scl_z,
            ):
                sp.blockSignals(True);
                sp.setValue(_BLANK);
                sp.blockSignals(False)
            return

        # ---------- Seçim varsa değerleri oku ------------------------
        verts = mesh.translation if hasattr(mesh, "translation") else (0, 0, 0)
        scl = mesh.scale if hasattr(mesh, "scale") else 1.0
        rot = mesh.rotation if hasattr(mesh, "rotation") else np.identity(4)

        # Üçgen sayısı = index_count // 3
        tri_cnt = mesh.index_count // 3

        pt_cnt = len(mesh.vertices)
        if  mesh.index_count:
            self.tri_label.setText(f"{tri_cnt:,}")
            self.pt_label.setText("–")
        else:
            self.tri_label.setText("–")
            self.pt_label.setText(f"{pt_cnt:,}")

        # Pozisyon
        self.pos_x.blockSignals(True);
        self.pos_x.setValue(verts[0]);
        self.pos_x.blockSignals(False)
        self.pos_y.blockSignals(True);
        self.pos_y.setValue(verts[1]);
        self.pos_y.blockSignals(False)
        self.pos_z.blockSignals(True);
        self.pos_z.setValue(verts[2]);
        self.pos_z.blockSignals(False)

        # Ölçek
        if isinstance(scl, (list, tuple, np.ndarray)):
            sx, sy, sz = scl
        else:
            sx = sy = sz = scl
        self.scl_x.blockSignals(True);
        self.scl_x.setValue(sx);
        self.scl_x.blockSignals(False)
        self.scl_y.blockSignals(True);
        self.scl_y.setValue(sy);
        self.scl_y.blockSignals(False)
        self.scl_z.blockSignals(True);
        self.scl_z.setValue(sz);
        self.scl_z.blockSignals(False)

        # Rotasyon (Euler, derece)
        rx = np.arctan2(rot[2, 1], rot[2, 2]) * _RAD2DEG
        ry = np.arcsin(-rot[2, 0]) * _RAD2DEG
        rz = np.arctan2(rot[1, 0], rot[0, 0]) * _RAD2DEG
        self.rot_x.blockSignals(True);
        self.rot_x.setValue(rx);
        self.rot_x.blockSignals(False)
        self.rot_y.blockSignals(True);
        self.rot_y.setValue(ry);
        self.rot_y.blockSignals(False)
        self.rot_z.blockSignals(True);
        self.rot_z.setValue(rz);
        self.rot_z.blockSignals(False)


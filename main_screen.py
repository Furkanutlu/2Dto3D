from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QToolButton, QWidget, QDialog,
    QSlider, QDoubleSpinBox
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt
import os, math

from add_object_dialog import AddObjectDialog
from repeat_button import RepeatButton
from object_panel import ObjectPanel
from inspector_panel import InspectorPanel
from notes_panel import NotesPanel


class MainScreen(QWidget):
    def __init__(self, main_window, cube_widget):
        super().__init__()
        self.main_window, self.cube_widget = main_window, cube_widget

        # ───── stil
        self.current_tool = None
        self.active_style = ("QToolButton {background:#FFB300;border:1px solid #666;"
                             "border-radius:5px;margin:5px;padding:10px;color:#1565C0;}"
                             "QToolButton:hover {background:#FFC107;}")
        self.inactive_style = ("QToolButton {background:#1565C0;border:1px solid #ccc;"
                               "border-radius:5px;margin:5px;padding:10px;color:white;}"
                               "QToolButton:hover {background:#1976D2;}")

        self.tool_buttons, self.sens_controls = {}, {}

        # ───── araç çubuğu
        self.tool_bar = QWidget(); self.tool_bar.setFixedWidth(150)
        self.tool_bar.setStyleSheet("background:#F2F4F7;border-right:1px solid #ccc;")
        tb = QVBoxLayout(self.tool_bar); tb.setContentsMargins(0, 0, 0, 0)

        icons = [
            ("Images/cursor.png",  "Cursor"),
            ("Images/circle-of-two-clockwise-arrows-rotation.png", "Rotate"),
            ("Images/expand-arrows.png", "Move"),
            ("Images/resize.png",  "Resize"),
            ("Images/eraser.png",  "Erase"),
            ("Images/color-wheel.png", "Background Color"),
            ("Images/scissors.png", "Cut"),
            ("Images/delete.png",  "Objeyi Sil"),
            ("Images/back.png",    "Undo"),
            ("Images/redo-arrow.png", "Redo"),
            ("Images/add-object.png", "Add Object"),
            ("Images/home.png",    "Giriş Ekranına Dön"),
        ]

        for path, tip in icons:
            # Undo / Redo (tekrar butonu)
            if tip in {"Undo", "Redo"}:
                btn = RepeatButton(initial_interval=500,
                                   min_interval=100,
                                   acceleration=0.8,
                                   parent=self)
                fallback = "edit-undo" if tip == "Undo" else "edit-redo"
                btn.setIcon(QIcon(path) if os.path.exists(path)
                            else QIcon.fromTheme(fallback))
                btn.setToolTip(tip);
                btn.setStyleSheet(self.inactive_style)
                (btn.repeat_signal.connect(self.cube_widget.undo)
                 if tip == "Undo" else btn.repeat_signal.connect(self.cube_widget.redo))
                tb.addWidget(btn)
                self.tool_buttons[tip] = btn
                continue

            # diğer araçlar
            wrapper = QWidget(); box = QVBoxLayout(wrapper)
            box.setContentsMargins(0, 0, 0, 0)

            btn = QToolButton()
            btn.setIcon(QIcon(path) if os.path.exists(path) else QIcon())
            btn.setToolTip(tip); btn.setStyleSheet(self.inactive_style)
            box.addWidget(btn)

            # ---- hassasiyet / yarıçap kontrolleri ------------------
            if tip in {"Move", "Rotate", "Resize", "Erase"}:
                if tip == "Move":
                    rng, step, fac = (0.01, 1.0), 0.01, 100
                    init = getattr(cube_widget, "sens_move", 0.05)
                elif tip == "Rotate":
                    rng, step, fac = (0.1, 5.0), 0.1, 10
                    init = getattr(cube_widget, "sens_rotate", 1.0)
                elif tip == "Resize":
                    rng, step, fac = (0.001, 1.0), 0.001, 1000
                    init = getattr(cube_widget, "sens_resize", 0.05)
                else:  # Erase yarıçapı
                    rng, step, fac = (0.005, 0.20), 0.005, 1000
                    init = getattr(cube_widget, "erase_radius", 0.02)

                init = min(max(init, rng[0]), rng[1])

                sld = QSlider(Qt.Horizontal); sld.setFixedHeight(14)
                sld.setRange(int(rng[0]*fac), int(rng[1]*fac))
                sld.setValue(int(init*fac))

                spn = QDoubleSpinBox(); spn.setDecimals(len(str(step).split('.')[-1]))
                spn.setSingleStep(step); spn.setRange(*rng); spn.setValue(init)

                def from_slider(val, f=fac, sp=spn, t=tip):
                    v = val / f
                    if abs(v - sp.value()) > 1e-6:
                        sp.blockSignals(True); sp.setValue(v); sp.blockSignals(False)
                    self._apply_sensitivity(t, v)

                def from_spin(v, f=fac, sl=sld, t=tip):
                    iv = int(v * f)
                    if iv != sl.value():
                        sl.blockSignals(True); sl.setValue(iv); sl.blockSignals(False)
                    self._apply_sensitivity(t, v)

                sld.valueChanged.connect(from_slider)
                spn.valueChanged.connect(from_spin)

                box.addWidget(sld); box.addWidget(spn)
                sld.hide(); spn.hide()
                self.sens_controls[tip] = (sld, spn)

            # ---- tıklama bağlantıları -----------------------------
            if tip in {"Cursor", "Rotate", "Move", "Resize", "Cut", "Erase"}:
                btn.clicked.connect(lambda _, t=tip: self.activate_tool(t))
            elif tip == "Background Color":
                btn.clicked.connect(cube_widget.set_background_color)
            elif tip == "Add Object":
                btn.clicked.connect(self.add_object)
            elif tip == "Giriş Ekranına Dön":
                btn.clicked.connect(self.main_window.go_entry_screen)
            elif tip == "Objeyi Sil":
                btn.clicked.connect(cube_widget.delete_selected_object)

            self.tool_buttons[tip] = btn
            tb.addWidget(wrapper)

        tb.addStretch()

        # ───── sağ paneller
        self.object_panel    = ObjectPanel(cube_widget)
        self.inspector_panel = InspectorPanel(cube_widget)
        self.notes_panel     = NotesPanel()

        sidebar = QWidget()
        sb = QVBoxLayout(sidebar); sb.setContentsMargins(0, 0, 0, 0)
        sb.addWidget(self.object_panel)
        sb.addWidget(self.inspector_panel)
        sb.addWidget(self.notes_panel); sb.addStretch()

        # ───── ana yerleşim
        lay = QHBoxLayout(self)
        lay.addWidget(self.tool_bar)
        lay.addWidget(cube_widget, 1)
        lay.addWidget(sidebar)

        # Connect theme changed signal
        self.main_window.theme_changed.connect(self.update_theme)

    # ---------------------------------------------------------------
    def _apply_sensitivity(self, tool, v):
        if tool == "Move":
            self.cube_widget.set_move_sensitivity(v)
        elif tool == "Rotate":
            self.cube_widget.set_rotate_sensitivity(v)
        elif tool == "Resize":
            self.cube_widget.set_resize_sensitivity(v)
        elif tool == "Erase":
            # v, slider/ spinbox tarafından 0.005–0.20 arası bir değer
            # slider'ın ham değeri = v * 1000 → 5–200 piksel
            px = int(v * 1000)
            self.cube_widget.set_erase_radius_px(px)

    # ---------------------------------------------------------------
    def activate_tool(self, tool):
        self.current_tool = None if self.current_tool == tool else tool
        mode = {"Rotate":"rotate","Move":"move","Resize":"resize",
                "Cut":"cut","Erase":"erase"}.get(self.current_tool)
        self.cube_widget.set_mode(mode)

        # buton stilleri / kontrol görünürlüğü
        for t, b in self.tool_buttons.items():
            if t in {"Cursor","Rotate","Move","Resize","Cut","Erase"}:
                b.setStyleSheet(self.active_style if t == self.current_tool
                                else self.inactive_style)
        for t,(s,sp) in self.sens_controls.items():
            vis = (t == self.current_tool)
            s.setVisible(vis); sp.setVisible(vis)

    # ---------------------------------------------------------------
    def add_object(self):
        dlg = AddObjectDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            _, fn = dlg.get_selection()
            if fn:
                self.cube_widget.load_obj(fn)
                self.main_window.go_main_screen()

    def update_theme(self, theme: str):
        """Update the UI elements based on the selected theme."""
        if theme == "light":
            # Update panel backgrounds
            self.tool_bar.setStyleSheet("background:#F2F4F7;border-right:1px solid #ccc;color:#1565C0;")
            self.object_panel.setStyleSheet("background:#F2F4F7;color:#1565C0;")
            self.inspector_panel.setStyleSheet("background:#F2F4F7;color:#1565C0;")
            self.notes_panel.setStyleSheet("background:#F2F4F7;color:#1565C0;")
            
            # Panel titles
            for panel in [self.object_panel, self.inspector_panel, self.notes_panel]:
                panel.title.setStyleSheet("background:#dddddd;color:#1565C0;font-weight:bold;")
            
            # Object panel list
            self.object_panel.list.setStyleSheet("background:#F2F4F7; color:#1565C0;")
            # Inspector panel widgets
            for widget in [self.inspector_panel.tri_label,
                           self.inspector_panel.pos_x, self.inspector_panel.pos_y, self.inspector_panel.pos_z,
                           self.inspector_panel.rot_x, self.inspector_panel.rot_y, self.inspector_panel.rot_z,
                           self.inspector_panel.scl_x, self.inspector_panel.scl_y, self.inspector_panel.scl_z]:
                widget.setStyleSheet("background:#F2F4F7; color:#1565C0;")
            # Notes panel text
            self.notes_panel.text.setStyleSheet("background:#F2F4F7; color:#1565C0;")
            
            # Update button styles
            self.active_style = ("QToolButton {background:#FFB300;border:1px solid #666;"
                                "border-radius:5px;margin:5px;padding:10px;color:#1565C0;}"
                                "QToolButton:hover {background:#FFC107;}")
            self.inactive_style = ("QToolButton {background:#1565C0;border:1px solid #ccc;"
                                  "border-radius:5px;margin:5px;padding:10px;color:white;}"
                                  "QToolButton:hover {background:#1976D2;}")
            
            # Update all tool buttons
            for name, btn in self.tool_buttons.items():
                if name == self.current_tool:
                    btn.setStyleSheet(self.active_style)
                    btn.setChecked(True)
                else:
                    btn.setStyleSheet(self.inactive_style)
                    btn.setChecked(False)
        elif theme == "dark":
            # Update panel backgrounds
            self.tool_bar.setStyleSheet("background:#1E1E1E;border-right:1px solid #333;color:#EDEDED;")
            self.object_panel.setStyleSheet("background:#1E1E1E;color:#EDEDED;")
            self.inspector_panel.setStyleSheet("background:#1E1E1E;color:#EDEDED;")
            self.notes_panel.setStyleSheet("background:#1E1E1E;color:#EDEDED;")
            
            # Panel titles
            for panel in [self.object_panel, self.inspector_panel, self.notes_panel]:
                panel.title.setStyleSheet("background:#222;color:#EDEDED;font-weight:bold;")
            
            # Object panel list
            self.object_panel.list.setStyleSheet("background:#1E1E1E; color:#EDEDED;")
            # Inspector panel widgets
            for widget in [self.inspector_panel.tri_label,
                           self.inspector_panel.pos_x, self.inspector_panel.pos_y, self.inspector_panel.pos_z,
                           self.inspector_panel.rot_x, self.inspector_panel.rot_y, self.inspector_panel.rot_z,
                           self.inspector_panel.scl_x, self.inspector_panel.scl_y, self.inspector_panel.scl_z]:
                widget.setStyleSheet("background:#1E1E1E; color:#EDEDED;")
            # Notes panel text
            self.notes_panel.text.setStyleSheet("background:#1E1E1E; color:#EDEDED;")
            
            # Update button styles
            self.active_style = ("QToolButton {background:#03DAC6;border:1px solid #666;"
                                "border-radius:5px;margin:5px;padding:10px;color:#EDEDED;}"
                                "QToolButton:hover {background:#00C4B4;}")
            self.inactive_style = ("QToolButton {background:#90CAF9;border:1px solid #ccc;"
                                  "border-radius:5px;margin:5px;padding:10px;color:#EDEDED;}"
                                  "QToolButton:hover {background:#64B5F6;}")
            
            # Update all tool buttons
            for name, btn in self.tool_buttons.items():
                if name == self.current_tool:
                    btn.setStyleSheet(self.active_style)
                    btn.setChecked(True)
                else:
                    btn.setStyleSheet(self.inactive_style)
                    btn.setChecked(False)

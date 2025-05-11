from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QToolButton, QWidget, QFileDialog,
    QDialog, QDoubleSpinBox, QSlider
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt
import os

from add_object_dialog import AddObjectDialog
from repeat_button import RepeatButton
from object_panel import ObjectPanel
from inspector_panel import InspectorPanel
from notes_panel import NotesPanel
class MainScreen(QWidget):
    def __init__(self, main_window, cube_widget):
        super().__init__()
        self.main_window  = main_window
        self.cube_widget  = cube_widget

        # —————————————————————————————— 1) Araç çubuğu
        self.current_tool  = None
        self.active_style  = (
            "QToolButton {background-color:#b0c4de;border:1px solid #666;"
            "border-radius:5px;margin:5px;padding:10px;}"
            "QToolButton:hover {background-color:#a0b4ce;}"
        )
        self.inactive_style = (
            "QToolButton {background-color:#ffffff;border:1px solid #ccc;"
            "border-radius:5px;margin:5px;padding:10px;}"
            "QToolButton:hover {background-color:#e0e0e0;}"
        )

        self.tool_buttons   = {}   # kısayol → QToolButton
        self.sens_controls  = {}   # kısayol → (slider, spin) ikilisi

        self.tool_bar       = QWidget()
        self.tool_bar.setFixedWidth(120)
        self.tool_bar.setStyleSheet("background-color:#f0f0f0;border-right:1px solid #ccc;")

        tb_lay = QVBoxLayout(self.tool_bar); tb_lay.setContentsMargins(0, 0, 0, 0)

        icons = [
            ("Images/cursor.png",  "Cursor"),
            ("Images/circle-of-two-clockwise-arrows-rotation.png", "Rotate"),
            ("Images/expand-arrows.png", "Move"),
            ("Images/resize.png",  "resize"),
            ("Images/transparency.png", "Transparency"),
            ("Images/color-wheel.png", "Background Color"),
            ("Images/scissors.png", "Cut"),
            ("Images/delete.png",  "Objeyi Sil"),
            ("Images/back.png",    "Undo"),
            ("Images/redo-arrow.png", "Redo"),
            ("Images/add-object.png", "Add Object"),
            ("Images/home.png",    "Giriş Ekranına Dön"),
        ]

        for icon_path, tip in icons:
            # ———— Tekrarlayan (Undo/Redo) düğmeleri
            if tip in {"Undo", "Redo"}:
                btn = RepeatButton(initial_interval=500, min_interval=100, acceleration=0.8)
                btn.setIcon(QIcon(icon_path) if os.path.exists(icon_path)
                            else QIcon.fromTheme("edit-undo" if tip == "Undo" else "edit-redo"))
                btn.setToolTip(tip); btn.setStyleSheet(self.inactive_style)
                (btn.repeat_signal.connect(self.cube_widget.undo)
                 if tip == "Undo" else btn.repeat_signal.connect(self.cube_widget.redo))
                tb_lay.addWidget(btn)

            # ———— Diğer tüm düğmeler
            else:
                wrapper = QWidget(); vbox = QVBoxLayout(wrapper)
                vbox.setContentsMargins(0, 0, 0, 0)

                btn = QToolButton()
                btn.setIcon(QIcon(icon_path) if os.path.exists(icon_path) else QIcon())
                btn.setToolTip(tip); btn.setStyleSheet(self.inactive_style)
                vbox.addWidget(btn)

                # Hassasiyet kontrolü (Move / Rotate / resize)
                if tip in {"Move", "Rotate", "resize"}:
                    slider = QSlider(Qt.Horizontal);   slider.setFixedHeight(14)
                    spin   = QDoubleSpinBox()
                    if tip == "Rotate":
                        slider.setRange(10, 500); factor = 100
                        spin.setDecimals(2); spin.setRange(0.1, 5.0); spin.setSingleStep(0.05)
                    else:  # Move / resize
                        slider.setRange(1, 100);  factor = 1000
                        spin.setDecimals(4); spin.setRange(0.0001, 0.1); spin.setSingleStep(0.0005)

                    # İki yönlü senkronizasyon
                    slider.valueChanged.connect(
                        lambda val, t=tip: self.set_tool_sensitivity(t, val / factor)
                    )
                    spin.valueChanged.connect(
                        lambda val, t=tip: self.set_tool_sensitivity(t, val)
                    )
                    slider.valueChanged.connect(lambda v, s=spin, f=factor: s.setValue(v / f))
                    spin.valueChanged.connect(lambda v, sl=slider, f=factor: sl.setValue(int(v * f)))

                    vbox.addWidget(slider); vbox.addWidget(spin)
                    slider.hide(); spin.hide()
                    self.sens_controls[tip] = (slider, spin)

                # Tıklama sinyalleri
                if tip in {"Cursor", "Rotate", "Move", "resize", "Cut", "Transparency"}:
                    btn.clicked.connect(lambda _, t=tip: self.activate_tool(t))
                elif tip == "Background Color":
                    btn.clicked.connect(self.cube_widget.set_background_color)
                elif tip == "Add Object":
                    btn.clicked.connect(self.add_object)
                elif tip == "Giriş Ekranına Dön":
                    btn.clicked.connect(self.main_window.go_entry_screen)
                elif tip == "Objeyi Sil":
                    btn.clicked.connect(self.cube_widget.delete_selected_object)

                self.tool_buttons[tip] = btn
                tb_lay.addWidget(wrapper)

        tb_lay.addStretch()

        # —————————————————————————————— 2) Sağ kenar panelleri
        self.object_panel    = ObjectPanel(self.cube_widget)
        self.inspector_panel = InspectorPanel(self.cube_widget)
        self.notes_panel     = NotesPanel()

        sidebar   = QWidget()
        s_lay     = QVBoxLayout(sidebar); s_lay.setContentsMargins(0, 0, 0, 0)
        s_lay.addWidget(self.object_panel)
        s_lay.addWidget(self.inspector_panel)
        s_lay.addWidget(self.notes_panel)
        s_lay.addStretch()

        # —————————————————————————————— 3) Ana yerleşim
        main_layout = QHBoxLayout(self)
        #main_layout.setContentsMargins(0, 0, 0, 0)
        #  main_layout.setSpacing(0)
        main_layout.addWidget(self.tool_bar)
        main_layout.addWidget(self.cube_widget, 1)
        main_layout.addWidget(sidebar)
        self.setLayout(main_layout)

    def set_tool_sensitivity(self, tool, val):
        if tool == "Move":
            self.cube_widget.set_move_sensitivity(val)
        elif tool == "Rotate":
            self.cube_widget.set_rotate_sensitivity(val)
        elif tool == "resize":
            self.cube_widget.set_resize_sensitivity(val)

    def activate_tool(self, tool):
        if self.current_tool == tool:
            self.current_tool = None
            self.cube_widget.set_mode(None)
        else:
            self.current_tool = tool
            if tool == "Cursor":
                self.cube_widget.set_mode(None)
            elif tool == "Rotate":
                self.cube_widget.set_mode("rotate")
            elif tool == "Move":
                self.cube_widget.set_mode("move")
            elif tool == "resize":
                self.cube_widget.set_mode("resize")
            elif tool == "Cut":
                self.cube_widget.set_mode("cut")
            elif tool == "Transparency":
                self.cube_widget.set_mode("transparency")
        for ttip, btn in self.tool_buttons.items():
            if ttip in ["Cursor", "Rotate", "Move", "resize", "Cut", "Transparency"]:
                btn.setStyleSheet(self.active_style if ttip == self.current_tool else self.inactive_style)
        for t, ctl in self.sens_controls.items():
            if ctl:
                ctl[0].setVisible(t == self.current_tool)
                ctl[1].setVisible(t == self.current_tool)

    def add_object(self):
        dialog = AddObjectDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            _, obj_file = dialog.get_selection()
            if obj_file:
                self.cube_widget.load_obj(obj_file)
                self.main_window.go_main_screen()

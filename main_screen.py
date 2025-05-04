from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QToolButton, QWidget, QFileDialog,
    QDialog, QDoubleSpinBox, QSlider
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt
from add_object_dialog import AddObjectDialog
import os
from repeat_button import RepeatButton
from object_panel import ObjectPanel

class MainScreen(QWidget):
    def __init__(self, main_window, cube_widget):
        super().__init__()
        self.main_window = main_window
        self.cube_widget = cube_widget
        self.current_tool = None
        self.active_style = """
            QToolButton {background-color:#b0c4de;border:1px solid #666;border-radius:5px;margin:5px;padding:10px;}
            QToolButton:hover {background-color:#a0b4ce;}
        """
        self.inactive_style = """
            QToolButton {background-color:#ffffff;border:1px solid #ccc;border-radius:5px;margin:5px;padding:10px;}
            QToolButton:hover {background-color:#e0e0e0;}
        """
        self.tool_buttons = {}
        self.sens_controls = {}
        self.tool_bar = QWidget()
        self.tool_bar_layout = QVBoxLayout(self.tool_bar)
        self.tool_bar.setFixedWidth(120)
        self.tool_bar.setStyleSheet("background-color:#f0f0f0;border-right:1px solid #ccc;")
        icons = [
            ("Images/cursor.png", "Cursor"),
            ("Images/circle-of-two-clockwise-arrows-rotation.png", "Rotate"),
            ("Images/expand-arrows.png", "Move"),
            ("Images/resize.png", "resize"),
            ("Images/transparency.png", "Transparency"),
            ("Images/color-wheel.png", "Background Color"),
            ("Images/scissors.png", "Cut"),
            ("Images/delete.png", "Objeyi Sil"),
            ("Images/back.png", "Undo"),
            ("Images/redo-arrow.png", "Redo"),
            ("Images/add-object.png", "Add Object"),
            ("Images/home.png", "Giriş Ekranına Dön")
        ]
        for icon_path, tooltip in icons:
            if tooltip in ["Undo", "Redo"]:
                button = RepeatButton(initial_interval=500, min_interval=100, acceleration=0.8)
                button.setIcon(QIcon(icon_path) if os.path.exists(icon_path) else QIcon.fromTheme("edit-undo" if tooltip == "Undo" else "edit-redo"))
                button.setToolTip(tooltip)
                button.setStyleSheet(self.inactive_style)
                (button.repeat_signal.connect(self.cube_widget.undo) if tooltip == "Undo" else button.repeat_signal.connect(self.cube_widget.redo))
                self.tool_bar_layout.addWidget(button)
            else:
                container = QWidget()
                vbox = QVBoxLayout(container)
                vbox.setContentsMargins(0, 0, 0, 0)
                button = QToolButton()
                button.setIcon(QIcon(icon_path) if os.path.exists(icon_path) else QIcon())
                button.setToolTip(tooltip)
                button.setStyleSheet(self.inactive_style)
                vbox.addWidget(button)
                if tooltip in ["Move", "Rotate", "resize"]:
                    slider = QSlider(Qt.Horizontal)
                    spin = QDoubleSpinBox()
                    if tooltip == "Rotate":
                        slider.setRange(10, 500)
                        factor = 100
                        spin.setDecimals(2)
                        spin.setRange(0.1, 5.0)
                        spin.setSingleStep(0.1)
                        init_val = self.cube_widget.sens_rotate
                        slider.setValue(int(init_val * factor))
                        spin.setValue(init_val)
                    else:
                        slider.setRange(1, 1000)
                        factor = 10000
                        spin.setDecimals(4)
                        spin.setRange(0.0001, 0.1)
                        spin.setSingleStep(0.0001)
                        init_val = self.cube_widget.sens_move if tooltip == "Move" else self.cube_widget.sens_resize
                        slider.setValue(int(init_val * factor))
                        spin.setValue(init_val)
                    def slider_changed(val, t=tooltip, f=factor):
                        v = val / f
                        spin.blockSignals(True)
                        spin.setValue(v)
                        spin.blockSignals(False)
                        self.set_tool_sensitivity(t, v)
                    def spin_changed(val, t=tooltip, f=factor):
                        slider.blockSignals(True)
                        slider.setValue(int(val * f))
                        slider.blockSignals(False)
                        self.set_tool_sensitivity(t, val)
                    slider.valueChanged.connect(slider_changed)
                    spin.valueChanged.connect(spin_changed)
                    vbox.addWidget(slider)
                    vbox.addWidget(spin)
                    slider.hide()
                    spin.hide()
                    self.sens_controls[tooltip] = (slider, spin)
                else:
                    self.sens_controls[tooltip] = None
                if tooltip in ["Cursor", "Rotate", "Move", "resize", "Cut", "Transparency"]:
                    button.clicked.connect(lambda _, t=tooltip: self.activate_tool(t))
                elif tooltip == "Background Color":
                    button.clicked.connect(self.cube_widget.set_background_color)
                elif tooltip == "Add Object":
                    button.clicked.connect(self.add_object)
                elif tooltip == "Giriş Ekranına Dön":
                    button.clicked.connect(self.main_window.go_entry_screen)
                elif tooltip == "Objeyi Sil":
                    button.clicked.connect(self.cube_widget.delete_selected_object)
                self.tool_buttons[tooltip] = button
                self.tool_bar_layout.addWidget(container)
        self.tool_bar_layout.addStretch()
        main_layout = QHBoxLayout(self)
        main_layout.addWidget(self.tool_bar)
        main_layout.addWidget(self.cube_widget)
        main_layout.addWidget(ObjectPanel(self.cube_widget))
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

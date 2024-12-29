from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QToolButton, QWidget,
    QPushButton, QFileDialog, QColorDialog, QStackedWidget, QDialog, QLabel,
    QComboBox, QDialogButtonBox
)
from PyQt5.QtGui import QIcon, QColor
from PyQt5.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt5.QtOpenGL import QGLWidget
from OpenGL.GL import *
from OpenGL.GLU import gluPerspective, gluNewQuadric, gluCylinder

import sys
import numpy as np
import os


class RepeatButton(QToolButton):
    """
    A QToolButton subclass that emits a signal repeatedly while pressed,
    with acceleration over time.
    """
    repeat_signal = pyqtSignal()

    def __init__(self, parent=None, initial_interval=500, min_interval=50, acceleration=0.9):
        super().__init__(parent)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.emit_repeat)
        self.initial_interval = initial_interval  # Initial delay in ms
        self.min_interval = min_interval          # Minimum interval in ms
        self.acceleration = acceleration          # Factor to decrease interval
        self.current_interval = initial_interval

    def emit_repeat(self):
        self.repeat_signal.emit()
        # Calculate the next interval with acceleration
        self.current_interval = max(int(self.current_interval * self.acceleration), self.min_interval)
        self.timer.setInterval(self.current_interval)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.repeat_signal.emit()  # Emit immediately on press
            self.current_interval = self.initial_interval
            self.timer.start(self.current_interval)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.timer.stop()
        super().mouseReleaseEvent(event)


class AddObjectDialog(QDialog):
    """
    Dialog to select the type of object to add or to load a custom OBJ file.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Object")
        self.setModal(True)
        self.selected_option = None
        self.obj_file_path = None

        layout = QVBoxLayout()

        # Dropdown to select object type
        self.combo = QComboBox()
        self.combo.addItems(["Cube", "Load OBJ"])
        layout.addWidget(QLabel("Select Object Type:"))
        layout.addWidget(self.combo)

        # Button to browse OBJ files, initially hidden
        self.browse_button = QPushButton("Browse OBJ File")
        self.browse_button.clicked.connect(self.browse_obj_file)
        self.browse_button.setVisible(False)
        layout.addWidget(self.browse_button)

        # Connect the dropdown selection to show/hide browse button
        self.combo.currentTextChanged.connect(self.on_selection_change)

        # OK and Cancel buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def on_selection_change(self, text):
        if text == "Load OBJ":
            self.browse_button.setVisible(True)
        else:
            self.browse_button.setVisible(False)

    def browse_obj_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select OBJ File", "", "OBJ Files (*.obj)")
        if file_name:
            self.obj_file_path = file_name

    def get_selection(self):
        return self.combo.currentText(), self.obj_file_path


class Cube3DWidget(QGLWidget):
    def __init__(self):
        super().__init__()
        # Scene transformation parameters
        self.rotation_matrix = np.identity(4, dtype=np.float32)  # Genel sahne döndürme matrisi
        self.x_translation = 0
        self.y_translation = 0
        self.zoom = -6.0
        self.last_mouse_position = None
        self.mode = None  # 'rotate', 'move', 'zoom', etc.
        self.bg_color = (1.0, 1.0, 1.0, 1.0)
        self.undo_stack = []
        self.redo_stack = []
        self.show_gizmo = False  # Gizmo starts as hidden
        self.objects = []
        self.selected_object = None

        # Initialize unique color ID counter for color picking
        self.next_color_id = 1  # Start from 1 to avoid black (0,0,0)

    def clear_scene(self):
        self.objects.clear()
        self.selected_object = None
        self.rotation_matrix = np.identity(4, dtype=np.float32)  # Reset sahne döndürme matrisi
        self.update()

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glClearColor(*self.bg_color)
        glEnable(GL_COLOR_MATERIAL)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_NORMALIZE)
        glEnable(GL_BLEND)  # Enable blending for transparency
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)  # Set blending function

    def resizeGL(self, w, h):
        if h == 0:
            h = 1
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, float(w) / float(h), 0.1, 50.0)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glTranslatef(self.x_translation, self.y_translation, self.zoom)

        # Apply scene rotation matrix
        glMultMatrixf(self.rotation_matrix.flatten('F'))

        # Sort objects by depth for proper transparency rendering
        sorted_objects = sorted(self.objects, key=lambda obj: obj.get("z_translation", 0), reverse=True)

        for obj in sorted_objects:
            glPushMatrix()
            glTranslatef(obj.get("x_translation", 0), obj.get("y_translation", 0), obj.get("z_translation", 0))

            # Apply object-specific scaling
            glScalef(obj.get("scale", 1.0), obj.get("scale", 1.0), obj.get("scale", 1.0))

            # Apply object-specific rotation matrix
            glMultMatrixf(obj.get("rotation_matrix", np.identity(4, dtype=np.float32)).flatten('F'))

            if obj["type"] == "cube":
                self.draw_cube(obj)
            else:
                self.draw_obj(obj)
            glPopMatrix()

        # Highlight the selected object
        if self.selected_object:
            glPushMatrix()
            glTranslatef(self.selected_object.get("x_translation", 0),
                         self.selected_object.get("y_translation", 0),
                         self.selected_object.get("z_translation", 0))
            # Apply selected object's scaling
            glScalef(self.selected_object.get("scale", 1.0), self.selected_object.get("scale", 1.0), self.selected_object.get("scale", 1.0))
            # Apply selected object's rotations for accurate highlighting
            glMultMatrixf(self.selected_object.get("rotation_matrix", np.identity(4, dtype=np.float32)).flatten('F'))
            self.draw_selection_highlight(self.selected_object)
            glPopMatrix()

        # Optionally draw the gizmo
        if self.show_gizmo and self.selected_object:
            self.draw_gizmo()

    def load_obj(self, filename):
        vertices = []
        faces = []
        colors = []
        try:
            with open(filename, 'r') as file:
                for line in file:
                    if line.startswith('v '):
                        vertices.append(list(map(float, line.strip().split()[1:4])))
                    elif line.startswith('f '):
                        face = line.strip().split()[1:]
                        face = [int(f.split('/')[0]) - 1 for f in face]
                        if len(face) >= 3:
                            # Triangulate if face has more than 3 vertices
                            for i in range(1, len(face) - 1):
                                faces.append([face[0], face[i], face[i + 1]])
                    elif line.startswith('vc '):
                        colors.append(list(map(float, line.strip().split()[1:4])))
        except Exception as e:
            print(f"Error loading OBJ file: {e}")
            return

        if vertices:
            self.center_model(vertices)

        self.objects.append({
            "id": self.next_color_id,
            "type": "obj",
            "vertices": vertices,
            "faces": faces,
            "colors": colors,
            "x_translation": 0,
            "y_translation": 0,
            "z_translation": 0,
            "rotation_matrix": np.identity(4, dtype=np.float32),  # Nesne döndürme matrisi
            "scale": 1.0,  # Ölçek faktörü
            "transparent": False  # Saydamlık bayrağı
        })
        self.next_color_id += 1
        self.update()

    def center_model(self, vertices):
        x_coords = [v[0] for v in vertices]
        y_coords = [v[1] for v in vertices]
        z_coords = [v[2] for v in vertices]
        x_center = (max(x_coords) + min(x_coords)) / 2
        y_center = (max(y_coords) + min(y_coords)) / 2
        z_center = (max(z_coords) + min(z_coords)) / 2
        for i in range(len(vertices)):
            vertices[i][0] -= x_center
            vertices[i][1] -= y_center
            vertices[i][2] -= z_center

    def draw_obj(self, obj):
        if not obj["vertices"] or not obj["faces"]:
            return
        glBegin(GL_TRIANGLES)
        for face in obj["faces"]:
            for v_idx in face:
                if obj["colors"]:
                    color = obj["colors"][v_idx]
                    alpha = 0.1 if obj.get("transparent", False) else 1.0
                    glColor4f(color[0], color[1], color[2], alpha)
                else:
                    alpha = 0.1 if obj.get("transparent", False) else 1.0
                    glColor4f(0.8, 0.8, 0.8, alpha)  # Default color
                glVertex3fv(obj["vertices"][v_idx])
        glEnd()

    def draw_cube(self, obj):
        # Set color based on selection and transparency
        if self.selected_object and obj["id"] == self.selected_object["id"]:
            base_color = (1.0, 1.0, 0.0)  # Highlight color (yellow)
        else:
            base_color = (0.0, 0.5, 1.0)  # Default cube color (blueish)

        alpha = 0.1 if obj.get("transparent", False) else 1.0
        glColor4f(*base_color, alpha)

        glBegin(GL_QUADS)
        # Front face
        glNormal3f(0.0, 0.0, 1.0)
        glVertex3f(-1.0, -1.0, 1.0)
        glVertex3f(1.0, -1.0, 1.0)
        glVertex3f(1.0, 1.0, 1.0)
        glVertex3f(-1.0, 1.0, 1.0)

        # Back face
        glNormal3f(0.0, 0.0, -1.0)
        glVertex3f(-1.0, -1.0, -1.0)
        glVertex3f(-1.0, 1.0, -1.0)
        glVertex3f(1.0, 1.0, -1.0)
        glVertex3f(1.0, -1.0, -1.0)

        # Left face
        glNormal3f(-1.0, 0.0, 0.0)
        glVertex3f(-1.0, -1.0, -1.0)
        glVertex3f(-1.0, -1.0, 1.0)
        glVertex3f(-1.0, 1.0, 1.0)
        glVertex3f(-1.0, 1.0, -1.0)

        # Right face
        glNormal3f(1.0, 0.0, 0.0)
        glVertex3f(1.0, -1.0, -1.0)
        glVertex3f(1.0, 1.0, -1.0)
        glVertex3f(1.0, 1.0, 1.0)
        glVertex3f(1.0, -1.0, 1.0)

        # Top face
        glNormal3f(0.0, 1.0, 0.0)
        glVertex3f(-1.0, 1.0, -1.0)
        glVertex3f(-1.0, 1.0, 1.0)
        glVertex3f(1.0, 1.0, 1.0)
        glVertex3f(1.0, 1.0, -1.0)

        # Bottom face
        glNormal3f(0.0, -1.0, 0.0)
        glVertex3f(-1.0, -1.0, -1.0)
        glVertex3f(-1.0, -1.0, 1.0)
        glVertex3f(1.0, -1.0, 1.0)
        glVertex3f(1.0, -1.0, -1.0)
        glEnd()

    def draw_arrow(self, length=1.0, shaft_radius=0.02, head_length=0.15, head_radius=0.06):
        quad = gluNewQuadric()
        gluCylinder(quad, shaft_radius, shaft_radius, length, 12, 1)
        glTranslatef(0, 0, length)
        gluCylinder(quad, head_radius, 0.0, head_length, 12, 1)

    def draw_gizmo(self):
        """
        Draws a gizmo (transformation tool) for the selected object.
        The gizmo is always centered at the selected object's origin.
        """
        if not self.selected_object:
            return  # No object selected; nothing to draw

        # Determine the position and scale for the gizmo
        # Here, we assume the gizmo is centered at the object's position
        glDisable(GL_LIGHTING)  # Disable lighting for gizmo visibility
        glLineWidth(3.0)
        glPushMatrix()
        glTranslatef(0, 0, 0)  # Gizmo is already translated with the object
        glPushMatrix()
        glColor3f(1.0, 0.0, 0.0)  # X-axis in red
        self.draw_arrow()
        glPopMatrix()
        glPushMatrix()
        glRotatef(90, 0, 1, 0)  # Rotate to align with Y-axis
        glColor3f(0.0, 1.0, 0.0)  # Y-axis in green
        self.draw_arrow()
        glPopMatrix()
        glPushMatrix()
        glRotatef(-90, 1, 0, 0)  # Rotate to align with Z-axis
        glColor3f(0.0, 0.0, 1.0)  # Z-axis in blue
        self.draw_arrow()
        glPopMatrix()
        glPopMatrix()
        glEnable(GL_LIGHTING)  # Re-enable lighting
        glLineWidth(1.0)

    def toggle_gizmo(self):
        self.show_gizmo = not self.show_gizmo
        self.update()

    def add_cube(self):
        # Her yeni küp için benzersiz bir pozisyon belirle
        position_offset = len(self.objects) * 2  # Yeni küpler arasındaki mesafeyi artır
        self.objects.append({
            "id": self.next_color_id,
            "type": "cube",
            "vertices": [],
            "faces": [],
            "colors": [],
            "x_translation": position_offset,  # X ekseni boyunca farklı bir konum
            "y_translation": 0,  # Sabit Y konumu
            "z_translation": 0,  # Sabit Z konumu
            "rotation_matrix": np.identity(4, dtype=np.float32),  # Nesne döndürme matrisi
            "scale": 1.0,  # Ölçek faktörü
            "transparent": False  # Saydamlık bayrağı
        })
        self.next_color_id += 1
        self.update()

    def set_background_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.bg_color = (color.redF(), color.greenF(), color.blueF(), 1.0)
            glClearColor(*self.bg_color)
            self.update()

    def save_state(self):
        state = {
            "objects": [obj.copy() for obj in self.objects],  # Shallow copy
            "rotation_matrix": self.rotation_matrix.copy(),
            "x_translation": self.x_translation,
            "y_translation": self.y_translation,
            "zoom": self.zoom,
            "selected_object_id": self.selected_object["id"] if self.selected_object else None
        }
        # Deep copy of rotation matrices, scale, and transparency for each object
        for obj in state["objects"]:
            obj["rotation_matrix"] = obj.get("rotation_matrix", np.identity(4, dtype=np.float32)).copy()
            obj["scale"] = obj.get("scale", 1.0)
            obj["transparent"] = obj.get("transparent", False)
        self.undo_stack.append(state)
        self.redo_stack.clear()

    def load_state(self, state):
        self.objects = [obj.copy() for obj in state["objects"]]
        self.rotation_matrix = state["rotation_matrix"].copy()
        self.x_translation = state["x_translation"]
        self.y_translation = state["y_translation"]
        self.zoom = state["zoom"]
        selected_id = state.get("selected_object_id")
        self.selected_object = next((obj for obj in self.objects if obj["id"] == selected_id), None)
        self.update()

    def undo(self):
        if self.undo_stack:
            state = self.undo_stack.pop()
            redo_state = {
                "objects": [obj.copy() for obj in self.objects],
                "rotation_matrix": self.rotation_matrix.copy(),
                "x_translation": self.x_translation,
                "y_translation": self.y_translation,
                "zoom": self.zoom,
                "selected_object_id": self.selected_object["id"] if self.selected_object else None
            }
            # Deep copy of rotation matrices, scale, and transparency for each object
            for obj in redo_state["objects"]:
                obj["rotation_matrix"] = obj.get("rotation_matrix", np.identity(4, dtype=np.float32)).copy()
                obj["scale"] = obj.get("scale", 1.0)
                obj["transparent"] = obj.get("transparent", False)
            self.redo_stack.append(redo_state)
            self.load_state(state)

    def redo(self):
        if self.redo_stack:
            state = self.redo_stack.pop()
            undo_state = {
                "objects": [obj.copy() for obj in self.objects],
                "rotation_matrix": self.rotation_matrix.copy(),
                "x_translation": self.x_translation,
                "y_translation": self.y_translation,
                "zoom": self.zoom,
                "selected_object_id": self.selected_object["id"] if self.selected_object else None
            }
            # Deep copy of rotation matrices, scale, and transparency for each object
            for obj in undo_state["objects"]:
                obj["rotation_matrix"] = obj.get("rotation_matrix", np.identity(4, dtype=np.float32)).copy()
                obj["scale"] = obj.get("scale", 1.0)
                obj["transparent"] = obj.get("transparent", False)
            self.undo_stack.append(undo_state)
            self.load_state(state)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.save_state()
            self.last_mouse_position = event.pos()
            # Handle object selection using color picking
            clicked_object = self.pick_object(event.pos())
            self.selected_object = clicked_object
            self.update()
        elif event.button() == Qt.RightButton:
            self.last_mouse_position = event.pos()

    def mouseMoveEvent(self, event):
        if self.last_mouse_position is not None:
            delta = event.pos() - self.last_mouse_position
            shift_pressed = event.modifiers() & Qt.ShiftModifier  # Shift key check

            if self.selected_object:
                if self.mode == "rotate":
                    # Handle individual object rotation only when selected and mode is rotate
                    angle_x = delta.y()
                    angle_y = delta.x()

                    if shift_pressed:
                        rotation_z = self.create_rotation_matrix(angle_y, 0, 0, 1)
                        self.selected_object["rotation_matrix"] = np.dot(rotation_z,
                                                                         self.selected_object["rotation_matrix"])
                    else:
                        rotation_x = self.create_rotation_matrix(angle_x, 1, 0, 0)
                        rotation_y = self.create_rotation_matrix(angle_y, 0, 1, 0)
                        rotation = np.dot(rotation_y, rotation_x)
                        self.selected_object["rotation_matrix"] = np.dot(rotation,
                                                                         self.selected_object["rotation_matrix"])
                elif self.mode == "move":
                    # Handle individual object movement
                    if shift_pressed:
                        self.selected_object["z_translation"] += delta.y() * 0.01
                    else:
                        self.selected_object["x_translation"] += delta.x() * 0.01
                        self.selected_object["y_translation"] -= delta.y() * 0.01
                elif self.mode == "zoom":
                    # Handle object scaling
                    scale_change = 1 + (delta.y() * 0.01)  # Scale factor based on vertical mouse movement
                    new_scale = self.selected_object.get("scale", 1.0) * scale_change
                    new_scale = max(new_scale, 0.1)  # Prevent scaling below 0.1
                    self.selected_object["scale"] = new_scale
                elif self.mode == "transparency":  # Yeni mod: Transparency
                    # Toggle transparency on horizontal movement
                    if delta.x() > 0:
                        # Artırarak saydamlaştır
                        self.set_object_transparency(self.selected_object, True)
                    elif delta.x() < 0:
                        # Azaltarak opaklaştır
                        self.set_object_transparency(self.selected_object, False)

            else:
                if self.mode == "move":
                    # Handle global movement
                    if shift_pressed:
                        # Zoom yapmayı engelledik
                        pass  # self.zoom += delta.y() * 0.01  # <-- Bu satırı kaldırdık veya yorum haline getirdik
                    else:
                        self.x_translation += delta.x() * 0.01
                        self.y_translation -= delta.y() * 0.01

            self.last_mouse_position = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        self.last_mouse_position = None

    def wheelEvent(self, event):
        # Eğer sahne zoomunu devre dışı bırakmak istiyorsanız, bu metodu boş bırakabilirsiniz.
        # Ancak, hala sahne zoomunu fare tekeri ile kullanmak istiyorsanız, bu kısmı koruyabilirsiniz.
        if event.angleDelta().y() != 0:
            self.save_state()
            delta = event.angleDelta().y()
            self.zoom += delta * 0.001
            self.update()

    def set_mode(self, mode):
        self.mode = mode

    def set_object_transparency(self, obj, transparent):
        if obj:
            obj["transparent"] = transparent
            self.update()

    def pick_object(self, pos):
        # Save OpenGL state
        glPushAttrib(GL_ALL_ATTRIB_BITS)

        # Disable lighting and other color effects
        glDisable(GL_LIGHTING)
        glDisable(GL_COLOR_MATERIAL)
        glDisable(GL_TEXTURE_2D)
        glShadeModel(GL_FLAT)
        glDisable(GL_BLEND)

        # Clear buffers
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glTranslatef(self.x_translation, self.y_translation, self.zoom)
        glMultMatrixf(self.rotation_matrix.flatten('F'))

        # Draw all objects with unique colors
        for obj in self.objects:
            glPushMatrix()
            glTranslatef(obj.get("x_translation", 0), obj.get("y_translation", 0), obj.get("z_translation", 0))
            # Apply object-specific scaling
            glScalef(obj.get("scale", 1.0), obj.get("scale", 1.0), obj.get("scale", 1.0))
            # Apply object-specific rotations
            glMultMatrixf(obj.get("rotation_matrix", np.identity(4, dtype=np.float32)).flatten('F'))

            # Convert object ID to color
            r = ((obj["id"] & 0xFF0000) >> 16) / 255.0
            g = ((obj["id"] & 0x00FF00) >> 8) / 255.0
            b = (obj["id"] & 0x0000FF) / 255.0
            glColor3f(r, g, b)

            # Draw the object based on its type
            if obj["type"] == "cube":
                self.draw_cube_selection(obj)
            else:
                self.draw_obj_selection(obj)
            glPopMatrix()

        glFlush()
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        x = pos.x()
        y = self.height() - pos.y()  # OpenGL coordinate system differs
        pixel = glReadPixels(x, y, 1, 1, GL_RGB, GL_UNSIGNED_BYTE)
        r, g, b = pixel[0], pixel[1], pixel[2]
        picked_id = (r << 16) + (g << 8) + b

        # Restore OpenGL state
        glPopAttrib()

        if picked_id == 0:
            return None  # No object selected

        # Find the selected object
        for obj in self.objects:
            if obj["id"] == picked_id:
                return obj

        return None

    def draw_obj_selection(self, obj):
        if not obj["vertices"] or not obj["faces"]:
            return
        glBegin(GL_TRIANGLES)
        for face in obj["faces"]:
            for v_idx in face:
                glVertex3fv(obj["vertices"][v_idx])
        glEnd()

    def draw_cube_selection(self, obj):
        glBegin(GL_QUADS)
        # Front face
        glNormal3f(0.0, 0.0, 1.0)
        glVertex3f(-1.0, -1.0, 1.0)
        glVertex3f(1.0, -1.0, 1.0)
        glVertex3f(1.0, 1.0, 1.0)
        glVertex3f(-1.0, 1.0, 1.0)

        # Back face
        glNormal3f(0.0, 0.0, -1.0)
        glVertex3f(-1.0, -1.0, -1.0)
        glVertex3f(-1.0, 1.0, -1.0)
        glVertex3f(1.0, 1.0, -1.0)
        glVertex3f(1.0, -1.0, -1.0)

        # Left face
        glNormal3f(-1.0, 0.0, 0.0)
        glVertex3f(-1.0, -1.0, -1.0)
        glVertex3f(-1.0, -1.0, 1.0)
        glVertex3f(-1.0, 1.0, 1.0)
        glVertex3f(-1.0, 1.0, -1.0)

        # Right face
        glNormal3f(1.0, 0.0, 0.0)
        glVertex3f(1.0, -1.0, -1.0)
        glVertex3f(1.0, 1.0, -1.0)
        glVertex3f(1.0, 1.0, 1.0)
        glVertex3f(1.0, -1.0, 1.0)

        # Top face
        glNormal3f(0.0, 1.0, 0.0)
        glVertex3f(-1.0, 1.0, -1.0)
        glVertex3f(-1.0, 1.0, 1.0)
        glVertex3f(1.0, 1.0, 1.0)
        glVertex3f(1.0, 1.0, -1.0)

        # Bottom face
        glNormal3f(0.0, -1.0, 0.0)
        glVertex3f(-1.0, -1.0, -1.0)
        glVertex3f(-1.0, -1.0, 1.0)
        glVertex3f(1.0, -1.0, 1.0)
        glVertex3f(1.0, -1.0, -1.0)
        glEnd()

    def draw_selection_highlight(self, obj):
        """
        Draw a wireframe around the selected object to highlight it.
        """
        glDisable(GL_LIGHTING)
        glColor3f(1.0, 1.0, 1.0)  # White color for highlight
        glLineWidth(2.0)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)

        if obj["type"] == "cube":
            self.draw_cube(obj)
        else:
            self.draw_obj(obj)

        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glEnable(GL_LIGHTING)

    def delete_selected_object(self):
        if self.selected_object:
            self.save_state()
            self.objects.remove(self.selected_object)
            self.selected_object = None
            self.update()

    def create_rotation_matrix(self, angle, x, y, z):
        """
        Creates a rotation matrix given an angle in degrees and an axis.
        """
        rad = np.deg2rad(angle)
        c = np.cos(rad)
        s = np.sin(rad)
        norm = np.sqrt(x * x + y * y + z * z)
        if norm == 0:
            return np.identity(4, dtype=np.float32)
        x /= norm
        y /= norm
        z /= norm
        rotation = np.array([
            [c + (1 - c) * x * x,       (1 - c) * x * y - s * z, (1 - c) * x * z + s * y, 0],
            [(1 - c) * y * x + s * z,   c + (1 - c) * y * y,     (1 - c) * y * z - s * x, 0],
            [(1 - c) * z * x - s * y,   (1 - c) * z * y + s * x, c + (1 - c) * z * z,     0],
            [0,                         0,                       0,                       1]
        ], dtype=np.float32)
        return rotation


class EntryScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        # Load icons only if they exist to prevent errors
        cube_icon_path = "Images/3d-cube.png"
        upload_icon_path = "Images/upload.png"

        cube_icon = QIcon(cube_icon_path) if os.path.exists(cube_icon_path) else QIcon.fromTheme("cube")
        upload_icon = QIcon(upload_icon_path) if os.path.exists(upload_icon_path) else QIcon.fromTheme("document-open")

        self.cube_button = QPushButton("Küp Göster")
        self.cube_button.setIcon(cube_icon)
        self.cube_button.clicked.connect(self.show_cube)

        self.upload_button = QPushButton("OBJ Yükle")
        self.upload_button.setIcon(upload_icon)
        self.upload_button.clicked.connect(self.upload_obj)

        layout.addWidget(self.cube_button)
        layout.addWidget(self.upload_button)
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


class MainScreen(QWidget):
    def __init__(self, main_window, cube_widget):
        super().__init__()
        self.main_window = main_window
        self.cube_widget = cube_widget

        self.active_style = """
            QToolButton {
                background-color: #b0c4de;
                border: 1px solid #666;
                border-radius: 5px;
                margin: 5px;
                padding: 10px;
            }
            QToolButton:hover {
                background-color: #a0b4ce;
            }
        """
        self.inactive_style = """
            QToolButton {
                background-color: #ffffff;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin: 5px;
                padding: 10px;
            }
            QToolButton:hover {
                background-color: #e0e0e0;
            }
        """

        self.tool_buttons = {}
        self.tool_bar = QWidget()
        self.tool_bar_layout = QVBoxLayout(self.tool_bar)
        self.tool_bar.setFixedWidth(100)
        self.tool_bar.setStyleSheet("background-color: #f0f0f0; border-right: 1px solid #ccc;")

        # Icons list
        icons = [
            {"icon": "Images/cursor.png", "tooltip": "Cursor"},
            {"icon": "Images/circle-of-two-clockwise-arrows-rotation.png", "tooltip": "Rotate"},
            {"icon": "Images/expand-arrows.png", "tooltip": "Move"},
            {"icon": "Images/zoom-in.png", "tooltip": "Zoom"},  # "Zoom" butonunu geri ekledik
            {"icon": "Images/transparency.png", "tooltip": "Transparency"},  # Yeni Transparency butonu
            {"icon": "Images/color-wheel.png", "tooltip": "Background Color"},
            {"icon": "Images/scissors.png", "tooltip": "Cut"},
            {"icon": "Images/delete.png", "tooltip": "Objeyi Sil"},  # Delete button
            {"icon": "Images/back.png", "tooltip": "Undo"},
            {"icon": "Images/redo-arrow.png", "tooltip": "Redo"},
            {"icon": "Images/add-object.png", "tooltip": "Add Object"},  # Add Object button
            {"icon": "Images/home.png", "tooltip": "Giriş Ekranına Dön"}
        ]

        for item in icons:
            icon_path = item["icon"]
            tooltip = item["tooltip"]
            if tooltip in ["Undo", "Redo"]:
                # Use RepeatButton for Undo and Redo
                button = RepeatButton(initial_interval=500, min_interval=100, acceleration=0.8)
                if os.path.exists(icon_path):
                    button.setIcon(QIcon(icon_path))
                else:
                    # Fallback to a default icon if not found
                    default_icon = QIcon.fromTheme("edit-undo") if tooltip == "Undo" else QIcon.fromTheme("edit-redo")
                    button.setIcon(default_icon)
                button.setToolTip(tooltip)
                button.setStyleSheet(self.inactive_style)
                if tooltip == "Undo":
                    button.repeat_signal.connect(self.cube_widget.undo)
                elif tooltip == "Redo":
                    button.repeat_signal.connect(self.cube_widget.redo)
            else:
                # Use regular QToolButton for other tools
                button = QToolButton()
                if os.path.exists(icon_path):
                    button.setIcon(QIcon(icon_path))
                else:
                    # Fallback to a default icon based on tooltip
                    if tooltip == "Cursor":
                        default_icon = QIcon.fromTheme("cursor-arrow")
                    elif tooltip == "Rotate":
                        default_icon = QIcon.fromTheme("object-rotate-right")
                    elif tooltip == "Move":
                        default_icon = QIcon.fromTheme("transform-move")
                    elif tooltip == "Zoom":
                        default_icon = QIcon.fromTheme("transform-scale")  # Ölçeklendirme için uygun bir tema ikonu
                    elif tooltip == "Transparency":
                        default_icon = QIcon.fromTheme("view-transparency")  # Transparency için uygun bir tema ikonu
                    elif tooltip == "Background Color":
                        default_icon = QIcon.fromTheme("color-picker")
                    elif tooltip == "Cut":
                        default_icon = QIcon.fromTheme("edit-cut")
                    elif tooltip == "Objeyi Sil":
                        default_icon = QIcon.fromTheme("edit-delete")
                    elif tooltip == "Add Object":
                        default_icon = QIcon.fromTheme("list-add")
                    elif tooltip == "Giriş Ekranına Dön":
                        default_icon = QIcon.fromTheme("go-home")
                    else:
                        default_icon = QIcon()
                    button.setIcon(default_icon)
                button.setToolTip(tooltip)
                button.setStyleSheet(self.inactive_style)
                if tooltip in ["Cursor", "Rotate", "Move", "Zoom", "Cut", "Transparency"]:
                    button.clicked.connect(lambda checked, tool=tooltip: self.activate_tool(tool))
                elif tooltip == "Background Color":
                    button.clicked.connect(self.cube_widget.set_background_color)
                elif tooltip == "Add Object":
                    button.clicked.connect(self.add_object)
                elif tooltip == "Giriş Ekranına Dön":
                    button.clicked.connect(self.main_window.go_entry_screen)
                elif tooltip == "Objeyi Sil":
                    button.clicked.connect(self.cube_widget.delete_selected_object)

            self.tool_buttons[tooltip] = button
            self.tool_bar_layout.addWidget(button)

        self.tool_bar_layout.addStretch()  # Push buttons to the top

        main_layout = QHBoxLayout(self)
        main_layout.addWidget(self.tool_bar)
        main_layout.addWidget(self.cube_widget)
        self.setLayout(main_layout)

    def activate_tool(self, tool):
        # Update button styles
        for ttip, btn in self.tool_buttons.items():
            if ttip in ["Cursor", "Rotate", "Move", "Zoom", "Cut", "Transparency"]:
                if ttip == tool:
                    btn.setStyleSheet(self.active_style)
                else:
                    btn.setStyleSheet(self.inactive_style)

        # Set the transformation mode
        if tool == "Cursor":
            self.cube_widget.set_mode(None)
        elif tool == "Rotate":
            self.cube_widget.set_mode("rotate")
        elif tool == "Move":
            self.cube_widget.set_mode("move")
        elif tool == "Zoom":
            self.cube_widget.set_mode("zoom")  # "Zoom" modunu ayarla
        elif tool == "Cut":
            self.cube_widget.set_mode("cut")
        elif tool == "Transparency":
            self.cube_widget.set_mode("transparency")  # Yeni "transparency" modunu ayarla

    def add_object(self):
        """
        Open the AddObjectDialog to allow users to add a Cube or load an OBJ file.
        """
        dialog = AddObjectDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            selected_type, obj_file = dialog.get_selection()
            if selected_type == "Cube":
                self.cube_widget.add_cube()
            elif selected_type == "Load OBJ" and obj_file:
                self.cube_widget.load_obj(obj_file)
            self.main_window.go_main_screen()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Görüntüleme (QStackedWidget)")
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.entry_screen = EntryScreen(self)
        self.cube_widget = Cube3DWidget()
        self.main_screen = MainScreen(self, self.cube_widget)
        self.stack.addWidget(self.entry_screen)
        self.stack.addWidget(self.main_screen)
        self.stack.setCurrentIndex(0)
        self.resize(800, 600)

    def go_entry_screen(self):
        self.stack.setCurrentIndex(0)

    def go_main_screen(self):
        self.stack.setCurrentIndex(1)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

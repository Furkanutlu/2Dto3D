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
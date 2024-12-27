from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QToolButton, QWidget,
    QPushButton, QFileDialog, QColorDialog, QStackedWidget, QDialog, QLabel,
    QComboBox, QDialogButtonBox
)
from PyQt5.QtGui import QIcon, QColor
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtOpenGL import QGLWidget
from OpenGL.GL import *
from OpenGL.GLU import gluPerspective, gluNewQuadric, gluCylinder

import sys


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
        self.combo.addItems(["Cube", "Load OBJ"])  # Removed "Sphere" option
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
        self.x_rotation = 0
        self.y_rotation = 0
        self.z_rotation = 0  # Additional Z rotation
        self.x_translation = 0
        self.y_translation = 0
        self.zoom = -6.0
        self.last_mouse_position = None
        self.mode = None
        self.bg_color = (1.0, 1.0, 1.0, 1.0)
        self.undo_stack = []
        self.redo_stack = []
        self.show_gizmo = False  # Gizmo starts as hidden
        self.picked_axis = None
        self.objects = []
        self.selected_object = None

        # Initialize unique color ID counter for color picking
        self.next_color_id = 1  # Start from 1 to avoid black (0,0,0)

    def clear_scene(self):
        self.objects.clear()
        self.selected_object = None
        self.update()

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glClearColor(*self.bg_color)
        glEnable(GL_COLOR_MATERIAL)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_NORMALIZE)

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
        glRotatef(self.x_rotation, 1.0, 0.0, 0.0)
        glRotatef(self.y_rotation, 0.0, 1.0, 0.0)
        glRotatef(self.z_rotation, 0.0, 0.0, 1.0)  # Additional Z rotation

        for obj in self.objects:
            glPushMatrix()
            glTranslatef(obj.get("x_translation", 0), obj.get("y_translation", 0), obj.get("z_translation", 0))

            # Apply object-specific rotations
            glRotatef(obj.get("rot_x", 0), 1.0, 0.0, 0.0)
            glRotatef(obj.get("rot_y", 0), 0.0, 1.0, 0.0)
            glRotatef(obj.get("rot_z", 0), 0.0, 0.0, 1.0)

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
            # Apply selected object's rotations for accurate highlighting
            glRotatef(self.selected_object.get("rot_x", 0), 1.0, 0.0, 0.0)
            glRotatef(self.selected_object.get("rot_y", 0), 0.0, 1.0, 0.0)
            glRotatef(self.selected_object.get("rot_z", 0), 0.0, 0.0, 1.0)
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
            "rot_x": 0,  # Rotation around X-axis
            "rot_y": 0,  # Rotation around Y-axis
            "rot_z": 0  # Rotation around Z-axis
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
                    glColor3fv(obj["colors"][v_idx])
                else:
                    glColor3f(0.8, 0.8, 0.8)  # Default color
                glVertex3fv(obj["vertices"][v_idx])
        glEnd()

    def draw_cube(self, obj):
        # Set color based on selection
        if self.selected_object and obj["id"] == self.selected_object["id"]:
            glColor3f(1.0, 1.0, 0.0)  # Highlight color (yellow)
        else:
            glColor3f(0.0, 0.5, 1.0)  # Default cube color (blueish)

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
        # Add a new cube with unique color ID and rotation parameters
        self.objects.append({
            "id": self.next_color_id,
            "type": "cube",
            "vertices": [],
            "faces": [],
            "colors": [],
            "x_translation": 0,
            "y_translation": 0,
            "z_translation": 0,
            "rot_x": 0,  # Rotation around X-axis
            "rot_y": 0,  # Rotation around Y-axis
            "rot_z": 0  # Rotation around Z-axis
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
            "objects": [obj.copy() for obj in self.objects],  # Deep copy
            "x_rotation": self.x_rotation,
            "y_rotation": self.y_rotation,
            "z_rotation": self.z_rotation,  # Additional Z rotation
            "x_translation": self.x_translation,
            "y_translation": self.y_translation,
            "zoom": self.zoom,
            "selected_object_id": self.selected_object["id"] if self.selected_object else None
        }
        self.undo_stack.append(state)
        self.redo_stack.clear()

    def load_state(self, state):
        self.objects = [obj.copy() for obj in state["objects"]]
        self.x_rotation = state["x_rotation"]
        self.y_rotation = state["y_rotation"]
        self.z_rotation = state.get("z_rotation", 0)  # Additional Z rotation
        self.x_translation = state["x_translation"]
        self.y_translation = state["y_translation"]
        self.zoom = state["zoom"]
        selected_id = state.get("selected_object_id")
        self.selected_object = next((obj for obj in self.objects if obj["id"] == selected_id), None)
        self.update()

    def undo(self):
        if self.undo_stack:
            state = self.undo_stack.pop()
            self.redo_stack.append({
                "objects": [obj.copy() for obj in self.objects],
                "x_rotation": self.x_rotation,
                "y_rotation": self.y_rotation,
                "z_rotation": self.z_rotation,  # Additional Z rotation
                "x_translation": self.x_translation,
                "y_translation": self.y_translation,
                "zoom": self.zoom,
                "selected_object_id": self.selected_object["id"] if self.selected_object else None
            })
            self.load_state(state)

    def redo(self):
        if self.redo_stack:
            state = self.redo_stack.pop()
            self.undo_stack.append({
                "objects": [obj.copy() for obj in self.objects],
                "x_rotation": self.x_rotation,
                "y_rotation": self.y_rotation,
                "z_rotation": self.z_rotation,  # Additional Z rotation
                "x_translation": self.x_translation,
                "y_translation": self.y_translation,
                "zoom": self.zoom,
                "selected_object_id": self.selected_object["id"] if self.selected_object else None
            })
            self.load_state(state)

    def mousePressEvent(self, event):
        self.save_state()
        if event.button() == Qt.LeftButton:
            self.last_mouse_position = event.pos()
            # Handle object selection using color picking
            clicked_object = self.pick_object(event.pos())
            self.selected_object = clicked_object
            self.update()
        if event.button() == Qt.RightButton:
            self.last_mouse_position = event.pos()

    def mouseMoveEvent(self, event):
        if self.last_mouse_position is not None:
            delta = event.pos() - self.last_mouse_position
            shift_pressed = event.modifiers() & Qt.ShiftModifier  # Check if Shift key is held

            if self.selected_object:
                if (event.buttons() == Qt.LeftButton and self.mode == "rotate"):
                    if shift_pressed:
                        # Rotate only around Z-axis
                        self.selected_object["rot_z"] += delta.x()
                    else:
                        # Rotate around X and Y axes
                        self.selected_object["rot_x"] += delta.y()
                        self.selected_object["rot_y"] += delta.x()
                    self.last_mouse_position = event.pos()
                    self.update()
                elif (event.buttons() == Qt.LeftButton and self.mode == "move"):
                    if shift_pressed:
                        # Move along Z-axis when Shift is held
                        self.selected_object["z_translation"] += delta.y() * 0.01
                    else:
                        # Move along X and Y axes
                        self.selected_object["x_translation"] += delta.x() * 0.01
                        self.selected_object["y_translation"] -= delta.y() * 0.01
                    self.last_mouse_position = event.pos()
                    self.update()
            else:
                # Handle rotation when no object is selected
                if (event.buttons() == Qt.LeftButton and self.mode == "rotate"):
                    if shift_pressed:
                        # Rotate only around Z-axis
                        self.z_rotation += delta.x()
                    else:
                        # Rotate around X and Y axes
                        self.x_rotation += delta.y()
                        self.y_rotation += delta.x()
                    self.last_mouse_position = event.pos()
                    self.update()
                elif (event.buttons() == Qt.LeftButton and self.mode == "move"):
                    if shift_pressed:
                        self.zoom += delta.y() * 0.01  # Example: Zoom in/out with Shift + Move
                    else:
                        self.x_translation += delta.x() * 0.01
                        self.y_translation += delta.y() * 0.01
                    self.last_mouse_position = event.pos()
                    self.update()
                elif event.buttons() == Qt.RightButton:
                    if shift_pressed:
                        # Optionally, define behavior for right-click with Shift
                        pass
                    self.x_rotation += delta.y()
                    self.y_rotation += delta.x()
                    self.z_rotation += delta.x() if shift_pressed else 0  # Extra Z rotation if Shift is pressed
                    self.last_mouse_position = event.pos()
                    self.update()

    def mouseReleaseEvent(self, event):
        self.last_mouse_position = None

    def wheelEvent(self, event):
        self.save_state()
        delta = event.angleDelta().y()
        self.zoom += delta * 0.001
        self.update()

    def set_mode(self, mode):
        self.mode = mode

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
        glRotatef(self.x_rotation, 1.0, 0.0, 0.0)
        glRotatef(self.y_rotation, 0.0, 1.0, 0.0)
        glRotatef(self.z_rotation, 0.0, 0.0, 1.0)  # Additional Z rotation

        # Draw all objects with unique colors
        for obj in self.objects:
            glPushMatrix()
            glTranslatef(obj.get("x_translation", 0), obj.get("y_translation", 0), obj.get("z_translation", 0))
            # Apply object-specific rotations
            glRotatef(obj.get("rot_x", 0), 1.0, 0.0, 0.0)
            glRotatef(obj.get("rot_y", 0), 0.0, 1.0, 0.0)
            glRotatef(obj.get("rot_z", 0), 0.0, 0.0, 1.0)

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


class EntryScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        # Load icons only if they exist to prevent errors
        cube_icon = QIcon("Images/3d-cube.png") if QIcon("Images/3d-cube.png").isNull() == False else QIcon()
        upload_icon = QIcon("Images/upload.png") if QIcon("Images/upload.png").isNull() == False else QIcon()

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
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

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

        # Updated icons list without the "Toggle Gizmo" tool
        icons = [
            {"icon": "Images/cursor.png", "tooltip": "Cursor"},
            {"icon": "Images/circle-of-two-clockwise-arrows-rotation.png", "tooltip": "Rotate"},
            {"icon": "Images/expand-arrows.png", "tooltip": "Move"},
            {"icon": "Images/zoom-in.png", "tooltip": "Zoom"},
            {"icon": "Images/color-wheel.png", "tooltip": "Background Color"},
            {"icon": "Images/scissors.png", "tooltip": "Cut"},
            {"icon": "Images/delete.png", "tooltip": "Objeyi Sil"},  # Delete button
            {"icon": "Images/back.png", "tooltip": "Undo"},
            {"icon": "Images/redo-arrow.png", "tooltip": "Redo"},
            {"icon": "Images/add-object.png", "tooltip": "Add Object"},  # New Add Object button
            {"icon": "Images/home.png", "tooltip": "Giriş Ekranına Dön"}
        ]

        for item in icons:
            button = QToolButton()
            button.setIcon(QIcon(item["icon"]))
            button.setToolTip(item["tooltip"])
            button.setStyleSheet(self.inactive_style)
            if item["tooltip"] in ["Cursor", "Rotate", "Move", "Zoom", "Cut"]:
                button.clicked.connect(lambda checked, tool=item["tooltip"]: self.activate_tool(tool))
            elif item["tooltip"] == "Background Color":
                button.clicked.connect(self.main_window.cube_widget.set_background_color)
            elif item["tooltip"] == "Undo":
                button.clicked.connect(self.main_window.cube_widget.undo)
            elif item["tooltip"] == "Redo":
                button.clicked.connect(self.main_window.cube_widget.redo)
            elif item["tooltip"] == "Add Object":
                button.clicked.connect(self.add_object)
            elif item["tooltip"] == "Giriş Ekranına Dön":
                button.clicked.connect(self.main_window.go_entry_screen)
            elif item["tooltip"] == "Objeyi Sil":  # Connect the delete button
                button.clicked.connect(self.main_window.cube_widget.delete_selected_object)

            self.tool_buttons[item["tooltip"]] = button
            self.tool_bar_layout.addWidget(button)

        self.tool_bar_layout.addStretch()  # Push buttons to the top

        main_layout = QHBoxLayout(self)
        main_layout.addWidget(self.tool_bar)
        main_layout.addWidget(self.main_window.cube_widget)
        self.setLayout(main_layout)

    def activate_tool(self, tool):
        for ttip, btn in self.tool_buttons.items():
            if ttip in ["Cursor", "Rotate", "Move", "Zoom", "Cut"]:
                if ttip == tool:
                    btn.setStyleSheet(self.active_style)
                else:
                    btn.setStyleSheet(self.inactive_style)

        if tool == "Cursor":
            self.main_window.cube_widget.set_mode(None)
        elif tool == "Rotate":
            self.main_window.cube_widget.set_mode("rotate")
        elif tool == "Move":
            self.main_window.cube_widget.set_mode("move")
        elif tool == "Zoom":
            self.main_window.cube_widget.set_mode("zoom")
        elif tool == "Cut":
            self.main_window.cube_widget.set_mode("cut")

    def add_object(self):
        """
        Open the AddObjectDialog to allow users to add a Cube or load an OBJ file.
        """
        dialog = AddObjectDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            selected_type, obj_file = dialog.get_selection()
            if selected_type == "Cube":
                self.main_window.cube_widget.add_cube()
            elif selected_type == "Load OBJ" and obj_file:
                self.main_window.cube_widget.load_obj(obj_file)
            self.main_window.go_main_screen()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Görüntüleme (QStackedWidget)")
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.entry_screen = EntryScreen(self)
        self.cube_widget = Cube3DWidget()
        self.main_screen = MainScreen(self)
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

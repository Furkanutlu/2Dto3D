# cube3d_widget.py

from PyQt5.QtWidgets import QColorDialog
from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtOpenGL import QGLWidget
from OpenGL.GL import *
from OpenGL.GLU import gluPerspective, gluNewQuadric, gluCylinder
import numpy as np
import copy


class Cube3DWidget(QGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Scene transformation parameters
        self.rotation_matrix = np.identity(4, dtype=np.float32)  # Genel sahne döndürme matrisi
        self.x_translation = 0
        self.y_translation = 0
        self.zoom = -6.0
        self.last_mouse_position = None
        self.mode = None  # 'rotate', 'move', 'resize', 'cut', 'transparency', etc.
        self.bg_color = (1.0, 1.0, 1.0, 1.0)
        self.undo_stack = []
        self.redo_stack = []
        self.objects = []
        self.selected_object = None

        # Initialize unique color ID counter for color picking
        self.next_color_id = 1  # Start from 1 to avoid black (0,0,0)

        # Cutting attributes
        self.cut_mode = False
        self.cut_plane_defined = False
        self.cut_plane_point = None
        self.cut_plane_normal = None
        self.cut_plane_visual = False
        self.cut_start_pos = None
        self.cut_end_pos = None

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

        # Disable face culling to render both front and back faces
        glDisable(GL_CULL_FACE)

        # Set up lighting
        glLightfv(GL_LIGHT0, GL_POSITION, [4.0, 4.0, 10.0, 1.0])
        glLightfv(GL_LIGHT0, GL_AMBIENT, [0.2, 0.2, 0.2, 1.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.8, 0.8, 0.8, 1.0])

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
            glScalef(self.selected_object.get("scale", 1.0), self.selected_object.get("scale", 1.0),
                     self.selected_object.get("scale", 1.0))
            # Apply selected object's rotations for accurate highlighting
            glMultMatrixf(self.selected_object.get("rotation_matrix", np.identity(4, dtype=np.float32)).flatten('F'))
            self.draw_selection_highlight(self.selected_object)
            glPopMatrix()

        # Draw the cutting plane visual if in cut mode
        if self.cut_plane_visual and self.cut_start_pos and self.cut_end_pos:
            self.draw_cut_plane()

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
            "objects": copy.deepcopy(self.objects),
            "rotation_matrix": self.rotation_matrix.copy(),
            "x_translation": self.x_translation,
            "y_translation": self.y_translation,
            "zoom": self.zoom,
            "selected_object_id": self.selected_object["id"] if self.selected_object else None
        }
        self.undo_stack.append(state)
        self.redo_stack.clear()

    def load_state(self, state):
        self.objects = copy.deepcopy(state["objects"])
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
                "objects": copy.deepcopy(self.objects),
                "rotation_matrix": self.rotation_matrix.copy(),
                "x_translation": self.x_translation,
                "y_translation": self.y_translation,
                "zoom": self.zoom,
                "selected_object_id": self.selected_object["id"] if self.selected_object else None
            }
            self.redo_stack.append(redo_state)
            self.load_state(state)

    def redo(self):
        if self.redo_stack:
            state = self.redo_stack.pop()
            undo_state = {
                "objects": copy.deepcopy(self.objects),
                "rotation_matrix": self.rotation_matrix.copy(),
                "x_translation": self.x_translation,
                "y_translation": self.y_translation,
                "zoom": self.zoom,
                "selected_object_id": self.selected_object["id"] if self.selected_object else None
            }
            self.undo_stack.append(undo_state)
            self.load_state(state)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.cut_mode and self.selected_object:
                # Start defining the cut plane
                self.cut_start_pos = event.pos()
                self.cut_plane_visual = True  # Start visual feedback
                self.update()
            else:
                # Existing selection logic
                self.save_state()
                self.last_mouse_position = event.pos()
                clicked_object = self.pick_object(event.pos())
                self.selected_object = clicked_object
                self.update()
        elif event.button() == Qt.RightButton:
            self.last_mouse_position = event.pos()

    def mouseMoveEvent(self, event):
        if self.cut_mode and self.cut_start_pos:
            # Update the end position for visual feedback
            self.cut_end_pos = event.pos()
            self.update()
        else:
            # Existing mouse move handling
            if self.last_mouse_position is not None:
                delta = event.pos() - self.last_mouse_position
                shift_pressed = event.modifiers() & Qt.ShiftModifier  # Shift key check

                if self.selected_object:
                    if self.mode == "rotate":
                        # Handle individual object rotation
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
                    elif self.mode == "resize":
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
                            pass  # Zoom devre dışı bırakıldı
                        else:
                            self.x_translation += delta.x() * 0.01
                            self.y_translation -= delta.y() * 0.01

                self.last_mouse_position = event.pos()
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.cut_mode and self.cut_start_pos:
                # Finish defining the cut plane
                self.cut_end_pos = event.pos()
                self.define_cut_plane()
                self.perform_cut()
                self.cut_mode = False
                self.cut_plane_visual = False
                self.cut_start_pos = None
                self.cut_end_pos = None
                self.setCursor(Qt.ArrowCursor)
                self.update()
            else:
                self.last_mouse_position = None

    def wheelEvent(self, event):
        # Handle zoom with mouse wheel
        if event.angleDelta().y() != 0:
            self.save_state()
            delta = event.angleDelta().y()
            self.zoom += delta * 0.001
            self.update()

    def set_mode(self, mode):
        self.mode = mode
        if mode == "cut":
            self.cut_mode = True
            self.cut_plane_defined = False
            self.cut_plane_point = None
            self.cut_plane_normal = None
            self.setCursor(Qt.CrossCursor)
        else:
            self.cut_mode = False
            self.cut_plane_defined = False
            self.cut_plane_point = None
            self.cut_plane_normal = None
            self.setCursor(Qt.ArrowCursor)

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

    def define_cut_plane(self):
        """
        Define the cutting plane based on mouse positions.
        """
        # Get the start and end positions
        start_pos = self.cut_start_pos
        end_pos = self.cut_end_pos

        # Define the plane normal based on the drag direction
        dx = end_pos.x() - start_pos.x()
        dy = end_pos.y() - start_pos.y()

        # Determine dominant drag direction
        if abs(dx) > abs(dy):
            normal = np.array([1.0, 0.0, 0.0], dtype=np.float32)  # Vertical cut
        else:
            normal = np.array([0.0, 1.0, 0.0], dtype=np.float32)  # Horizontal cut

        # Define a point on the plane (using the selected object's position)
        point = np.array([
            self.selected_object["x_translation"],
            self.selected_object["y_translation"],
            self.selected_object["z_translation"]
        ], dtype=np.float32)

        self.cut_plane_normal = normal
        self.cut_plane_point = point

    def perform_cut(self):
        """
        Perform the cut operation on the selected object by splitting its mesh along the defined plane.
        """
        if not self.selected_object or self.cut_plane_normal is None:
            return

        obj = self.selected_object
        self.save_state()
        new_objects = self.split_object(obj, self.cut_plane_point, self.cut_plane_normal)

        if new_objects:
            # Remove the original object
            self.objects.remove(obj)
            # Add the new split objects
            self.objects.extend(new_objects)
            # Deselect the current selection
            self.selected_object = None
            self.update()

    def split_object(self, obj, plane_point, plane_normal):
        """
        Split the object into two parts along the defined plane.
        Returns a list of new objects with unique IDs, including new faces to cap the cuts.
        """
        vertices = np.array(obj["vertices"])
        faces = np.array(obj["faces"])

        # Compute the signed distance from each vertex to the plane
        distances = np.dot(vertices - plane_point, plane_normal)

        # Classify vertices on each side of the plane
        side = np.sign(distances)
        side[side == 0] = 1  # Treat points on the plane as positive side

        # Initialize lists for front and back faces
        front_faces = []
        back_faces = []
        intersection_edges = {}

        # To store new vertices created at the intersection
        new_vertices = []
        vertex_map = {}

        for face in faces:
            face_side = side[face]
            if np.all(face_side >= 0):
                front_faces.append(face.tolist())
            elif np.all(face_side <= 0):
                back_faces.append(face.tolist())
            else:
                # Faces intersect the plane; split the face
                # We'll handle only triangular faces
                v_indices = face
                v0, v1, v2 = v_indices
                d0, d1, d2 = distances[v0], distances[v1], distances[v2]

                # Determine the sides
                sides = [d0 >= 0, d1 >= 0, d2 >= 0]

                # Count how many vertices are on each side
                num_positive = sum(sides)
                num_negative = 3 - num_positive

                if num_positive == 1 and num_negative == 2:
                    # One vertex positive, two negative
                    # Create one face for front and two for back
                    # Find the positive vertex
                    pos_idx = v_indices[sides.index(True)]
                    neg_idx1, neg_idx2 = v_indices[sides.index(False)], v_indices[::-1][sides[::-1].index(False)]

                    # Compute intersection points on edges pos->neg1 and pos->neg2
                    intersect1 = self.interpolate_vertex(pos_idx, neg_idx1, d0, d1)
                    intersect2 = self.interpolate_vertex(pos_idx, neg_idx2, d0, d2)

                    # Add new vertices and get their indices
                    new_v1 = len(vertices) + len(new_vertices)
                    new_v2 = len(vertices) + len(new_vertices) + 1
                    new_vertices.extend([intersect1, intersect2])

                    # Create new faces
                    front_faces.append([pos_idx, new_v1, new_v2])
                    back_faces.append([neg_idx1, neg_idx2, new_v2])
                    back_faces.append([neg_idx1, new_v2, new_v1])

                elif num_positive == 2 and num_negative == 1:
                    # Two vertices positive, one negative
                    # Create two faces for front and one for back
                    # Find the negative vertex
                    neg_idx = v_indices[sides.index(False)]
                    pos_idx1, pos_idx2 = v_indices[sides.index(True)], v_indices[::-1][sides[::-1].index(True)]

                    # Compute intersection points on edges neg->pos1 and neg->pos2
                    intersect1 = self.interpolate_vertex(neg_idx, pos_idx1, d_neg=distances[neg_idx], d_pos=distances[pos_idx1])
                    intersect2 = self.interpolate_vertex(neg_idx, pos_idx2, d_neg=distances[neg_idx], d_pos=distances[pos_idx2])

                    # Add new vertices and get their indices
                    new_v1 = len(vertices) + len(new_vertices)
                    new_v2 = len(vertices) + len(new_vertices) + 1
                    new_vertices.extend([intersect1, intersect2])

                    # Create new faces
                    front_faces.append([pos_idx1, pos_idx2, new_v2])
                    front_faces.append([pos_idx1, new_v2, new_v1])
                    back_faces.append([neg_idx, new_v1, new_v2])

        # Add new vertices to the object
        if new_vertices:
            obj_vertices = list(obj["vertices"])
            obj_vertices.extend(new_vertices)
            obj["vertices"] = obj_vertices

        # Generate cap faces (optional but recommended for closed meshes)
        # This requires tracking all intersection edges and forming a loop
        # For simplicity, this implementation does not generate cap faces
        # Implementing cap face generation is complex and typically requires
        # more advanced mesh processing techniques

        new_objects = []

        if front_faces:
            front_obj = copy.deepcopy(obj)
            front_obj["faces"] = front_faces
            front_obj["id"] = self.next_color_id
            self.next_color_id += 1
            new_objects.append(front_obj)

        if back_faces:
            back_obj = copy.deepcopy(obj)
            back_obj["faces"] = back_faces
            back_obj["id"] = self.next_color_id
            self.next_color_id += 1
            new_objects.append(back_obj)

        return new_objects

    def interpolate_vertex(self, idx1, idx2, d_neg, d_pos):
        """
        Linearly interpolate between two vertices to find the intersection point with the plane.
        """
        v1 = np.array(self.selected_object["vertices"][idx1])
        v2 = np.array(self.selected_object["vertices"][idx2])
        t = d_neg / (d_neg - d_pos)
        intersection = v1 + t * (v2 - v1)
        return intersection.tolist()

    def draw_cut_plane(self):
        """
        Draw a visual representation of the cutting plane.
        """
        glPushMatrix()
        # Position the plane based on the selected object's transformation
        glTranslatef(self.selected_object.get("x_translation", 0),
                     self.selected_object.get("y_translation", 0),
                     self.selected_object.get("z_translation", 0))

        # Apply the cutting plane's rotation
        # Assuming the plane normal aligns with one of the primary axes for simplicity
        if np.array_equal(self.cut_plane_normal, np.array([1.0, 0.0, 0.0])):
            # Vertical plane (YZ)
            pass  # No rotation needed
        elif np.array_equal(self.cut_plane_normal, np.array([0.0, 1.0, 0.0])):
            # Horizontal plane (XZ)
            glRotatef(90, 1, 0, 0)

        glColor4f(1.0, 0.0, 0.0, 0.3)  # Semi-transparent red
        glBegin(GL_QUADS)
        size = 2.0  # Adjust size as needed
        glVertex3f(-size, -size, 0.0)
        glVertex3f(size, -size, 0.0)
        glVertex3f(size, size, 0.0)
        glVertex3f(-size, size, 0.0)
        glEnd()
        glPopMatrix()

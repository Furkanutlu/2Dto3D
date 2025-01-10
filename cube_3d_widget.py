from PyQt5.QtWidgets import QColorDialog
from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtOpenGL import QGLWidget
from OpenGL.GL import *
from OpenGL.GLU import gluPerspective, gluNewQuadric, gluCylinder, gluUnProject
from OpenGL.GL import glGetDoublev, glGetIntegerv, GL_MODELVIEW_MATRIX, GL_PROJECTION_MATRIX, GL_VIEWPORT
import numpy as np
import copy

class Cube3DWidget(QGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Sahne ve kamera parametreleri
        self.rotation_matrix = np.identity(4, dtype=np.float32)
        self.x_translation = 0
        self.y_translation = 0
        self.zoom = -6.0
        self.last_mouse_position = None
        self.mode = None
        self.bg_color = (1.0, 1.0, 1.0, 1.0)

        # Undo/Redo
        self.undo_stack = []
        self.redo_stack = []

        # Sahnedeki objeler
        self.objects = []
        self.selected_object = None
        self.next_color_id = 1

        # Kesme ile ilgili veriler
        self.cut_mode = False
        self.cut_plane_defined = False
        self.cut_plane_point = None
        self.cut_plane_normal = None
        self.cut_plane_visual = False
        self.cut_start_pos = None
        self.cut_end_pos = None

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glClearColor(*self.bg_color)
        glEnable(GL_COLOR_MATERIAL)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_NORMALIZE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_CULL_FACE)

        # Basit bir ışık
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
        glMultMatrixf(self.rotation_matrix.flatten('F'))

        # Objeleri çiz
        sorted_objects = sorted(self.objects, key=lambda obj: obj.get("z_translation", 0), reverse=True)
        for obj in sorted_objects:
            glPushMatrix()
            glTranslatef(obj.get("x_translation", 0),
                         obj.get("y_translation", 0),
                         obj.get("z_translation", 0))
            glScalef(obj.get("scale", 1.0), obj.get("scale", 1.0), obj.get("scale", 1.0))
            glMultMatrixf(obj.get("rotation_matrix", np.identity(4, dtype=np.float32)).flatten('F'))

            if obj["type"] == "cube":
                self.draw_cube(obj)
            else:
                self.draw_obj(obj)
            glPopMatrix()

        # Seçili objeyi highlight
        if self.selected_object:
            glPushMatrix()
            glTranslatef(self.selected_object.get("x_translation", 0),
                         self.selected_object.get("y_translation", 0),
                         self.selected_object.get("z_translation", 0))
            glScalef(self.selected_object.get("scale", 1.0),
                     self.selected_object.get("scale", 1.0),
                     self.selected_object.get("scale", 1.0))
            glMultMatrixf(self.selected_object.get("rotation_matrix", np.identity(4, dtype=np.float32)).flatten('F'))
            self.draw_selection_highlight(self.selected_object)
            glPopMatrix()

        # Kesme düzlemi görünümünü isterseniz (cut_plane_visual) 2D/3D olarak ekleyebilirsiniz
        # if self.cut_plane_visual and self.cut_start_pos and self.cut_end_pos:
        #     self.draw_cut_plane()

        # 2D çizgi (fareyle çizdiğin) görünümü
        self.draw_cut_line_2d()

    def draw_cut_line_2d(self):
        """
        Ekranda fareyle tıklayıp sürüklediğin çizgiyi 2D olarak çizer.
        """
        if not self.cut_mode or self.cut_start_pos is None or self.cut_end_pos is None:
            return

        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.width(), self.height(), 0, -1, 1)

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glDisable(GL_DEPTH_TEST)
        glColor3f(1.0, 0.0, 0.0)
        glLineWidth(2.0)

        glBegin(GL_LINES)
        glVertex2f(self.cut_start_pos.x(), self.cut_start_pos.y())
        glVertex2f(self.cut_end_pos.x(),   self.cut_end_pos.y())
        glEnd()

        glEnable(GL_DEPTH_TEST)
        glPopMatrix()

        glMatrixMode(GL_PROJECTION)
        glPopMatrix()

        glMatrixMode(GL_MODELVIEW)

    def unproject(self, screen_x, screen_y, screen_z):
        """
        Ekrandaki (x, y, z) noktasını sahnenin (world_x, world_y, world_z) noktasına çevirir.
        Mevcut modelview, projection matrislerine göre hesaplar.
        """
        modelview = glGetDoublev(GL_MODELVIEW_MATRIX)
        projection = glGetDoublev(GL_PROJECTION_MATRIX)
        viewport = glGetIntegerv(GL_VIEWPORT)

        real_y = viewport[3] - screen_y - 1  # OpenGL pencere koordinatı düzeltmesi

        world_x, world_y, world_z = gluUnProject(screen_x, real_y, screen_z,
                                                 modelview, projection, viewport)
        return np.array([world_x, world_y, world_z], dtype=np.float32)

    def define_cut_plane(self):
        """
        Farede çizdiğin 2D çizgiyi, sahneyi nasıl döndürürsen döndür,
        her zaman 'ekran düzlemine göre sabit' bir kesme düzlemine dönüştür.
        """
        if not self.cut_start_pos or not self.cut_end_pos:
            return

        # Ekrandaki çizgi uçlarını unproject et
        sx, sy = self.cut_start_pos.x(), self.cut_start_pos.y()
        ex, ey = self.cut_end_pos.x(), self.cut_end_pos.y()

        startNear = self.unproject(sx, sy, 0.0)
        startFar = self.unproject(sx, sy, 1.0)
        endNear = self.unproject(ex, ey, 0.0)
        endFar = self.unproject(ex, ey, 1.0)

        # Ekranda çizdiğin çizginin 3D karşılığı
        line_vec = endNear - startNear
        # Kameradan dışarı doğru yön
        cam_vec = startFar - startNear

        # Normal = line_vec x cam_vec
        normal = np.cross(line_vec, cam_vec)
        length = np.linalg.norm(normal)
        if length < 1e-6:
            return

        plane_normal = normal / length
        plane_point = startNear  # (startNear + endNear) / 2 de olabilir

        self.cut_plane_normal = plane_normal
        self.cut_plane_point = plane_point

    def perform_cut(self):
        """
        Kesme operasyonunu gerçekleştir: Sahnedeki tüm objeleri ekrandaki düzlemle kes.
        """
        if self.cut_plane_normal is None:
            return

        self.save_state()  # Undo için

        objects_to_add = []
        objects_to_remove = []

        # Her obje için split_object uygula
        for obj in self.objects:
            new_objects = self.split_object(obj, self.cut_plane_point, self.cut_plane_normal)
            if new_objects:
                # Bu obje kesilmiş, yerine 2 yeni parça konacak
                objects_to_remove.append(obj)
                objects_to_add.extend(new_objects)

        # Sahneyi güncelle
        for obj in objects_to_remove:
            self.objects.remove(obj)

        self.objects.extend(objects_to_add)
        # Kesim sonrası seçili objeyi sıfırlayalım (isteğe bağlı)
        self.selected_object = None

        self.update()

    def split_object(self, obj, plane_point, plane_normal):
        """
        'plane_point' ve 'plane_normal' ile tanımlanan düzlemde
        objeyi ikiye böler, yeni oluşan parçaları geri döndürür.
        """
        vertices = np.array(obj["vertices"], dtype=np.float32)
        faces = np.array(obj["faces"])
        distances = np.dot(vertices - plane_point, plane_normal)
        side = np.sign(distances)
        side[side == 0] = 1  # Tam düzlem üstündekini + tarafta kabul

        front_faces = []
        back_faces = []
        new_vertices = []

        for face in faces:
            face_side = side[face]
            if np.all(face_side >= 0):
                # Tümü düzlemin ön tarafında
                front_faces.append(face.tolist())
            elif np.all(face_side <= 0):
                # Tümü düzlemin arka tarafında
                back_faces.append(face.tolist())
            else:
                # Üçgen düzlem tarafından kesiliyor, bölmek gerekiyor
                v0, v1, v2 = face
                d0, d1, d2 = distances[v0], distances[v1], distances[v2]
                signs = [d0 >= 0, d1 >= 0, d2 >= 0]
                num_positive = sum(signs)
                # num_negative = 3 - num_positive

                if num_positive == 1:
                    # Bir nokta ön tarafta, iki nokta arka tarafta
                    pos_idx = face[signs.index(True)]
                    neg_indices = [face[i] for i in range(3) if not signs[i]]

                    intersect1 = self.interpolate_vertex(obj, pos_idx, neg_indices[0],
                                                         distances[pos_idx],
                                                         distances[neg_indices[0]])
                    intersect2 = self.interpolate_vertex(obj, pos_idx, neg_indices[1],
                                                         distances[pos_idx],
                                                         distances[neg_indices[1]])

                    new_v1 = len(vertices) + len(new_vertices)
                    new_v2 = len(vertices) + len(new_vertices) + 1
                    new_vertices.extend([intersect1, intersect2])

                    # Ön taraf (pozitif) tek noktaya ek, iki kesişim
                    front_faces.append([pos_idx, new_v1, new_v2])
                    # Arka taraf
                    back_faces.append([neg_indices[0], neg_indices[1], new_v2])
                    back_faces.append([neg_indices[0], new_v2, new_v1])

                elif num_positive == 2:
                    # İki nokta ön tarafta, bir nokta arka tarafta
                    neg_idx = face[signs.index(False)]
                    pos_indices = [face[i] for i in range(3) if signs[i]]

                    intersect1 = self.interpolate_vertex(obj, neg_idx, pos_indices[0],
                                                         distances[neg_idx],
                                                         distances[pos_indices[0]])
                    intersect2 = self.interpolate_vertex(obj, neg_idx, pos_indices[1],
                                                         distances[neg_idx],
                                                         distances[pos_indices[1]])

                    new_v1 = len(vertices) + len(new_vertices)
                    new_v2 = len(vertices) + len(new_vertices) + 1
                    new_vertices.extend([intersect1, intersect2])

                    # Ön taraf
                    front_faces.append([pos_indices[0], pos_indices[1], new_v2])
                    front_faces.append([pos_indices[0], new_v2, new_v1])
                    # Arka taraf
                    back_faces.append([neg_idx, new_v1, new_v2])

        # Yeni oluşan tepe noktalarını orijinal vertex listesine ekle
        new_objects = []
        if new_vertices:
            obj_vertices = list(obj["vertices"])
            obj_vertices.extend(new_vertices)
            obj["vertices"] = obj_vertices

            # Renkler
            if obj["colors"]:
                default_color = [0.8, 0.8, 0.8]
                obj_colors = list(obj["colors"])
                for _ in new_vertices:
                    obj_colors.append(default_color)
                obj["colors"] = obj_colors
            else:
                obj["colors"] = [[0.8, 0.8, 0.8] for _ in obj["vertices"]]

        # Ön parça
        if front_faces:
            front_obj = copy.deepcopy(obj)
            front_obj["faces"] = front_faces
            front_obj["id"] = self.next_color_id
            self.next_color_id += 1
            new_objects.append(front_obj)

        # Arka parça
        if back_faces:
            back_obj = copy.deepcopy(obj)
            back_obj["faces"] = back_faces
            back_obj["id"] = self.next_color_id
            self.next_color_id += 1
            new_objects.append(back_obj)

        return new_objects

    def interpolate_vertex(self, obj, idx1, idx2, d1, d2):
        """
        Kenar üzerinde kesme düzlemiyle oluşan kesişim noktasını hesaplar.
        d1 ve d2, idx1 ve idx2'ye ait mesafeler.
        """
        denominator = d1 - d2
        epsilon = 1e-6
        if abs(denominator) < epsilon:
            t = 0.5
        else:
            t = d1 / denominator
            t = np.clip(t, 0.0, 1.0)

        v1 = np.array(obj["vertices"][idx1], dtype=np.float32)
        v2 = np.array(obj["vertices"][idx2], dtype=np.float32)
        intersection = v1 + t * (v2 - v1)
        return intersection.tolist()

    def draw_cut_plane(self):
        """
        İstersen kesme düzlemini sahnede yarı saydam bir alan olarak gösterebilirsin (opsiyonel).
        """
        if self.cut_plane_normal is None or self.cut_plane_point is None:
            return
        # Burada örnek bir gösterim yapabilirdiniz (örn. büyük bir quad),
        # ama tam ekrana sabit yapmak istiyorsanız farklı bir yaklaşım gerekebilir.
        pass

    # ----------------------
    #  Diğer temel fonksiyonlar
    # ----------------------

    def clear_scene(self):
        self.objects.clear()
        self.selected_object = None
        self.rotation_matrix = np.identity(4, dtype=np.float32)
        self.update()

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
                            for i in range(1, len(face) - 1):
                                faces.append([face[0], face[i], face[i + 1]])
                    elif line.startswith('vc '):
                        colors.append(list(map(float, line.strip().split()[1:4])))
        except Exception as e:
            print("OBJ Load Error:", e)
            return

        if vertices:
            self.center_model(vertices)

        if colors and len(colors) == len(vertices):
            obj_colors = colors
        else:
            obj_colors = [[0.8, 0.8, 0.8] for _ in vertices]

        self.objects.append({
            "id": self.next_color_id,
            "type": "obj",
            "vertices": vertices,
            "faces": faces,
            "colors": obj_colors,
            "x_translation": 0,
            "y_translation": 0,
            "z_translation": 0,
            "rotation_matrix": np.identity(4, dtype=np.float32),
            "scale": 1.0,
            "transparent": False
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
                if obj["colors"] and v_idx < len(obj["colors"]):
                    color = obj["colors"][v_idx]
                    alpha = 0.1 if obj.get("transparent", False) else 1.0
                    glColor4f(color[0], color[1], color[2], alpha)
                else:
                    alpha = 0.1 if obj.get("transparent", False) else 1.0
                    glColor4f(0.8, 0.8, 0.8, alpha)
                glVertex3fv(obj["vertices"][v_idx])
        glEnd()

    def draw_cube(self, obj):
        if self.selected_object and obj["id"] == self.selected_object["id"]:
            base_color = (1.0, 1.0, 0.0)  # Seçilince sarı
        else:
            base_color = (0.0, 0.5, 1.0)

        alpha = 0.1 if obj.get("transparent", False) else 1.0
        glColor4f(*base_color, alpha)

        glBegin(GL_QUADS)
        # Ön yüz
        glNormal3f(0.0, 0.0, 1.0)
        glVertex3f(-1.0, -1.0, 1.0)
        glVertex3f( 1.0, -1.0, 1.0)
        glVertex3f( 1.0,  1.0, 1.0)
        glVertex3f(-1.0,  1.0, 1.0)

        # Arka yüz
        glNormal3f(0.0, 0.0, -1.0)
        glVertex3f(-1.0, -1.0, -1.0)
        glVertex3f(-1.0,  1.0, -1.0)
        glVertex3f( 1.0,  1.0, -1.0)
        glVertex3f( 1.0, -1.0, -1.0)

        # Sol yüz
        glNormal3f(-1.0, 0.0, 0.0)
        glVertex3f(-1.0, -1.0, -1.0)
        glVertex3f(-1.0, -1.0,  1.0)
        glVertex3f(-1.0,  1.0,  1.0)
        glVertex3f(-1.0,  1.0, -1.0)

        # Sağ yüz
        glNormal3f(1.0, 0.0, 0.0)
        glVertex3f( 1.0, -1.0, -1.0)
        glVertex3f( 1.0,  1.0, -1.0)
        glVertex3f( 1.0,  1.0,  1.0)
        glVertex3f( 1.0, -1.0,  1.0)

        # Üst yüz
        glNormal3f(0.0, 1.0, 0.0)
        glVertex3f(-1.0,  1.0, -1.0)
        glVertex3f(-1.0,  1.0,  1.0)
        glVertex3f( 1.0,  1.0,  1.0)
        glVertex3f( 1.0,  1.0, -1.0)

        # Alt yüz
        glNormal3f(0.0, -1.0, 0.0)
        glVertex3f(-1.0, -1.0, -1.0)
        glVertex3f(-1.0, -1.0,  1.0)
        glVertex3f( 1.0, -1.0,  1.0)
        glVertex3f( 1.0, -1.0, -1.0)
        glEnd()

    def draw_selection_highlight(self, obj):
        glDisable(GL_LIGHTING)
        glColor3f(1.0, 1.0, 1.0)
        glLineWidth(2.0)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)

        if obj["type"] == "cube":
            self.draw_cube(obj)
        else:
            self.draw_obj(obj)

        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glEnable(GL_LIGHTING)

    def add_cube(self):
        position_offset = len(self.objects) * 2
        self.objects.append({
            "id": self.next_color_id,
            "type": "cube",
            "vertices": [],
            "faces": [],
            "colors": [],
            "x_translation": position_offset,
            "y_translation": 0,
            "z_translation": 0,
            "rotation_matrix": np.identity(4, dtype=np.float32),
            "scale": 1.0,
            "transparent": False
        })
        self.next_color_id += 1
        self.update()

    def set_background_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.bg_color = (color.redF(), color.greenF(), color.blueF(), 1.0)
            glClearColor(*self.bg_color)
            self.update()

    # ----------------------
    #  Undo / Redo
    # ----------------------

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

    # ----------------------
    #  Fare Etkileşimleri
    # ----------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.cut_mode:
                # Kesme çizgisi başlama
                self.cut_start_pos = event.pos()
                self.update()
            else:
                # Obje seçimi
                self.save_state()
                self.last_mouse_position = event.pos()
                clicked_object = self.pick_object(event.pos())
                self.selected_object = clicked_object
                self.update()
        elif event.button() == Qt.RightButton:
            self.last_mouse_position = event.pos()

    def mouseMoveEvent(self, event):
        if self.cut_mode and self.cut_start_pos:
            # Kesme çizgisi çiziliyor
            self.cut_end_pos = event.pos()
            self.update()
        else:
            # Normal sürükleme
            if self.last_mouse_position is not None:
                delta = event.pos() - self.last_mouse_position
                shift_pressed = event.modifiers() & Qt.ShiftModifier

                if self.selected_object:
                    if self.mode == "rotate":
                        angle_x = delta.y()
                        angle_y = delta.x()
                        if shift_pressed:
                            rotation_z = self.create_rotation_matrix(angle_y, 0, 0, 1)
                            self.selected_object["rotation_matrix"] = np.dot(rotation_z,
                                                            self.selected_object["rotation_matrix"])
                        else:
                            rotation_x = self.create_rotation_matrix(angle_x, 1, 0, 0)
                            rotation_y = self.create_rotation_matrix(angle_y, 0, 1, 0)
                            rotation   = np.dot(rotation_y, rotation_x)
                            self.selected_object["rotation_matrix"] = np.dot(rotation,
                                                            self.selected_object["rotation_matrix"])

                    elif self.mode == "move":
                        if shift_pressed:
                            self.selected_object["z_translation"] += delta.y() * 0.01
                        else:
                            self.selected_object["x_translation"] += delta.x() * 0.01
                            self.selected_object["y_translation"] -= delta.y() * 0.01

                    elif self.mode == "resize":
                        scale_change = 1 + (delta.y() * 0.01)
                        new_scale = self.selected_object.get("scale", 1.0) * scale_change
                        new_scale = max(new_scale, 0.1)
                        self.selected_object["scale"] = new_scale

                    elif self.mode == "transparency":
                        if delta.x() > 0:
                            self.set_object_transparency(self.selected_object, True)
                        elif delta.x() < 0:
                            self.set_object_transparency(self.selected_object, False)
                else:
                    # Hiç seçili obje yokken global move
                    if self.mode == "move":
                        if shift_pressed:
                            # İsterseniz global z translation vb.
                            pass
                        else:
                            self.x_translation += delta.x() * 0.01
                            self.y_translation -= delta.y() * 0.01

                self.last_mouse_position = event.pos()
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.cut_mode and self.cut_start_pos:
                # Fareyi sol tuştan bırakınca kesim tamamlansın
                self.cut_end_pos = event.pos()
                self.define_cut_plane()  # düzlemi hesapla (ekrana sabit)
                self.perform_cut()       # kesimi uygula
                self.cut_mode = False
                self.cut_plane_visual = False
                self.cut_start_pos = None
                self.cut_end_pos = None
                self.setCursor(Qt.ArrowCursor)
                self.update()
            else:
                self.last_mouse_position = None

    def wheelEvent(self, event):
        if event.angleDelta().y() != 0:
            self.save_state()
            delta = event.angleDelta().y()
            self.zoom += delta * 0.001
            self.update()

    def set_mode(self, mode):
        """
        move / rotate / resize / transparency / cut vb.
        """
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

    # ----------------------
    #  Obje Seçme (Renk Kodlama)
    # ----------------------

    def pick_object(self, pos):
        glPushAttrib(GL_ALL_ATTRIB_BITS)
        glDisable(GL_LIGHTING)
        glDisable(GL_COLOR_MATERIAL)
        glDisable(GL_TEXTURE_2D)
        glShadeModel(GL_FLAT)
        glDisable(GL_BLEND)

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glTranslatef(self.x_translation, self.y_translation, self.zoom)
        glMultMatrixf(self.rotation_matrix.flatten('F'))

        # Tüm objeleri renk koduyla çiz
        for obj in self.objects:
            glPushMatrix()
            glTranslatef(obj.get("x_translation", 0),
                         obj.get("y_translation", 0),
                         obj.get("z_translation", 0))
            glScalef(obj.get("scale", 1.0), obj.get("scale", 1.0), obj.get("scale", 1.0))
            glMultMatrixf(obj.get("rotation_matrix", np.identity(4, dtype=np.float32)).flatten('F'))

            r = ((obj["id"] & 0xFF0000) >> 16) / 255.0
            g = ((obj["id"] & 0x00FF00) >> 8)  / 255.0
            b = (obj["id"]  & 0x0000FF)        / 255.0
            glColor3f(r, g, b)

            if obj["type"] == "cube":
                self.draw_cube_selection(obj)
            else:
                self.draw_obj_selection(obj)

            glPopMatrix()

        glFlush()
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        x = pos.x()
        y = self.height() - pos.y()

        try:
            pixel = glReadPixels(x, y, 1, 1, GL_RGB, GL_UNSIGNED_BYTE)
            r, g, b = pixel[0], pixel[1], pixel[2]
            picked_id = (r << 16) + (g << 8) + b
        except:
            picked_id = 0

        glPopAttrib()

        if picked_id == 0:
            return None

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
        glNormal3f(0.0, 0.0, 1.0)
        glVertex3f(-1.0, -1.0, 1.0)
        glVertex3f( 1.0, -1.0, 1.0)
        glVertex3f( 1.0,  1.0, 1.0)
        glVertex3f(-1.0,  1.0, 1.0)

        glNormal3f(0.0, 0.0, -1.0)
        glVertex3f(-1.0, -1.0, -1.0)
        glVertex3f(-1.0,  1.0, -1.0)
        glVertex3f( 1.0,  1.0, -1.0)
        glVertex3f( 1.0, -1.0, -1.0)

        glNormal3f(-1.0, 0.0, 0.0)
        glVertex3f(-1.0, -1.0, -1.0)
        glVertex3f(-1.0, -1.0,  1.0)
        glVertex3f(-1.0,  1.0,  1.0)
        glVertex3f(-1.0,  1.0, -1.0)

        glNormal3f(1.0, 0.0, 0.0)
        glVertex3f( 1.0, -1.0, -1.0)
        glVertex3f( 1.0,  1.0, -1.0)
        glVertex3f( 1.0,  1.0,  1.0)
        glVertex3f( 1.0, -1.0,  1.0)

        glNormal3f(0.0, 1.0, 0.0)
        glVertex3f(-1.0,  1.0, -1.0)
        glVertex3f(-1.0,  1.0,  1.0)
        glVertex3f( 1.0,  1.0,  1.0)
        glVertex3f( 1.0,  1.0, -1.0)

        glNormal3f(0.0, -1.0, 0.0)
        glVertex3f(-1.0, -1.0, -1.0)
        glVertex3f(-1.0, -1.0,  1.0)
        glVertex3f( 1.0, -1.0,  1.0)
        glVertex3f( 1.0, -1.0, -1.0)
        glEnd()

    def delete_selected_object(self):
        if self.selected_object:
            self.save_state()
            self.objects.remove(self.selected_object)
            self.selected_object = None
            self.update()

    def create_rotation_matrix(self, angle, x, y, z):
        rad = np.deg2rad(angle)
        c = np.cos(rad)
        s = np.sin(rad)
        norm = np.sqrt(x*x + y*y + z*z)
        if norm == 0:
            return np.identity(4, dtype=np.float32)
        x /= norm
        y /= norm
        z /= norm

        rotation = np.array([
            [c + (1 - c)*x*x,     (1 - c)*x*y - s*z, (1 - c)*x*z + s*y, 0],
            [(1 - c)*y*x + s*z,   c + (1 - c)*y*y,   (1 - c)*y*z - s*x, 0],
            [(1 - c)*z*x - s*y,   (1 - c)*z*y + s*x, c + (1 - c)*z*z,   0],
            [0,                   0,                 0,                 1]
        ], dtype=np.float32)
        return rotation

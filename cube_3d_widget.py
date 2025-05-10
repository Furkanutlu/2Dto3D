from PyQt5.QtWidgets import QColorDialog, QOpenGLWidget
from PyQt5.QtCore import Qt
from OpenGL.GL import *
from OpenGL.GLU import gluPerspective
from mesh import Mesh
from shader_utils import build_program   #  ← EKLE
from OpenGL.GL import glGetDoublev, GL_PROJECTION_MATRIX, GL_MODELVIEW_MATRIX
import numpy as np, copy, math, os, sys     #  ← sys de eklendi
from PyQt5.QtCore import Qt, pyqtSignal

class Cube3DWidget(QOpenGLWidget):
    scene_changed = pyqtSignal()  # objeler eklendi/silindi
    selection_changed = pyqtSignal(int)  # seçilen mesh id  (yoksa -1)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rotation_matrix = np.identity(4, np.float32)
        self.x_translation = 0.0
        self.y_translation = 0.0
        self.zoom = -6.0
        self.last_mouse_position = None
        self.mode = None
        self.bg_color = (1, 1, 1, 1)
        self.use_vao = False
        self.undo_stack = []
        self.redo_stack = []
        self.meshes = []
        self.selected_mesh = None
        self.next_color_id = 1
        self.cut_mode = False
        self.cut_start_pos = None
        self.cut_end_pos = None
        self._dragging = False
        # hassasiyetler
        self.sens_move = 0.01
        self.sens_rotate = 1.0
        self.sens_resize = 0.01
        self.sens_zoom = self.sens_resize
        self.use_shader = False

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glClearColor(*self.bg_color)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_CULL_FACE)

        # --- shader derle ---
        vsrc = """
        #version 120
        attribute vec3 a_pos;
        attribute vec3 a_col;
        uniform   mat4 u_mvp;
        varying   vec3 v_col;
        void main(){
            v_col = a_col;
            gl_Position = u_mvp * vec4(a_pos,1.0);
        }"""
        fsrc = """
        #version 120
        varying vec3 v_col;
        void main(){
            gl_FragColor = vec4(v_col,1.0);
        }"""
        try:
            self.prog = build_program(vsrc, fsrc)
            self.u_mvp = glGetUniformLocation(self.prog, "u_mvp")
            self.use_shader = True
        except RuntimeError as e:
            print("Shader derlenemedi, eski pipeline’a düşüldü:", e, file=sys.stderr)
            self.use_shader = False

        # fixed-pipeline ışık yedeği
        if not self.use_shader:
            glEnable(GL_COLOR_MATERIAL)
            glEnable(GL_LIGHTING)
            glEnable(GL_LIGHT0)
            glLightfv(GL_LIGHT0, GL_POSITION, [4, 4, 10, 1])
            glLightfv(GL_LIGHT0, GL_AMBIENT, [0.2, 0.2, 0.2, 1])
            glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.8, 0.8, 0.8, 1])

    def resizeGL(self, w, h):
        w = max(1, w)
        h = max(1, h)
        glViewport(0, 0, w, h)
        self._update_projection()  # <- her pencere yeniden çiziminde

    def paintGL(self):
        self.debug_dump()
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glTranslatef(self.x_translation, self.y_translation, self.zoom)
        glMultMatrixf(self.rotation_matrix.flatten('F'))
        for m in self.meshes:
            self._draw_mesh(m)
        if self.selected_mesh:
            self._highlight(self.selected_mesh)
        self._draw_cut_line()


    def _create_vao(self, m):
        if not self.use_vao:
            m.vao = 0
            return
        vao = glGenVertexArrays(1)
        glBindVertexArray(vao)
        glBindBuffer(GL_ARRAY_BUFFER, m.vbo_v)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)
        if m.vbo_c:
            glBindBuffer(GL_ARRAY_BUFFER, m.vbo_c)
            glEnableVertexAttribArray(1)
            glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 0, None)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, m.vbo_i)
        glBindVertexArray(0)
        m.vao = vao

    def _draw_mesh(self, m, id_color=None):
        if not hasattr(m, "vao"):
            self._create_vao(m)

        use_vao = self.use_vao and getattr(m, "vao", 0) and id_color is None

        # ---------- tampon bağlama ----------
        if use_vao:
            glBindVertexArray(m.vao)
        else:
            glBindBuffer(GL_ARRAY_BUFFER, m.vbo_v)
            glEnableVertexAttribArray(0)
            glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)

            if id_color is None and m.vbo_c:
                # renk dizisi
                glBindBuffer(GL_ARRAY_BUFFER, m.vbo_c)
                glEnableVertexAttribArray(1)
                glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 0, None)
            else:
                glDisableVertexAttribArray(1)

            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, m.vbo_i)

        # ---------- model dönüşümleri ----------
        glPushMatrix()
        glTranslatef(*m.translation)
        glScalef(m.scale, m.scale, m.scale)
        glMultMatrixf(m.rotation.flatten('F'))

        # ---------- shader / sabit pip. ----------
        if id_color is None and self.use_shader:
            glUseProgram(self.prog)

            # --- doğru sütun-major MVP oluştur ---
            mv = np.array(glGetFloatv(GL_MODELVIEW_MATRIX),
                          dtype=np.float32).reshape(4, 4).T
            pr = np.array(glGetFloatv(GL_PROJECTION_MATRIX),
                          dtype=np.float32).reshape(4, 4).T
            mvp = pr @ mv
            glUniformMatrix4fv(self.u_mvp, 1, GL_FALSE, mvp.T)

            # Eğer mesh’te renk dizisi yoksa sabit renk ver
            if not m.vbo_c:
                r, g, b = m.color
                glDisableVertexAttribArray(1)
                glVertexAttrib3f(1, r, g, b)

        else:
            glUseProgram(0)
            if id_color:
                glDisableVertexAttribArray(1)
                glColor3f(*id_color)  # seçim tek renk
            elif not m.vbo_c:  # sabit renkli mesh
                alpha = 0.1 if m.transparent else 1.0
                glColor4f(*m.color, alpha)

        # ---------- çizim ----------
        glDrawElements(GL_TRIANGLES, m.index_count, GL_UNSIGNED_INT, None)

        # ---------- temizlik ----------
        glPopMatrix()
        if use_vao:
            glBindVertexArray(0)
        glUseProgram(0)

    def _highlight(self, m):
        glDisable(GL_LIGHTING)
        glColor3f(0, 0, 0)
        glLineWidth(2)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
        self._draw_mesh(m)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glEnable(GL_LIGHTING)

    def _draw_cut_line(self):
        if not (self.cut_mode and self.cut_start_pos and self.cut_end_pos):
            return
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.width(), self.height(), 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glDisable(GL_DEPTH_TEST)
        glColor3f(1, 0, 0)
        glLineWidth(2)
        glBegin(GL_LINES)
        glVertex2f(self.cut_start_pos.x(), self.cut_start_pos.y())
        glVertex2f(self.cut_end_pos.x(), self.cut_end_pos.y())
        glEnd()
        glEnable(GL_DEPTH_TEST)
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    def save_state(self):
        self.undo_stack.append({
            'meshes': copy.deepcopy(self.meshes),
            'rotation_matrix': self.rotation_matrix.copy(),
            'x_translation': self.x_translation,
            'y_translation': self.y_translation,
            'zoom': self.zoom,
            'bg_color': self.bg_color,
            'selected_id': self.selected_mesh.id if self.selected_mesh else None
        })
        self.redo_stack.clear()

    def load_state(self, s):
        """Undo/redo için kaydedilmiş durumu geri yükler ve GPU tamponlarını günceller."""
        # 1) Python-side kopyaları yükle
        self.meshes = copy.deepcopy(s['meshes'])
        # 2) GPU buffer’larını yeniden oluştur
        for m in self.meshes:
            # Vertex positions
            glBindBuffer(GL_ARRAY_BUFFER, m.vbo_v)
            glBufferData(GL_ARRAY_BUFFER,
                         m.vertices.nbytes,
                         m.vertices,
                         GL_STATIC_DRAW)
            # Indices
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, m.vbo_i)
            glBufferData(GL_ELEMENT_ARRAY_BUFFER,
                         m.indices.nbytes,
                         m.indices,
                         GL_STATIC_DRAW)
            # Renk buffer’ı varsa (opsiyonel)
            if getattr(m, 'vbo_c', None):
                glBindBuffer(GL_ARRAY_BUFFER, m.vbo_c)
                glBufferData(GL_ARRAY_BUFFER,
                             m.colors.nbytes,
                             m.colors,
                             GL_STATIC_DRAW)

        # 3) Kamera & sahne durumunu yükle
        self.rotation_matrix = s['rotation_matrix'].copy()
        self.x_translation = s['x_translation']
        self.y_translation = s['y_translation']
        self.zoom = s['zoom']
        # 4) Arkaplan rengi
        self.bg_color = s.get('bg_color', self.bg_color)
        glClearColor(*self.bg_color)
        # 5) Seçili mesh’i geri yükle
        sid = s['selected_id']
        self.selected_mesh = next((m for m in self.meshes if m.id == sid), None)
        # 6) Görünümü güncelle
        self.update()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append({
            'meshes': copy.deepcopy(self.meshes),
            'rotation_matrix': self.rotation_matrix.copy(),
            'x_translation': self.x_translation,
            'y_translation': self.y_translation,
            'zoom': self.zoom,
            'bg_color': self.bg_color,
            'selected_id': self.selected_mesh.id if self.selected_mesh else None
        })
        self.load_state(self.undo_stack.pop())
        self.scene_changed.emit()                           #  <<< panel
        sid = self.selected_mesh.id if self.selected_mesh else -1
        self.selection_changed.emit(sid)

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append({
            'meshes': copy.deepcopy(self.meshes),
            'rotation_matrix': self.rotation_matrix.copy(),
            'x_translation': self.x_translation,
            'y_translation': self.y_translation,
            'zoom': self.zoom,
            'bg_color': self.bg_color,
            'selected_id': self.selected_mesh.id if self.selected_mesh else None
        })
        self.load_state(self.redo_stack.pop())
        self.scene_changed.emit()  # <<< panel
        sid = self.selected_mesh.id if self.selected_mesh else -1
        self.selection_changed.emit(sid)  # <<< panel

    def clear_scene(self):
        """Tüm objeleri ve dönüşümleri sıfırla."""
        self.save_state()
        self.meshes.clear()
        self.selected_mesh = None
        self.rotation_matrix = np.identity(4, np.float32)
        self.scene_changed.emit()  # <<< panel
        self.selection_changed.emit(-1)  # <<< panel
        self.update()

    def load_obj(self, fn):
        """OBJ dosyasını okur, yeni Mesh oluşturur ve sahneye ekler."""
        verts, faces, cols = [], [], []
        with open(fn, 'r', errors='ignore') as f:
            for line in f:
                if line.startswith('v '):
                    vals = list(map(float, line.split()[1:]))
                    verts.append(vals[:3])
                    if len(vals) >= 6:
                        cols.append(vals[3:6])
                elif line.startswith('f '):
                    idx = [int(p.split('/')[0]) - 1 for p in line.split()[1:]]
                    if len(idx) >= 3:
                        for i in range(1, len(idx) - 1):
                            faces.append([idx[0], idx[i], idx[i + 1]])

        if not verts or not faces:
            return                                          # geçersiz dosya

        verts  = np.asarray(verts,  np.float32)
        faces  = np.asarray(faces,  np.uint32).flatten()
        verts -= verts.mean(axis=0)
        colors = np.asarray(cols, np.float32) if cols else None

        self.save_state()
        mesh         = Mesh(verts, faces, colors, mesh_name=os.path.basename(fn))
        mesh.id      = self.next_color_id
        self.next_color_id += 1
        self.meshes.append(mesh)

        self.scene_changed.emit()                           #  <<< panel
        self.update()
    def set_background_color(self):
        self.save_state()
        c = QColorDialog.getColor()
        if c.isValid():
            self.bg_color = (c.redF(), c.greenF(), c.blueF(), 1)
            glClearColor(*self.bg_color)
            self.update()

    def delete_selected_object(self):
        """Seçili mesh’i sil."""
        if self.selected_mesh:
            self.save_state()
            self.meshes.remove(self.selected_mesh)
            self.selected_mesh = None
            self.scene_changed.emit()                       #  <<< panel
            self.selection_changed.emit(-1)                 #  <<< panel
            self.update()

    def set_mode(self, mode):
        self.mode = mode
        if mode == 'cut':
            self.cut_mode = True
            self.setCursor(Qt.CrossCursor)
        else:
            self.cut_mode = False
            self.setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, e):
        if e.button() not in (Qt.LeftButton, Qt.RightButton):
            return

        # normal drag flag’ini güncelle
        self._dragging = True
        self.last_mouse_position = e.pos()

        # --- KESME KİPİNDE İLK TIK: başlangıç noktasını ve matrisleri ayıkla
        if self.cut_mode and e.button() == Qt.LeftButton:
            self.cut_start_pos = e.pos()
            self._dragging = False  # cut olarak handle et
            self.update()
            return

        # --- NORMAL SOL TUŞ: seçim
        if e.button() == Qt.LeftButton and self.mode is None:
            self.selected_mesh = self._pick(e.pos())
            self.update()

    def mouseMoveEvent(self, e):
        if self.cut_mode and self.cut_start_pos:
            self.cut_end_pos = e.pos()
            self.update()
            return
        if self.last_mouse_position is None:
            return
        d = e.pos() - self.last_mouse_position
        shift = bool(e.modifiers() & Qt.ShiftModifier)
        if self.selected_mesh:
            if self.mode == 'move':
                R = self.rotation_matrix[:3, :3]
                if shift:
                    cam_forward = R.T @ np.array([0, 0, -1], np.float32)
                    self.selected_mesh.translation += cam_forward * (-d.y() * self.sens_move)
                else:
                    cam_right = R.T @ np.array([1, 0, 0], np.float32)
                    cam_up = R.T @ np.array([0, 1, 0], np.float32)
                    self.selected_mesh.translation += cam_right * (d.x() * self.sens_move) + cam_up * (-d.y() * self.sens_move)
            elif self.mode == 'rotate':
                ax, ay = d.y() * self.sens_rotate, d.x() * self.sens_rotate
                R = self.rotation_matrix[:3, :3]
                cam_right = R.T @ np.array([1, 0, 0], np.float32)
                cam_up = R.T @ np.array([0, 1, 0], np.float32)
                r_vert = self._rot_axis(ax, cam_right)
                r_horz = self._rot_axis(ay, cam_up)
                self.selected_mesh.rotation = r_horz @ r_vert @ self.selected_mesh.rotation
            elif self.mode == 'resize':
                delta = d.y() * self.sens_resize
                if delta:
                    self.selected_mesh.scale = max(self.selected_mesh.scale * (1 + delta), 0.1)
            elif self.mode == 'transparency':
                if d.x():
                    self.selected_mesh.transparent = d.x() > 0
        else:
            if self.mode == 'move':
                if shift:
                    self.zoom += -d.y() * self.sens_zoom
                else:
                    self.x_translation += d.x() * self.sens_move
                    self.y_translation += -d.y() * self.sens_move
            elif self.mode == 'rotate' and (e.buttons() & Qt.RightButton):
                ax, ay = d.y() * self.sens_rotate, d.x() * self.sens_rotate
                rx = self._rot(ax, 1, 0, 0)
                ry = self._rot(ay, 0, 1, 0)
                self.rotation_matrix = ry @ rx @ self.rotation_matrix
        self.last_mouse_position = e.pos()
        self.update()

    def mouseReleaseEvent(self, e):
        # drag sonucu undo yalnızca cut_mod değilse kaydet
        if self._dragging and not self.cut_mode:
            self.save_state()
        self._dragging = False

        # --- KESME KİPİNDE SOL TUŞA BIRAKMA: düzlemi uygula
        if e.button() == Qt.LeftButton and self.cut_mode and self.cut_start_pos:
            self.cut_end_pos = e.pos()
            self.cut_mode = False
            self.setCursor(Qt.ArrowCursor)
            self._perform_cut()  # burada save_state var
            self.cut_start_pos = self.cut_end_pos = None
            self.update()
            return

        # diğer release olayları
        self.last_mouse_position = None
    def screen_to_world(self, sx, sy, proj_inv, view_inv):
        """
        Convert 2D widget coords (sx,sy) into a world‐space point on the near plane.
        We add a 0.5 offset so that we unproject from the pixel center, which
        makes the cut plane align exactly with the red guide line.
        """
        w, h = self.width(), self.height()

        # pixel‐center correction
        x_ndc =  2.0 * (sx + 0.5) / w - 1.0
        y_ndc =  1.0 - 2.0 * (sy + 0.5) / h
        z_ndc = -1.0   # near plane

        ndc = np.array([x_ndc, y_ndc, z_ndc, 1.0], dtype=np.float64)

        # eye‐space
        eye = proj_inv @ ndc
        eye /= eye[3]

        # world‐space
        world = view_inv @ eye
        world /= world[3]

        return world[:3]

    def _perform_cut(self):
        # 1) must have start/end and a mesh
        if not (self.cut_start_pos and self.cut_end_pos and self.selected_mesh):
            return

        # 2) save for undo
        self.save_state()

        # 2.5) ensure projection & modelview match what paintGL would have set,
        #      even if paintGL hasn't run since the last user rotation/zoom.
        #      _update_projection sets the GL_PROJECTION matrix and
        #      switches back to GL_MODELVIEW.
        self._update_projection()
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glTranslatef(self.x_translation, self.y_translation, self.zoom)
        glMultMatrixf(self.rotation_matrix.flatten('F'))

        # 3) now fetch & invert current GL matrices
        proj = glGetDoublev(GL_PROJECTION_MATRIX)
        model = glGetDoublev(GL_MODELVIEW_MATRIX)
        P = np.array(proj, dtype=np.float64).reshape(4, 4).T
        V = np.array(model, dtype=np.float64).reshape(4, 4).T
        proj_inv = np.linalg.inv(P)
        view_inv = np.linalg.inv(V)

        # 4) unproject your two screen points into world‐space rays
        sx, sy = self.cut_start_pos.x(), self.cut_start_pos.y()
        ex, ey = self.cut_end_pos.x(), self.cut_end_pos.y()
        ws = self.screen_to_world(sx, sy, proj_inv, view_inv)
        we = self.screen_to_world(ex, ey, proj_inv, view_inv)

        # 5) camera world‐position
        cam_h = view_inv @ np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float64)
        cam_pos = cam_h[:3] / cam_h[3]

        # 6) build plane from the two rays (camera→ws) and (camera→we)
        a = ws - cam_pos
        b = we - cam_pos
        normal = np.cross(a, b)
        nrm = np.linalg.norm(normal)
        if nrm < 1e-6:
            return
        normal /= nrm
        d = -normal.dot(cam_pos)

        # 7) copy & cut the mesh
        orig = self.selected_mesh
        verts = orig.vertices.copy()
        inds = orig.indices.copy()
        orig_cols = getattr(orig, 'colors', None)

        mk = Mesh(verts, inds, colors=orig_cols, color=orig.color, mesh_name=orig.name + "_keep")
        mc = Mesh(verts, inds, colors=orig_cols, color=orig.color, mesh_name=orig.name + "_cut")

        # preserve transforms & reupload colors
        mk.id, mc.id = orig.id, self.next_color_id;
        self.next_color_id += 1
        for m in (mk, mc):
            m.translation = orig.translation.copy()
            m.rotation = orig.rotation.copy()
            m.scale = orig.scale
            m.transparent = orig.transparent
        if orig_cols is not None:
            glBindBuffer(GL_ARRAY_BUFFER, mk.vbo_c)
            glBufferData(GL_ARRAY_BUFFER, orig_cols.nbytes, orig_cols, GL_STATIC_DRAW)

        # 8) do the split
        mk.cut_by_plane(normal, d)
        mc.cut_by_plane(-normal, -d)

        # 9) swap into scene
        self.meshes.remove(orig)
        self.meshes.extend([mk, mc])
        self.selected_mesh = None

        # 10) refresh UI
        self.scene_changed.emit()
        self.selection_changed.emit(-1)
        self.update()

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        if delta:
            self.save_state()
            self.zoom += delta * self.sens_zoom  # zoom NEGATİF kalır
            self.zoom = max(self.zoom, -500.0)  # en uzak
            self.zoom = min(self.zoom, -0.2)  # en yakın
            self._update_projection()  # <- yeni near / far
            self.update()

    def _update_projection(self):
        """Kamera uzaklığına göre near/far düzeltir; hep görünür kalır."""
        w = max(1, self.width())
        h = max(1, self.height())

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()

        near = max(0.1, abs(self.zoom) * 0.05)  # kamera nesneye çok
        far = abs(self.zoom) + 50.0  # + tampon

        gluPerspective(45.0, w / h, near, far)
        glMatrixMode(GL_MODELVIEW)

    def _rot(self, angle, x, y, z):
        r = math.radians(angle)
        c, s = math.cos(r), math.sin(r)
        n = math.sqrt(x * x + y * y + z * z)
        if n == 0:
            return np.identity(4, np.float32)
        x, y, z = x / n, y / n, z / n
        return np.array([
            [c + (1 - c) * x * x, (1 - c) * x * y - s * z, (1 - c) * x * z + s * y, 0],
            [(1 - c) * y * x + s * z, c + (1 - c) * y * y, (1 - c) * y * z - s * x, 0],
            [(1 - c) * z * x - s * y, (1 - c) * z * y + s * x, c + (1 - c) * z * z, 0],
            [0, 0, 0, 1]
        ], np.float32)

    def _rot_axis(self, angle, axis):
        r = math.radians(angle)
        c, s = math.cos(r), math.sin(r)
        ax = axis / (np.linalg.norm(axis) + 1e-8)
        x, y, z = ax
        return np.array([
            [c + (1 - c) * x * x, (1 - c) * x * y - s * z, (1 - c) * x * z + s * y, 0],
            [(1 - c) * y * x + s * z, c + (1 - c) * y * y, (1 - c) * y * z - s * x, 0],
            [(1 - c) * z * x - s * y, (1 - c) * z * y + s * x, c + (1 - c) * z * z, 0],
            [0, 0, 0, 1]
        ], np.float32)

    def _pick(self, pos):
        """
        Tıklanan konumdan mesh seçimi.
        1) Renk-ID yöntemi; başarısızsa Ray-AABB yedeği.
        """
        pid = self._pick_id_color(pos)
        if pid:
            mesh = next((m for m in self.meshes if m.id == pid), None)
        else:
            mesh = self._pick_by_ray(pos)

        self.selection_changed.emit(mesh.id if mesh else -1)  #  <<< panel
        return mesh

    # ---------- 1 · Renk-ID (hızlı yol) --------------------------------
    def _pick_id_color(self, pos):
        glPushAttrib(GL_ALL_ATTRIB_BITS)
        glDisable(GL_LIGHTING)
        glDisable(GL_BLEND)
        glDisable(GL_MULTISAMPLE)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # Kamera matrisi
        glLoadIdentity()
        glTranslatef(self.x_translation, self.y_translation, self.zoom)
        glMultMatrixf(self.rotation_matrix.flatten('F'))

        # Her mesh’i kendine özgü tek renkle çiz
        for m in self.meshes:
            r = ((m.id >> 16) & 0xFF) / 255.0
            g = ((m.id >>  8) & 0xFF) / 255.0
            b = ( m.id        & 0xFF) / 255.0
            self._draw_mesh(m, id_color=(r, g, b))

        glFlush(); glFinish()

        # Ekran koordinatını OpenGL tamponuna çevir ve oku
        x = pos.x()
        y = self.height() - pos.y() - 1
        pix = glReadPixels(x, y, 1, 1, GL_RGB, GL_UNSIGNED_BYTE)

        # Çıktı PyOpenGL sürümüne göre bytes veya ndarray olabilir → düzleştir
        r, g, b = list(pix if isinstance(pix, (bytes, bytearray))
                       else np.array(pix).flatten())[:3]
        glPopAttrib()
        return (r << 16) | (g << 8) | b      # 0 ise arka plan

    # ---------- 2 · Ray + AABB (yedek) --------------------------------
    def _pick_by_ray(self, pos):
        # 2-a: Ekran (px) → Normalized Device Coordinate
        ndc_x =  2.0 * pos.x() / self.width()  - 1.0
        ndc_y = -2.0 * pos.y() / self.height() + 1.0

        # 2-b: Klip → Göz → Dünya
        inv_proj = np.linalg.inv(self._proj_mat())
        inv_view = np.linalg.inv(self._view_mat())

        clip_near = np.array([ndc_x, ndc_y, -1, 1], np.float32)
        clip_far  = np.array([ndc_x, ndc_y,  1, 1], np.float32)

        eye_near = inv_proj @ clip_near; eye_near /= eye_near[3]
        eye_far  = inv_proj @ clip_far ; eye_far  /= eye_far[3]

        world_near = inv_view @ eye_near
        world_far  = inv_view @ eye_far
        ray_dir    = world_far[:3] - world_near[:3]
        ray_dir   /= np.linalg.norm(ray_dir)

        # 2-c: Her mesh’in axis-aligned bounding box’ı ile kesişimi bul
        best_mesh, best_t = None, 1e9
        for m in self.meshes:
            mn, mx = m.aabb_world()                # Mesh.aabb_world() şart
            t1, t2 = self._ray_aabb(world_near[:3], ray_dir, mn, mx)
            if t2 >= max(t1, 0) and t1 < best_t:   # kesişme ve en yakın
                best_mesh, best_t = m, t1
        return best_mesh

    # ---------- Yardımcı matrisler ------------------------------------
    def _proj_mat(self):
        f = 1 / np.tan(np.deg2rad(45) / 2)
        asp = self.width() / max(1, self.height())
        n, fz = 0.1, abs(self.zoom) + 50.0
        return np.array([[f/asp,0,0,0],
                         [0,f,0,0],
                         [0,0,(fz+n)/(n-fz), 2*fz*n/(n-fz)],
                         [0,0,-1,0]], np.float32)

    def _view_mat(self):
        M = np.identity(4, np.float32)
        M[:3,:3] = self.rotation_matrix[:3,:3]
        M[:3, 3] = [self.x_translation, self.y_translation, self.zoom]
        return M

    # ---------- Ray / AABB kesişimi (DDA yöntemi) ---------------------
    @staticmethod
    def _ray_aabb(orig, dir_, mn, mx):
        t1 = (mn - orig) / dir_
        t2 = (mx - orig) / dir_
        tmin = np.maximum.reduce(np.minimum(t1, t2))
        tmax = np.minimum.reduce(np.maximum(t1, t2))
        return tmin, tmax

    def set_move_sensitivity(self, v):
        self.sens_move = float(v)

    def set_rotate_sensitivity(self, v):
        self.sens_rotate = float(v)

    def set_resize_sensitivity(self, v):
        self.sens_resize = float(v)
        self.sens_zoom = float(v)
    def debug_dump(self):
        print(f"[DEBUG] mesh count = {len(self.meshes)}")
        for m in self.meshes:
            print("   id:", m.id, "name:", getattr(m, "name", "none"))

    def _screen_to_world(self, px, py, proj_inv, view_inv):
        ndc = np.array([2 * px / self.width() - 1,
                        1 - 2 * py / self.height(),
                        -1, 1], np.float32)
        eye = proj_inv @ ndc
        eye /= eye[3]
        world = view_inv @ eye
        return world[:3]
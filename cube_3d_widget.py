from PyQt5.QtWidgets import QColorDialog, QOpenGLWidget
from OpenGL.GL import *
from mesh import Mesh
from shader_utils import build_program
from OpenGL.GL import glGetDoublev, GL_PROJECTION_MATRIX, GL_MODELVIEW_MATRIX
import numpy as np, copy, math, os, sys
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QProgressDialog
from OpenGL.GLU import gluPerspective, gluProject


def _parse_mtl(mtl_path: str) -> dict[str, tuple[float, float, float]]:
    """
    .mtl dosyasındaki   newmtl <name> / Kd r g b   satırlarını     (0-1 veya 0-255)
    okur ve  {name: (r,g,b)} sözlüğü döndürür.
    """
    if not os.path.isfile(mtl_path):
        return {}

    mats, current = {}, None
    with open(mtl_path, "r", errors="ignore") as f:
        for line in f:
            if line.startswith("newmtl "):
                current = line.split(maxsplit=1)[1].strip()
            elif current and line.startswith("Kd "):
                r, g, b = map(float, line.split()[1:4])
                if max(r, g, b) > 1.0:  # 0-255 ise ölçekle
                    r, g, b = r / 255.0, g / 255.0, b / 255.0
                mats[current] = (r, g, b)
    return mats
class Cube3DWidget(QOpenGLWidget):
    scene_changed = pyqtSignal()  # objeler eklendi/silindi
    selection_changed = pyqtSignal(int)  # seçilen mesh id  (yoksa -1)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rotation_matrix = np.identity(4, np.float32)
        self.x_translation = 0.0
        self.y_translation = 0.0
        self.zoom = -6.0
        # how many lines each side of center; increase for finer "infinite" illusion
        self._grid_half_count = 200
        self._grid_spacing = 1.0
        self.last_mouse_position = None
        self.mode = None
        self.bg_color = (1, 1, 1, 1)
        self.use_vao = False
        self.undo_stack = []
        self.redo_stack = []
        self.meshes = []
        self.selected_mesh = None

        self.axis_visible = False
        self.axis_length = 5.0
        self.grid_visible = False

        # grid_mode: 'all', 'xy', 'xz', 'yz'
        self.grid_mode = 'all'
        self._grid_half_count = 200
        self._grid_spacing = 1.0

        self.next_color_id = 1
        self.cut_mode = False
        self.cut_start_pos = None
        self.cut_end_pos = None
        self._dragging = False
        # hassasiyetler
        self.sens_move = 0.05 # 1 px → 0.05 birim
        self.sens_rotate = 0.5 # 1 px → 0.5°
        self.sens_resize = 0.05
        self.sens_zoom = self.sens_resize
        self.erase_radius_px = 40
        self.erase_cursor = None  # ekran pozisyonu (QPoint)
        self.use_shader = False
        # camera konfigürasyonu projeye göre ayarlayın
        self.camera = None
        self.erase_dirty = False

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glClearColor(*self.bg_color)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_CULL_FACE)

        # ── Lambert aydınlatmalı shader ───────────────────────────────
        vsrc = """
        #version 120
        attribute vec3 a_pos;
        attribute vec3 a_col;
        attribute vec3 a_nrm;

        uniform   mat4 u_mvp;
        uniform   mat3 u_normalMat;
        uniform   vec3 u_lightDir;

        varying   vec3 v_col;
        varying   float v_lambert;

        void main(){
            vec3 n = normalize(u_normalMat * a_nrm);
            v_lambert = max(dot(n, u_lightDir), 0.0);
            v_col = a_col;
            gl_Position = u_mvp * vec4(a_pos,1.0);
        }""";

        fsrc = """
        #version 120
        varying vec3  v_col;
        varying float v_lambert;
        uniform vec3  u_ambient;
        uniform vec3  u_diffuse;
        void main(){
            vec3 c = v_col * (u_ambient + u_diffuse * v_lambert);
            gl_FragColor = vec4(c,1.0);
        }""";

        try:
            self.prog = build_program(vsrc, fsrc)
            self.u_mvp = glGetUniformLocation(self.prog, "u_mvp")
            self.u_nmat = glGetUniformLocation(self.prog, "u_normalMat")
            self.u_ldir = glGetUniformLocation(self.prog, "u_lightDir")
            self.u_amb = glGetUniformLocation(self.prog, "u_ambient")
            self.u_dif = glGetUniformLocation(self.prog, "u_diffuse")
            self.use_shader = True
        except RuntimeError as e:
            print("Shader derlenemedi, eski pipeline'a düşüldü:", e, file=sys.stderr)
            self.use_shader = False

        # ── Eski sabit-pipeline yedeği ────────────────────────────────
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


    def set_grid_mode(self, mode: str):
        """
        mode:
          'all' – XY, XZ and YZ together
          'xy'  – XY plane only
          'xz'  – XZ plane only
          'yz'  – YZ plane only
        """
        assert mode in ('all', 'xy', 'xz', 'yz'), f"Unknown grid_mode: {mode}"
        self.grid_mode = mode
        self.grid_visible = True
        self.update()

    def set_grid_spacing(self, spacing: float):
        self._grid_spacing = spacing
        # isteğe bağlı: half_count'ü de orantılamak isterseniz:
        self._grid_half_count = int(200 * (1.0 / spacing))
        self.update()

    def paintGL(self):
        # --- debug / kamera matrisi / temel temizlik -------------------
        self.debug_dump()
        glClearColor(*self.bg_color)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glTranslatef(self.x_translation, self.y_translation, self.zoom)
        glMultMatrixf(self.rotation_matrix.flatten('F'))

        # --- IZGARA -----------------------------------------------------
        if self.grid_visible:
            glUseProgram(0)
            glDisable(GL_LIGHTING)
            if self.grid_mode == 'all':
                self._draw_grid_xy();
                self._draw_grid_xz();
                self._draw_grid_yz()
            elif self.grid_mode == 'xy':
                self._draw_grid_xy()
            elif self.grid_mode == 'xz':
                self._draw_grid_xz()
            elif self.grid_mode == 'yz':
                self._draw_grid_yz()
            glEnable(GL_LIGHTING)
            if self.use_shader: glUseProgram(self.prog)

        # --- EKSEN ------------------------------------------------------
        if self.axis_visible:
            glUseProgram(0);
            glDisable(GL_LIGHTING)
            glLineWidth(0.5);
            self._draw_axis()
            glEnable(GL_LIGHTING)
            if self.use_shader: glUseProgram(self.prog)

        # --- MESH'LER ---------------------------------------------------
        for mesh in self.meshes:
            self._draw_mesh(mesh)

        # --- Seçili mesh vurgusu + kesme çizgisi ------------------------
        if self.selected_mesh:
            self._highlight(self.selected_mesh)
        self._draw_cut_line()

        # --- ERASE overlay ---------------------------------------------
        if self.mode == 'erase' and self.erase_cursor is not None:
            self._draw_erase_circle()

    def set_axis_visible(self, visible: bool):
        """Eksen çizimini aç/kapa."""
        self.axis_visible = visible
        self.update()

    def set_erase_radius_px(self, px: float):
        self.erase_radius_px = float(px)
        self.update()

    def set_grid_visible(self, visible: bool):
        """Grid çizimini aç/kapa."""
        self.grid_visible = visible
        self.update()

    def _draw_axis(self):
        """X (kırmızı), Y (yeşil), Z (mavi) eksenlerini çizer."""
        l = self.axis_length
        glBegin(GL_LINES)
        # X ekseni – kırmızı
        glColor3f(1.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(l, 0.0, 0.0)
        # Y ekseni – yeşil
        glColor3f(0.0, 1.0, 0.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, l, 0.0)
        # Z ekseni – mavi
        glColor3f(0.0, 0.0, 1.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, l)
        glEnd()

    def set_axis_length(self, length: float):
        """Eksen uzunluğunu günceller ve yeniden çizim yapar."""
        self.axis_length = length
        self.update()

    def _draw_grid_xy(self):
        """XY düzleminde sonsuz ızgara (Z=0)."""
        cam = getattr(self, 'camera', None)
        cx = cy = 0.0
        if cam:
            pos = cam.position
            s = self._grid_spacing
            cx = math.floor(pos[0]/s) * s
            cy = math.floor(pos[1]/s) * s

        half = self._grid_half_count
        s = self._grid_spacing
        glColor3f(0.5, 0.5, 0.5)
        glBegin(GL_LINES)
        for i in range(-half, half+1):
            off = i*s
            # Y sabit çizgi (X boyunca)
            glVertex3f(cx-half*s, cy+off, 0.0)
            glVertex3f(cx+half*s, cy+off, 0.0)
            # X sabit çizgi (Y boyunca)
            glVertex3f(cx+off, cy-half*s, 0.0)
            glVertex3f(cx+off, cy+half*s, 0.0)
        glEnd()

    def _draw_grid_xz(self):
        """XZ düzleminde sonsuz ızgara (Y=0)."""
        cam = getattr(self, 'camera', None)
        cx = cz = 0.0
        if cam:
            pos = cam.position
            s = self._grid_spacing
            cx = math.floor(pos[0]/s) * s
            cz = math.floor(pos[2]/s) * s

        half = self._grid_half_count
        s = self._grid_spacing
        glColor3f(0.5, 0.5, 0.5)
        glBegin(GL_LINES)
        for i in range(-half, half+1):
            off = i*s
            # Z sabit çizgi (X boyunca)
            glVertex3f(cx-half*s, 0.0, cz+off)
            glVertex3f(cx+half*s, 0.0, cz+off)
            # X sabit çizgi (Z boyunca)
            glVertex3f(cx+off, 0.0, cz-half*s)
            glVertex3f(cx+off, 0.0, cz+half*s)
        glEnd()

    def _draw_grid_yz(self):
        """YZ düzleminde sonsuz ızgara (X=0)."""
        cam = getattr(self, 'camera', None)
        cy = cz = 0.0
        if cam:
            pos = cam.position
            s = self._grid_spacing
            cy = math.floor(pos[1]/s) * s
            cz = math.floor(pos[2]/s) * s

        half = self._grid_half_count
        s = self._grid_spacing
        glColor3f(0.5, 0.5, 0.5)
        glBegin(GL_LINES)
        for i in range(-half, half+1):
            off = i*s
            # Z sabit çizgi (Y boyunca)
            glVertex3f(0.0, cy-half*s, cz+off)
            glVertex3f(0.0, cy+half*s, cz+off)
            # Y sabit çizgi (Z boyunca)
            glVertex3f(0.0, cy+off, cz-half*s)
            glVertex3f(0.0, cy+off, cz+half*s)
        glEnd()

    def _create_vao(self, mesh):
        """Bir Mesh için (henüz yoksa) VAO kurar ve öznitelikleri bağlar."""
        if mesh.vao:
            return
        mesh.vao = glGenVertexArrays(1)
        glBindVertexArray(mesh.vao)

        # --- Pozisyon ---
        glBindBuffer(GL_ARRAY_BUFFER, mesh.vbo_v)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)

        # --- Renk (varsa) ---
        if mesh.vbo_c:
            glBindBuffer(GL_ARRAY_BUFFER, mesh.vbo_c)
            glEnableVertexAttribArray(1)
            glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 0, None)

        # --- Normal ---
        glBindBuffer(GL_ARRAY_BUFFER, mesh.vbo_n)
        glEnableVertexAttribArray(2)
        glVertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, 0, None)

        # --- Eleman dizisi ---
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, mesh.vbo_i)

        glBindVertexArray(0)  # temizle

    def _draw_mesh(self, m, id_color=None):
        if not hasattr(m, "vao"):
            self._create_vao(m)

        use_vao = self.use_vao and getattr(m, "vao", 0) and id_color is None

        # ── tampon bağlama ────────────────────────────────────────────
        if use_vao:
            glBindVertexArray(m.vao)
        else:
            # a_pos
            glBindBuffer(GL_ARRAY_BUFFER, m.vbo_v)
            glEnableVertexAttribArray(0)
            glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)

            # a_col (yalnız seçim-renk veya vertex-renk varsa)
            if id_color is None and m.vbo_c:
                glBindBuffer(GL_ARRAY_BUFFER, m.vbo_c)
                glEnableVertexAttribArray(1)
                glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 0, None)
            else:
                glDisableVertexAttribArray(1)

            # a_nrm (daima gerekli)
            glBindBuffer(GL_ARRAY_BUFFER, m.vbo_n)
            glEnableVertexAttribArray(2)
            glVertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, 0, None)

            # indeks
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, m.vbo_i)

        # ── model matrisleri ──────────────────────────────────────────
        glPushMatrix()
        glTranslatef(*m.translation)
        sx, sy, sz = (m.scale if isinstance(m.scale, (list, tuple, np.ndarray))
                      else (m.scale,) * 3)
        glScalef(sx, sy, sz)

        R = np.asarray(m.rotation, np.float32)
        if R.shape == (3, 3):
            M = np.identity(4, np.float32);
            M[:3, :3] = R
        else:
            M = R.reshape(4, 4)
        glMultMatrixf(M.flatten('F'))

        # ── shader / sabit pip. ───────────────────────────────────────
        restore_attr1 = False
        if id_color is None and self.use_shader:
            glUseProgram(self.prog)

            # MVP
            mv = np.array(glGetFloatv(GL_MODELVIEW_MATRIX),
                          np.float32).reshape(4, 4).T
            pr = np.array(glGetFloatv(GL_PROJECTION_MATRIX),
                          np.float32).reshape(4, 4).T
            mvp = pr @ mv
            glUniformMatrix4fv(self.u_mvp, 1, GL_FALSE, mvp.T)

            # normal matrisi (MV'nin üst-sol 3×3'ü)
            glUniformMatrix3fv(self.u_nmat, 1, GL_FALSE, mv[:3, :3].T)

            # ışık + malzeme
            glUniform3f(self.u_ldir, 0.577, 0.577, 0.577)  # (1,1,1) normalleştirilmiş
            glUniform3f(self.u_amb, 0.20, 0.20, 0.20)
            glUniform3f(self.u_dif, 0.80, 0.80, 0.80)

            # sabit renkli mesh için tek renk aktar
            if not m.vbo_c:
                glDisableVertexAttribArray(1)
                glVertexAttrib3f(1, *m.color)
        else:
            glUseProgram(0)
            if id_color:  # seçim modu
                glDisableVertexAttribArray(1)
                glVertexAttrib3f(1, *id_color)
                if m.vbo_c:  # <<< mesh'te vertex renk VARDIysa sonra geri aç
                    restore_attr1 = True  #
            elif not m.vbo_c:
                glDisableVertexAttribArray(1)
                glColor4f(*m.color, 0.1 if m.transparent else 1.0)

        # ── çizim ─────────────────────────────────────────────────────
        glDrawElements(GL_TRIANGLES, m.index_count, GL_UNSIGNED_INT, None)

        # ── temizlik ─────────────────────────────────────────────────
        if use_vao and restore_attr1:  # +++ EKLENDİ +++
            glEnableVertexAttribArray(1)  # attr-1'i tekrar aktif et
        if use_vao:
            glBindVertexArray(0)
        glUseProgram(0)
        glPopMatrix()

    def _highlight(self, m):
        glDisable(GL_LIGHTING)
        glColor3f(0, 0, 0)
        glLineWidth(0.5)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
        self._draw_mesh(m)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glEnable(GL_LIGHTING)

    def _draw_erase_circle(self):
        if self.erase_cursor is None:
            return
        cx, cy = self.erase_cursor.x(), self.height() - self.erase_cursor.y()
        rad_px = self.erase_radius_px

        glMatrixMode(GL_PROJECTION);
        glPushMatrix();
        glLoadIdentity()
        glOrtho(0, self.width(), 0, self.height(), -1, 1)
        glMatrixMode(GL_MODELVIEW);
        glPushMatrix();
        glLoadIdentity()

        glDisable(GL_DEPTH_TEST)
        glColor3f(0, 0, 0);
        glLineWidth(1.0)
        glBegin(GL_LINE_LOOP)
        for i in range(64):
            a = 2 * math.pi * i / 64
            glVertex2f(cx + rad_px * math.cos(a),
                       cy + rad_px * math.sin(a))
        glEnd()
        glEnable(GL_DEPTH_TEST)

        glPopMatrix();
        glMatrixMode(GL_PROJECTION);
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    def _model_matrix(self, m):
        S = np.diag([m.scale if np.isscalar(m.scale) else 1,
                     m.scale if np.isscalar(m.scale) else 1,
                     m.scale if np.isscalar(m.scale) else 1, 1]).astype(np.float32)
        R = np.identity(4, np.float32)
        R[:3, :3] = m.rotation if m.rotation.shape == (3, 3) \
            else m.rotation.reshape(4, 4)[:3, :3]
        T = np.identity(4, np.float32);
        T[:3, 3] = m.translation
        return T @ R @ S
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
        glLineWidth(0.5)
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
        # Create a deep copy of meshes with proper color handling
        meshes_copy = []
        for m in self.meshes:
            mesh_copy = copy.deepcopy(m)
            # Ensure colors are properly copied if they exist
            if hasattr(m, 'colors') and m.colors is not None:
                mesh_copy.colors = m.colors.copy()
            meshes_copy.append(mesh_copy)

        self.undo_stack.append({
            'meshes': meshes_copy,
            'rotation_matrix': self.rotation_matrix.copy(),
            'x_translation': self.x_translation,
            'y_translation': self.y_translation,
            'zoom': self.zoom,
            'bg_color': self.bg_color,
            'selected_id': self.selected_mesh.id if self.selected_mesh else None
        })
        self.redo_stack.clear()

    def load_state(self, s):
        """
        Undo/redo için kaydedilmiş durumu geri yükler ve GPU tamponlarını günceller.
        """
        try:
            self.makeCurrent()
            
            # 1) Önce mevcut GPU kaynaklarını temizle
            for m in self.meshes:
                if hasattr(m, 'vbo_v'):
                    glDeleteBuffers(1, [m.vbo_v])
                if hasattr(m, 'vbo_i'):
                    glDeleteBuffers(1, [m.vbo_i])
                if hasattr(m, 'vbo_c'):
                    glDeleteBuffers(1, [m.vbo_c])
                if hasattr(m, 'vbo_n'):
                    glDeleteBuffers(1, [m.vbo_n])
                if hasattr(m, 'vao'):
                    glDeleteVertexArrays(1, [m.vao])

            # 2) Python-side kopyaları yükle
            self.meshes = []
            for m in s['meshes']:
                mesh_copy = copy.deepcopy(m)
                # Ensure colors are properly copied if they exist
                if hasattr(m, 'colors') and m.colors is not None:
                    mesh_copy.colors = m.colors.copy()
                self.meshes.append(mesh_copy)

            # 3) GPU buffer'larını yeniden oluştur
            for m in self.meshes:
                # Vertex pozisyonu
                m.vbo_v = glGenBuffers(1)
                glBindBuffer(GL_ARRAY_BUFFER, m.vbo_v)
                glBufferData(GL_ARRAY_BUFFER,
                             m.vertices.nbytes,
                             m.vertices,
                             GL_STATIC_DRAW)

                # İndeksler
                m.vbo_i = glGenBuffers(1)
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, m.vbo_i)
                glBufferData(GL_ELEMENT_ARRAY_BUFFER,
                             m.indices.nbytes,
                             m.indices,
                             GL_STATIC_DRAW)

                # Renk tamponu (varsa)
                if hasattr(m, 'colors') and m.colors is not None:
                    m.vbo_c = glGenBuffers(1)
                    glBindBuffer(GL_ARRAY_BUFFER, m.vbo_c)
                    glBufferData(GL_ARRAY_BUFFER,
                                 m.colors.nbytes,
                                 m.colors,
                                 GL_STATIC_DRAW)

                # Normal tamponu
                if hasattr(m, 'normals') and m.normals is not None:
                    m.vbo_n = glGenBuffers(1)
                    glBindBuffer(GL_ARRAY_BUFFER, m.vbo_n)
                    glBufferData(GL_ARRAY_BUFFER,
                                 m.normals.nbytes,
                                 m.normals,
                                 GL_STATIC_DRAW)

                # VAO oluştur (eğer kullanılıyorsa)
                if self.use_vao:
                    m.vao = glGenVertexArrays(1)
                    glBindVertexArray(m.vao)
                    
                    # Vertex attributes
                    glBindBuffer(GL_ARRAY_BUFFER, m.vbo_v)
                    glEnableVertexAttribArray(0)
                    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)
                    
                    if hasattr(m, 'vbo_c') and m.vbo_c is not None:
                        glBindBuffer(GL_ARRAY_BUFFER, m.vbo_c)
                        glEnableVertexAttribArray(1)
                        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 0, None)
                    
                    glBindBuffer(GL_ARRAY_BUFFER, m.vbo_n)
                    glEnableVertexAttribArray(2)
                    glVertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, 0, None)
                    
                    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, m.vbo_i)
                    glBindVertexArray(0)

            # 4) Kamera & sahne durumunu yükle
            self.rotation_matrix = s['rotation_matrix'].copy()
            self.x_translation = s['x_translation']
            self.y_translation = s['y_translation']
            self.zoom = s['zoom']

            # 5) Arkaplan rengi
            self.bg_color = s.get('bg_color', self.bg_color)
            glClearColor(*self.bg_color)

            # 6) Seçili mesh
            sid = s['selected_id']
            self.selected_mesh = next((m for m in self.meshes if m.id == sid), None)

            # 7) Görünümü yenile
            self.update()

        except Exception as e:
            print(f"Error in load_state: {e}")
        finally:
            self.doneCurrent()

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

    def load_obj(self, fn: str):
        """
        HIZLI OBJ yükleyici:
          •   read() → tek pass; NumPy ile vertex/faces çıkarımı
          •   "f" satırlarındaki n-gon'ları tek seferde üçgen fana açar
          •   Vertex-renk yoksa MTL renklerini korur
        """
        import re, numpy as np, os
        from collections import defaultdict

        txt = open(fn, "r", errors="ignore").read().splitlines()

        v_lines = [l for l in txt if l.startswith("v ")]
        f_lines = [l for l in txt if l.startswith("f ")]
        usemtl = np.array([i for i, l in enumerate(txt) if l.startswith("usemtl")])
        mtl_of_line = {}
        for i in range(len(usemtl)):
            start = usemtl[i]
            end = usemtl[i + 1] if i + 1 < len(usemtl) else len(txt)
            mat = txt[start].split()[1]
            for ln in range(start + 1, end):
                mtl_of_line[ln] = mat

        # ---------- Vertex pozisyonları (r g b varsa al) ----------
        verts = np.empty((len(v_lines), 3), np.float32)
        vcols = np.empty((len(v_lines), 3), np.float32)
        has_col = False
        for i, l in enumerate(v_lines):
            vals = list(map(float, l.split()[1:]))
            verts[i] = vals[:3]
            if len(vals) >= 6:
                vcols[i] = vals[3:6]
                has_col = True
        c_arr = vcols if has_col else None
        verts -= verts.mean(0)

        # ---------- Faces → tek pass triangülasyon ----------
        faces_by_mat = defaultdict(list)
        tri_cnt = 0
        for ln, l in enumerate(f_lines):
            idx = [int(tok.split("/")[0]) - 1 for tok in l.split()[1:]]
            if len(idx) < 3:
                continue
            # fan
            base = idx[0]
            tris = [[base, idx[i], idx[i + 1]] for i in range(1, len(idx) - 1)]
            mat = mtl_of_line.get(ln, None)
            faces_by_mat[mat].extend(tris)
            tri_cnt += len(tris)

        if not tri_cnt:
            return  # boş

        # ---------- .mtl renklerini yükle ----------
        mtl_colors = {}
        mtl_match = re.search(r"mtllib +(\S+)", "\n".join(txt))
        if mtl_match:
            mtl_path = os.path.join(os.path.dirname(fn), mtl_match.group(1))
            mtl_colors = _parse_mtl(mtl_path)

        # ---------- Mesh'leri oluştur ----------
        self.save_state()
        for mat, tris in faces_by_mat.items():
            v_idx = np.array(tris, np.uint32).flatten()
            col = mtl_colors.get(mat, (0.8, 0.8, 0.8))
            m = Mesh(verts, v_idx,
                     colors=c_arr if has_col else None,
                     color=col,
                     mesh_name=f"{os.path.basename(fn)}_{mat or 'def'}")
            m.id = self.next_color_id;
            self.next_color_id += 1
            self.meshes.append(m)

        self.scene_changed.emit()
        self.update()

    def set_background_color(self):
        self.save_state()
        c = QColorDialog.getColor()
        if c.isValid():
            self.bg_color = (c.redF(), c.greenF(), c.blueF(), 1)
            self.makeCurrent()
            glClearColor(*self.bg_color)
            self.doneCurrent()
            self.update()

    def delete_selected_object(self):
        """Seçili mesh'i sil."""
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
        elif mode == 'erase':
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.cut_mode = False
            self.setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, e):
        if e.button() not in (Qt.LeftButton, Qt.RightButton):
            return

        self._dragging = True
        self.last_mouse_position = e.pos()

        # Cut modu başlangıcı
        if self.cut_mode and e.button() == Qt.LeftButton:
            self.cut_start_pos = e.pos()
            self._dragging = False
            self.update()
            return

        if self.mode == 'erase' and e.button() == Qt.LeftButton:
            # Sadece bayrak kaldırılıyor; save_state() buradan kaldırıldı.
            if not self.erase_dirty:
                self.save_state()  # ← silme öncesi state kaydı :contentReference[oaicite:0]{index=0}:contentReference[oaicite:1]{index=1}
                self.erase_dirty = True
            self.erase_cursor = e.pos()
            self._erase_triangles()
            self.update()
            return

        # Normal seçim
        if e.button() == Qt.LeftButton and self.mode is None:
            self.selected_mesh = self._pick(e.pos())
            self.update()

    def mouseMoveEvent(self, e):
        # Cut çizgisi
        if self.cut_mode and self.cut_start_pos:
            self.cut_end_pos = e.pos()
            self.update()
            return

        if self.mode == 'erase':
            self.erase_cursor = e.pos()
            if e.buttons() & Qt.LeftButton:
                self._erase_triangles()
            self.update()
            return

        if self.last_mouse_position is None:
            return

        d = e.pos() - self.last_mouse_position
        shift = bool(e.modifiers() & Qt.ShiftModifier)

        # -------- Seçili mesh varsa -----------------------------------
        if self.selected_mesh:
            if self.mode == 'move':
                R = self.rotation_matrix[:3, :3]
                if shift:  # ileri / geri
                    cam_fwd = R.T @ np.array([0, 0, -1], np.float32)
                    self.selected_mesh.translation += cam_fwd * (-d.y() * self.sens_move)
                else:  # sağ / yukarı
                    cam_r = R.T @ np.array([1, 0, 0], np.float32)
                    cam_u = R.T @ np.array([0, 1, 0], np.float32)
                    self.selected_mesh.translation += cam_r * (d.x() * self.sens_move) \
                                                      + cam_u * (-d.y() * self.sens_move)

            elif self.mode == 'rotate':
                ax, ay = d.y() * self.sens_rotate, d.x() * self.sens_rotate
                R = self.rotation_matrix[:3, :3]
                cam_r = R.T @ np.array([1, 0, 0], np.float32)
                cam_u = R.T @ np.array([0, 1, 0], np.float32)
                self.selected_mesh.rotation = self._rot_axis(ay, cam_u) @ \
                                              self._rot_axis(ax, cam_r) @ \
                                              self.selected_mesh.rotation

            elif self.mode == 'resize':
                delta = d.y() * self.sens_resize
                if delta:
                    self.selected_mesh.scale = max(self.selected_mesh.scale * (1 + delta), 0.1)

        # -------- Seçili mesh yok -------------------------------------
        else:
            if self.mode == 'move':
                if shift:  # zoom
                    self.zoom += -d.y() * self.sens_zoom
                    self.zoom = max(min(self.zoom, -0.2), -500.0)
                    self._update_projection()
                else:  # pan
                    self.x_translation += d.x() * self.sens_move
                    self.y_translation += -d.y() * self.sens_move

            elif self.mode == 'rotate' and (e.buttons() & Qt.RightButton):
                ax, ay = d.y() * self.sens_rotate, d.x() * self.sens_rotate
                self.rotation_matrix = self._rot(ay, 0, 1, 0) @ \
                                       self._rot(ax, 1, 0, 0) @ \
                                       self.rotation_matrix

        self.last_mouse_position = e.pos()
        self.update()

    def _inverse_mats(self):
        proj = glGetDoublev(GL_PROJECTION_MATRIX)
        view = glGetDoublev(GL_MODELVIEW_MATRIX)
        return np.linalg.inv(np.array(proj).reshape(4, 4).T), \
            np.linalg.inv(np.array(view).reshape(4, 4).T)

    def mouseReleaseEvent(self, e):
        # drag sonucu undo yalnızca cut_mod değilse kaydet

        # Silgi modunda release anında undo kaydı almak için:
        if self.mode == 'erase' and e.button() == Qt.LeftButton:
            if self.erase_dirty:
                self.save_state()  # değişiklik: silme sonrası undo için durum kaydı
                self.erase_dirty = False  # bayrak sıfırlanıyor
            return

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
        if self._dragging and not self.cut_mode and not self.mode == 'erase':
            self.save_state()
        self._dragging = False
        self.last_mouse_position = None

    def _erase_triangles(self):
        """
        Silgi dairesine giren üçgenleri keser; mesh boşalırsa siler.
        Silgi merkezi ve yarıçapı ekran pikselinde (`self.erase_cursor`,
        `self.erase_radius_px`) saklıdır.
        """
        if self.erase_cursor is None:
            return
        cx, cy = self.erase_cursor.x(), self.erase_cursor.y()
        r2 = self.erase_radius_px ** 2

        changed = False
        for m in list(self.meshes):
            try:
                # 1) verteksleri dünya → ekran
                verts_w = (self._model_matrix(m) @
                           np.c_[m.vertices, np.ones(len(m.vertices))].T).T[:, :3]
                scr_xy = self._screen_coords(verts_w)

                # 2) hangi verteksler daire içinde?
                dx = scr_xy[:, 0] - cx
                dy = scr_xy[:, 1] - cy  # y-eksen düzeltmesi
                inside = dx * dx + dy * dy < r2
                if not inside.any():
                    continue

                tri = m.indices.reshape(-1, 3)
                hit_tri = inside[tri].any(axis=1)  # ≥1 vert içerde
                if not hit_tri.any():
                    continue

                keep_tri = ~hit_tri
                changed = True

                if not keep_tri.any():  # mesh tamamen gitti
                    # Clean up GPU resources before removing
                    if hasattr(m, 'vbo_v'):
                        glDeleteBuffers(1, [m.vbo_v])
                    if hasattr(m, 'vbo_i'):
                        glDeleteBuffers(1, [m.vbo_i])
                    if hasattr(m, 'vbo_c'):
                        glDeleteBuffers(1, [m.vbo_c])
                    if hasattr(m, 'vbo_n'):
                        glDeleteBuffers(1, [m.vbo_n])
                    if hasattr(m, 'vao'):
                        glDeleteVertexArrays(1, [m.vao])
                    self.meshes.remove(m)
                    continue

                keep_idx = tri[keep_tri].flatten()
                uniq, new_idx = np.unique(keep_idx, return_inverse=True)

                # ── dizileri senkron küçült ───────────────────────────────
                m.vertices = m.vertices[uniq]
                if getattr(m, "colors", None) is not None:
                    m.colors = m.colors[uniq]
                if getattr(m, "normals", None) is not None:
                    m.normals = m.normals[uniq]

                m.indices = new_idx.astype(np.uint32)
                m.index_count = len(m.indices)

                # opsiyonel: normalleri yeniden hesapla (kaba)
                self._recalc_normals(m)

                # Update GPU buffers with error checking
                try:
                    self.makeCurrent()
                    # Vertex buffer
                    glBindBuffer(GL_ARRAY_BUFFER, m.vbo_v)
                    glBufferData(GL_ARRAY_BUFFER, m.vertices.nbytes, m.vertices, GL_STATIC_DRAW)
                    
                    # Index buffer
                    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, m.vbo_i)
                    glBufferData(GL_ELEMENT_ARRAY_BUFFER, m.indices.nbytes, m.indices, GL_STATIC_DRAW)
                    
                    # Color buffer (if exists)
                    if getattr(m, 'vbo_c', None) is not None and getattr(m, 'colors', None) is not None:
                        glBindBuffer(GL_ARRAY_BUFFER, m.vbo_c)
                        glBufferData(GL_ARRAY_BUFFER, m.colors.nbytes, m.colors, GL_STATIC_DRAW)
                    
                    # Normal buffer
                    if getattr(m, 'vbo_n', None) is not None and getattr(m, 'normals', None) is not None:
                        glBindBuffer(GL_ARRAY_BUFFER, m.vbo_n)
                        glBufferData(GL_ARRAY_BUFFER, m.normals.nbytes, m.normals, GL_STATIC_DRAW)
                    
                    glBindBuffer(GL_ARRAY_BUFFER, 0)
                    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
                    self.doneCurrent()
                except Exception as e:
                    print(f"Error updating GPU buffers: {e}")
                    continue

            except Exception as e:
                print(f"Error processing mesh: {e}")
                continue

        if changed:
            self.save_state()  # undo
            self.selected_mesh = None
            self.scene_changed.emit()
            self.selection_changed.emit(-1)
            self.update()

    def _recalc_normals(self, mesh):
        """
        Çok basit – her üçgen normali, o üçgenin üç verteksine kopyalanır.
        İsterseniz daha gelişmiş ortalama normal de hesaplayabilirsiniz.
        """
        v = mesh.vertices
        tri = mesh.indices.reshape(-1, 3)
        n = np.zeros_like(v, dtype=np.float32)

        a = v[tri[:, 1]] - v[tri[:, 0]]
        b = v[tri[:, 2]] - v[tri[:, 0]]
        face_n = np.cross(a, b)
        lens = np.linalg.norm(face_n, axis=1, keepdims=True) + 1e-12
        face_n /= lens

        for i, fn in enumerate(face_n):
            n[tri[i]] += fn
        lens = np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        mesh.normals = (n / lens).astype(np.float32)
    def screen_to_world(self, sx, sy, proj_inv, view_inv):
        """
        Convert 2D widget coords (sx,sy) into a world-space point on the near plane.
        We add a 0.5 offset so that we unproject from the pixel center, which
        makes the cut plane align exactly with the red guide line.
        """
        w, h = self.width(), self.height()

        # pixel-center correction
        x_ndc =  2.0 * (sx + 0.5) / w - 1.0
        y_ndc =  1.0 - 2.0 * (sy + 0.5) / h
        z_ndc = -1.0   # near plane

        ndc = np.array([x_ndc, y_ndc, z_ndc, 1.0], dtype=np.float64)

        # eye-space
        eye = proj_inv @ ndc
        eye /= eye[3]

        # world-space
        world = view_inv @ eye
        world /= world[3]

        return world[:3]

    def _perform_cut(self):
        # 1) must have start/end and a mesh
        if not (self.cut_start_pos and self.cut_end_pos and self.selected_mesh):
            return
            # 2) İlerleme iletişim kutusu
        dp = QProgressDialog("Mesh bölünüyor...", "İptal", 0, 100, self)
        dp.setWindowModality(Qt.WindowModal)
        dp.setValue(0)
        dp.show()

        # 3) Undo için mevcut durumu kaydet
        self.save_state()

        # 4) GL matrislerini güncelle, paintGL ile senkronize et
        self._update_projection()
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glTranslatef(self.x_translation, self.y_translation, self.zoom)
        glMultMatrixf(self.rotation_matrix.flatten('F'))

        # 5) Mevcut projeksiyon ve modelview matrislerini al ve terslerini hesapla
        proj = glGetDoublev(GL_PROJECTION_MATRIX)
        model = glGetDoublev(GL_MODELVIEW_MATRIX)
        P = np.array(proj, dtype=np.float64).reshape(4, 4).T
        V = np.array(model, dtype=np.float64).reshape(4, 4).T
        proj_inv = np.linalg.inv(P)
        view_inv = np.linalg.inv(V)

        # 6) Ekrandaki iki noktayı dünya uzayına geri dönüştür
        sx, sy = self.cut_start_pos.x(), self.cut_start_pos.y()
        ex, ey = self.cut_end_pos.x(), self.cut_end_pos.y()
        ws = self.screen_to_world(sx, sy, proj_inv, view_inv)
        we = self.screen_to_world(ex, ey, proj_inv, view_inv)

        # 7) Kamera pozisyonunu dünya uzayında bul
        cam_h = view_inv @ np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float64)
        cam_pos = cam_h[:3] / cam_h[3]

        # 8) İki ışınla düzlemi oluştur
        a = ws - cam_pos
        b = we - cam_pos
        normal = np.cross(a, b)
        nrm = np.linalg.norm(normal)
        if nrm < 1e-6:
            dp.close()
            return
        normal /= nrm
        d = -normal.dot(cam_pos)

        # 9) Mesh verilerini kopyala ve yeni Mesh örnekleri oluştur
        orig = self.selected_mesh
        verts = orig.vertices.copy()
        inds = orig.indices.copy()
        orig_cols = getattr(orig, 'colors', None)

        mk = Mesh(verts, inds, colors=orig_cols,
                  color=orig.color, mesh_name=orig.name + "_keep")
        mc = Mesh(verts, inds, colors=orig_cols,
                  color=orig.color, mesh_name=orig.name + "_cut")

        # 10) Orijinal transform ve render ayarlarını aktar
        mk.id, mc.id = orig.id, self.next_color_id
        self.next_color_id += 1
        for m in (mk, mc):
            m.translation = orig.translation.copy()
            m.rotation = orig.rotation.copy()
            m.scale = orig.scale
            m.transparent = orig.transparent

        # VBO renk verisini yeniden yükle
        if orig_cols is not None:
            from OpenGL.GL import glBindBuffer, glBufferData
            glBindBuffer(GL_ARRAY_BUFFER, mk.vbo_c)
            glBufferData(GL_ARRAY_BUFFER, orig_cols.nbytes, orig_cols, GL_STATIC_DRAW)

        # 11) Kesme işlemini yap ve ilerleme callback ile göster
        #    Pozitif yarı: %0–50
        mk.cut_by_plane(normal, d,
                        progress_callback=lambda p: dp.setValue(int(p * 0.5)))
        #    Negatif yarı: %50–100
        mc.cut_by_plane(-normal, -d,
                        progress_callback=lambda p: dp.setValue(50 + int(p * 0.5)))

        # 12) İşlem tamamlandı
        dp.setValue(100)
        dp.close()

        # 13) Sahneyi güncelle: orijinal mesh'i çıkar, yenilerini ekle
        self.meshes.remove(orig)
        self.meshes.extend([mk, mc])
        self.selected_mesh = None

        # 14) UI olaylarını tetikle ve yeniden çiz
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

        # Her mesh'i kendine özgü tek renkle çiz
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

        # 2-c: Her mesh'in axis-aligned bounding box'ı ile kesişimi bul
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

    def _world_radius_from_pixels(self, px):
        proj_inv, view_inv = self._inverse_mats()
        cx, cy = self.erase_cursor.x(), self.erase_cursor.y()
        w_c = self.screen_to_world(cx, cy, proj_inv, view_inv)
        w_rx = self.screen_to_world(cx + 1, cy, proj_inv, view_inv)
        dx = self._world_to_screen(w_rx)[0] - self._world_to_screen(w_c)[0]
        if dx == 0:  # güvenlik
            return 0.0
        return px / abs(dx)

    def _screen_coords(self, verts_world: np.ndarray) -> np.ndarray:
        """
        verts_world : (N,3) float32
        Dönüş       : (N,2) float32  – Qt ekran piksel koordinatı
        (0,0) sol-üst köşe olacak şekilde döner.
        """
        # --- 1)  dünya → kamera (view) -----------------------------------
        view = self._view_mat().astype(np.float64)  # (4×4)
        proj = self._proj_mat().astype(np.float64)  # (4×4)
        verts_h = np.c_[verts_world, np.ones(len(verts_world))].T  # (4×N)

        clip = proj @ (view @ verts_h)  # (4×N)
        ndc = (clip[:3] / clip[3]).T  # (N×3)

        # --- 2)  NDC (−1…+1)  →  ekran px (0,0 sol-üst) ------------------
        w, h = self.width(), self.height()
        scr = np.empty((len(ndc), 2), np.float32)
        scr[:, 0] = (ndc[:, 0] * 0.5 + 0.5) * w  # x
        scr[:, 1] = (1.0 - (ndc[:, 1] * 0.5 + 0.5)) * h  # y (sol-üst)
        return scr

    def _world_to_screen(self, world_pt):
        proj = glGetDoublev(GL_PROJECTION_MATRIX)
        view = glGetDoublev(GL_MODELVIEW_MATRIX)
        vp = glGetIntegerv(GL_VIEWPORT)
        sx, sy, _ = gluProject(world_pt[0], world_pt[1], world_pt[2],
                               view, proj, vp)
        return sx, sy

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


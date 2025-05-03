from PyQt5.QtWidgets import QColorDialog
from PyQt5.QtCore import Qt
from PyQt5.QtOpenGL import QGLWidget
from OpenGL.GL import *
from OpenGL.GLU import gluPerspective
from mesh import Mesh
import numpy as np
import copy

class Cube3DWidget(QGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rotation_matrix = np.identity(4, np.float32)
        self.x_translation = 0.0
        self.y_translation = 0.0
        self.zoom = -6.0
        self.last_mouse_position = None
        self.mode = None
        self.bg_color = (1, 1, 1, 1)
        self.undo_stack = []
        self.redo_stack = []
        self.meshes = []
        self.selected_mesh = None
        self.next_color_id = 1
        self.cut_mode = False
        self.cut_start_pos = None
        self.cut_end_pos = None
        self._dragging = False

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
        glLightfv(GL_LIGHT0, GL_POSITION, [4, 4, 10, 1])
        glLightfv(GL_LIGHT0, GL_AMBIENT, [0.2, 0.2, 0.2, 1])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.8, 0.8, 0.8, 1])

    def resizeGL(self, w, h):
        h = h or 1
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45, w / h, 0.1, 50)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glTranslatef(self.x_translation, self.y_translation, self.zoom)
        glMultMatrixf(self.rotation_matrix.flatten('F'))
        for m in self.meshes:
            self._draw_mesh(m)
        if self.selected_mesh:
            self._highlight(self.selected_mesh)
        self._draw_cut_line()

    def _draw_mesh(self, m, id_color=None):
        glPushMatrix()
        glTranslatef(*m.translation)
        glScalef(m.scale, m.scale, m.scale)
        glMultMatrixf(m.rotation.flatten('F'))
        a = 0.1 if m.transparent else 1.0

        # Eğer pick modunda id_color verilmişse onu kullan
        if id_color:
            glColor3f(*id_color)
        # Vertex-color varsa onu kullan, yoksa tek renk
        elif m.vbo_c:
            glEnableClientState(GL_COLOR_ARRAY)
            glBindBuffer(GL_ARRAY_BUFFER, m.vbo_c)
            glColorPointer(3, GL_FLOAT, 0, None)
        else:
            glColor4f(*m.color, a)

        # Vertex pozisyonu
        glBindBuffer(GL_ARRAY_BUFFER, m.vbo_v)
        glEnableClientState(GL_VERTEX_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, None)

        # Çizim
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, m.vbo_i)
        glDrawElements(GL_TRIANGLES, m.index_count, GL_UNSIGNED_INT, None)

        # Cleanup
        glDisableClientState(GL_VERTEX_ARRAY)
        if m.vbo_c:
            glDisableClientState(GL_COLOR_ARRAY)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
        glPopMatrix()

    def _highlight(self, m):
        glDisable(GL_LIGHTING)
        glColor3f(1, 1, 1)
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
        self.meshes = copy.deepcopy(s['meshes'])
        self.rotation_matrix = s['rotation_matrix'].copy()
        self.x_translation = s['x_translation']
        self.y_translation = s['y_translation']
        self.zoom = s['zoom']
        self.bg_color = s.get('bg_color', self.bg_color)
        glClearColor(*self.bg_color)
        sid = s['selected_id']
        self.selected_mesh = next((m for m in self.meshes if m.id == sid), None)
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

    def clear_scene(self):
        self.save_state()
        self.meshes.clear()
        self.selected_mesh = None
        self.rotation_matrix = np.identity(4, np.float32)
        self.update()

    def load_obj(self, fn):
        self.save_state()
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
            return

        self.makeCurrent()
        verts = np.asarray(verts, np.float32)
        faces = np.asarray(faces, np.uint32).flatten()
        verts -= verts.mean(axis=0)

        colors = np.asarray(cols, np.float32) if cols else None
        mesh = Mesh(verts, faces, colors)
        mesh.id = self.next_color_id
        self.next_color_id += 1
        self.meshes.append(mesh)
        self.doneCurrent()
        self.update()

    def set_background_color(self):
        self.save_state()
        c = QColorDialog.getColor()
        if c.isValid():
            self.bg_color = (c.redF(), c.greenF(), c.blueF(), 1)
            glClearColor(*self.bg_color)
            self.update()

    def delete_selected_object(self):
        if self.selected_mesh:
            self.save_state()
            self.meshes.remove(self.selected_mesh)
            self.selected_mesh = None
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
        if e.button() in (Qt.LeftButton, Qt.RightButton):
            self._dragging = True
            self.last_mouse_position = e.pos()
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
                    self.selected_mesh.translation += cam_forward * (-d.y() * 0.01)
                else:
                    cam_right = R.T @ np.array([1, 0, 0], np.float32)
                    cam_up    = R.T @ np.array([0, 1, 0], np.float32)
                    self.selected_mesh.translation += cam_right * (d.x() * 0.01) + cam_up * (-d.y() * 0.01)
            elif self.mode == 'rotate':
                ax, ay = d.y(), d.x()
                R = self.rotation_matrix[:3, :3]
                cam_right = R.T @ np.array([1, 0, 0], np.float32)
                cam_up    = R.T @ np.array([0, 1, 0], np.float32)
                r_vert = self._rot_axis(ax, cam_right)
                r_horz = self._rot_axis(ay, cam_up)
                self.selected_mesh.rotation = r_horz @ r_vert @ self.selected_mesh.rotation
            elif self.mode == 'resize':
                delta = d.y() * 0.01
                if delta:
                    self.selected_mesh.scale = max(self.selected_mesh.scale * (1 + delta), 0.1)
            elif self.mode == 'transparency':
                if d.x():
                    self.selected_mesh.transparent = d.x() > 0
        else:
            if self.mode == 'move':
                if shift:
                    self.zoom += -d.y() * 0.01
                else:
                    self.x_translation += d.x() * 0.01
                    self.y_translation += -d.y() * 0.01
            elif self.mode == 'rotate' and (e.buttons() & Qt.RightButton):
                ax, ay = d.y(), d.x()
                rx = self._rot(ax, 1, 0, 0)
                ry = self._rot(ay, 0, 1, 0)
                self.rotation_matrix = ry @ rx @ self.rotation_matrix
        self.last_mouse_position = e.pos()
        self.update()

    def mouseReleaseEvent(self, e):
        if self._dragging:
            self.save_state()
            self._dragging = False
        if e.button() == Qt.LeftButton and self.cut_mode and self.cut_start_pos:
            self.cut_end_pos = e.pos()
            self.cut_mode = False
            self.cut_start_pos = None
            self.cut_end_pos = None
            self.setCursor(Qt.ArrowCursor)
            self.update()
        else:
            self.last_mouse_position = None

    def wheelEvent(self, e):
        if e.angleDelta().y():
            self.save_state()
            self.zoom += e.angleDelta().y() * 0.001
            self.update()

    def _rot(self, angle, x, y, z):
        r = np.deg2rad(angle)
        c, s = np.cos(r), np.sin(r)
        n = np.sqrt(x*x + y*y + z*z)
        if n == 0:
            return np.identity(4, np.float32)
        x, y, z = x/n, y/n, z/n
        return np.array([
            [c + (1-c)*x*x,     (1-c)*x*y - s*z, (1-c)*x*z + s*y, 0],
            [(1-c)*y*x + s*z, c + (1-c)*y*y,     (1-c)*y*z - s*x, 0],
            [(1-c)*z*x - s*y, (1-c)*z*y + s*x, c + (1-c)*z*z,     0],
            [0,                 0,                 0,                 1]
        ], np.float32)

    def _rot_axis(self, angle, axis):
        r = np.deg2rad(angle)
        c, s = np.cos(r), np.sin(r)
        ax = axis / (np.linalg.norm(axis) + 1e-8)
        x, y, z = ax
        return np.array([
            [c + (1-c)*x*x,     (1-c)*x*y - s*z, (1-c)*x*z + s*y, 0],
            [(1-c)*y*x + s*z, c + (1-c)*y*y,     (1-c)*y*z - s*x, 0],
            [(1-c)*z*x - s*y, (1-c)*z*y + s*x, c + (1-c)*z*z,     0],
            [0,                 0,                 0,                 1]
        ], np.float32)

    def _pick(self, pos):
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
        for m in self.meshes:
            r = ((m.id & 0xFF0000) >> 16) / 255.0
            g = ((m.id & 0x00FF00) >> 8)  / 255.0
            b = (m.id & 0x0000FF)        / 255.0
            self._draw_mesh(m, (r, g, b))
        glFlush()
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        x, y = pos.x(), self.height() - pos.y()
        pix = glReadPixels(x, y, 1, 1, GL_RGB, GL_UNSIGNED_BYTE)
        pid = (pix[0] << 16) + (pix[1] << 8) + pix[2]
        glPopAttrib()
        return next((m for m in self.meshes if m.id == pid), None)

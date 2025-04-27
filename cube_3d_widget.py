from PyQt5.QtWidgets import QColorDialog
from PyQt5.QtCore import Qt
from PyQt5.QtOpenGL import QGLWidget
from OpenGL.GL import *
from OpenGL.GLU import gluPerspective, gluUnProject
from OpenGL.GL import glGetDoublev, glGetIntegerv, GL_MODELVIEW_MATRIX, GL_PROJECTION_MATRIX, GL_VIEWPORT
import numpy as np, copy
from mesh import Mesh

class Cube3DWidget(QGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rotation_matrix = np.identity(4, np.float32)
        self.x_translation = 0
        self.y_translation = 0
        self.zoom = -6.0
        self.last_mouse_position = None
        self.mode = None
        self.bg_color = (1, 1, 1, 1)
        self.undo_stack, self.redo_stack = [], []
        self.meshes, self.selected_mesh = [], None
        self.next_color_id = 1
        self.cut_mode = False
        self.cut_plane_point = self.cut_plane_normal = None
        self.cut_start_pos = self.cut_end_pos = None

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

    def _draw_mesh(self, m: Mesh, id_color=None):
        glPushMatrix()
        glTranslatef(*m.translation)
        glScalef(m.scale, m.scale, m.scale)
        glMultMatrixf(m.rotation.flatten('F'))
        a = 0.1 if m.transparent else 1.0
        if id_color:
            glColor3f(*id_color)
        else:
            glColor4f(*m.color, a)
        glBindBuffer(GL_ARRAY_BUFFER, m.vbo_v)
        glEnableClientState(GL_VERTEX_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, None)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, m.vbo_i)
        glDrawElements(GL_TRIANGLES, m.index_count, GL_UNSIGNED_INT, None)
        glDisableClientState(GL_VERTEX_ARRAY)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
        glPopMatrix()

    def _highlight(self, m: Mesh):
        glDisable(GL_LIGHTING)
        glColor3f(1, 1, 1)
        glLineWidth(2)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
        self._draw_mesh(m)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glEnable(GL_LIGHTING)

    def _draw_cut_line(self):
        if not (self.cut_mode and self.cut_start_pos and self.cut_end_pos): return
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

    def clear_scene(self):
        self.meshes.clear()
        self.selected_mesh = None
        self.rotation_matrix = np.identity(4, np.float32)
        self.update()

    def load_obj(self, fn):
        verts, faces = [], []
        with open(fn, 'r', errors='ignore') as f:
            for line in f:
                if line.startswith('v '):
                    verts.append(list(map(float, line.split()[1:4])))
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
        mesh = Mesh(verts, faces)
        mesh.id = self.next_color_id
        self.next_color_id += 1
        self.meshes.append(mesh)

        self.doneCurrent()
        self.update()

    def set_background_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.bg_color = (c.redF(), c.greenF(), c.blueF(), 1)
            glClearColor(*self.bg_color)
            self.update()

    def save_state(self):
        self.undo_stack.append({
            "meshes": copy.deepcopy(self.meshes, memo={}),
            "rotation_matrix": self.rotation_matrix.copy(),
            "x_translation": self.x_translation,
            "y_translation": self.y_translation,
            "zoom": self.zoom,
            "selected_id": self.selected_mesh.id if self.selected_mesh else None
        })
        self.redo_stack.clear()

    def load_state(self, s):
        self.meshes = copy.deepcopy(s["meshes"], memo={})
        self.rotation_matrix = s["rotation_matrix"].copy()
        self.x_translation = s["x_translation"]
        self.y_translation = s["y_translation"]
        self.zoom = s["zoom"]
        sid = s["selected_id"]
        self.selected_mesh = next((m for m in self.meshes if m.id == sid), None)
        self.update()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append({
            "meshes": copy.deepcopy(self.meshes, memo={}),
            "rotation_matrix": self.rotation_matrix.copy(),
            "x_translation": self.x_translation,
            "y_translation": self.y_translation,
            "zoom": self.zoom,
            "selected_id": self.selected_mesh.id if self.selected_mesh else None
        })
        self.load_state(self.undo_stack.pop())

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append({
            "meshes": copy.deepcopy(self.meshes, memo={}),
            "rotation_matrix": self.rotation_matrix.copy(),
            "x_translation": self.x_translation,
            "y_translation": self.y_translation,
            "zoom": self.zoom,
            "selected_id": self.selected_mesh.id if self.selected_mesh else None
        })
        self.load_state(self.redo_stack.pop())

    def delete_selected_object(self):
        if self.selected_mesh:
            self.save_state()
            self.meshes.remove(self.selected_mesh)
            self.selected_mesh = None
            self.update()

    def set_mode(self, mode):
        self.mode = mode
        if mode == "cut":
            self.cut_mode = True
            self.setCursor(Qt.CrossCursor)
        else:
            self.cut_mode = False
            self.setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self.cut_mode:
                self.cut_start_pos = e.pos()
                self.update()
            else:
                self.save_state()
                self.last_mouse_position = e.pos()
                self.selected_mesh = self._pick(e.pos())
                self.update()
        elif e.button() == Qt.RightButton:
            self.last_mouse_position = e.pos()

    def mouseMoveEvent(self, e):
        if self.cut_mode and self.cut_start_pos:
            self.cut_end_pos = e.pos()
            self.update()
            return
        if self.last_mouse_position is None:
            return
        d = e.pos() - self.last_mouse_position
        shift = e.modifiers() & Qt.ShiftModifier
        if self.selected_mesh:
            if self.mode == "rotate":
                ax, ay = d.y(), d.x()
                if shift:
                    rz = self._rot(ax, 0, 0, 1)
                    self.selected_mesh.rotation = rz @ self.selected_mesh.rotation
                else:
                    rx = self._rot(ax, 1, 0, 0)
                    ry = self._rot(ay, 0, 1, 0)
                    self.selected_mesh.rotation = (ry @ rx) @ self.selected_mesh.rotation
            elif self.mode == "move":
                if shift:
                    self.selected_mesh.translation[2] += d.y() * 0.01
                else:
                    self.selected_mesh.translation[0] += d.x() * 0.01
                    self.selected_mesh.translation[1] -= d.y() * 0.01
            elif self.mode == "resize":
                self.selected_mesh.scale = max(self.selected_mesh.scale * (1 + d.y() * 0.01), 0.1)
            elif self.mode == "transparency":
                if d.x() != 0:
                    self.selected_mesh.transparent = d.x() > 0
        else:
            if self.mode == "move" and not shift:
                self.x_translation += d.x() * 0.01
                self.y_translation -= d.y() * 0.01
        self.last_mouse_position = e.pos()
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.cut_mode and self.cut_start_pos:
            self.cut_end_pos = e.pos()
            self.cut_mode = False
            self.cut_start_pos = self.cut_end_pos = None
            self.setCursor(Qt.ArrowCursor)
            self.update()
        else:
            self.last_mouse_position = None

    def wheelEvent(self, e):
        if e.angleDelta().y() != 0:
            self.save_state()
            self.zoom += e.angleDelta().y() * 0.001
            self.update()

    def _rot(self, angle, x, y, z):
        r = np.deg2rad(angle)
        c, s = np.cos(r), np.sin(r)
        n = np.sqrt(x * x + y * y + z * z)
        if n == 0:
            return np.identity(4, np.float32)
        x, y, z = x / n, y / n, z / n
        return np.array(
            [
                [c + (1 - c) * x * x, (1 - c) * x * y - s * z, (1 - c) * x * z + s * y, 0],
                [(1 - c) * y * x + s * z, c + (1 - c) * y * y, (1 - c) * y * z - s * x, 0],
                [(1 - c) * z * x - s * y, (1 - c) * z * y + s * x, c + (1 - c) * z * z, 0],
                [0, 0, 0, 1],
            ],
            np.float32,
        )

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
            r = ((m.id & 0xFF0000) >> 16) / 255
            g = ((m.id & 0x00FF00) >> 8) / 255
            b = (m.id & 0x0000FF) / 255
            self._draw_mesh(m, (r, g, b))
        glFlush()
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        x, y = pos.x(), self.height() - pos.y()
        pix = glReadPixels(x, y, 1, 1, GL_RGB, GL_UNSIGNED_BYTE)
        pid = (pix[0] << 16) + (pix[1] << 8) + pix[2]
        glPopAttrib()
        return next((m for m in self.meshes if m.id == pid), None)

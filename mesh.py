# mesh.py
import numpy as np
from OpenGL.GL import *

class Mesh:
    def __init__(self,
                 vertices: np.ndarray,
                 indices: np.ndarray,
                 colors: np.ndarray | None = None,
                 color: tuple = (0.8, 0.8, 0.8),
                 normals: np.ndarray | None = None,  # ⬅ YENİ
                 mesh_name: str | None = None):

        # ---------- CPU kopyaları ----------
        self.vertices = vertices.copy().astype(np.float32)
        self.indices = indices.copy().astype(np.uint32)
        self.index_count = self.indices.size
        self.color = color
        self.colors = colors.copy().astype(np.float32) if colors is not None else None

        # ---------- Normalleri hazırla ----------
        if normals is None:  # OBJ’de vn yoksa üret
            normals = np.zeros_like(self.vertices)
            faces = self.indices.reshape(-1, 3)
            for f in faces:
                v0, v1, v2 = self.vertices[f]
                n = np.cross(v1 - v0, v2 - v0)
                ln = np.linalg.norm(n)
                if ln > 1e-8:
                    n /= ln
                normals[f] += n
            lens = np.linalg.norm(normals, axis=1)
            nz = lens > 1e-8
            normals[nz] /= lens[nz, None]
        self.normals = normals.astype(np.float32)

        # ---------- GPU tamponları ----------
        self.vbo_v = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_v)
        glBufferData(GL_ARRAY_BUFFER, self.vertices.nbytes,
                     self.vertices, GL_STATIC_DRAW)

        self.vbo_i = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.vbo_i)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, self.indices.nbytes,
                     self.indices, GL_STATIC_DRAW)

        if self.colors is not None:
            self.vbo_c = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo_c)
            glBufferData(GL_ARRAY_BUFFER, self.colors.nbytes,
                         self.colors, GL_STATIC_DRAW)
        else:
            self.vbo_c = None

        # ⬇⬇⬇  YENİ: normal VBO  ⬇⬇⬇
        self.vbo_n = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_n)
        glBufferData(GL_ARRAY_BUFFER, self.normals.nbytes,
                     self.normals, GL_STATIC_DRAW)

        # ---------- transform varsayılanları ----------
        self.translation = np.zeros(3, np.float32)
        self.scale = 1.0
        self.rotation = np.identity(4, np.float32)
        self.transparent = False
        self.name = mesh_name or f"Mesh {id(self)}"
        # self.id  Cube3DWidget tarafından atanacak

    def aabb_world(self):
        """Dünya uzayında axis-aligned bounding-box (mins, maxs)."""
        if not hasattr(self, "_aabb_local"):
            self._aabb_local = (self.vertices.min(0), self.vertices.max(0))
        mn, mx = self._aabb_local
        # ölçek + rot
        R = self.rotation[:3,:3] * self.scale
        corners = (R @ np.array([[mn[0],mn[1],mn[2]],
                                 [mx[0],mn[1],mn[2]],
                                 [mn[0],mx[1],mn[2]],
                                 [mx[0],mx[1],mn[2]],
                                 [mn[0],mn[1],mx[2]],
                                 [mx[0],mn[1],mx[2]],
                                 [mn[0],mx[1],mx[2]],
                                 [mx[0],mx[1],mx[2]]]).T).T
        corners += self.translation
        return corners.min(0), corners.max(0)

    def cut_by_plane(self, n: np.ndarray, d: float, progress_callback=None) -> bool:
        """
        n·p + d = 0 düzlemiyle mesh’i ikiye böler (Sutherland–Hodgman klipleme).
        Bu metod “pozitif” tarafta kalan kısmı *yerinde* tutar, öteki yarının
        yüzeylerini atar.    Dönüş değeri:  True  →  kesimden sonra hâlâ üçgen var.
        """

        # ---------- 1 · Düzlemi mesh’in yerel uzayına dönüştür ----------
        R = self.rotation[:3, :3] * self.scale  # world = R·local + t
        n_local = R.T @ n
        d_local = d + n.dot(self.translation)

        verts = self.vertices
        cols = self.colors if getattr(self, 'colors', None) is not None else None
        faces = self.indices.reshape(-1, 3)

        total = len(faces)  # ilerleme için
        from PyQt5.QtWidgets import QApplication

        new_verts, new_faces = [], []
        new_cols = [] if cols is not None else None

        # ---------- 2 · Yardımcı: çokgeni düzleme göre kliple ----------
        def clip_polygon(p_pts, p_cols, signs, keep_positive):
            out_pts, out_cols = [], [] if p_cols is not None else None
            L = len(p_pts)
            for i in range(L):
                j = (i + 1) % L
                P, Q = p_pts[i], p_pts[j]
                sP, sQ = signs[i], signs[j]
                cP = p_cols[i] if p_cols is not None else None

                insideP = (sP >= 0) if keep_positive else (sP <= 0)
                insideQ = (sQ >= 0) if keep_positive else (sQ <= 0)

                if insideP:  # P içerideyse koru
                    out_pts.append(P)
                    if out_cols is not None:
                        out_cols.append(cP)

                if insideP != insideQ:  # kenar kesişiyorsa
                    t = sP / (sP - sQ)
                    X = P + (Q - P) * t  # kesişim noktası
                    out_pts.append(X)
                    if out_cols is not None:
                        cQ = p_cols[j]
                        out_cols.append(cP + (cQ - cP) * t)
            return out_pts, out_cols

        # ---------- 3 · Tüm üçgenlerde klipleme + fan triangulation ----------
        for k, f in enumerate(faces):
            p = [verts[i] for i in f]
            c = [cols[i] for i in f] if cols is not None else None
            s = [float(n_local.dot(pi) + d_local) for pi in p]

            poly_pos, col_pos = clip_polygon(p, c, s, True)  # pozitif yarı

            def emit(poly, colpoly):
                if len(poly) < 3:
                    return
                base = len(new_verts)
                for pt in poly:
                    new_verts.append(pt)
                    if new_cols is not None:
                        new_cols.append(colpoly.pop(0))
                for i in range(1, len(poly) - 1):  # fan
                    new_faces.append([base, base + i, base + i + 1])

            emit(poly_pos, col_pos)

            if progress_callback:
                progress_callback(int((k + 1) / total * 100))
                QApplication.processEvents()

        if not new_faces:  # bu tarafta üçgen kalmadı
            return False

        # ---------- 4 · CPU tarafı dizileri güncelle ----------
        self.vertices = np.asarray(new_verts, np.float32)
        self.indices = np.asarray(new_faces, np.uint32).flatten()
        self.index_count = self.indices.size
        if cols is not None:
            self.colors = np.asarray(new_cols, np.float32)

        # ---------- 5 · Normalleri yeniden hesapla ----------
        normals = np.zeros_like(self.vertices)
        for f in self.indices.reshape(-1, 3):
            v0, v1, v2 = self.vertices[f]
            nrm = np.cross(v1 - v0, v2 - v0)
            ln = np.linalg.norm(nrm)
            if ln > 1e-8:
                nrm /= ln
            normals[f] += nrm
        lens = np.linalg.norm(normals, axis=1)
        nz = lens > 1e-8
        normals[nz] /= lens[nz, None]
        self.normals = normals.astype(np.float32)

        # ---------- 6 · GPU tamponlarını tazele ----------
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_v)
        glBufferData(GL_ARRAY_BUFFER,
                     self.vertices.nbytes, self.vertices, GL_STATIC_DRAW)

        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.vbo_i)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER,
                     self.indices.nbytes, self.indices, GL_STATIC_DRAW)

        if cols is not None and getattr(self, 'vbo_c', None):
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo_c)
            glBufferData(GL_ARRAY_BUFFER,
                         self.colors.nbytes, self.colors, GL_STATIC_DRAW)

        # --- normal VBO’su (yoksa oluştur) ------------------------------
        if not getattr(self, 'vbo_n', None):
            self.vbo_n = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_n)
        glBufferData(GL_ARRAY_BUFFER,
                     self.normals.nbytes, self.normals, GL_STATIC_DRAW)

        return True

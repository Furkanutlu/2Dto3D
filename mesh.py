# mesh.py
import numpy as np
from OpenGL.GL import *

class Mesh:
    def __init__(self,
                 vertices: np.ndarray,
                 indices: np.ndarray,
                 colors: np.ndarray | None = None,
                 color: tuple = (0.8, 0.8, 0.8),
                 mesh_name: str | None = None):
        # ------------- veriyi sakla -----------------
        self.vertices = vertices.copy()
        self.indices = indices.copy()
        self.index_count = indices.size
        self.color = color
        self.colors = colors.copy()
        self.translation = np.zeros(3, np.float32)
        self.scale = 1.0
        self.rotation = np.identity(4, np.float32)
        self.transparent = False
        self.name = mesh_name or f"Mesh {id(self)}"
        # id atama Cube3DWidget’te yapılacak

        # ------------- VBO / IBO --------------------
        self.vbo_v = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_v)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)

        self.vbo_i = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.vbo_i)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)

        if colors is not None:
            self.vbo_c = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo_c)
            glBufferData(GL_ARRAY_BUFFER, colors.nbytes, colors, GL_STATIC_DRAW)
        else:
            self.vbo_c = None

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

    def cut_by_plane(self, n: np.ndarray, d: float) -> bool:
        """
        n·p + d = 0 düzlemi ile gerçek split:
         - self.vertices / self.colors üzerinden Sutherland–Hodgman ile klipleme yapar
         - üçgenleri bölüp her yarıda kendi poligonlarını korur
         - yüzeyi kapatma (open cut), ancak parçalar shape kaybı yaşamaz
        Dönüş: eğer bu yarıda hiç yüzey kalmadıysa False, yoksa True.
        """

        # 1) Lokal uzayda klip için düzlemi dönüştür
        #    world = R @ local + t, R = scale·rotation
        R = self.rotation[:3, :3] * self.scale
        n_local = R.T @ n
        d_local = d + n.dot(self.translation)

        verts = self.vertices
        cols  = self.colors if hasattr(self, 'colors') else None
        faces = self.indices.reshape(-1, 3)

        new_verts = []
        new_cols  = [] if cols is not None else None
        new_faces = []

        # yardımcı: bir poligonu yarıya kliple
        def clip_polygon(poly_pts, poly_cols, signs, keep_positive):
            out_pts, out_cols = [], [] if poly_cols is not None else None
            L = len(poly_pts)
            for i in range(L):
                j = (i + 1) % L
                P, Q = poly_pts[i], poly_pts[j]
                sP, sQ = signs[i], signs[j]
                cP = poly_cols[i] if poly_cols is not None else None

                insideP = (sP >= 0) if keep_positive else (sP <= 0)
                insideQ = (sQ >= 0) if keep_positive else (sQ <= 0)

                # 1) eğer P içerdeyse, kaydet
                if insideP:
                    out_pts.append(P)
                    if poly_cols is not None: out_cols.append(cP)

                # 2) kenar kesişiyorsa, kesişim noktasını ekle
                if insideP != insideQ:
                    t = sP / (sP - sQ)
                    X = P + (Q - P) * t
                    out_pts.append(X)
                    if poly_cols is not None:
                        cQ = poly_cols[j]
                        out_cols.append(cP + (cQ - cP) * t)

            return out_pts, out_cols

        # her üçgeni ayrıştır
        for f in faces:
            p = [verts[i] for i in f]
            c = [cols[i] for i in f] if cols is not None else None
            s = [float(n_local.dot(pi) + d_local) for pi in p]

            # pozitif yarı (n·p + d >= 0)
            poly_pos, col_pos = clip_polygon(p, c, s, True)
            # negatif yarı
            poly_neg, col_neg = clip_polygon(p, c, s, False)

            # triangulate ve ekle
            def emit(poly, colpoly):
                if len(poly) < 3: return
                # v0, v1, v2... fan triangulation
                base = len(new_verts)
                for pt in poly:
                    new_verts.append(pt)
                    if new_cols is not None: new_cols.append(colpoly.pop(0))
                for k in range(1, len(poly) - 1):
                    new_faces.append([base, base + k, base + k + 1])

            # bu mesh.method çağrısı pozitif tarafı tutacağı için sadece pos ekle
            emit(poly_pos, col_pos)

        if not new_faces:
            return False

        # flatten ve yeniden atama
        new_verts = np.array(new_verts, np.float32)
        new_idx   = np.array(new_faces, np.uint32).flatten()
        self.vertices   = new_verts
        self.indices    = new_idx
        self.index_count = new_idx.size

        # renk varsa güncelle
        if cols is not None:
            self.colors = np.array(new_cols, np.float32)

        # GPU buffer’larını yenile
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_v)
        glBufferData(GL_ARRAY_BUFFER, self.vertices.nbytes, self.vertices, GL_STATIC_DRAW)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.vbo_i)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, self.indices.nbytes, self.indices, GL_STATIC_DRAW)
        if getattr(self, 'vbo_c', None) and cols is not None:
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo_c)
            glBufferData(GL_ARRAY_BUFFER, self.colors.nbytes, self.colors, GL_STATIC_DRAW)

        return True
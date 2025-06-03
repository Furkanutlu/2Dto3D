# mesh.py  –  CPU-optimize & stable
import numpy as np
from OpenGL.GL import *
from numba import njit            #  ← eklendi
from OpenGL.GL import GL_POINTS, GL_TRIANGLES
from math import radians, sin, cos

# ----------------------------------------------------------------------
# Numba JIT’li Sutherland–Hodgman clip
# ----------------------------------------------------------------------
@njit(cache=True, fastmath=True)
def _clip_polygon(pts, cols, sg):
    """
    Pozitif yarıyı (sg ≥ 0) korur, kenar kesişimlerinde ara nokta ekler.
    DÖNÜŞ: out_pts (N×3), out_cols (N×3)  – cols=None ise ikinci eleman None
    """
    keep = sg >= 0.0
    L = pts.shape[0]

    # En fazla 6 köşe çıkabilir; 10 garantili tampon yeterli
    out_p = np.empty((10, 3), np.float32)
    out_c = np.empty((10, 3), np.float32) if cols is not None else None
    n = 0

    for i in range(L):
        j = (i + 1) % L
        P = pts[i];  Q = pts[j]
        sP = sg[i];  sQ = sg[j]

        if keep[i]:
            out_p[n] = P
            if out_c is not None:
                out_c[n] = cols[i]
            n += 1

        if sP * sQ < 0.0:               # kenar düzlemi kesiyor
            t = sP / (sP - sQ)
            X = P + (Q - P) * t
            out_p[n] = X
            if out_c is not None:
                out_c[n] = cols[i] + (cols[j] - cols[i]) * t
            n += 1

    return out_p[:n], (out_c[:n] if out_c is not None else None)


# ----------------------------------------------------------------------
# Ana Mesh sınıfı
# ----------------------------------------------------------------------
class Mesh:
    def __init__(self,
                 vertices: np.ndarray,
                 indices: np.ndarray,
                 colors: np.ndarray | None = None,
                 color: tuple = (0.8, 0.8, 0.8),
                 normals: np.ndarray | None = None,
                 mesh_name: str | None = None):

        # ---------- CPU kopyaları ----------
        self.vertices = vertices.astype(np.float32).copy()
        self.indices = indices.astype(np.uint32).copy()
        self.index_count = self.indices.size
        self.draw_mode = GL_POINTS if self.index_count == 0 else GL_TRIANGLES
        self.colors = colors.astype(np.float32).copy() if colors is not None else None
        self.color = color
        self.vao = 0


        # ---------- Normalleri üret ----------
        if normals is None:
            normals = np.zeros_like(self.vertices)

            if self.index_count >= 3:
                f = self.indices.reshape(-1, 3)
                v0, v1, v2 = self.vertices[f[:, 0]], self.vertices[f[:, 1]], self.vertices[f[:, 2]]
                nrm = np.cross(v1 - v0, v2 - v0)
                ln = np.linalg.norm(nrm, axis=1)
                ln[ln < 1e-8] = 1.0
                nrm /= ln[:, None]  # normalize
                np.add.at(normals, f[:, 0], nrm)
                np.add.at(normals, f[:, 1], nrm)
                np.add.at(normals, f[:, 2], nrm)
                lens = np.linalg.norm(normals, axis=1)
                mask = lens > 1e-8
                normals[mask] /= lens[mask][:, None]
        self.normals = normals.astype(np.float32)

        # ---------- GPU tamponları ----------
        self.vbo_v = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_v)
        glBufferData(GL_ARRAY_BUFFER, self.vertices.nbytes, self.vertices, GL_STATIC_DRAW)

        self.vbo_i = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.vbo_i)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, self.indices.nbytes, self.indices, GL_STATIC_DRAW)

        self.vbo_c = None
        if self.colors is not None:
            self.vbo_c = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo_c)
            glBufferData(GL_ARRAY_BUFFER, self.colors.nbytes, self.colors, GL_STATIC_DRAW)

        self.vbo_n = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_n)
        glBufferData(GL_ARRAY_BUFFER, self.normals.nbytes, self.normals, GL_STATIC_DRAW)

        # ---------- Transform ----------
        self.translation = np.zeros(3, np.float32)
        self.scale = 1.0
        self.rotation = np.identity(4, np.float32)
        self.transparent = False
        self.name = mesh_name or f"Mesh_{id(self)}"
        # self.id  → Cube3DWidget atar

    # ------------------------------------------------------------------
    # Axis-aligned bounding box (world space)
    # ------------------------------------------------------------------
    def aabb_world(self):
        if not hasattr(self, "_aabb_local"):
            self._aabb_local = (self.vertices.min(0), self.vertices.max(0))
        mn, mx = self._aabb_local
        R = self.rotation[:3, :3] * self.scale
        corners = (R @ np.array(
            [[mn[0], mn[1], mn[2]],
             [mx[0], mn[1], mn[2]],
             [mn[0], mx[1], mn[2]],
             [mx[0], mx[1], mn[2]],
             [mn[0], mn[1], mx[2]],
             [mx[0], mn[1], mx[2]],
             [mn[0], mx[1], mx[2]],
             [mx[0], mx[1], mx[2]]]).T).T + self.translation
        return corners.min(0), corners.max(0)

    # ------------------------------------------------------------------
    # Kesme işlemi (CPU, hızlı)
    # ------------------------------------------------------------------
    def cut_by_plane(self,
                     n: np.ndarray,          # dünya uzayı normali
                     d: float,               # world denklem sabiti
                     progress_callback=None,
                     flush_gpu=True) -> bool:
        """
        n·p + d = 0 düzlemiyle mesh’i ikiye böler.  Pozitif yarı tutulur.
        True dönerse kesim sonrası üçgen kaldı.
        """

        # 1) Düzlemi yerel uzaya çevir
        R = self.rotation[:3, :3] * self.scale
        n_loc = R.T @ n
        d_loc = d + n.dot(self.translation)

        V = self.vertices
        F = self.indices.reshape(-1, 3)
        C = self.colors if self.colors is not None else None

        # 2) Tepe işaretleri tek geçişte
        sign = (V @ n_loc + d_loc).astype(np.float32)

        keep_tri, cross_tri = [], []
        for fi, f in enumerate(F):
            s = sign[f]
            if np.all(s >= 0):
                keep_tri.append(fi)
            elif np.all(s <= 0):
                continue
            else:
                cross_tri.append(fi)

        # 3) Tam içeride üçgenleri kopyala
        new_V, new_F = [], []
        new_C = [] if C is not None else None
        v_ofs = 0
        for fi in keep_tri:
            idx = F[fi]
            new_V.extend(V[idx])
            if new_C is not None:
                new_C.extend(C[idx])
            new_F.append([v_ofs, v_ofs + 1, v_ofs + 2])
            v_ofs += 3

        # 4) Kesen üçgenleri kliple
        total = len(cross_tri)
        step = max(1, total // 100)
        for k, fi in enumerate(cross_tri, 1):
            idx = F[fi]
            pts = V[idx]
            cols = C[idx] if C is not None else None
            sg = sign[idx]

            poly, colpoly = _clip_polygon(pts, cols, sg)

            if len(poly) < 3:
                continue

            base = v_ofs
            new_V.extend(poly)
            if new_C is not None:
                new_C.extend(colpoly)
            for i in range(1, len(poly) - 1):
                new_F.append([base, base + i, base + i + 1])
            v_ofs += len(poly)

            if progress_callback and k % step == 0:
                progress_callback(int(k / total * 100))

        if not new_F:                # her şey silindiyse
            return False

        # 5) CPU dizilerini güncelle
        self.vertices = np.asarray(new_V, np.float32)
        self.indices = np.asarray(new_F, np.uint32).flatten()
        self.index_count = self.indices.size
        if new_C is not None:
            self.colors = np.asarray(new_C, np.float32)

        # 6) Normalleri tek geçişte hesapla
        normals = np.zeros_like(self.vertices)
        f = self.indices.reshape(-1, 3)
        v0, v1, v2 = self.vertices[f[:, 0]], self.vertices[f[:, 1]], self.vertices[f[:, 2]]
        nrm = np.cross(v1 - v0, v2 - v0)
        ln = np.linalg.norm(nrm, axis=1)
        ln[ln < 1e-8] = 1.0
        nrm /= ln[:, None]  # ← düzeltme
        np.add.at(normals, f[:, 0], nrm)
        np.add.at(normals, f[:, 1], nrm)
        np.add.at(normals, f[:, 2], nrm)
        lens = np.linalg.norm(normals, axis=1)  # ← keepdims=False
        mask = lens > 1e-8
        normals[mask] /= lens[mask][:, None]  # ← broadcast
        self.normals = normals.astype(np.float32)

        # 7) GPU tamponlarını istersek tazele
        if flush_gpu:
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo_v)
            glBufferData(GL_ARRAY_BUFFER, self.vertices.nbytes, self.vertices, GL_STATIC_DRAW)

            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.vbo_i)
            glBufferData(GL_ELEMENT_ARRAY_BUFFER, self.indices.nbytes, self.indices, GL_STATIC_DRAW)

            if self.colors is not None:
                if self.vbo_c is None:
                    self.vbo_c = glGenBuffers(1)
                glBindBuffer(GL_ARRAY_BUFFER, self.vbo_c)
                glBufferData(GL_ARRAY_BUFFER, self.colors.nbytes, self.colors, GL_STATIC_DRAW)

            glBindBuffer(GL_ARRAY_BUFFER, self.vbo_n)
            glBufferData(GL_ARRAY_BUFFER, self.normals.nbytes, self.normals, GL_STATIC_DRAW)

        return True

    def _update_gpu(self):
        """
        vertices / colors / normals / indices dizilerindeki son
        değişiklikleri mevcut VBO’lara kopyalar.
        """
        import numpy as np
        from OpenGL.GL import (
            glBindBuffer, glBufferData,
            GL_ARRAY_BUFFER, GL_ELEMENT_ARRAY_BUFFER, GL_STATIC_DRAW
        )

        # --- vertex pozisyonu ------------------------------------------------
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_v)
        glBufferData(GL_ARRAY_BUFFER,
                     self.vertices.astype(np.float32).nbytes,
                     self.vertices.astype(np.float32),
                     GL_STATIC_DRAW)

        # --- renk ------------------------------------------------------------
        if getattr(self, "vbo_c", 0) and getattr(self, "colors", None) is not None:
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo_c)
            glBufferData(GL_ARRAY_BUFFER,
                         self.colors.astype(np.float32).nbytes,
                         self.colors.astype(np.float32),
                         GL_STATIC_DRAW)

        # --- normal ----------------------------------------------------------
        if getattr(self, "vbo_n", 0) and getattr(self, "normals", None) is not None:
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo_n)
            glBufferData(GL_ARRAY_BUFFER,
                         self.normals.astype(np.float32).nbytes,
                         self.normals.astype(np.float32),
                         GL_STATIC_DRAW)

        # --- indeks ----------------------------------------------------------
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.vbo_i)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER,
                     self.indices.astype(np.uint32).nbytes,
                     self.indices.astype(np.uint32),
                     GL_STATIC_DRAW)

    def update_buffers(self):

        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_v)
        glBufferData(GL_ARRAY_BUFFER,
                     self.vertices.astype(np.float32).nbytes,
                     self.vertices.astype(np.float32),
                     GL_STATIC_DRAW)

        if getattr(self, "vbo_c", None) and self.colors is not None:
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo_c)
            glBufferData(GL_ARRAY_BUFFER,
                         self.colors.astype(np.float32).nbytes,
                         self.colors.astype(np.float32),
                         GL_STATIC_DRAW)

    def model_matrix(self) -> np.ndarray:
        sx, sy, sz = self.scale, self.scale, self.scale
        rx, ry, rz = map(radians, self.rotation)  # deg→rad
        cx, sx_ = cos(rx), sin(rx)
        cy, sy_ = cos(ry), sin(ry)
        cz, sz_ = cos(rz), sin(rz)

        R = np.array([
            [cy * cz, -cy * sz_, sy_, 0],
            [sx_ * sy_ * cz + cx * sz_, -sx_ * sy_ * sz_ + cx * cz, -sx_ * cy, 0],
            [-cx * sy_ * cz + sx_ * sz_, cx * sy_ * sz_ + sx_ * cz, cx * cy, 0],
            [0, 0, 0, 1]
        ], dtype=np.float32)
        S = np.diag([sx, sy, sz, 1])
        T = np.eye(4, dtype=np.float32);
        T[0:3, 3] = self.translation
        return T @ R @ S  # T·R·S
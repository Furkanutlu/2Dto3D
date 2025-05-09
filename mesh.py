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
        n·p + d = 0 düzleminin n·p + d < 0 tarafını SİLER.
        Üçgenin tüm verteksi kesim tarafındaysa yüzey atılır.
        Dönüş: Mesh boş kalırsa False (sahneden atılmalı).
        """
        # 1) World-space’e dönüştürülmüş vertex’ler
        R = self.rotation[:3, :3] * self.scale
        verts_w = (R @ self.vertices.T).T + self.translation

        # 2) Her vertex’in düzleme göre işareti
        sign = verts_w @ n + d  # (N,)
        keep_mask = sign >= 0  # True → bu vertex kalacak

        # 3) Üçgenleri (faces) ayıkla
        faces = self.indices.reshape(-1, 3)  # (M,3)
        keep_faces = keep_mask[faces].all(axis=1)  # (M,)
        if not keep_faces.any():
            return False  # Tüm mesh siliniyor

        kept = faces[keep_faces]  # (K,3)

        # 4) Sadece kullanılan vertex indekslerini bulup tekilleştir
        flat_idxs, inv_map = np.unique(kept.flatten(), return_inverse=True)

        # 5) Yeni vertex ve index dizilerini oluştur
        new_vertices = self.vertices[flat_idxs]  # (V',3)
        new_indices = inv_map.reshape(-1, 3).astype(np.uint32)  # (K,3)
        new_indices = new_indices.flatten()  # (K*3,)

        # 6) Mesh verisini güncelle
        self.vertices = new_vertices
        self.indices = new_indices
        self.index_count = new_indices.size

        # 7) GPU buffer’larını yenile
        #    vertex buffer
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_v)
        glBufferData(GL_ARRAY_BUFFER,
                     self.vertices.nbytes,
                     self.vertices,
                     GL_STATIC_DRAW)
        #    index buffer
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.vbo_i)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER,
                     self.indices.nbytes,
                     self.indices,
                     GL_STATIC_DRAW)

        return True
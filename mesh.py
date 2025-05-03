# mesh.py
import numpy as np
from OpenGL.GL import *

class Mesh:
    def __init__(self,
                 vertices: np.ndarray,
                 indices: np.ndarray,
                 colors: np.ndarray = None,
                 color: tuple = (0.8, 0.8, 0.8)):
        self.index_count = indices.size
        self.color       = color
        self.translation = np.zeros(3, np.float32)
        self.scale       = 1.0
        self.rotation    = np.identity(4, np.float32)
        self.transparent = False

        # Vertex positions
        self.vbo_v = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_v)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)

        # Indices
        self.vbo_i = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.vbo_i)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)

        # Optional vertex colors
        if colors is not None:
            self.vbo_c = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo_c)
            glBufferData(GL_ARRAY_BUFFER, colors.nbytes, colors, GL_STATIC_DRAW)
        else:
            self.vbo_c = None

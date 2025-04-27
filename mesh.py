import numpy as np
from OpenGL.GL import *

class Mesh:
    def __init__(self, vertices: np.ndarray, indices: np.ndarray, color=(0.8, 0.8, 0.8)):
        self.index_count = indices.size
        self.color = color
        self.translation = np.zeros(3, np.float32)
        self.scale = 1.0
        self.rotation = np.identity(4, np.float32)
        self.transparent = False
        self.vbo_v = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo_v)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
        self.vbo_i = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.vbo_i)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)

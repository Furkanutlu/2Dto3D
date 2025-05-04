from OpenGL.GL import *
import ctypes, sys

def _compile(src, stype):
    sid = glCreateShader(stype)
    glShaderSource(sid, src)
    glCompileShader(sid)
    if glGetShaderiv(sid, GL_COMPILE_STATUS) != GL_TRUE:
        log = glGetShaderInfoLog(sid).decode()
        raise RuntimeError(f"Shader hata [{stype}] ▸\n{log}")
    return sid

def build_program(vsrc: str, fsrc: str) -> int:
    vs = _compile(vsrc, GL_VERTEX_SHADER)
    fs = _compile(fsrc, GL_FRAGMENT_SHADER)
    prog = glCreateProgram()
    glAttachShader(prog, vs)
    glAttachShader(prog, fs)
    glBindAttribLocation(prog, 0, "a_pos")
    glBindAttribLocation(prog, 1, "a_col")
    glLinkProgram(prog)
    if glGetProgramiv(prog, GL_LINK_STATUS) != GL_TRUE:
        raise RuntimeError(glGetProgramInfoLog(prog).decode())
    glDeleteShader(vs); glDeleteShader(fs)
    return prog

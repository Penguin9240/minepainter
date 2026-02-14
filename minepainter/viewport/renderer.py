"""
ModelRenderer: manages all OpenGL resources (VAOs, VBOs, textures, shaders)
and issues draw calls for the Minecraft character model.

Must only be used from inside the QOpenGLWidget context (after initializeGL).
"""
from __future__ import annotations

import ctypes
import math
from typing import Optional

import numpy as np
from OpenGL import GL

from minepainter.viewport.shaders import VERTEX_SRC, FRAGMENT_SRC
from minepainter.viewport.mesh_builder import VERTEX_STRIDE, POSITION_OFFSET, UV_OFFSET, NORMAL_OFFSET, STAND_PARTS
from minepainter.skin_constants import BASE_PARTS, OUTER_PARTS


# Fixed key-light direction (pre-normalised)
_RAW_LIGHT = np.array([1.0, 2.0, 1.5], dtype=np.float32)
LIGHT_DIR = (_RAW_LIGHT / np.linalg.norm(_RAW_LIGHT)).tolist()
AMBIENT = 0.65


def _compile_shader(src: str, shader_type: int) -> int:
    shader = GL.glCreateShader(shader_type)
    GL.glShaderSource(shader, src)
    GL.glCompileShader(shader)
    if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
        log = GL.glGetShaderInfoLog(shader).decode()
        raise RuntimeError(f"Shader compile error:\n{log}")
    return shader


def _link_program(vert: int, frag: int) -> int:
    prog = GL.glCreateProgram()
    if not prog:
        raise RuntimeError("glCreateProgram returned 0 — GL context may not be active")
    GL.glAttachShader(prog, vert)
    GL.glAttachShader(prog, frag)
    GL.glLinkProgram(prog)
    if not GL.glGetProgramiv(prog, GL.GL_LINK_STATUS):
        log = GL.glGetProgramInfoLog(prog).decode()
        raise RuntimeError(f"Shader link error:\n{log}")
    GL.glDeleteShader(vert)
    GL.glDeleteShader(frag)
    return prog


class ModelRenderer:
    def __init__(self) -> None:
        self._program: int = 0
        self._vaos: dict[str, int] = {}
        self._vbos: dict[str, int] = {}
        self._vertex_counts: dict[str, int] = {}
        self._tex_base: int = 0
        self._tex_armor: int = 0
        self._show_base: bool = True
        self._show_armor: bool = True
        self._show_stand: bool = False   # only True when editing armor layer

    # ------------------------------------------------------------------
    # Initialisation (call once, from initializeGL)
    # ------------------------------------------------------------------

    def initialize(self, meshes: dict[str, np.ndarray]) -> None:
        """Compile shaders, upload geometry, create textures."""
        # Clear any pre-existing GL errors left by Qt's own initialization.
        # On macOS this is common and causes PyOpenGL's error checker to fire
        # on the very first GL call if not cleared first.
        # Use the raw (unchecked) glGetError to drain without triggering the checker.
        from OpenGL.raw.GL.VERSION.GL_1_0 import glGetError as _raw_glGetError
        while _raw_glGetError() != GL.GL_NO_ERROR:
            pass

        vert = _compile_shader(VERTEX_SRC, GL.GL_VERTEX_SHADER)
        frag = _compile_shader(FRAGMENT_SRC, GL.GL_FRAGMENT_SHADER)
        self._program = _link_program(vert, frag)

        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glClearColor(0.35, 0.35, 0.40, 1.0)

        for name, verts in meshes.items():
            vao = GL.glGenVertexArrays(1)
            vbo = GL.glGenBuffers(1)
            GL.glBindVertexArray(vao)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, verts.nbytes, verts, GL.GL_STATIC_DRAW)

            stride = VERTEX_STRIDE
            # position: location 0, 3 floats
            GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, stride,
                                     ctypes.c_void_p(POSITION_OFFSET))
            GL.glEnableVertexAttribArray(0)
            # UV coords: location 1, 2 floats
            GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, stride,
                                     ctypes.c_void_p(UV_OFFSET))
            GL.glEnableVertexAttribArray(1)
            # normal: location 2, 3 floats
            GL.glVertexAttribPointer(2, 3, GL.GL_FLOAT, GL.GL_FALSE, stride,
                                     ctypes.c_void_p(NORMAL_OFFSET))
            GL.glEnableVertexAttribArray(2)

            GL.glBindVertexArray(0)
            self._vaos[name] = vao
            self._vbos[name] = vbo
            self._vertex_counts[name] = len(verts) // 8

        self._tex_base  = self._create_texture()
        self._tex_armor = self._create_texture()

    def _create_texture(self) -> int:
        tex = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        # GL_NEAREST is critical: no blurring on pixel-art skin textures
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
        # Allocate 64×64 RGBA initially transparent
        zeros = np.zeros((64, 64, 4), dtype=np.uint8)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, 64, 64, 0,
                        GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, zeros)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        return tex

    # ------------------------------------------------------------------
    # Texture updates
    # ------------------------------------------------------------------

    def upload_texture(self, layer: str, image: np.ndarray) -> None:
        """Upload a full 64×64 RGBA array to the GPU texture for `layer`.

        OpenGL's glTexSubImage2D places row 0 of the data at the *bottom*
        of the texture (v=0).  Our UV formula uses v = 1 - py/64, so PNG
        row 0 (py=0) maps to v=1.0 which is the GL *top*.  We must flip
        the image vertically before upload so that PNG row 0 lands at GL
        v=1 (top) rather than v=0 (bottom).  Without this flip, the top
        of the head (py=0..7) samples from the wrong part of the texture
        and appears as a hole.
        """
        tex = self._tex_base if layer == "base" else self._tex_armor
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        GL.glTexSubImage2D(GL.GL_TEXTURE_2D, 0, 0, 0, 64, 64,
                           GL.GL_RGBA, GL.GL_UNSIGNED_BYTE,
                           np.ascontiguousarray(image[::-1]))
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

    def update_texture_pixel(
        self, layer: str, x: int, y: int, rgba: tuple[int, int, int, int]
    ) -> None:
        """Efficient single-pixel update via glTexSubImage2D.

        y is in PNG space (row 0 = top).  GL texture y=0 is the bottom,
        so we convert: gl_y = 63 - y.
        """
        tex = self._tex_base if layer == "base" else self._tex_armor
        pixel = np.array([[rgba]], dtype=np.uint8)  # shape (1, 1, 4)
        gl_y = 63 - y   # flip PNG row → GL row
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        GL.glTexSubImage2D(GL.GL_TEXTURE_2D, 0, x, gl_y, 1, 1,
                           GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, pixel)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

    # ------------------------------------------------------------------
    # Visibility
    # ------------------------------------------------------------------

    def set_layer_visible(self, layer: str, visible: bool) -> None:
        if layer == "base":
            self._show_base = visible
        else:
            self._show_armor = visible

    def set_show_stand(self, show: bool) -> None:
        """Show or hide the armor stand rod/base geometry."""
        self._show_stand = show

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(
        self,
        view: np.ndarray,
        proj: np.ndarray,
        model: Optional[np.ndarray] = None,
    ) -> None:
        if model is None:
            from minepainter.viewport.math_utils import identity
            model = identity()

        if not self._program:
            return

        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        GL.glUseProgram(self._program)

        # Set uniforms
        self._set_uniform_mat4("u_model", model)
        self._set_uniform_mat4("u_view",  view)
        self._set_uniform_mat4("u_proj",  proj)
        GL.glUniform3f(GL.glGetUniformLocation(self._program, "u_light_dir"),
                       *LIGHT_DIR)
        GL.glUniform1f(GL.glGetUniformLocation(self._program, "u_ambient"), AMBIENT)
        GL.glUniform1i(GL.glGetUniformLocation(self._program, "u_texture"), 0)

        GL.glActiveTexture(GL.GL_TEXTURE0)
        loc_is_base  = GL.glGetUniformLocation(self._program, "u_is_base")
        loc_use_flat = GL.glGetUniformLocation(self._program, "u_use_flat")
        loc_flat_col = GL.glGetUniformLocation(self._program, "u_flat_color")

        # Default: textured mode
        GL.glUniform1i(loc_use_flat, 0)

        if self._show_base:
            GL.glUniform1i(loc_is_base, 1)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._tex_base)
            for part in BASE_PARTS:
                if part in self._vaos:
                    self._draw_part(part)

        if self._show_armor:
            GL.glUniform1i(loc_is_base, 0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._tex_armor)
            for part in OUTER_PARTS:
                if part in self._vaos:
                    self._draw_part(part)

        # Draw the armor stand structure: wooden frame in tan, stone base in grey
        if self._show_stand:
            GL.glUniform1i(loc_use_flat, 1)
            # Wooden parts — warm oak/birch tan (matches Minecraft's stripped wood)
            GL.glUniform4f(loc_flat_col, 0.71, 0.55, 0.33, 1.0)  # rgb(181,140,84)
            for part in STAND_PARTS:
                if part == "stand_base":
                    continue   # drawn separately below
                if part in self._vaos:
                    self._draw_part(part)
            # Stone slab base — cool grey
            GL.glUniform4f(loc_flat_col, 0.52, 0.52, 0.52, 1.0)  # rgb(133,133,133)
            if "stand_base" in self._vaos:
                self._draw_part("stand_base")
            GL.glUniform1i(loc_use_flat, 0)

        GL.glUseProgram(0)

    def _draw_part(self, name: str) -> None:
        GL.glBindVertexArray(self._vaos[name])
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, self._vertex_counts[name])
        GL.glBindVertexArray(0)

    def _set_uniform_mat4(self, name: str, mat: np.ndarray) -> None:
        loc = GL.glGetUniformLocation(self._program, name)
        GL.glUniformMatrix4fv(loc, 1, GL.GL_TRUE, mat.astype(np.float32))

    def set_viewport(self, w: int, h: int) -> None:
        GL.glViewport(0, 0, w, h)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        for vao in self._vaos.values():
            GL.glDeleteVertexArrays(1, [vao])
        for vbo in self._vbos.values():
            GL.glDeleteBuffers(1, [vbo])
        if self._tex_base:
            GL.glDeleteTextures(1, [self._tex_base])
        if self._tex_armor:
            GL.glDeleteTextures(1, [self._tex_armor])
        if self._program:
            GL.glDeleteProgram(self._program)

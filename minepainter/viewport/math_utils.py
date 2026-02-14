"""
Minimal numpy-based 3D math helpers.
Avoids adding pyrr or glm as a dependency.
"""
from __future__ import annotations

import math

import numpy as np


def look_at(
    eye: np.ndarray | list,
    target: np.ndarray | list,
    up: np.ndarray | list,
) -> np.ndarray:
    """Return a column-major 4×4 view matrix (float32)."""
    e = np.asarray(eye,    dtype=np.float32)
    t = np.asarray(target, dtype=np.float32)
    u = np.asarray(up,     dtype=np.float32)

    f = t - e
    f = f / np.linalg.norm(f)

    r = np.cross(f, u)
    r = r / np.linalg.norm(r)

    up_real = np.cross(r, f)

    m = np.eye(4, dtype=np.float32)
    m[0, :3] =  r
    m[1, :3] =  up_real
    m[2, :3] = -f
    m[0, 3]  = -np.dot(r, e)
    m[1, 3]  = -np.dot(up_real, e)
    m[2, 3]  =  np.dot(f, e)
    return m


def perspective(fov_rad: float, aspect: float, near: float, far: float) -> np.ndarray:
    """Return a column-major 4×4 perspective projection matrix (float32)."""
    f = 1.0 / math.tan(fov_rad / 2.0)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[3, 2] = -1.0
    m[2, 3] = (2.0 * far * near) / (near - far)
    return m


def identity() -> np.ndarray:
    return np.eye(4, dtype=np.float32)

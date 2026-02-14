"""
CPU-side ray casting against the character mesh for 3D painting.

Given a mouse position and the current camera matrices, casts a ray into the
scene and finds the closest triangle that it hits.  Returns the skin-texture
pixel coordinates (px, py) at the intersection point by interpolating the
per-vertex UV coordinates stored in the mesh.

All mesh data stays on the CPU (the same numpy arrays used to build the VAOs),
so no GPU readback is needed.
"""
from __future__ import annotations

from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Ray construction
# ---------------------------------------------------------------------------

def ray_from_screen(
    mouse_x: float,
    mouse_y: float,
    viewport_w: int,
    viewport_h: int,
    view: np.ndarray,
    proj: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Construct a world-space ray from a screen pixel position.

    Returns (origin, direction) as float32 (3,) arrays.

    We build the ray analytically from the view matrix rows rather than
    inverting matrices, which avoids sign-convention issues in look_at.

    The view matrix rows are the camera's right (row 0), up (row 1), and
    -forward (row 2) axes in world space.  The camera eye position is
    recovered as  eye = -R^T @ t  (transpose of rotation × translation).
    """
    V = view.astype(np.float64)

    # Camera basis vectors (world space) from view matrix rows
    right   = V[0, :3]
    up      = V[1, :3]
    forward = -V[2, :3]   # row 2 is -forward in standard look_at

    # Eye position: V maps world→camera, so eye = R^T * (-t) where t = V[:3,3]
    t   = V[:3, 3]
    R   = V[:3, :3]
    eye = -R.T @ t

    # Half-extents of the near plane in world units
    # proj[1,1] = f = 1/tan(fov/2),  so tan(fov/2) = 1/f
    # near-plane half-height = near * tan(fov/2) = near/f
    f      = float(proj[1, 1])
    near   = float(proj[2, 3] / (proj[2, 2] - 1.0))   # recover near from projection
    aspect = float(proj[1, 1] / proj[0, 0])            # f/aspect = proj[0,0]

    half_h = near / f
    half_w = half_h * aspect

    # NDC coordinates: x in [-1,1], y in [-1,1] (screen top → ndc y = +1)
    ndc_x = (2.0 * mouse_x / viewport_w) - 1.0
    ndc_y = 1.0 - (2.0 * mouse_y / viewport_h)

    # Point on the near plane in world space
    near_point = (eye
                  + forward * near
                  + right   * (ndc_x * half_w)
                  + up      * (ndc_y * half_h))

    direction = near_point - eye
    norm = np.linalg.norm(direction)
    if norm < 1e-10:
        direction = np.array([0.0, 0.0, -1.0])
    else:
        direction /= norm

    return eye.astype(np.float32), direction.astype(np.float32)


# ---------------------------------------------------------------------------
# Ray-triangle intersection (Möller–Trumbore)
# ---------------------------------------------------------------------------

_EPS = 1e-7


def ray_triangle(
    origin: np.ndarray,
    direction: np.ndarray,
    v0: np.ndarray,
    v1: np.ndarray,
    v2: np.ndarray,
) -> Optional[tuple[float, float, float]]:
    """
    Möller–Trumbore ray-triangle intersection.

    Returns (t, u_bary, v_bary) if the ray hits the front face of the triangle
    (t > 0), or None if it misses or hits the back face.

    t         = distance along the ray to the intersection
    u_bary, v_bary = barycentric coordinates (w = 1 - u - v)
    """
    edge1 = v1 - v0
    edge2 = v2 - v0
    h = np.cross(direction, edge2)
    a = np.dot(edge1, h)

    if abs(a) < _EPS:
        return None  # Ray is parallel to triangle

    f = 1.0 / a
    s = origin - v0
    u = f * np.dot(s, h)
    if u < 0.0 or u > 1.0:
        return None

    q = np.cross(s, edge1)
    v = f * np.dot(direction, q)
    if v < 0.0 or u + v > 1.0:
        return None

    t = f * np.dot(edge2, q)
    if t < _EPS:
        return None  # Intersection behind the ray origin

    return t, u, v


# ---------------------------------------------------------------------------
# Mesh hit test
# ---------------------------------------------------------------------------

def hit_mesh(
    origin: np.ndarray,
    direction: np.ndarray,
    meshes: dict[str, np.ndarray],
    parts: list[str],
) -> Optional[tuple[str, str, int, int]]:
    """
    Test the ray against all triangles in the given parts of the mesh.

    Returns (part_name, face_name, px, py) for the closest hit, or None.

    part_name is the key into `meshes` (e.g. "body", "r_arm").
    face_name is one of "front","back","right","left","top","bottom".
    px, py are skin-texture pixel coordinates (0..63).

    Each cuboid has 6 faces × 6 verts = 36 verts total.
    Face order matches build_cuboid: front, back, right, left, top, bottom.
    UV → skin pixel:  px = u * 64,  py = (1 - v) * 64
    """
    # Face names in the order they are appended by build_cuboid
    _FACE_NAMES = ["front", "back", "right", "left", "top", "bottom"]

    best_t     = float("inf")
    best_part: Optional[str] = None
    best_face: Optional[str] = None
    best_px:   Optional[int] = None
    best_py:   Optional[int] = None

    for part in parts:
        if part not in meshes:
            continue
        verts = meshes[part].reshape(-1, 8)   # (N_tris*3, 8)

        for i in range(0, len(verts), 3):
            p0 = verts[i,     :3].astype(np.float32)
            p1 = verts[i + 1, :3].astype(np.float32)
            p2 = verts[i + 2, :3].astype(np.float32)

            result = ray_triangle(origin, direction, p0, p1, p2)
            if result is None:
                continue

            t, u_bary, v_bary = result
            if t >= best_t:
                continue

            best_t = t

            w   = 1.0 - u_bary - v_bary
            uv0 = verts[i,     3:5]
            uv1 = verts[i + 1, 3:5]
            uv2 = verts[i + 2, 3:5]
            uv  = w * uv0 + u_bary * uv1 + v_bary * uv2

            px = int(uv[0] * 64)
            py = int((1.0 - uv[1]) * 64)
            px = max(0, min(63, px))
            py = max(0, min(63, py))
            best_part = part
            # Each face occupies 6 verts (2 triangles).
            # Triangle index i//3 divided by 2 gives the face index.
            face_idx  = (i // 3) // 2
            best_face = _FACE_NAMES[face_idx] if face_idx < len(_FACE_NAMES) else "front"
            best_px   = px
            best_py   = py

    if best_part is None:
        return None
    return best_part, best_face, best_px, best_py

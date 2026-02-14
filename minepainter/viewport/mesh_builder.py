"""
MeshBuilder: generates interleaved vertex data (position + UV texture coords
+ normal) for each Minecraft body-part cuboid.

"UV" here means OpenGL texture coordinates (0..1), derived from the pixel
regions defined in skin_constants.py — not related to the `uv` package manager.

Vertex layout (8 floats per vertex, interleaved):
    [x, y, z,  u, v,  nx, ny, nz]

Each cuboid face is two triangles = 6 vertices (no index buffer).
"""
from __future__ import annotations

import numpy as np

from minepainter.skin_constants import (
    BASE_PARTS,
    BASE_UV,
    BODY_DIMENSIONS,
    BODY_POSITIONS,
    OUTER_PARTS,
    OUTER_UV,
    TEXTURE_SIZE,
    ALEX_DIMENSIONS,
)

# Stride in bytes for one vertex
VERTEX_STRIDE = 8 * 4   # 8 floats × 4 bytes
POSITION_OFFSET = 0
UV_OFFSET       = 3 * 4
NORMAL_OFFSET   = 5 * 4


def _px_to_uv(px: int, py: int, pw: int, ph: int) -> tuple[float, float, float, float]:
    """
    Convert a pixel-space region (x, y, w, h) on the 64×64 PNG into
    normalised OpenGL UV coordinates.

    PNG convention: (0,0) is top-left.
    OpenGL convention: (0,0) is bottom-left, so v must be flipped.

    Returns (u0, u1, v0_top, v1_bottom) where:
        u0 = left edge,  u1 = right edge
        v0_top = GL v at the top pixel row (higher value)
        v1_bottom = GL v at the bottom pixel row (lower value)
    """
    u0 = px / TEXTURE_SIZE
    u1 = (px + pw) / TEXTURE_SIZE
    v0 = 1.0 - py / TEXTURE_SIZE           # top edge in GL coords
    v1 = 1.0 - (py + ph) / TEXTURE_SIZE    # bottom edge in GL coords
    return u0, u1, v0, v1


def _build_face(
    v0: np.ndarray, v1: np.ndarray, v2: np.ndarray, v3: np.ndarray,
    uv_corners: list[tuple[float, float]],
    normal: np.ndarray,
) -> np.ndarray:
    """
    Build 6 vertices (2 triangles, CCW winding) for a quad.

    v0..v3 are the four 3D corner positions (quad corners in order:
      bottom-left, bottom-right, top-right, top-left).
    uv_corners must match the same order.
    """
    nx, ny, nz = normal
    data: list[float] = []
    # Triangle 1: v0, v1, v2
    for v, (u, v_coord) in zip([v0, v1, v2], [uv_corners[0], uv_corners[1], uv_corners[2]]):
        data += [v[0], v[1], v[2], u, v_coord, nx, ny, nz]
    # Triangle 2: v0, v2, v3
    for v, (u, v_coord) in zip([v0, v2, v3], [uv_corners[0], uv_corners[2], uv_corners[3]]):
        data += [v[0], v[1], v[2], u, v_coord, nx, ny, nz]
    return np.array(data, dtype=np.float32)


def build_cuboid(
    w: float, h: float, d: float,
    cx: float, cy: float, cz: float,
    uv_faces: dict[str, tuple[int, int, int, int]],
) -> np.ndarray:
    """
    Build the 36-vertex (6 faces × 6 verts) mesh for a single cuboid.

    w, h, d: dimensions in model units (half-extents = w/2, h/2, d/2).
    cx, cy, cz: centre position.

    uv_faces: mapping face_name -> (px, py, pw, ph) pixel region.
      Face names: "front", "back", "right", "left", "top", "bottom".

    The Minecraft skin "net" UV convention for the back face is mirrored
    horizontally relative to the front face, so u0/u1 are swapped for it.
    """
    hw, hh, hd = w / 2, h / 2, d / 2

    # 8 corners of the cuboid
    # fmt: off
    corners = {
        "rlb": np.array([cx + hw, cy - hh, cz - hd]),  # right-lower-back
        "llb": np.array([cx - hw, cy - hh, cz - hd]),  # left-lower-back
        "rub": np.array([cx + hw, cy + hh, cz - hd]),  # right-upper-back
        "lub": np.array([cx - hw, cy + hh, cz - hd]),  # left-upper-back
        "rlf": np.array([cx + hw, cy - hh, cz + hd]),  # right-lower-front
        "llf": np.array([cx - hw, cy - hh, cz + hd]),  # left-lower-front
        "ruf": np.array([cx + hw, cy + hh, cz + hd]),  # right-upper-front
        "luf": np.array([cx - hw, cy + hh, cz + hd]),  # left-upper-front
    }
    # fmt: on

    faces: list[np.ndarray] = []

    # --- Front face (+Z, facing the viewer) ---
    if "front" in uv_faces:
        u0, u1, vt, vb = _px_to_uv(*uv_faces["front"])
        # Quad corners BL, BR, TR, TL from the viewer's perspective
        faces.append(_build_face(
            corners["llf"], corners["rlf"], corners["ruf"], corners["luf"],
            [(u0, vb), (u1, vb), (u1, vt), (u0, vt)],
            np.array([0, 0, 1], dtype=np.float32),
        ))

    # --- Back face (-Z) ---
    # Back face UVs are read right-to-left in the Minecraft skin net,
    # so u0 and u1 are swapped.
    if "back" in uv_faces:
        u0, u1, vt, vb = _px_to_uv(*uv_faces["back"])
        faces.append(_build_face(
            corners["rlb"], corners["llb"], corners["lub"], corners["rub"],
            [(u0, vb), (u1, vb), (u1, vt), (u0, vt)],
            np.array([0, 0, -1], dtype=np.float32),
        ))

    # --- Right face (+X, character's right) ---
    if "right" in uv_faces:
        u0, u1, vt, vb = _px_to_uv(*uv_faces["right"])
        faces.append(_build_face(
            corners["rlf"], corners["rlb"], corners["rub"], corners["ruf"],
            [(u0, vb), (u1, vb), (u1, vt), (u0, vt)],
            np.array([1, 0, 0], dtype=np.float32),
        ))

    # --- Left face (-X, character's left) ---
    if "left" in uv_faces:
        u0, u1, vt, vb = _px_to_uv(*uv_faces["left"])
        faces.append(_build_face(
            corners["llb"], corners["llf"], corners["luf"], corners["lub"],
            [(u0, vb), (u1, vb), (u1, vt), (u0, vt)],
            np.array([-1, 0, 0], dtype=np.float32),
        ))

    # --- Top face (+Y) ---
    if "top" in uv_faces:
        u0, u1, vt, vb = _px_to_uv(*uv_faces["top"])
        # Top face uses the upper corners; U runs along +X, V along +Z
        faces.append(_build_face(
            corners["luf"], corners["ruf"], corners["rub"], corners["lub"],
            [(u0, vt), (u1, vt), (u1, vb), (u0, vb)],
            np.array([0, 1, 0], dtype=np.float32),
        ))

    # --- Bottom face (-Y) ---
    if "bottom" in uv_faces:
        u0, u1, vt, vb = _px_to_uv(*uv_faces["bottom"])
        # Bottom face uses the lower corners; U runs along +X, V along +Z
        faces.append(_build_face(
            corners["rlf"], corners["llf"], corners["llb"], corners["rlb"],
            [(u0, vt), (u1, vt), (u1, vb), (u0, vb)],
            np.array([0, -1, 0], dtype=np.float32),
        ))

    return np.concatenate(faces, axis=0).astype(np.float32)


def _rotate_vertices_z(verts: np.ndarray, angle_deg: float, pivot: tuple[float, float]) -> np.ndarray:
    """
    Rotate position and normal XY components of all vertices around a Z-axis
    pivot point by angle_deg degrees.  The array has 8 floats per vertex:
    [x, y, z, u, v, nx, ny, nz] — only x,y (pos) and nx,ny (normal) are affected.
    """
    r = np.radians(angle_deg)
    cos_r, sin_r = np.cos(r), np.sin(r)
    out = verts.copy()
    # Positions — 8 floats/vertex, positions at offsets 0,1,2
    out[0::8] -= pivot[0]
    out[1::8] -= pivot[1]
    x = out[0::8].copy()
    y = out[1::8].copy()
    out[0::8] =  cos_r * x - sin_r * y + pivot[0]
    out[1::8] =  sin_r * x + cos_r * y + pivot[1]
    # Normals at offsets 5,6
    nx = out[5::8].copy()
    ny = out[6::8].copy()
    out[5::8] = cos_r * nx - sin_r * ny
    out[6::8] = sin_r * nx + cos_r * ny
    return out


def _rotate_vertices_x(verts: np.ndarray, angle_deg: float, pivot: tuple[float, float]) -> np.ndarray:
    """
    Rotate position and normal YZ components around an X-axis pivot (py, pz).
    """
    r = np.radians(angle_deg)
    cos_r, sin_r = np.cos(r), np.sin(r)
    out = verts.copy()
    # Positions y,z at offsets 1,2
    out[1::8] -= pivot[0]
    out[2::8] -= pivot[1]
    y = out[1::8].copy()
    z = out[2::8].copy()
    out[1::8] =  cos_r * y - sin_r * z + pivot[0]
    out[2::8] =  sin_r * y + cos_r * z + pivot[1]
    # Normals ny,nz at offsets 6,7
    ny = out[6::8].copy()
    nz = out[7::8].copy()
    out[6::8] = cos_r * ny - sin_r * nz
    out[7::8] = sin_r * ny + cos_r * nz
    return out


def build_stand_meshes() -> dict[str, np.ndarray]:
    """
    Build the untextured geometry for a Minecraft armor stand.

    Coordinate system: Y=0 at feet, matching the body model.
    The stand is built from several wooden cuboids + a stone slab base.

    Parts (all rendered flat — UV faces are dummy):
      "stand_head_knob"   – small knob where the head sits
      "stand_shoulder"    – wide horizontal shoulder bar
      "stand_body"        – narrow vertical torso pole
      "stand_waist"       – slightly wider waist joint
      "stand_leg_r"       – right leg, angled outward
      "stand_leg_l"       – left leg, angled outward
      "stand_base"        – flat stone slab at ground level
    """
    _DU = {f: (0, 0, 1, 1) for f in ("front", "back", "right", "left", "top", "bottom")}

    meshes: dict[str, np.ndarray] = {}

    # ── Head knob ───────────────────────────────────────────────────────
    # Sits at the top of the torso pole, small 2×3×2 block
    meshes["stand_head_knob"] = build_cuboid(2, 3, 2, 0, 25.5, 0, _DU)

    # ── Shoulder bar ────────────────────────────────────────────────────
    # Wide thin plank across the shoulders: 12 wide × 2 tall × 2 deep
    meshes["stand_shoulder"] = build_cuboid(12, 2, 2, 0, 23, 0, _DU)

    # ── Body pole ────────────────────────────────────────────────────────
    # Narrow vertical column from waist to shoulder: 2×8×2
    meshes["stand_body"] = build_cuboid(2, 8, 2, 0, 18, 0, _DU)

    # ── Waist joint ─────────────────────────────────────────────────────
    # Slightly wider block where legs meet torso: 4×2×2
    meshes["stand_waist"] = build_cuboid(4, 2, 2, 0, 13, 0, _DU)

    # ── Legs ────────────────────────────────────────────────────────────
    # Each leg is a thin pole (1.5×12×1.5) placed at ±1.5 from centre,
    # then rotated ~10° outward so they splay like the real stand.
    # Build straight first, then rotate around the waist pivot (y=12).
    r_leg = build_cuboid(1.5, 12, 1.5, 1.5, 6, 0, _DU)
    r_leg = _rotate_vertices_z(r_leg, +8.0, pivot=(1.5, 12.0))
    meshes["stand_leg_r"] = r_leg

    l_leg = build_cuboid(1.5, 12, 1.5, -1.5, 6, 0, _DU)
    l_leg = _rotate_vertices_z(l_leg, -8.0, pivot=(-1.5, 12.0))
    meshes["stand_leg_l"] = l_leg

    # ── Stone base ───────────────────────────────────────────────────────
    # Flat wide slab: 14 wide × 2 tall × 10 deep, sitting at y=1
    meshes["stand_base"] = build_cuboid(14, 2, 10, 0, 1, 0, _DU)

    return meshes


def build_stand_body_meshes(skin_type: str = "steve") -> dict[str, np.ndarray]:
    """
    Build the OUTER (armor) body-part meshes with arm/head poses baked in,
    matching the Minecraft armor stand appearance:
      - Right arm rotated ~-40° outward (Z rotation around right shoulder pivot)
      - Left arm rotated ~+40° outward (Z rotation around left shoulder pivot)
      - Head tilted ~-12° forward (X rotation around neck pivot)

    Returns a dict with the same outer-part keys as build_all_meshes but with
    modified vertex positions.
    """
    dims = ALEX_DIMENSIONS if skin_type == "alex" else BODY_DIMENSIONS
    meshes: dict[str, np.ndarray] = {}

    # Build non-arm, non-head outer parts normally
    for part in ("body", "r_leg", "l_leg"):
        outer = part + "_outer"
        w, h, d = dims[outer]
        cx, cy, cz = BODY_POSITIONS[part]
        meshes[outer] = build_cuboid(w, h, d, cx, cy, cz, OUTER_UV[part])

    # Head — build at normal position then tilt forward (rotate around X at neck y=24)
    hw, hh, hd = dims["head_outer"]
    hx, hy, hz = BODY_POSITIONS["head"]
    head_verts = build_cuboid(hw, hh, hd, hx, hy, hz, OUTER_UV["head"])
    # Neck pivot is at y=24 (top of body), z=0; positive angle tilts chin forward (+Z)
    head_verts = _rotate_vertices_x(head_verts, +12.0, pivot=(24.0, 0.0))
    meshes["head_outer"] = head_verts

    # Right arm — shoulder pivot at top of arm (rx, 24).
    # Positive Z rotation = counter-clockwise from front = arm swings right/outward.
    rw, rh, rd = dims["r_arm_outer"]
    rx, ry, rz = BODY_POSITIONS["r_arm"]
    r_arm_verts = build_cuboid(rw, rh, rd, rx, ry, rz, OUTER_UV["r_arm"])
    r_arm_verts = _rotate_vertices_z(r_arm_verts, +40.0, pivot=(rx, 24.0))
    meshes["r_arm_outer"] = r_arm_verts

    # Left arm — negative rotation swings it outward to the left.
    lw, lh, ld = dims["l_arm_outer"]
    lx, ly, lz = BODY_POSITIONS["l_arm"]
    l_arm_verts = build_cuboid(lw, lh, ld, lx, ly, lz, OUTER_UV["l_arm"])
    l_arm_verts = _rotate_vertices_z(l_arm_verts, -40.0, pivot=(lx, 24.0))
    meshes["l_arm_outer"] = l_arm_verts

    return meshes


# Names of the armor-stand-only mesh parts (wooden frame + stone base)
STAND_PARTS = [
    "stand_head_knob",
    "stand_shoulder",
    "stand_body",
    "stand_waist",
    "stand_leg_r",
    "stand_leg_l",
    "stand_base",
]


def build_all_meshes(skin_type: str = "steve") -> dict[str, np.ndarray]:
    """
    Build vertex data for all base and outer (armor overlay) body parts.

    Returns a dict: part_name -> float32 ndarray of shape (N, 8)
      where N = 36 per complete cuboid (6 faces × 6 verts each).
    """
    dims = ALEX_DIMENSIONS if skin_type == "alex" else BODY_DIMENSIONS
    meshes: dict[str, np.ndarray] = {}

    for part in BASE_PARTS:
        w, h, d = dims[part]
        cx, cy, cz = BODY_POSITIONS[part]
        uv_faces = BASE_UV[part]
        meshes[part] = build_cuboid(w, h, d, cx, cy, cz, uv_faces)

    for outer_part in OUTER_PARTS:
        base = outer_part.replace("_outer", "")
        w, h, d = dims[outer_part]
        cx, cy, cz = BODY_POSITIONS[base]
        uv_faces = OUTER_UV[base]
        meshes[outer_part] = build_cuboid(w, h, d, cx, cy, cz, uv_faces)

    return meshes

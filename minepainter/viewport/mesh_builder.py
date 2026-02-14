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

BOOT_OUTER_PARTS = ["r_boot_outer", "l_boot_outer"]
SPREAD_OFFSETS: dict[str, tuple[float, float, float]] = {
    # "Exploded" layout offsets for easier painting/inspection.
    "head":  (0.0, 2.0, 0.0),
    "body":  (0.0, 0.0, 0.0),
    "r_arm": (2.5, 0.0, 0.0),
    "l_arm": (-2.5, 0.0, 0.0),
    "r_leg": (1.2, -1.0, 0.0),
    "l_leg": (-1.2, -1.0, 0.0),
}

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


def _apply_pose(meshes: dict[str, np.ndarray], pose: str) -> dict[str, np.ndarray]:
    """Apply a simple Minecraft-style pose to body and armor meshes."""
    pose = (pose or "stand").lower()
    # X rotations (forward/back swing), Z rotations (tilt).
    presets: dict[str, dict[str, dict[str, float]]] = {
        "stand": {"x": {}, "z": {}},
        "walk": {
            "x": {"r_arm": 25.0, "l_arm": -25.0, "r_leg": -25.0, "l_leg": 25.0},
            "z": {},
        },
        "run": {
            "x": {"r_arm": 55.0, "l_arm": -55.0, "r_leg": -45.0, "l_leg": 45.0, "head": -8.0},
            "z": {},
        },
        "fly": {
            "x": {"r_arm": 160.0, "l_arm": 160.0, "r_leg": 18.0, "l_leg": 18.0, "head": 12.0},
            "z": {"r_arm": 6.0, "l_arm": -6.0},
        },
    }
    p = presets.get(pose, presets["stand"])
    x_angles = p["x"]
    z_angles = p["z"]

    # Shoulder/hip/neck pivots in model space.
    pivots: dict[str, tuple[float, float, float]] = {
        "head": (BODY_POSITIONS["head"][0], 24.0, BODY_POSITIONS["head"][2]),
        "r_arm": (BODY_POSITIONS["r_arm"][0], 24.0, BODY_POSITIONS["r_arm"][2]),
        "l_arm": (BODY_POSITIONS["l_arm"][0], 24.0, BODY_POSITIONS["l_arm"][2]),
        "r_leg": (BODY_POSITIONS["r_leg"][0], 12.0, BODY_POSITIONS["r_leg"][2]),
        "l_leg": (BODY_POSITIONS["l_leg"][0], 12.0, BODY_POSITIONS["l_leg"][2]),
        # Boots follow their leg pivots.
        "r_boot_outer": (BODY_POSITIONS["r_leg"][0], 12.0, BODY_POSITIONS["r_leg"][2]),
        "l_boot_outer": (BODY_POSITIONS["l_leg"][0], 12.0, BODY_POSITIONS["l_leg"][2]),
    }

    # Apply to base + outer meshes for each animated part.
    for part in ("head", "r_arm", "l_arm", "r_leg", "l_leg"):
        for mesh_name in (part, f"{part}_outer"):
            if mesh_name not in meshes:
                continue
            verts = meshes[mesh_name]
            if part in x_angles:
                py, pz = pivots[part][1], pivots[part][2]
                verts = _rotate_vertices_x(verts, x_angles[part], pivot=(py, pz))
            if part in z_angles:
                px, py = pivots[part][0], pivots[part][1]
                verts = _rotate_vertices_z(verts, z_angles[part], pivot=(px, py))
            meshes[mesh_name] = verts

    # Rotate boot shells with legs so armor and base stay aligned.
    for boot, leg in (("r_boot_outer", "r_leg"), ("l_boot_outer", "l_leg")):
        if boot not in meshes:
            continue
        verts = meshes[boot]
        if leg in x_angles:
            py, pz = pivots[boot][1], pivots[boot][2]
            verts = _rotate_vertices_x(verts, x_angles[leg], pivot=(py, pz))
        if leg in z_angles:
            px, py = pivots[boot][0], pivots[boot][1]
            verts = _rotate_vertices_z(verts, z_angles[leg], pivot=(px, py))
        meshes[boot] = verts

    return meshes


def _part_center(part: str, spread_out: bool) -> tuple[float, float, float]:
    cx, cy, cz = BODY_POSITIONS[part]
    if spread_out:
        ox, oy, oz = SPREAD_OFFSETS.get(part, (0.0, 0.0, 0.0))
        return cx + ox, cy + oy, cz + oz
    return cx, cy, cz


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


def build_stand_body_meshes(
    skin_type: str = "steve",
    spread_out: bool = False,
    pose: str = "stand",
) -> dict[str, np.ndarray]:
    """
    Build OUTER (armor) body-part meshes for armor editor mode.

    Keep the same neutral pose as the base player mesh so the armor reads like
    in-game worn armor instead of an exaggerated mannequin pose.
    """
    dims = ALEX_DIMENSIONS if skin_type == "alex" else BODY_DIMENSIONS
    meshes: dict[str, np.ndarray] = {}

    for part in ("head", "body", "r_arm", "l_arm", "r_leg", "l_leg"):
        outer = part + "_outer"
        w, h, d = dims[outer]
        cx, cy, cz = _part_center(part, spread_out)
        meshes[outer] = build_cuboid(w, h, d, cx, cy, cz, OUTER_UV[part])

    return _apply_pose(meshes, pose)


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


def build_all_meshes(
    skin_type: str = "steve",
    spread_out: bool = False,
    pose: str = "stand",
) -> dict[str, np.ndarray]:
    """
    Build vertex data for all base and outer (armor overlay) body parts.

    Returns a dict: part_name -> float32 ndarray of shape (N, 8)
      where N = 36 per complete cuboid (6 faces × 6 verts each).
    """
    dims = ALEX_DIMENSIONS if skin_type == "alex" else BODY_DIMENSIONS
    meshes: dict[str, np.ndarray] = {}

    for part in BASE_PARTS:
        w, h, d = dims[part]
        cx, cy, cz = _part_center(part, spread_out)
        uv_faces = BASE_UV[part]
        meshes[part] = build_cuboid(w, h, d, cx, cy, cz, uv_faces)

    for outer_part in OUTER_PARTS:
        base = outer_part.replace("_outer", "")
        w, h, d = dims[outer_part]
        cx, cy, cz = _part_center(base, spread_out)
        uv_faces = OUTER_UV[base]
        meshes[outer_part] = build_cuboid(w, h, d, cx, cy, cz, uv_faces)

    # Extra raised boot shells around the lower legs.
    for leg in ("r_leg", "l_leg"):
        lx, _, lz = _part_center(leg, spread_out)
        boot_name = "r_boot_outer" if leg == "r_leg" else "l_boot_outer"
        # Boots are 1.0px off the leg shell => +2.0 total per axis around 4x4 area.
        # Lower-leg boot section is 4px tall, so a 1px shell becomes 6px total height.
        bw, bh, bd = 6.0, 6.0, 6.0
        by = 2.0
        if spread_out:
            by = 0.5
        leg_uv = OUTER_UV[leg]
        # Map boots to lower 4 rows of the leg side UV faces.
        boot_uv = {
            "right":  (leg_uv["right"][0],  leg_uv["right"][1] + 8, 4, 4),
            "front":  (leg_uv["front"][0],  leg_uv["front"][1] + 8, 4, 4),
            "left":   (leg_uv["left"][0],   leg_uv["left"][1] + 8, 4, 4),
            "back":   (leg_uv["back"][0],   leg_uv["back"][1] + 8, 4, 4),
            "bottom": leg_uv["bottom"],
        }
        meshes[boot_name] = build_cuboid(bw, bh, bd, lx, by, lz, boot_uv)

    return _apply_pose(meshes, pose)

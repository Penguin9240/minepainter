"""
Minecraft skin UV layout constants and body part geometry.

All UV regions are (x, y, width, height) in pixel coordinates on a 64x64 texture,
with (0, 0) at the top-left corner (matching PNG convention).

"UV mapping" here refers to how each face of a 3D body-part cuboid maps to a
specific pixel region on the flat 64x64 skin PNG — completely unrelated to the
`uv` Python package manager.
"""

# ---------------------------------------------------------------------------
# Base layer UV regions  (inner skin)
# ---------------------------------------------------------------------------
# Each body part key maps to a dict of face -> (x, y, w, h) pixel coordinates.

BASE_UV: dict[str, dict[str, tuple[int, int, int, int]]] = {
    "head": {
        "top":    ( 8,  0,  8,  8),
        "bottom": (16,  0,  8,  8),
        "right":  ( 0,  8,  8,  8),
        "front":  ( 8,  8,  8,  8),
        "left":   (16,  8,  8,  8),
        "back":   (24,  8,  8,  8),
    },
    "body": {
        "top":    (20, 16,  8,  4),
        "bottom": (28, 16,  8,  4),
        "right":  (16, 20,  4, 12),
        "front":  (20, 20,  8, 12),
        "left":   (28, 20,  4, 12),
        "back":   (32, 20,  8, 12),
    },
    "r_arm": {
        "top":    (44, 16,  4,  4),
        "bottom": (48, 16,  4,  4),
        "right":  (40, 20,  4, 12),
        "front":  (44, 20,  4, 12),
        "left":   (48, 20,  4, 12),
        "back":   (52, 20,  4, 12),
    },
    "l_arm": {
        "top":    (36, 48,  4,  4),
        "bottom": (40, 48,  4,  4),
        "right":  (32, 52,  4, 12),
        "front":  (36, 52,  4, 12),
        "left":   (40, 52,  4, 12),
        "back":   (44, 52,  4, 12),
    },
    "r_leg": {
        "top":    ( 4, 16,  4,  4),
        "bottom": ( 8, 16,  4,  4),
        "right":  ( 0, 20,  4, 12),
        "front":  ( 4, 20,  4, 12),
        "left":   ( 8, 20,  4, 12),
        "back":   (12, 20,  4, 12),
    },
    "l_leg": {
        "top":    (20, 48,  4,  4),
        "bottom": (24, 48,  4,  4),
        "right":  (16, 52,  4, 12),
        "front":  (20, 52,  4, 12),
        "left":   (24, 52,  4, 12),
        "back":   (28, 52,  4, 12),
    },
}

# ---------------------------------------------------------------------------
# Outer (armor overlay) UV regions  — same 64x64 texture, different regions
# ---------------------------------------------------------------------------

OUTER_UV: dict[str, dict[str, tuple[int, int, int, int]]] = {
    "head": {
        "top":    (40,  0,  8,  8),
        "bottom": (48,  0,  8,  8),
        "right":  (32,  8,  8,  8),
        "front":  (40,  8,  8,  8),
        "left":   (48,  8,  8,  8),
        "back":   (56,  8,  8,  8),
    },
    "body": {
        "top":    (20, 32,  8,  4),
        "bottom": (28, 32,  8,  4),
        "right":  (16, 36,  4, 12),
        "front":  (20, 36,  8, 12),
        "left":   (28, 36,  4, 12),
        "back":   (32, 36,  8, 12),
    },
    "r_arm": {
        "top":    (44, 32,  4,  4),
        "bottom": (48, 32,  4,  4),
        "right":  (40, 36,  4, 12),
        "front":  (44, 36,  4, 12),
        "left":   (48, 36,  4, 12),
        "back":   (52, 36,  4, 12),
    },
    "l_arm": {
        "top":    (52, 48,  4,  4),
        "bottom": (56, 48,  4,  4),
        "right":  (48, 52,  4, 12),
        "front":  (52, 52,  4, 12),
        "left":   (56, 52,  4, 12),
        "back":   (60, 52,  4, 12),
    },
    "r_leg": {
        "top":    ( 4, 32,  4,  4),
        "bottom": ( 8, 32,  4,  4),
        "right":  ( 0, 36,  4, 12),
        "front":  ( 4, 36,  4, 12),
        "left":   ( 8, 36,  4, 12),
        "back":   (12, 36,  4, 12),
    },
    "l_leg": {
        "top":    ( 4, 48,  4,  4),
        "bottom": ( 8, 48,  4,  4),
        "right":  ( 0, 52,  4, 12),
        "front":  ( 4, 52,  4, 12),
        "left":   ( 8, 52,  4, 12),
        "back":   (12, 52,  4, 12),
    },
}

# ---------------------------------------------------------------------------
# Body part 3D dimensions  (in Minecraft model units, 1 unit = 1 skin pixel)
# (width, height, depth)
# ---------------------------------------------------------------------------

BODY_DIMENSIONS: dict[str, tuple[int, int, int]] = {
    # Base (inner) layer
    "head":  (8, 8, 8),
    "body":  (8, 12, 4),
    "r_arm": (4, 12, 4),   # Steve; Alex arms are 3 wide
    "l_arm": (4, 12, 4),
    "r_leg": (4, 12, 4),
    "l_leg": (4, 12, 4),
    # Outer (armor) layer — vanilla second layer is +0.5 total per axis
    # Helmet/arms/leggings: 0.5px off body => +1.0 total per axis.
    "head_outer":  (9, 9, 9),
    "r_arm_outer": (5, 13, 5),
    "l_arm_outer": (5, 13, 5),
    "r_leg_outer": (5, 13, 5),
    "l_leg_outer": (5, 13, 5),
    # Chestplate: 1.0px off body => +2.0 total per axis.
    "body_outer":  (10, 14, 6),
}

# Alex-variant arm widths (3 instead of 4)
ALEX_DIMENSIONS: dict[str, tuple[int, int, int]] = {
    **BODY_DIMENSIONS,
    "r_arm": (3, 12, 4),
    "l_arm": (3, 12, 4),
    # Alex arm overlay still keeps 0.5px shell relative to 3x12x4 base arm.
    "r_arm_outer": (4, 13, 5),
    "l_arm_outer": (4, 13, 5),
}

# ---------------------------------------------------------------------------
# Body part positions  (center of each part, in model space)
# Y = 0 at ground level.  One Minecraft unit = 1 pixel on the skin.
# ---------------------------------------------------------------------------

BODY_POSITIONS: dict[str, tuple[float, float, float]] = {
    "head":  ( 0.0, 28.0, 0.0),   # center of head cube sits at y=24..32
    "body":  ( 0.0, 18.0, 0.0),   # center of torso sits at y=12..24
    "r_arm": ( 6.0, 18.0, 0.0),   # shoulder attached at body right edge
    "l_arm": (-6.0, 18.0, 0.0),
    "r_leg": ( 2.0,  6.0, 0.0),   # center of leg sits at y=0..12
    "l_leg": (-2.0,  6.0, 0.0),
}

# Convenience: ordered list of base part names for iteration
BASE_PARTS = ["head", "body", "r_arm", "l_arm", "r_leg", "l_leg"]
OUTER_PARTS = [p + "_outer" for p in BASE_PARTS]
ALL_PARTS = BASE_PARTS + OUTER_PARTS

TEXTURE_SIZE = 64  # skin PNG is always 64×64 pixels (modern format)

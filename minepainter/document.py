"""
SkinDocument: the central data model shared by all widgets.

Both the 2D UV editor and the 3D viewport observe this object via Qt signals,
so any paint operation is automatically reflected in both views without
tight coupling between the widgets themselves.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, Signal


class SkinDocument(QObject):
    """
    Holds the skin and armor overlay image data as numpy arrays and
    broadcasts changes to connected widgets via Qt signals.

    Arrays are uint8 RGBA with shape (64, 64, 4), indexed [row, col] = [y, x].
    """

    # Emitted after a single pixel changes.
    # (layer: "base"|"armor", x: int, y: int, rgba: tuple[int,int,int,int])
    pixel_changed = Signal(str, int, int, object)

    # Emitted when an entire layer's image is replaced (file open / new).
    # (layer: "base"|"armor")
    layer_replaced = Signal(str)

    # Emitted when a layer's visibility is toggled.
    # (layer: "base"|"armor", visible: bool)
    visibility_changed = Signal(str, bool)

    # Emitted when the document's dirty state changes (for window title "*").
    dirty_changed = Signal(bool)

    # Maximum number of undo steps kept in memory
    MAX_UNDO = 50

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        self.skin_type: str = "steve"          # "steve" | "alex"
        self.base_image: np.ndarray = np.zeros((64, 64, 4), dtype=np.uint8)  # replaced below
        self.armor_image: np.ndarray = np.zeros((64, 64, 4), dtype=np.uint8)
        # Fill base with white default; armor starts transparent in skin-edit mode
        self.base_image  = SkinDocument._blank_white_skin()
        self.armor_image = np.zeros((64, 64, 4), dtype=np.uint8)
        self.base_visible: bool = True
        self.armor_visible: bool = True
        self._dirty: bool = False
        self.filepath: Optional[Path] = None

        # Undo stack: list of (layer_name, np.ndarray snapshot) tuples
        self._undo_stack: list[tuple[str, np.ndarray]] = []

    # ------------------------------------------------------------------
    # Pixel access
    # ------------------------------------------------------------------

    def set_pixel(
        self,
        layer: str,
        x: int,
        y: int,
        rgba: tuple[int, int, int, int],
    ) -> None:
        """Write one pixel and emit pixel_changed."""
        if not (0 <= x < 64 and 0 <= y < 64):
            return
        arr = self.base_image if layer == "base" else self.armor_image
        arr[y, x] = rgba
        self.pixel_changed.emit(layer, x, y, rgba)
        self._mark_dirty()

    def get_pixel(self, layer: str, x: int, y: int) -> tuple[int, int, int, int]:
        """Return the RGBA tuple at (x, y) for the given layer."""
        arr = self.base_image if layer == "base" else self.armor_image
        r, g, b, a = arr[y, x]
        return (int(r), int(g), int(b), int(a))

    def get_image(self, layer: str) -> np.ndarray:
        """Return the numpy array for the given layer."""
        return self.base_image if layer == "base" else self.armor_image

    # ------------------------------------------------------------------
    # Layer visibility
    # ------------------------------------------------------------------

    def set_layer_visible(self, layer: str, visible: bool) -> None:
        if layer == "base":
            self.base_visible = visible
        else:
            self.armor_visible = visible
        self.visibility_changed.emit(layer, visible)

    # ------------------------------------------------------------------
    # File I/O  (delegates to SkinIO, imported lazily to avoid circular refs)
    # ------------------------------------------------------------------

    @staticmethod
    def _blank_white_skin() -> np.ndarray:
        """Return a 64×64 RGBA image with all skin UV regions filled white,
        plus a small smiley face drawn on the head front face."""
        from minepainter.skin_constants import BASE_UV, OUTER_UV
        arr = np.zeros((64, 64, 4), dtype=np.uint8)
        for part_uv in list(BASE_UV.values()) + list(OUTER_UV.values()):
            for px, py, pw, ph in part_uv.values():
                arr[py:py + ph, px:px + pw] = (255, 255, 255, 255)

        # Head front face: skin pixels (8..15, 8..15) — 8×8 region.
        # Draw just the eyes and mouth in black; background stays white.
        # Local coords (row, col) within the 8×8 region, origin at skin (8,8).
        B = (0, 0, 0, 255)  # black
        for row, col in [
            # Eyes
            (2, 2), (2, 5),
            # Mouth
            (5, 1), (5, 6),
            (6, 2), (6, 3), (6, 4), (6, 5),
        ]:
            arr[8 + row, 8 + col] = B

        return arr

    @staticmethod
    def _blank_white_armor(armor_type: str = "iron") -> np.ndarray:
        """Return a 64×64 RGBA starter armor overlay with vanilla-like piece shapes."""
        from minepainter.skin_constants import OUTER_UV

        arr = np.zeros((64, 64, 4), dtype=np.uint8)

        armor_palettes = {
            "iron": {
                "border": (122, 122, 122, 255),
                "mid": (176, 176, 176, 255),
                "light": (206, 206, 206, 255),
                "highlight": (238, 238, 238, 255),
                "spec": (255, 255, 255, 255),
            },
            "gold": {
                "border": (128, 92, 38, 255),
                "mid": (207, 153, 58, 255),
                "light": (233, 182, 86, 255),
                "highlight": (248, 212, 125, 255),
                "spec": (255, 255, 255, 255),
            },
            "diamond": {
                "border": (51, 120, 120, 255),
                "mid": (89, 196, 196, 255),
                "light": (121, 224, 224, 255),
                "highlight": (176, 246, 246, 255),
                "spec": (255, 255, 255, 255),
                "accent": (34, 84, 84, 255),
                "accent_light": (208, 255, 255, 255),
            },
            "netherite": {
                "border": (42, 42, 46, 255),
                "mid": (72, 72, 78, 255),
                "light": (102, 102, 110, 255),
                "highlight": (140, 140, 150, 255),
                "spec": (255, 255, 255, 255),
            },
        }
        palette = armor_palettes.get(armor_type.lower(), armor_palettes["iron"])
        accent = palette.get("accent", palette["border"])
        accent_light = palette.get("accent_light", palette["highlight"])

        def _paint_masked_face(
            px: int,
            py: int,
            pw: int,
            ph: int,
            include_pixel,
            *,
            boots_band: bool = False,
        ) -> None:
            for ly in range(ph):
                for lx in range(pw):
                    if not include_pixel(lx, ly, pw, ph):
                        continue

                    edge = lx == 0 or ly == 0 or lx == pw - 1 or ly == ph - 1
                    near_top_left = lx <= 1 and ly <= 1
                    inner = (lx > 0 and ly > 0 and lx < pw - 1 and ly < ph - 1)

                    color = palette["mid"]
                    if edge:
                        color = palette["border"]
                    if inner:
                        color = palette["light"]
                    if near_top_left and inner:
                        color = palette["highlight"]
                    if lx == 1 and ly == 1 and pw > 2 and ph > 2:
                        color = palette["spec"]

                    # Darker bottom band on lower legs to suggest boots.
                    if boots_band and ly >= ph - 4:
                        r, g, b, a = color
                        color = (max(0, r - 22), max(0, g - 22), max(0, b - 22), a)

                    arr[py + ly, px + lx] = color

        def _set_local(px: int, py: int, pw: int, ph: int, lx: int, ly: int, color) -> None:
            if 0 <= lx < pw and 0 <= ly < ph:
                # Keep detail strokes inside already-visible armor pixels.
                if arr[py + ly, px + lx, 3] == 0:
                    return
                arr[py + ly, px + lx] = color

        def _hline(px: int, py: int, pw: int, ph: int, x0: int, x1: int, y: int, color) -> None:
            for lx in range(max(0, x0), min(pw, x1 + 1)):
                _set_local(px, py, pw, ph, lx, y, color)

        def _vline(px: int, py: int, pw: int, ph: int, x: int, y0: int, y1: int, color) -> None:
            for ly in range(max(0, y0), min(ph, y1 + 1)):
                _set_local(px, py, pw, ph, x, ly, color)

        def _diamond_gem(px: int, py: int, pw: int, ph: int) -> None:
            cx = pw // 2
            cy = max(2, ph // 3)
            size = max(1, min(pw, ph) // 4)
            for dy in range(-size, size + 1):
                span = size - abs(dy)
                for dx in range(-span, span + 1):
                    color = accent_light if (dx == 0 and dy <= 0) else palette["highlight"]
                    _set_local(px, py, pw, ph, cx + dx, cy + dy, color)
            _set_local(px, py, pw, ph, cx, cy, palette["spec"])

        def _apply_diamond_helmet_front_template(px: int, py: int, pw: int, ph: int) -> None:
            # Exact helmet-front silhouette/color template (8x8 reference), scaled.
            D = palette["border"]
            M = palette["mid"]
            L = palette["light"]
            S = palette["spec"]
            A = accent
            T = (0, 0, 0, 0)
            template = [
                [D, D, D, D, D, D, D, D],
                [D, S, L, L, L, L, S, D],
                [D, M, M, M, M, M, M, D],
                [D, T, T, M, M, T, T, D],
                [T, T, T, M, M, T, T, T],
                [T, T, T, T, T, T, T, T],
                [T, T, T, T, T, T, T, T],
                [T, T, T, T, T, T, T, T],
            ]
            for ly in range(ph):
                gy = min(7, int(ly * 8 / max(1, ph)))
                for lx in range(pw):
                    gx = min(7, int(lx * 8 / max(1, pw)))
                    arr[py + ly, px + lx] = template[gy][gx]

        def _paint_diamond_helmet_face(face_name: str, px: int, py: int, pw: int, ph: int) -> None:
            # Explicit pixel templates (8x8 reference) matched to the provided
            # helmet screenshots (shape + cutouts), then scaled to face size.
            def _lerp(ca: tuple[int, int, int, int], cb: tuple[int, int, int, int], t: float) -> tuple[int, int, int, int]:
                t = max(0.0, min(1.0, t))
                return (
                    int(ca[0] * (1.0 - t) + cb[0] * t),
                    int(ca[1] * (1.0 - t) + cb[1] * t),
                    int(ca[2] * (1.0 - t) + cb[2] * t),
                    255,
                )

            # Build diamond-cyan ramps from the active palette.
            C0 = _lerp(palette["light"], palette["highlight"], 0.90)  # brightest
            C1 = _lerp(palette["light"], palette["highlight"], 0.45)
            C2 = _lerp(palette["mid"], palette["light"], 0.60)
            C3 = _lerp(palette["mid"], palette["light"], 0.25)
            C4 = _lerp(palette["border"], palette["mid"], 0.20)
            C5 = palette["border"]
            T = (0, 0, 0, 0)

            templates: dict[str, list[list[tuple[int, int, int, int]]]] = {
                "front": [
                    [C5, C5, C5, C5, C5, C5, C5, C5],
                    [C5, C0, C1, C1, C1, C1, C0, C5],
                    [C5, C3, C3, C1, C1, C3, C3, C5],
                    [C5,  T,  T, C0, C2,  T,  T, C5],
                    [T ,  T,  T, C3, C3,  T,  T,  T],
                    [T ,  T,  T,  T,  T,  T,  T,  T],
                    [T,   T,  T,  T,  T,  T,  T, T ],
                    [T,  T,  T,  T,  T,  T,  T,  T ],
                ],
                "left": [
                    [C5, C5, C5, C5, C5, C5, C5, C5],
                    [C5, C0, C1, C1, C1, C1, C1, C5],
                    [C5, C1, C1, C1, C3, C2, C2, C5],
                    [C5, C2, C3, C3, C5, C5, C5, C5],
                    [C5, C5, C5, C5,  T,  T,  T,  T],
                    [T ,  T,  T,  T,  T, T,  T,  T ],
                    [T ,  T,  T,  T, T,  T,  T,  T ],
                    [T ,  T,  T, T,  T,  T,  T,  T ],
                ],
                "right": [
                    [C5, C5, C5, C5, C5, C5, C5, C5],
                    [C5, C1, C1, C1, C1, C1, C0, C5],
                    [C5, C2, C2, C3, C1, C1, C1, C5],
                    [C5, C5, C5, C5, C3, C3, C2, C5],
                    [T ,  T,  T,  T, C5, C5, C5, C5],
                    [T,  T,  T,   T,  T,  T,  T,  T],
                    [T,  T,  T,  T,   T,  T,  T,  T],
                    [T,  T,  T,  T,  T,   T,  T,  T],
                ],
                "top": [
                    [C5, C5, C5, C5, C5, C5, C5, C5],
                    [C5, C1, C1, C1, C1, C1, C1, C5],
                    [C5, C1, C1, C1, C1, C1, C1, C5],
                    [C5, C1, C1, C1, C1, C1, C1, C5],
                    [C5, C1, C1, C1, C1, C1, C1, C5],
                    [C5, C1, C1, C1, C1, C1, C1, C5],
                    [C5, C1, C1, C1, C1, C1, C1, C5],
                    [C5, C5, C5, C5, C5, C5, C5, C5],
                ],  
                "back": [
                    [C5, C5, C5, C5, C5, C5, C5, C5],
                    [C5, C3, C3, C3, C3, C3, C3, C5],
                    [C5, C3, C3, C3, C3, C3, C3, C5],
                    [C5, C3, C3, C3, C3, C3, C3, C5],
                    [C5, C3, C3, C3, C3, C3, C3, C5],
                    [C5, C5, C5, C3, C3, C5, C5, C5],
                    [ T,  T, C5, C5, C5, C5,  T,  T],
                    [ T,  T,  T,  T,  T,  T, T,  T ],
                ],
                "bottom": [
                    [T, T, T, T, T, T, T, T],
                    [T, T, T, T, T, T, T, T],
                    [T, T, T, T, T, T, T, T],
                    [T, T, T, T, T, T, T, T],
                    [T, T, T, T, T, T, T, T],
                    [T, T, T, T, T, T, T, T],
                    [T, T, T, T, T, T, T, T],
                    [T, T, T, T, T, T, T, T],
                ],
            }

            template = templates.get(face_name)
            if template is None:
                return
            for ly in range(ph):
                gy = min(7, int(ly * 8 / max(1, ph)))
                for lx in range(pw):
                    gx = min(7, int(lx * 8 / max(1, pw)))
                    arr[py + ly, px + lx] = template[gy][gx]

        def _paint_diamond_chestplate_face(face_name: str, px: int, py: int, pw: int, ph: int) -> None:
            # Fixed chestplate templates using native proportions:
            # - front/back: 8x11
            # - left/right: 4x11
            # - top/bottom: 8x4
            def _lerp(ca: tuple[int, int, int, int], cb: tuple[int, int, int, int], t: float) -> tuple[int, int, int, int]:
                t = max(0.0, min(1.0, t))
                return (
                    int(ca[0] * (1.0 - t) + cb[0] * t),
                    int(ca[1] * (1.0 - t) + cb[1] * t),
                    int(ca[2] * (1.0 - t) + cb[2] * t),
                    255,
                )

            C0 = _lerp(palette["light"], palette["highlight"], 0.75)
            C1 = _lerp(palette["light"], palette["highlight"], 0.45)
            C2 = _lerp(palette["mid"], palette["light"], 0.60)
            C3 = _lerp(palette["mid"], palette["light"], 0.25)
            C5 = palette["border"]
            T = (0, 0, 0, 0)

            templates: dict[str, list[list[tuple[int, int, int, int]]]] = {
                "front": [
                    [C5, C5,  T,  T,  T,  T, C5, C5],
                    [C5, C2, C5,  T,  T, C5, C2, C5],
                    [C5, C0, C2, C5, C5, C0, C2, C5],
                    [C5, C0, C2, C1, C1, C2, C2, C5],
                    [C5, C2, C2, C1, C1, C2, C2, C5],
                    [C5, C2, C2, C2, C2, C2, C2, C5],
                    [C5, C2, C2, C2, C2, C2, C2, C5],
                    [C5, C2, C2, C2, C2, C2, C2, C5],
                    [C5, C2, C2, C2, C2, C2, C2, C5],
                    [ T, C5, C2, C2, C2, C2, C5,  T],
                    [ T,  T, C5, C5, C5, C5,  T,  T],
                ],
                "back": [
                    [C5, C5, C5, C5, C5, C5, C5, C5],
                    [C5, C3, C3, C3, C3, C3, C3, C5],
                    [C5, C3, C3, C3, C3, C3, C3, C5],
                    [C5, C3, C3, C3, C3, C3, C3, C5],
                    [C5, C3, C3, C3, C3, C3, C3, C5],
                    [C5, C3, C3, C3, C3, C3, C3, C5],
                    [C5, C3, C3, C3, C3, C3, C3, C5],
                    [C5, C3, C3, C3, C3, C3, C3, C5],
                    [C5, C3, C3, C3, C3, C3, C3, C5],
                    [ T, C5, C5, C5, C5, C5, C5,  T],
                    [ T,  T,  T,  T,  T,  T,  T,  T],
                ],
                "left": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [ T,  T,  T,  T],
                    [ T,  T,  T,  T],
                ],
                "right": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [ T,  T,  T,  T],
                    [ T,  T,  T,  T],
                ],
                "top": [
                    [T, T, T, T, T, T, T, T],
                    [T, T, T, T, T, T, T, T],
                    [T, T, T, T, T, T, T, T],
                    [T, T, T, T, T, T, T, T],
                ],
                "bottom": [
                    [T, T, T, T, T, T, T, T],
                    [T, T, T, T, T, T, T, T],
                    [T, T, T, T, T, T, T, T],
                    [T, T, T, T, T, T, T, T],
                ],
            }

            template = templates.get(face_name)
            if template is None:
                return
            th = len(template)
            tw = len(template[0]) if th > 0 else 0
            if th == 0 or tw == 0:
                return

            # Preserve intended template height (e.g. 11px chest on 12px UV face)
            # by padding extra rows at the top with transparency instead of stretching.
            pad_top = max(0, ph - th)
            for ly in range(ph):
                if ly < pad_top:
                    for lx in range(pw):
                        arr[py + ly, px + lx] = T
                    continue
                local_y = ly - pad_top
                gy = min(th - 1, int(local_y * th / max(1, ph - pad_top)))
                for lx in range(pw):
                    gx = min(tw - 1, int(lx * tw / max(1, pw)))
                    arr[py + ly, px + lx] = template[gy][gx]

        def _paint_diamond_arm_face(part: str, face_name: str, px: int, py: int, pw: int, ph: int) -> None:
            # Fixed arm templates using native arm proportions:
            # - side faces: 4x12
            # - caps: 4x4
            # Separate sets for right and left arms.
            def _lerp(ca: tuple[int, int, int, int], cb: tuple[int, int, int, int], t: float) -> tuple[int, int, int, int]:
                t = max(0.0, min(1.0, t))
                return (
                    int(ca[0] * (1.0 - t) + cb[0] * t),
                    int(ca[1] * (1.0 - t) + cb[1] * t),
                    int(ca[2] * (1.0 - t) + cb[2] * t),
                    255,
                )

            C0 = _lerp(palette["light"], palette["highlight"], 0.75)
            C1 = _lerp(palette["light"], palette["highlight"], 0.45)
            C2 = _lerp(palette["mid"], palette["light"], 0.60)
            C3 = _lerp(palette["mid"], palette["light"], 0.25)
            C2 = _lerp(palette["mid"], palette["light"], 0.45)
            C5 = _lerp(palette["border"], palette["mid"], 0.25)
            B0 = _lerp(palette["border"], palette["mid"], 0.15)
            B1 = palette["border"]
            C5 = palette["border"]
            T = (0, 0, 0, 0)

            templates_by_part: dict[str, dict[str, list[list[tuple[int, int, int, int]]]]] = {
                "r_arm": {
                    "front": [
                        [C5, C5, C5, C5],
                        [C5, C0, C2, C5],
                        [C5, C2, C2, C5],
                        [ T,  T, C2, C5],
                        [T,  T, C2,  C5],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                    ],
                    "back": [
                        [C5, C5, C5, C5],
                        [C5, C3, C3, C5],
                        [C5, C3, C3, C5],
                        [C5, C3,  T,  T],
                        [C5, C3, T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                    ],
                    "left": [
                        [C5, C5, C5, C5],
                        [C5, C2, C2, C5],
                        [C5, C2, C2, C5],
                        [T,  T , T , T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                    ],
                    "right": [
                        [C5, C5, C5, C5],
                        [C5, C2, C2, C5],
                        [C5, C2, C2, C5],
                        [C5, C2, C2, C5],
                        [C5, C5, C5, C5],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                    ],
                    "top": [
                        [C5, C5, C5, C5],
                        [C5, C2, C2, C5],
                        [C5, C2, C1, C5],
                        [C5, C5, C5, C5],
                    ],
                    "bottom": [
                        [T, T, T, T],
                        [T, T, T, T],
                        [T, T, T, T],
                        [T, T, T, T],
                    ],
                },
                "l_arm": {
                    "front": [
                        [C5, C5, C5, C5],
                        [C5, C0, C2, C5],
                        [C5, C2, C2, C5],
                        [C5, C2,  T, T ],
                        [C5, C2,  T, T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                    ],
                    "back": [
                        [C5, C5, C5, C5],
                        [C5, C3, C3, C5],
                        [C5, C3, C3, C5],
                        [T ,  T, C3, C5],
                        [T,  T,  C3, C5],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                    ],
                    "left": [
                        [C5, C5, C5, C5],
                        [C5, C2, C2, C5],
                        [C5, C2, C2, C5],
                        [C5, C2, C2, C5],
                        [C5, C2, C2, C5],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                    ],
                    "right": [
                        [C5, C5, C5, C5],
                        [C5, C2, C2, C5],
                        [C5, C2, C2, C5],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                        [T,  T,  T,  T ],
                    ],
                    "top": [
                        [C5, C5, C5, C5],
                        [C5, C2, C2, C5],
                        [C5, C2, C1, C5],
                        [C5, C5, C5, C5],
                    ],
                    "bottom": [
                        [T, T, T, T],
                        [T, T, T, T],
                        [T, T, T, T],
                        [T, T, T, T],
                    ],
                },
            }

            template = templates_by_part.get(part, {}).get(face_name)
            if template is None:
                return
            th = len(template)
            tw = len(template[0]) if th > 0 else 0
            if th == 0 or tw == 0:
                return
            for ly in range(ph):
                gy = min(th - 1, int(ly * th / max(1, ph)))
                for lx in range(pw):
                    gx = min(tw - 1, int(lx * tw / max(1, pw)))
                    arr[py + ly, px + lx] = template[gy][gx]

        def _paint_diamond_leg_face(part: str, face_name: str, px: int, py: int, pw: int, ph: int) -> None:
            # Fixed leg templates using native leg proportions:
            # - side faces: 4x12
            # - caps: 4x4
            # with separate regions for leggings (upper) and boots (lower).
            def _lerp(ca: tuple[int, int, int, int], cb: tuple[int, int, int, int], t: float) -> tuple[int, int, int, int]:
                t = max(0.0, min(1.0, t))
                return (
                    int(ca[0] * (1.0 - t) + cb[0] * t),
                    int(ca[1] * (1.0 - t) + cb[1] * t),
                    int(ca[2] * (1.0 - t) + cb[2] * t),
                    255,
                )

            L0 = _lerp(palette["light"], palette["highlight"], 0.80)  # leggings highlight
            C2 = _lerp(palette["mid"], palette["light"], 0.60)        # leggings base
            B1 = _lerp(palette["border"], palette["mid"], 0.25)       # leggings dark edge
            B0 = _lerp(palette["border"], palette["mid"], 0.15)       # boots base darker
            C5 = palette["border"]                                     # boots darkest
            T = (0, 0, 0, 0)

            # Full explicit leg templates (4x12 sides, 4x4 caps),
            # with bottom 4 rows as boots.
            r_leg_faces = {
                "front": [
                    [C5, C5, C5, C5],
                    [C5, L0, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C5, C5, C5],
                ],
                "back": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C5, C5, C5],
                ],
                "left": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C5, C5, C5],
                ],
                "right": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C5, C5, C5],
                ],
                "top": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, L0, C5],
                    [C5, C5, C5, C5],
                ],
                "bottom": [
                    [C5, C5, C5, C5],
                    [C5, C5, C5, C5],
                    [C5, C5, C5, C5],
                    [C5, C5, C5, C5],
                ],
            }
            l_leg_faces = {
                "front": [
                    [C5, C5, C5, C5],
                    [C5, L0, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C5, C5, C5],
                ],
                "back": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C5, C5, C5],
                ],
                "left": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C5, C5, C5],
                ],
                "right": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C5, C5, C5],
                ],
                "top": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, L0, C5],
                    [C5, C5, C5, C5],
                ],
                "bottom": [
                    [C5, C5, C5, C5],
                    [C5, C5, C5, C5],
                    [C5, C5, C5, C5],
                    [C5, C5, C5, C5],
                ],
            }
            templates_by_part: dict[str, dict[str, list[list[tuple[int, int, int, int]]]]] = {
                "r_leg": r_leg_faces,
                "l_leg": l_leg_faces,
            }

            # Explicit boot templates (kept separate for editing; not wired into leg templates).
            r_boot_faces = {
                "front": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C5, C5, C5],
                ],
                "back": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C5, C5, C5],
                ],
                "left": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C5, C5, C5],
                ],
                "right": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C5, C5, C5],
                ],
                "top": [
                    [T,  T,  T,  T ],
                    [T,  T,  T,  T ],
                    [T,  T,  T,  T ],
                    [T,  T,  T,  T ],
                ],
                "bottom": [
                    [C5, C5, C5, C5],
                    [C5, C5, C5, C5],
                    [C5, C5, C5, C5],
                    [C5, C5, C5, C5],
                ],
            }
            l_boot_faces = {
                "front": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C5, C5, C5],
                ],
                "back": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C5, C5, C5],
                ],
                "left": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C5, C5, C5],
                ],
                "right": [
                    [C5, C5, C5, C5],
                    [C5, C2, C2, C5],
                    [C5, C2, C2, C5],
                    [C5, C5, C5, C5],
                ],
                "top": [
                    [T,  T,  T,  T ],
                    [T,  T,  T,  T ],
                    [T,  T,  T,  T ],
                    [T,  T,  T,  T ],
                ],
                "bottom": [
                    [C5, C5, C5, C5],
                    [C5, C5, C5, C5],
                    [C5, C5, C5, C5],
                    [C5, C5, C5, C5],
                ],
            }

            template = templates_by_part.get(part, {}).get(face_name)
            if template is None:
                return
            th = len(template)
            tw = len(template[0]) if th > 0 else 0
            if th == 0 or tw == 0:
                return
            for ly in range(ph):
                gy = min(th - 1, int(ly * th / max(1, ph)))
                for lx in range(pw):
                    gx = min(tw - 1, int(lx * tw / max(1, pw)))
                    arr[py + ly, px + lx] = template[gy][gx]

        def _apply_diamond_helmet_details(face_name: str, px: int, py: int, pw: int, ph: int) -> None:
            if face_name == "front":
                _apply_diamond_helmet_front_template(px, py, pw, ph)
            elif face_name in ("left", "right"):
                # Dark front seam on cheek plates.
                _vline(px, py, pw, ph, 1, 1, ph - 3, accent)

        def _full(_x: int, _y: int, _w: int, _h: int) -> bool:
            return True

        def _arm_plate(_x: int, y: int, _w: int, h: int) -> bool:
            return y < max(1, h // 2)

        def _diamond_piece_mask(part: str, face_name: str, lx: int, ly: int, pw: int, ph: int) -> bool:
            # Closer to real Minecraft full armor set silhouettes.
            if part == "head":
                if face_name == "front":
                    return True
                if face_name in ("left", "right"):
                    gx = int(lx * 8 / max(1, pw))
                    gy = int(ly * 8 / max(1, ph))
                    if gy <= 4:
                        return True
                    if gy >= 6:
                        return gx <= 3
                    return gx <= 5
                if face_name == "bottom":
                    return False
                return True

            # Chestplate: full torso, open underside.
            if part == "body":
                return face_name != "bottom"

            # Chestplate shoulders: only upper arm band.
            if part in ("r_arm", "l_arm"):
                if face_name in ("front", "back", "left", "right"):
                    return ly <= max(2, ph // 3)
                if face_name == "top":
                    return True
                if face_name == "bottom":
                    return False
                return True

            # Leggings (upper legs) + boots (lower legs), small knee gap.
            if part in ("r_leg", "l_leg"):
                if face_name in ("front", "back", "left", "right"):
                    upper = ly <= max(4, ph // 2)
                    lower = ly >= ph - 3
                    return upper or lower
                if face_name == "top":
                    return True
                if face_name == "bottom":
                    return True
                return True

            return True

        for part, part_uv in OUTER_UV.items():
            for face_name, (px, py, pw, ph) in part_uv.items():
                include = _full
                boots_band = False

                # Chestplates only cover shoulder/upper-arm area.
                if part in ("r_arm", "l_arm") and face_name in ("front", "back", "left", "right"):
                    include = _arm_plate

                # Keep full caps for arms and all head/body faces.
                # Legs are full, but add a dark lower band to suggest boots.
                if part in ("r_leg", "l_leg"):
                    boots_band = True

                if armor_type.lower() == "diamond":
                    include = lambda lx, ly, w, h, p=part, f=face_name: _diamond_piece_mask(p, f, lx, ly, w, h)

                if armor_type.lower() == "diamond" and part == "head":
                    _paint_diamond_helmet_face(face_name, px, py, pw, ph)
                    continue
                if armor_type.lower() == "diamond" and part == "body":
                    _paint_diamond_chestplate_face(face_name, px, py, pw, ph)
                    continue
                if armor_type.lower() == "diamond" and part in ("r_arm", "l_arm"):
                    _paint_diamond_arm_face(part, face_name, px, py, pw, ph)
                    continue
                if armor_type.lower() == "diamond" and part in ("r_leg", "l_leg"):
                    _paint_diamond_leg_face(part, face_name, px, py, pw, ph)
                    continue

                _paint_masked_face(px, py, pw, ph, include, boots_band=boots_band)
                if armor_type.lower() == "diamond" and part == "head":
                    _apply_diamond_helmet_details(face_name, px, py, pw, ph)

        return arr


    def new(self) -> None:
        """Reset to blank white skin with transparent armor overlay."""
        self.base_image  = self._blank_white_skin()
        self.armor_image = np.zeros((64, 64, 4), dtype=np.uint8)
        self.skin_type = "steve"
        self.filepath = None
        self.layer_replaced.emit("base")
        self.layer_replaced.emit("armor")
        self._dirty = False
        self.dirty_changed.emit(False)
        self.clear_undo()

    def load_from_file(self, path: Path) -> None:
        from minepainter.io.skin_io import SkinIO
        base_arr, skin_type = SkinIO.load(path)
        self.base_image  = base_arr
        self.skin_type   = skin_type
        self.armor_image = np.zeros((64, 64, 4), dtype=np.uint8)
        self.filepath = path
        self.layer_replaced.emit("base")
        self.layer_replaced.emit("armor")
        self._dirty = False
        self.dirty_changed.emit(False)
        self.clear_undo()

    def load_armor_main_file(self, path: Path) -> None:
        """
        Load a 64x32 armor-main PNG into the upper half (rows 0..31)
        of the 64x64 armor overlay.
        """
        from minepainter.io.skin_io import SkinIO

        layer = SkinIO.load_armor_layer(path)  # shape (32, 64, 4)
        self.push_undo_snapshot("armor")
        self.armor_image[0:32, :, :] = layer
        self.layer_replaced.emit("armor")
        self._mark_dirty()

    def load_armor_leggings_file(self, path: Path) -> None:
        """
        Load a 64x32 leggings PNG into the lower half (rows 32..63)
        of the 64x64 armor overlay.
        """
        from minepainter.io.skin_io import SkinIO

        layer = SkinIO.load_armor_layer(path)  # shape (32, 64, 4)
        self.push_undo_snapshot("armor")
        self.armor_image[32:64, :, :] = layer
        self.layer_replaced.emit("armor")
        self._mark_dirty()

    def save_to_file(self, path: Path) -> None:
        from minepainter.io.skin_io import SkinIO
        SkinIO.save(path, self.base_image, self.armor_image)
        self.filepath = path
        self._dirty = False
        self.dirty_changed.emit(False)

    # ------------------------------------------------------------------
    # Dirty state helpers
    # ------------------------------------------------------------------

    def _mark_dirty(self) -> None:
        if not self._dirty:
            self._dirty = True
            self.dirty_changed.emit(True)

    @property
    def dirty(self) -> bool:
        return self._dirty

    # ------------------------------------------------------------------
    # Undo support
    # ------------------------------------------------------------------

    def push_undo_snapshot(self, layer: str) -> None:
        """Save a copy of *layer* before a paint stroke begins."""
        arr = self.base_image if layer == "base" else self.armor_image
        self._undo_stack.append((layer, arr.copy()))
        # Trim oldest entries to stay within memory budget
        if len(self._undo_stack) > self.MAX_UNDO:
            self._undo_stack.pop(0)

    def undo(self) -> bool:
        """Restore the most recent undo snapshot.  Returns True if something was undone."""
        if not self._undo_stack:
            return False
        layer, snapshot = self._undo_stack.pop()
        if layer == "base":
            self.base_image = snapshot
        else:
            self.armor_image = snapshot
        self.layer_replaced.emit(layer)
        self._mark_dirty()
        return True

    def clear_undo(self) -> None:
        """Clear the undo history (called after new / load)."""
        self._undo_stack.clear()

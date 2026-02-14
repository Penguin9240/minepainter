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
        """Return a 64×64 RGBA image styled as default iron armor.

        Uses the real Minecraft iron armor palette (pure greyscale, 7 tones).
        Each face gets:
          - 1-px dark border
          - mid-tone fill — the dominant vanilla color
          - lighter inner panel to break up large flat areas
          - 1-px highlight on the top-left inner edge
          - single specular dot on top-left corner (white)

        Armor types supported:
            - iron
            - gold
            - diamond
            - netherite

        Color reference:
            Iron: https://minecraft.fandom.com/wiki/Armor#Iron_Armor
            Gold: https://minecraft.fandom.com/wiki/Armor#Golden_Armor
            Diamond: https://minecraft.fandom.com/wiki/Armor#Diamond_Armor
            Netherite: https://minecraft.fandom.com/wiki/Armor#Netherite_Armor

        Reference the table in the link above to verify the color palette.

        Only OUTER_UV regions are written; everything else stays transparent.
        """
        from minepainter.skin_constants import OUTER_UV
        arr = np.zeros((64, 64, 4), dtype=np.uint8)

        # Define armor palettes
        armor_palettes = {
            "iron": {
                "BORDER":    (183, 183, 183, 255),   # B7B7B7 — shadow / edge
                "MID":       (194, 194, 194, 255),   # C2C2C2 — primary face color
                "LIGHT":     (209, 209, 209, 255),   # D1D1D1 — mid-high face
                "HIGHLIGHT": (229, 229, 229, 255),   # E5E5E5 — highlight edge
                "SPECULAR":  (255, 255, 255, 255)   # FFFFFF  — specular dot
            },
            "gold": {
                "BORDER":    (199, 143, 63, 255),   # C78F3F — shadow / edge
                "MID":       (231, 175, 95, 255),   # E7AF5F — primary face color
                "LIGHT":     (255, 207, 127, 255),   # FFCD7F — mid-high face
                "HIGHLIGHT": (255, 239, 159, 255),   # FFEF9F — highlight edge
                "SPECULAR":  (255, 255, 255, 255)   # FFFFFF  — specular dot
            },
           "diamond": {
                "BORDER":    (71, 215, 215, 255),   # 47D7D7 — shadow / edge
                "MID":       (103, 247, 247, 255),   # 67F7F7 — primary face color
                "LIGHT":     (135, 255, 255, 255),   # 87FFFF — mid-high face
                "HIGHLIGHT": (167, 255, 255, 255),   # A7FFFF — highlight edge
                "SPECULAR":  (255, 255, 255, 255)   # FFFFFF  — specular dot
            },
            "netherite": {
                "BORDER":    (47, 47, 47, 255),   # 2F2F2F — shadow / edge
                "MID":       (79, 79, 79, 255),   # 4F4F4F — primary face color
                "LIGHT":     (111, 111, 111, 255),   # 6F6F6F — mid-high face
                "HIGHLIGHT": (143, 143, 143, 255),   # 8F8F8F — highlight edge
        SPECULAR  = (255, 255, 255, 255)   # #FFFFFF  — specular dot

        def _paint_face(px: int, py: int, pw: int, ph: int) -> None:
            """Fill one UV face rectangle with iron-armor shading."""
            if pw < 1 or ph < 1:
                return

            # 1. Flood fill with mid-tone
            arr[py:py + ph, px:px + pw] = MID

            # 2. Dark 1-px border on all four edges
            arr[py,           px:px + pw] = BORDER   # top row
            arr[py + ph - 1,  px:px + pw] = BORDER   # bottom row
            arr[py:py + ph,   px]          = BORDER   # left col
            arr[py:py + ph,   px + pw - 1] = BORDER   # right col

            # 3. For faces wider/taller than 3px, lighten the interior slightly
            if pw > 3 and ph > 3:
                arr[py + 1:py + ph - 1, px + 1:px + pw - 1] = LIGHT

            # 4. Highlight: 1-px line just inside the top and left border
            if ph > 2:
                arr[py + 1, px + 1:px + pw - 1] = HIGHLIGHT  # inner top
            if pw > 2:
                arr[py + 1:py + ph - 1, px + 1] = HIGHLIGHT  # inner left

            # 5. Single specular dot at the inner top-left corner
            if pw > 2 and ph > 2:
                arr[py + 1, px + 1] = SPECULAR

        for part_uv in OUTER_UV.values():
            for (px, py, pw, ph) in part_uv.values():
                _paint_face(px, py, pw, ph)

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

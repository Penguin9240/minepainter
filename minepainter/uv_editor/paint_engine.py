"""
PaintEngine: translates brush/erase tool actions into document.set_pixel() calls.

All pixel coordinates are in skin-texture space (0..63, 0..63).
"""
from __future__ import annotations

from minepainter.document import SkinDocument


class PaintEngine:
    def __init__(self, document: SkinDocument) -> None:
        self.document = document

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def paint(
        self,
        layer: str,
        x: int, y: int,
        rgba: tuple[int, int, int, int],
        brush_size: int = 1,
    ) -> None:
        """Paint a square of pixels centred at (x, y)."""
        half = brush_size // 2
        for dy in range(-half, half + (brush_size % 2)):
            for dx in range(-half, half + (brush_size % 2)):
                self.document.set_pixel(layer, x + dx, y + dy, rgba)

    def erase(self, layer: str, x: int, y: int, brush_size: int = 1) -> None:
        """Erase (set to fully transparent) a square of pixels."""
        self.paint(layer, x, y, (0, 0, 0, 0), brush_size)

    def paint_line(
        self,
        layer: str,
        x0: int, y0: int,
        x1: int, y1: int,
        rgba: tuple[int, int, int, int],
        brush_size: int = 1,
    ) -> None:
        """
        Paint along a line from (x0,y0) to (x1,y1) using Bresenham's algorithm.
        Fills in pixels that would otherwise be skipped during fast mouse drags.
        """
        for x, y in _bresenham(x0, y0, x1, y1):
            self.paint(layer, x, y, rgba, brush_size)

    def erase_line(
        self,
        layer: str,
        x0: int, y0: int,
        x1: int, y1: int,
        brush_size: int = 1,
    ) -> None:
        for x, y in _bresenham(x0, y0, x1, y1):
            self.erase(layer, x, y, brush_size)

    def fill(
        self,
        layer: str,
        x: int, y: int,
        rgba: tuple[int, int, int, int],
    ) -> None:
        """Flood-fill starting at (x, y), replacing all connected pixels of the
        same color with *rgba*.  Uses a simple iterative 4-connected BFS."""
        target = self.document.get_pixel(layer, x, y)
        if target == rgba:
            return
        stack = [(x, y)]
        visited: set[tuple[int, int]] = set()
        while stack:
            cx, cy = stack.pop()
            if (cx, cy) in visited:
                continue
            if not (0 <= cx < 64 and 0 <= cy < 64):
                continue
            if self.document.get_pixel(layer, cx, cy) != target:
                continue
            visited.add((cx, cy))
            self.document.set_pixel(layer, cx, cy, rgba)
            stack.extend([(cx+1,cy),(cx-1,cy),(cx,cy+1),(cx,cy-1)])

    def draw_line(
        self,
        layer: str,
        x0: int, y0: int,
        x1: int, y1: int,
        rgba: tuple[int, int, int, int],
        brush_size: int = 1,
    ) -> None:
        """Draw a straight line from (x0,y0) to (x1,y1)."""
        for x, y in _bresenham(x0, y0, x1, y1):
            self.paint(layer, x, y, rgba, brush_size)

    def draw_rect_outline(
        self,
        layer: str,
        x0: int, y0: int,
        x1: int, y1: int,
        rgba: tuple[int, int, int, int],
        brush_size: int = 1,
    ) -> None:
        """Draw the outline of a rectangle from corner (x0,y0) to (x1,y1)."""
        lx, rx = min(x0, x1), max(x0, x1)
        ty, by = min(y0, y1), max(y0, y1)
        for x in range(lx, rx + 1):
            self.paint(layer, x, ty, rgba, brush_size)
            self.paint(layer, x, by, rgba, brush_size)
        for y in range(ty, by + 1):
            self.paint(layer, lx, y, rgba, brush_size)
            self.paint(layer, rx, y, rgba, brush_size)

    def draw_rect_filled(
        self,
        layer: str,
        x0: int, y0: int,
        x1: int, y1: int,
        rgba: tuple[int, int, int, int],
    ) -> None:
        """Fill a rectangle from corner (x0,y0) to (x1,y1)."""
        lx, rx = min(x0, x1), max(x0, x1)
        ty, by = min(y0, y1), max(y0, y1)
        for y in range(ty, by + 1):
            for x in range(lx, rx + 1):
                self.document.set_pixel(layer, x, y, rgba)

    def pick_color(
        self, layer: str, x: int, y: int
    ) -> tuple[int, int, int, int]:
        """Return the RGBA color at (x, y) for use as the active paint color."""
        return self.document.get_pixel(layer, x, y)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bresenham(x0: int, y0: int, x1: int, y1: int):
    """Yield all integer points on the line from (x0,y0) to (x1,y1)."""
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        yield x0, y0
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy

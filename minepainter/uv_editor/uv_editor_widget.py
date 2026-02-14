"""
UVEditorWidget: the 2D pixel-grid canvas for painting the 64×64 skin texture.

"UV" here refers to the texture-coordinate mapping on the skin PNG — nothing
to do with the `uv` Python package manager.

Controls:
  Left mouse drag  → paint / erase / dropper (depending on active tool)
  Left click+drag  → line / rect (preview shown while dragging, committed on release)
  Ctrl + scroll    → zoom in/out
  Middle drag      → pan
  Plain scroll     → pan vertically
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, Signal, QObject
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QMouseEvent, QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from minepainter.document import SkinDocument
from minepainter.uv_editor.paint_engine import PaintEngine


class UVEditorWidget(QWidget):
    # Emitted when the dropper picks a color: (r, g, b, a)
    color_picked = Signal(tuple)

    def __init__(self, document: SkinDocument, tool_state: "ToolState", parent=None) -> None:
        super().__init__(parent)
        self.document = document
        self.tool_state = tool_state
        self.engine = PaintEngine(document)

        # Zoom: pixels per skin-pixel (how large each skin pixel appears on screen)
        self.zoom: float = 8.0
        # Pan offset in screen pixels
        self.pan: QPointF = QPointF(16.0, 16.0)
        # Keep the UV map fully visible in the top-left and locked in place.
        self._lock_corner_view: bool = True

        self._painting: bool = False
        self._last_skin_pos: Optional[tuple[int, int]] = None
        self._mid_drag_start: Optional[QPointF] = None
        self._mid_drag_pan_start: Optional[QPointF] = None

        # For line / rect tools: start point (skin coords) set on press,
        # current end point updated on drag, committed on release.
        self._shape_start: Optional[tuple[int, int]] = None
        self._shape_end:   Optional[tuple[int, int]] = None

        self.setMouseTracking(True)
        self.setMinimumSize(200, 200)

        document.pixel_changed.connect(self._on_pixel_changed)
        document.layer_replaced.connect(self._on_layer_replaced)

    def set_corner_locked_view(self, enabled: bool) -> None:
        """Lock/unlock UV camera so the whole 64x64 stays pinned in-corner."""
        self._lock_corner_view = bool(enabled)
        if self._lock_corner_view:
            self._fit_texture_to_corner()
            self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._lock_corner_view:
            self._fit_texture_to_corner()

    def _fit_texture_to_corner(self) -> None:
        """Fit the whole UV texture in this widget and pin it to top-left."""
        pad = 8.0
        avail_w = max(1.0, self.width() - pad * 2.0)
        avail_h = max(1.0, self.height() - pad * 2.0)
        self.zoom = max(2.0, min(avail_w / 64.0, avail_h / 64.0))
        self.pan = QPointF(pad, pad)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Background — slightly darker than the panel so the texture stands out
        painter.fillRect(self.rect(), QColor(100, 110, 120))

        z = self.zoom
        ox, oy = self.pan.x(), self.pan.y()

        # Draw each pixel of the 64×64 skin texture
        for py in range(64):
            for px in range(64):
                r = QRectF(ox + px * z, oy + py * z, z, z)
                # Skip pixels outside the visible area
                if (r.right() < 0 or r.bottom() < 0
                        or r.left() > self.width() or r.top() > self.height()):
                    continue

                color = self._composite_pixel(px, py)
                painter.fillRect(r, color)

        # Grid lines (only when zoom is large enough to see them)
        if z >= 4.0:
            pen = QPen(QColor(60, 70, 80, 160))
            pen.setWidthF(0.5)
            painter.setPen(pen)
            for px in range(65):
                x = ox + px * z
                painter.drawLine(QPointF(x, oy), QPointF(x, oy + 64 * z))
            for py in range(65):
                y = oy + py * z
                painter.drawLine(QPointF(ox, y), QPointF(ox + 64 * z, y))

        # Live preview overlay for line / rect tools while dragging
        tool = self.tool_state.active_tool
        if self._shape_start is not None and self._shape_end is not None:
            self._draw_shape_preview(painter, tool)

        # Highlight hovered cell
        sp = self._screen_to_skin(self.mapFromGlobal(self.cursor().pos()))
        if sp is not None:
            sx, sy = sp
            hover_rect = QRectF(ox + sx * z, oy + sy * z, z, z)
            painter.setPen(QPen(QColor(255, 255, 255, 180), max(1.0, z * 0.1)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(hover_rect)

        painter.end()

    def _draw_shape_preview(self, painter: QPainter, tool: str) -> None:
        """Draw a semi-transparent preview of the line or rect being dragged."""
        z = self.zoom
        ox, oy = self.pan.x(), self.pan.y()
        x0, y0 = self._shape_start
        x1, y1 = self._shape_end
        r, g, b, a = self.tool_state.active_color
        preview_color = QColor(r, g, b, 160)

        pen = QPen(preview_color, max(1.0, z * 0.9))
        pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if tool == "line":
            painter.drawLine(
                QPointF(ox + (x0 + 0.5) * z, oy + (y0 + 0.5) * z),
                QPointF(ox + (x1 + 0.5) * z, oy + (y1 + 0.5) * z),
            )
        elif tool == "rect_outline":
            lx, rx = min(x0, x1), max(x0, x1)
            ty, by = min(y0, y1), max(y0, y1)
            painter.drawRect(QRectF(
                ox + lx * z, oy + ty * z,
                (rx - lx + 1) * z, (by - ty + 1) * z,
            ))
        elif tool == "rect_filled":
            lx, rx = min(x0, x1), max(x0, x1)
            ty, by = min(y0, y1), max(y0, y1)
            painter.setBrush(QBrush(QColor(r, g, b, 80)))
            painter.drawRect(QRectF(
                ox + lx * z, oy + ty * z,
                (rx - lx + 1) * z, (by - ty + 1) * z,
            ))

    def _composite_pixel(self, px: int, py: int) -> QColor:
        """Return the display colour at this skin pixel (base + armor composited)."""
        br, bg, bb, ba = self.document.get_pixel("base", px, py) if self.document.base_visible else (0, 0, 0, 0)
        ar, ag, ab, aa = self.document.get_pixel("armor", px, py) if self.document.armor_visible else (0, 0, 0, 0)

        if aa == 0:
            r, g, b, a = br, bg, bb, ba
        elif ba == 0:
            r, g, b, a = ar, ag, ab, aa
        else:
            # Simple alpha compositing: armor over base
            af = aa / 255.0
            r = int(ar * af + br * (1 - af))
            g = int(ag * af + bg * (1 - af))
            b = int(ab * af + bb * (1 - af))
            a = min(255, ba + aa)

        # Checkerboard for transparency
        if a < 255:
            checker = 200 if ((px // 4 + py // 4) % 2 == 0) else 160
            af = a / 255.0
            r = int(r * af + checker * (1 - af))
            g = int(g * af + checker * (1 - af))
            b = int(b * af + checker * (1 - af))
            a = 255

        return QColor(r, g, b, a)

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            if self._lock_corner_view:
                return
            self._mid_drag_start = event.position()
            self._mid_drag_pan_start = QPointF(self.pan)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            sp = self._screen_to_skin(event.position().toPoint())
            if sp is None:
                return

            tool = self.tool_state.active_tool
            layer = self.tool_state.active_layer

            if tool in ("line", "rect_outline", "rect_filled"):
                # Shape tools: record start, show preview on drag, commit on release
                self._shape_start = sp
                self._shape_end   = sp
                self.document.push_undo_snapshot(layer)
                self.update()
            else:
                self._painting = True
                self._last_skin_pos = sp
                if tool in ("brush", "eraser", "fill"):
                    self.document.push_undo_snapshot(layer)
                self._apply_tool(*sp)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        # Middle-button pan
        if self._mid_drag_start is not None:
            delta = event.position() - self._mid_drag_start
            self.pan = self._mid_drag_pan_start + delta
            self.update()
            return

        tool = self.tool_state.active_tool

        if self._shape_start is not None:
            # Update shape end point and repaint preview
            sp = self._screen_to_skin(event.position().toPoint())
            if sp is not None:
                self._shape_end = sp
            self.update()
            return

        if self._painting:
            sp = self._screen_to_skin(event.position().toPoint())
            if sp is not None:
                lx, ly = self._last_skin_pos or sp
                self._apply_tool_line(lx, ly, *sp)
                self._last_skin_pos = sp
        else:
            self.update()  # refresh hover highlight

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._mid_drag_start = None
            self._mid_drag_pan_start = None

        if event.button() == Qt.MouseButton.LeftButton:
            tool  = self.tool_state.active_tool
            layer = self.tool_state.active_layer
            color = self.tool_state.active_color
            size  = self.tool_state.brush_size

            if self._shape_start is not None and self._shape_end is not None:
                x0, y0 = self._shape_start
                x1, y1 = self._shape_end
                if tool == "line":
                    self.engine.draw_line(layer, x0, y0, x1, y1, color, size)
                elif tool == "rect_outline":
                    self.engine.draw_rect_outline(layer, x0, y0, x1, y1, color, size)
                elif tool == "rect_filled":
                    self.engine.draw_rect_filled(layer, x0, y0, x1, y1, color)
                self._shape_start = None
                self._shape_end   = None
                self.update()

            self._painting = False
            self._last_skin_pos = None

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._lock_corner_view:
            return
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Zoom toward mouse cursor
            mouse_skin = event.position()
            factor = 1.15 if delta > 0 else 1.0 / 1.15
            old_zoom = self.zoom
            self.zoom = max(2.0, min(64.0, self.zoom * factor))
            # Adjust pan so the pixel under the cursor stays fixed
            scale = self.zoom / old_zoom
            self.pan = mouse_skin - (mouse_skin - self.pan) * scale
        else:
            # Plain scroll: pan vertically
            self.pan = QPointF(self.pan.x(), self.pan.y() + delta * 0.2)
        self.update()

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    def _apply_tool(self, sx: int, sy: int) -> None:
        layer = self.tool_state.active_layer
        tool  = self.tool_state.active_tool
        size  = self.tool_state.brush_size
        color = self.tool_state.active_color

        if tool == "brush":
            self.engine.paint(layer, sx, sy, color, size)
        elif tool == "eraser":
            self.engine.erase(layer, sx, sy, size)
        elif tool == "fill":
            self.engine.fill(layer, sx, sy, color)
        elif tool == "dropper":
            picked = self.engine.pick_color(layer, sx, sy)
            self.tool_state.set_color(picked)
            self.color_picked.emit(picked)
            self.tool_state.set_tool("brush")   # switch back after picking

    def _apply_tool_line(
        self, x0: int, y0: int, x1: int, y1: int
    ) -> None:
        layer = self.tool_state.active_layer
        tool  = self.tool_state.active_tool
        size  = self.tool_state.brush_size
        color = self.tool_state.active_color

        if tool == "brush":
            self.engine.paint_line(layer, x0, y0, x1, y1, color, size)
        elif tool == "eraser":
            self.engine.erase_line(layer, x0, y0, x1, y1, size)
        # fill / dropper / shape tools don't use continuous drag painting

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _screen_to_skin(self, pos) -> Optional[tuple[int, int]]:
        """Convert a screen position to skin pixel coordinates (0..63)."""
        if isinstance(pos, QPointF):
            sx = pos.x()
            sy = pos.y()
        else:
            sx = pos.x()
            sy = pos.y()
        px = int((sx - self.pan.x()) / self.zoom)
        py = int((sy - self.pan.y()) / self.zoom)
        if 0 <= px < 64 and 0 <= py < 64:
            return px, py
        return None

    # ------------------------------------------------------------------
    # Document signal handlers
    # ------------------------------------------------------------------

    def _on_pixel_changed(self, layer, x, y, color) -> None:
        # Repaint only the affected pixel cell for efficiency
        z = self.zoom
        ox, oy = self.pan.x(), self.pan.y()
        rect = QRectF(ox + x * z - 1, oy + y * z - 1, z + 2, z + 2)
        self.update(rect.toRect())

    def _on_layer_replaced(self, layer) -> None:
        self.update()

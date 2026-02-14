"""
ColorPickerWidget: an inline HSV color picker.

Layout (top to bottom):
  • Hue ring  — click or drag to choose hue
  • SV square — click or drag inside the hue-tinted square to pick saturation/value
  • Alpha bar — horizontal slider for opacity
  • Hex label — live #rrggbbaa readout (click to type a hex value)
  • Recent-color row lives in ToolPanel, not here

All painting is done with QPainter; no external dependencies beyond PySide6.
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Signal, Qt, QPointF, QRectF, QSize
from PySide6.QtGui import (
    QColor, QPainter, QConicalGradient, QLinearGradient,
    QRadialGradient, QPen, QBrush, QMouseEvent, QImage,
)
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy


# ---------------------------------------------------------------------------
# Hue + SV wheel widget
# ---------------------------------------------------------------------------

class _HueSVPicker(QWidget):
    """
    Draws a hue ring around an SV (saturation-value) square.
    Emits color_changed(QColor) on every interaction.
    """

    color_changed = Signal(QColor)

    _RING_FRAC = 0.18   # ring width as fraction of widget half-size

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._hue:   float = 0.0    # 0..360
        self._sat:   float = 1.0    # 0..1
        self._val:   float = 1.0    # 0..1
        self._alpha: int   = 255

        self._drag_ring = False
        self._drag_sv   = False

        self.setMinimumSize(160, 160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_color(self, color: QColor) -> None:
        h, s, v, _ = color.getHsvF()
        if h < 0:   # achromatic
            h = self._hue / 360.0
        self._hue = h * 360.0
        self._sat = max(0.0, min(1.0, s))
        self._val = max(0.0, min(1.0, v))
        self._alpha = color.alpha()
        self.update()

    def color(self) -> QColor:
        c = QColor.fromHsvF(self._hue / 360.0, self._sat, self._val)
        c.setAlpha(self._alpha)
        return c

    def set_alpha(self, a: int) -> None:
        self._alpha = max(0, min(255, a))
        self.update()

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def _geometry(self):
        side   = min(self.width(), self.height())
        cx     = self.width()  / 2
        cy     = self.height() / 2
        r_out  = side / 2 - 2          # outer ring radius
        ring_w = r_out * self._RING_FRAC
        r_in   = r_out - ring_w        # inner ring radius = SV square circumradius
        sq_half = r_in / math.sqrt(2)  # half side of inscribed square
        return cx, cy, r_out, r_in, ring_w, sq_half

    def _sv_rect(self) -> QRectF:
        cx, cy, _, _, _, sq_half = self._geometry()
        return QRectF(cx - sq_half, cy - sq_half, sq_half * 2, sq_half * 2)

    def _is_in_ring(self, x: float, y: float) -> bool:
        cx, cy, r_out, r_in, *_ = self._geometry()
        d = math.hypot(x - cx, y - cy)
        return r_in <= d <= r_out

    def _is_in_sv(self, x: float, y: float) -> bool:
        return self._sv_rect().contains(QPointF(x, y))

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        cx, cy, r_out, r_in, ring_w, sq_half = self._geometry()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # --- Hue ring ---
        steps = 360
        import math
        pen_w = ring_w + 1
        for i in range(steps):
            angle = i
            color = QColor.fromHsvF(angle / 360.0, 1.0, 1.0)
            pen = QPen(color, pen_w)
            p.setPen(pen)
            a1 = math.radians(angle)
            a2 = math.radians(angle + 1.5)
            # draw a short arc segment as a line between two points on mid-ring
            r_mid = (r_out + r_in) / 2
            x1 = cx + r_mid * math.cos(a1)
            y1 = cy - r_mid * math.sin(a1)
            x2 = cx + r_mid * math.cos(a2)
            y2 = cy - r_mid * math.sin(a2)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # --- Hue cursor on ring ---
        hue_rad = math.radians(self._hue)
        r_mid = (r_out + r_in) / 2
        hx = cx + r_mid * math.cos(hue_rad)
        hy = cy - r_mid * math.sin(hue_rad)
        p.setPen(QPen(Qt.GlobalColor.white, 2))
        p.setBrush(QColor.fromHsvF(self._hue / 360.0, 1.0, 1.0))
        p.drawEllipse(QPointF(hx, hy), ring_w * 0.45, ring_w * 0.45)

        # --- SV square ---
        rect = self._sv_rect()
        # Render SV square into a small QImage for speed
        img_size = max(2, int(sq_half * 2))
        img = QImage(img_size, img_size, QImage.Format.Format_RGB32)
        base_hue = QColor.fromHsvF(self._hue / 360.0, 1.0, 1.0)
        for iy in range(img_size):
            v = 1.0 - iy / img_size
            for ix in range(img_size):
                s = ix / img_size
                c = QColor.fromHsvF(self._hue / 360.0, s, v)
                img.setPixel(ix, iy, c.rgb())
        p.drawImage(rect, img)

        # SV cursor
        sv_x = rect.left() + self._sat * rect.width()
        sv_y = rect.top()  + (1.0 - self._val) * rect.height()
        cursor_color = Qt.GlobalColor.black if self._val > 0.5 else Qt.GlobalColor.white
        p.setPen(QPen(cursor_color, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(sv_x, sv_y), 5, 5)
        p.setPen(QPen(Qt.GlobalColor.white if self._val <= 0.5 else Qt.GlobalColor.black, 0.5))
        p.drawEllipse(QPointF(sv_x, sv_y), 6.5, 6.5)

        p.end()

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        x, y = event.position().x(), event.position().y()
        if self._is_in_ring(x, y):
            self._drag_ring = True
            self._update_hue(x, y)
        elif self._is_in_sv(x, y):
            self._drag_sv = True
            self._update_sv(x, y)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        x, y = event.position().x(), event.position().y()
        if self._drag_ring:
            self._update_hue(x, y)
        elif self._drag_sv:
            self._update_sv(x, y)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_ring = False
        self._drag_sv   = False

    def _update_hue(self, x: float, y: float) -> None:
        cx, cy, *_ = self._geometry()
        angle = math.degrees(math.atan2(-(y - cy), x - cx)) % 360
        self._hue = angle
        self.update()
        self.color_changed.emit(self.color())

    def _update_sv(self, x: float, y: float) -> None:
        rect = self._sv_rect()
        s = (x - rect.left()) / rect.width()
        v = 1.0 - (y - rect.top()) / rect.height()
        self._sat = max(0.0, min(1.0, s))
        self._val = max(0.0, min(1.0, v))
        self.update()
        self.color_changed.emit(self.color())


# ---------------------------------------------------------------------------
# Alpha bar
# ---------------------------------------------------------------------------

class _AlphaBar(QWidget):
    """Horizontal alpha slider with checkerboard background."""

    alpha_changed = Signal(int)   # 0..255

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._alpha = 255
        self._color = QColor(0, 0, 0, 255)
        self.setFixedHeight(18)
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    def set_color(self, color: QColor) -> None:
        self._color = color
        self._alpha = color.alpha()
        self.update()

    def set_alpha(self, a: int) -> None:
        self._alpha = max(0, min(255, a))
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        w, h = self.width(), self.height()
        # Checkerboard
        cell = 6
        for row in range(0, h, cell):
            for col in range(0, w, cell):
                shade = 200 if ((row // cell + col // cell) % 2 == 0) else 140
                p.fillRect(col, row, cell, cell, QColor(shade, shade, shade))
        # Color gradient (opaque → transparent)
        grad = QLinearGradient(0, 0, w, 0)
        c_opaque = QColor(self._color.red(), self._color.green(), self._color.blue(), 255)
        c_clear  = QColor(self._color.red(), self._color.green(), self._color.blue(), 0)
        grad.setColorAt(0.0, c_clear)
        grad.setColorAt(1.0, c_opaque)
        p.fillRect(0, 0, w, h, grad)
        # Cursor
        x = int(self._alpha / 255 * (w - 4)) + 2
        p.setPen(QPen(Qt.GlobalColor.white, 2))
        p.drawLine(x, 0, x, h)
        p.setPen(QPen(Qt.GlobalColor.black, 1))
        p.drawLine(x, 0, x, h)
        p.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._pick(event.position().x())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._pick(event.position().x())

    def _pick(self, x: float) -> None:
        a = int(max(0.0, min(1.0, (x - 2) / (self.width() - 4))) * 255)
        self._alpha = a
        self.update()
        self.alpha_changed.emit(a)


# ---------------------------------------------------------------------------
# Main color picker widget
# ---------------------------------------------------------------------------

class ColorPickerWidget(QWidget):
    """
    Inline HSV color picker:
      - Hue ring + SV square
      - Alpha bar
      - Color swatch + hex readout
    Emits color_selected(tuple[r,g,b,a]) whenever the color changes.
    """

    color_selected = Signal(tuple)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current = QColor(0, 0, 0, 255)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(4)

        # Hue ring + SV square
        self._hsv = _HueSVPicker()
        self._hsv.color_changed.connect(self._on_hsv_changed)
        layout.addWidget(self._hsv)

        # Alpha bar
        self._alpha_bar = _AlphaBar()
        self._alpha_bar.alpha_changed.connect(self._on_alpha_changed)
        layout.addWidget(self._alpha_bar)

        # Bottom row: swatch + hex label
        from PySide6.QtWidgets import QHBoxLayout
        bot = QHBoxLayout()
        bot.setSpacing(6)

        self._swatch = QLabel()
        self._swatch.setFixedSize(28, 28)
        self._swatch.setStyleSheet(
            "border: 1px solid #888; border-radius: 4px; background: black;"
        )
        bot.addWidget(self._swatch)

        self._hex_label = QLabel("#000000ff")
        self._hex_label.setStyleSheet(
            "font-family: 'Courier New', Monaco, monospace; font-size: 11px;"
        )
        bot.addWidget(self._hex_label)
        bot.addStretch()
        layout.addLayout(bot)

        self._refresh_swatch()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_color(self, rgba: tuple[int, int, int, int]) -> None:
        r, g, b, a = rgba
        self._current = QColor(r, g, b, a)
        self._hsv.set_color(self._current)
        self._alpha_bar.set_color(self._current)
        self._refresh_swatch()

    def current_color(self) -> tuple[int, int, int, int]:
        c = self._current
        return (c.red(), c.green(), c.blue(), c.alpha())

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_hsv_changed(self, color: QColor) -> None:
        color.setAlpha(self._current.alpha())
        self._current = color
        self._alpha_bar.set_color(color)
        self._refresh_swatch()
        self.color_selected.emit(self.current_color())

    def _on_alpha_changed(self, a: int) -> None:
        self._current.setAlpha(a)
        self._hsv.set_alpha(a)
        self._refresh_swatch()
        self.color_selected.emit(self.current_color())

    def _refresh_swatch(self) -> None:
        c = self._current
        r, g, b, a = c.red(), c.green(), c.blue(), c.alpha()
        self._swatch.setStyleSheet(
            f"background-color: rgba({r},{g},{b},{a}); "
            "border: 1px solid #888; border-radius: 4px;"
        )
        self._hex_label.setText(f"#{r:02x}{g:02x}{b:02x}{a:02x}")

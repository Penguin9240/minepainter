"""
HomeScreen: colorful splash / landing page.

Shown on startup. The user picks one of two modes:
  • Paint Skin PNG   – opens the main editor set up for the base-skin layer
  • Paint Armor PNG  – opens the main editor set up for the armor-overlay layer

Signals
-------
skin_chosen           – user clicked "Paint Skin PNG"
armor_chosen          – user clicked "Paint Armor PNG"
open_skin_chosen(str) – user clicked a saved skin thumbnail (path string)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QTimer, QSize
from PySide6.QtGui import (
    QColor, QLinearGradient, QRadialGradient, QPainter,
    QPen, QBrush, QFont, QFontMetrics, QPainterPath, QPixmap, QImage,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSizePolicy,
    QScrollArea, QLabel, QFileDialog, QMenu, QMessageBox,
)


# ---------------------------------------------------------------------------
# Persistent skin registry  (~/.config/minepainter/recent_skins.json)
# ---------------------------------------------------------------------------

_CONFIG_DIR  = Path.home() / ".config" / "minepainter"
_REGISTRY    = _CONFIG_DIR / "recent_skins.json"

def _load_registry() -> list[Path]:
    """Return list of known skin paths (existing files only)."""
    try:
        data = json.loads(_REGISTRY.read_text())
        return [Path(p) for p in data if Path(p).exists()]
    except Exception:
        return []

def _save_registry(paths: list[Path]) -> None:
    """Persist the skin path list."""
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _REGISTRY.write_text(json.dumps([str(p) for p in paths], indent=2))
    except Exception:
        pass

def register_skin_path(path: Path) -> None:
    """Add a path to the registry (called after save/open in the editor)."""
    paths = _load_registry()
    if path not in paths and path.exists():
        paths.insert(0, path)
        _save_registry(paths)


# ---------------------------------------------------------------------------
# Animated background canvas
# ---------------------------------------------------------------------------

class _Background(QWidget):
    """
    Draws a lively animated background:
      - Deep gradient sky
      - Floating coloured "pixel blocks" that drift slowly upward
      - Subtle radial glow in the centre
    """

    _BLOCKS = [
        # (x_frac, y_frac, size, color, speed_frac)
        (0.08, 0.15, 32, "#e74c3c", 0.00014),
        (0.18, 0.60, 24, "#e67e22", 0.00019),
        (0.30, 0.35, 40, "#f1c40f", 0.00011),
        (0.45, 0.75, 20, "#2ecc71", 0.00022),
        (0.55, 0.20, 36, "#1abc9c", 0.00016),
        (0.68, 0.55, 28, "#3498db", 0.00013),
        (0.80, 0.30, 44, "#9b59b6", 0.00018),
        (0.90, 0.70, 22, "#e91e63", 0.00020),
        (0.12, 0.80, 30, "#ff5722", 0.00015),
        (0.38, 0.10, 26, "#00bcd4", 0.00017),
        (0.62, 0.88, 38, "#8bc34a", 0.00012),
        (0.75, 0.08, 20, "#ff9800", 0.00021),
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tick = 0
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        timer = QTimer(self)
        timer.timeout.connect(self._animate)
        timer.start(30)   # ~33 fps

    def _animate(self) -> None:
        self._tick += 1
        self.update()

    def paintEvent(self, event) -> None:
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # --- Background gradient (dark purple → deep blue) ---
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor("#0d0d2b"))
        grad.setColorAt(0.5, QColor("#1a1a4e"))
        grad.setColorAt(1.0, QColor("#0a1628"))
        p.fillRect(0, 0, w, h, grad)

        # --- Radial glow in centre ---
        cx, cy = w / 2, h / 2
        glow = QRadialGradient(cx, cy, max(w, h) * 0.55)
        glow.setColorAt(0.0, QColor(80, 40, 160, 80))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, w, h, glow)

        # --- Floating pixel blocks ---
        t = self._tick
        for (xf, yf, size, color, speed) in self._BLOCKS:
            offset = (t * speed * h) % (h + size + 100)
            bx = int(xf * w)
            by = int((yf * h - offset) % (h + size + 100)) - size
            # slight horizontal bob
            bx += int(math.sin(t * 0.018 + xf * 10) * 12)
            c = QColor(color)
            # shadow
            p.fillRect(bx + 4, by + 4, size, size, QColor(0, 0, 0, 60))
            # block face
            p.fillRect(bx, by, size, size, c)
            # highlight top edge
            lighter = c.lighter(150)
            p.fillRect(bx, by, size, 3, lighter)
            # highlight left edge
            p.fillRect(bx, by, 3, size, lighter)
            # darker bottom/right edge
            darker = c.darker(160)
            p.fillRect(bx, by + size - 3, size, 3, darker)
            p.fillRect(bx + size - 3, by, 3, size, darker)

        p.end()


# ---------------------------------------------------------------------------
# Big card button
# ---------------------------------------------------------------------------

class _CardButton(QPushButton):
    """
    A large, colourful rounded card that acts as the main choice button.
    Hover/press states handled via style flags + repaint.
    """

    # Fixed card dimensions — always looks good, no layout fights
    _W = 240
    _H = 240

    def __init__(self, title: str, subtitle: str, color: str, icon_char: str, parent=None) -> None:
        super().__init__(parent)
        self._title    = title
        self._subtitle = subtitle
        self._color    = QColor(color)
        self._icon     = icon_char
        self._hovered  = False
        self._pressed  = False

        self.setFixedSize(self._W, self._H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        scale = 0.94 if self._pressed else (1.04 if self._hovered else 1.0)
        p.translate(w / 2, h / 2)
        p.scale(scale, scale)
        p.translate(-w / 2, -h / 2)

        radius = 18.0

        # Drop shadow
        shadow_color = QColor(0, 0, 0, 90 if self._hovered else 55)
        p.setBrush(shadow_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(6, 8, w - 12, h - 12), radius, radius)

        # Card gradient background
        c1 = self._color.lighter(130)
        c2 = self._color.darker(110)
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, c1)
        grad.setColorAt(1.0, c2)
        p.setBrush(grad)

        # Border glow on hover
        if self._hovered:
            p.setPen(QPen(QColor(255, 255, 255, 180), 2.5))
        else:
            p.setPen(QPen(self._color.darker(140), 1.5))

        p.drawRoundedRect(QRectF(2, 2, w - 4, h - 4), radius, radius)

        # Divide the card into three proportional zones:
        #   top 42% → icon, next 22% → title, bottom 32% → subtitle
        icon_zone_h  = h * 0.42
        title_zone_y = h * 0.42
        title_zone_h = h * 0.22
        sub_zone_y   = h * 0.64
        sub_zone_h   = h * 0.32

        # Icon — scale font with card height
        icon_pt = max(10, int(h * 0.20))
        font = QFont("Segoe UI Emoji", icon_pt)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255, 220))
        p.drawText(QRectF(0, 4, w, icon_zone_h - 4),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   self._icon)

        # Title — scale font with card height
        title_pt = max(9, int(h * 0.092))
        title_font = QFont("Segoe UI", title_pt, QFont.Weight.Bold)
        p.setFont(title_font)
        p.setPen(Qt.GlobalColor.white)
        p.drawText(QRectF(8, title_zone_y, w - 16, title_zone_h),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   self._title)

        # Subtitle — scale font with card height
        sub_pt = max(7, int(h * 0.060))
        sub_font = QFont("Segoe UI", sub_pt)
        p.setFont(sub_font)
        p.setPen(QColor(255, 255, 255, 180))
        p.drawText(QRectF(8, sub_zone_y, w - 16, sub_zone_h),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   self._subtitle)

        p.end()


# ---------------------------------------------------------------------------
# Centre panel (transparent card that holds the buttons)
# ---------------------------------------------------------------------------

class _CentrePanel(QWidget):
    """Semi-transparent rounded panel drawn behind the choice buttons."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(10, 10, 30, 180))
        p.setPen(QPen(QColor(255, 255, 255, 40), 1.5))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 24, 24)
        p.end()


# ---------------------------------------------------------------------------
# Skin gallery
# ---------------------------------------------------------------------------

class _SkinThumbnail(QWidget):
    """
    A single skin preview card: 64×64 PNG rendered pixel-art style at 2×
    with the filename underneath.  Emits clicked(path) when left-clicked,
    delete_requested(path) when the user picks Delete from the context menu.
    """
    clicked          = Signal(str)
    delete_requested = Signal(str)

    _THUMB = 80   # display size of the skin preview in pixels

    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self._path    = path
        self._pixmap  = self._load_pixmap(path)
        self._hovered = False
        self._name    = path.stem[:16] + ("…" if len(path.stem) > 16 else "")

        self.setFixedSize(self._THUMB + 16, self._THUMB + 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1e1e3c; border: 1px solid #3a3a6a; color: #dde3f0; "
            "        border-radius: 6px; padding: 4px; }"
            "QMenu::item { padding: 6px 18px; border-radius: 4px; }"
            "QMenu::item:selected { background: #2e2e60; }"
        )
        open_act  = menu.addAction("🎨  Open")
        menu.addSeparator()
        del_act   = menu.addAction("🗑️  Remove from list")
        del_file  = menu.addAction("❌  Delete file")

        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen == open_act:
            self.clicked.emit(str(self._path))
        elif chosen == del_act:
            self.delete_requested.emit(str(self._path))
        elif chosen == del_file:
            reply = QMessageBox.question(
                self,
                "Delete file",
                f"Permanently delete '{self._path.name}' from disk?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    self._path.unlink()
                except Exception as e:
                    QMessageBox.warning(self, "Delete failed", str(e))
                self.delete_requested.emit(str(self._path))

    @staticmethod
    def _load_pixmap(path: Path) -> QPixmap | None:
        try:
            img = QImage(str(path))
            if img.isNull():
                return None
            # Scale to _THUMB × _THUMB with nearest-neighbour (pixel-art)
            img = img.scaled(
                _SkinThumbnail._THUMB, _SkinThumbnail._THUMB,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            return QPixmap.fromImage(img)
        except Exception:
            return None

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(str(self._path))
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Card background
        bg = QColor(30, 30, 60, 200) if self._hovered else QColor(18, 18, 42, 200)
        border = QColor(100, 100, 200, 220) if self._hovered else QColor(58, 58, 106, 160)
        p.setBrush(bg)
        p.setPen(QPen(border, 1.5))
        p.drawRoundedRect(QRectF(0, 0, w, h), 8, 8)

        # Checkerboard behind transparent skin pixels
        cell = 4
        px = (w - self._THUMB) // 2
        py = 6
        for row in range(0, self._THUMB, cell):
            for col in range(0, self._THUMB, cell):
                shade = 50 if ((row // cell + col // cell) % 2 == 0) else 38
                p.fillRect(px + col, py + row, cell, cell, QColor(shade, shade, shade + 10))

        # Skin pixmap
        if self._pixmap:
            p.drawPixmap(px, py, self._pixmap)
        else:
            p.setPen(QColor(150, 100, 100))
            p.drawText(QRectF(0, py, w, self._THUMB),
                       Qt.AlignmentFlag.AlignCenter, "?")

        # Filename label
        font = QFont("Segoe UI", 8)
        p.setFont(font)
        p.setPen(QColor(200, 210, 240, 200) if self._hovered else QColor(160, 170, 200, 180))
        p.drawText(QRectF(2, py + self._THUMB + 4, w - 4, 18),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   self._name)
        p.end()


class _SkinGallery(QWidget):
    """
    Horizontally scrollable row of _SkinThumbnail cards plus a Browse button.
    Uses the persistent registry (~/.config/minepainter/recent_skins.json)
    so it remembers every skin that was ever opened or saved.

    Emits open_requested(path_str) when the user picks a skin.
    """
    open_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        # Section header row
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("Recent skins")
        lbl.setStyleSheet(
            "color: rgba(180,190,230,200); font-size: 12px; font-weight: bold;"
            "background: transparent;"
        )
        header.addWidget(lbl)
        header.addStretch()

        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedHeight(24)
        browse_btn.setStyleSheet(
            "QPushButton { background: #252550; border: 1px solid #3a3a6a; "
            "border-radius: 4px; color: #dde3f0; padding: 0 10px; font-size: 11px; }"
            "QPushButton:hover { background: #2e2e60; border-color: #5555aa; }"
        )
        browse_btn.clicked.connect(self._on_browse)
        header.addWidget(browse_btn)
        outer.addLayout(header)

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFixedHeight(_SkinThumbnail._THUMB + 48)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:horizontal { background: #1a1a38; height: 6px; border: none; }"
            "QScrollBar::handle:horizontal { background: #3a3a6a; border-radius: 3px; min-width: 20px; }"
            "QScrollBar::handle:horizontal:hover { background: #5555aa; }"
            "QScrollBar::add-line, QScrollBar::sub-line { width: 0; }"
        )

        self._container = QWidget()
        self._container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._row = QHBoxLayout(self._container)
        self._row.setContentsMargins(4, 4, 4, 4)
        self._row.setSpacing(10)
        self._row.addStretch()

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

        self._refresh()

    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Rebuild the thumbnail row from the registry."""
        while self._row.count():
            item = self._row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        paths = _load_registry()
        if not paths:
            placeholder = QLabel("No recent skins — open or save a skin to see it here")
            placeholder.setStyleSheet(
                "color: rgba(150,160,200,160); font-style: italic; background: transparent;"
            )
            self._row.addWidget(placeholder, 0, Qt.AlignmentFlag.AlignVCenter)
        else:
            for p in paths:
                thumb = _SkinThumbnail(p)
                thumb.clicked.connect(self.open_requested)
                thumb.delete_requested.connect(self._on_delete)
                self._row.addWidget(thumb)

        self._row.addStretch()

    def _on_delete(self, path_str: str) -> None:
        """Remove a skin from the registry and refresh."""
        paths = _load_registry()
        paths = [p for p in paths if str(p) != path_str]
        _save_registry(paths)
        self._refresh()

    def _on_browse(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open Skin PNG(s)", str(Path.home()), "PNG files (*.png)"
        )
        if paths:
            for ps in paths:
                register_skin_path(Path(ps))
            self._refresh()
            self.open_requested.emit(paths[0])

    def add_path(self, path: Path) -> None:
        """Register a newly saved skin and refresh the gallery."""
        register_skin_path(path)
        self._refresh()


# ---------------------------------------------------------------------------
# HomeScreen widget
# ---------------------------------------------------------------------------

class HomeScreen(QWidget):
    """
    Full-window splash page.
    Emits skin_chosen or armor_chosen when the user picks a mode.
    """

    skin_chosen       = Signal()
    armor_chosen      = Signal()
    open_skin_chosen  = Signal(str)   # path to a PNG the user wants to open

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        # Animated background fills the whole widget
        self._bg = _Background(self)
        self._bg.setGeometry(0, 0, self.width(), self.height())

        # Centre panel
        panel = _CentrePanel(self)

        # Title label (painted on a transparent QWidget)
        title_widget = _TitleWidget()

        # Choice buttons
        self._btn_skin = _CardButton(
            "Paint Skin",
            "Design the base skin layer\n(body + face texture)",
            "#e74c3c",
            "🎨",
        )
        self._btn_armor = _CardButton(
            "Paint Armor",
            "Design the outer armor overlay\n(helmet, chestplate …)",
            "#3498db",
            "🛡️",
        )

        self._btn_skin.clicked.connect(self.skin_chosen)
        self._btn_armor.clicked.connect(self.armor_chosen)

        # --- Panel layout: title on top, cards centered below ---
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(40, 28, 40, 28)
        panel_layout.setSpacing(16)

        panel_layout.addWidget(title_widget)

        tagline_inner = _TaglineWidget("The Minecraft skin painting studio")
        panel_layout.addWidget(tagline_inner)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(32)
        btn_row.addStretch(1)
        btn_row.addWidget(self._btn_skin)
        btn_row.addWidget(self._btn_armor)
        btn_row.addStretch(1)
        panel_layout.addLayout(btn_row)

        # The panel's natural size is driven by its fixed-size children — let it be.
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        # --- Gallery of saved skins (below panel) ---
        self.gallery = _SkinGallery()
        self.gallery.open_requested.connect(self.open_skin_chosen)

        # --- Outer layout: centre the panel vertically, gallery at bottom ---
        outer = QVBoxLayout(self)
        outer.setContentsMargins(60, 32, 60, 24)
        outer.setSpacing(12)
        outer.addStretch(1)
        outer.addWidget(panel, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)
        outer.addWidget(self.gallery, 0)

        # Push the background behind all layout children
        self._bg.lower()

    def resizeEvent(self, event) -> None:
        self._bg.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(event)


# ---------------------------------------------------------------------------
# Small helper label widgets
# ---------------------------------------------------------------------------

class _TitleWidget(QWidget):
    """Paints the big "MinePainter" title with a rainbow gradient."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        title_pt = 28
        font = QFont("Segoe UI", title_pt, QFont.Weight.Black)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        p.setFont(font)

        text = "MinePainter"
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(text)
        text_h = fm.height()
        x = (w - text_w) / 2
        y = (h + text_h) / 2 - fm.descent()

        # Rainbow horizontal gradient across the text
        grad = QLinearGradient(x, 0, x + text_w, 0)
        grad.setColorAt(0.00, QColor("#e74c3c"))
        grad.setColorAt(0.20, QColor("#f39c12"))
        grad.setColorAt(0.40, QColor("#f1c40f"))
        grad.setColorAt(0.60, QColor("#2ecc71"))
        grad.setColorAt(0.80, QColor("#3498db"))
        grad.setColorAt(1.00, QColor("#9b59b6"))

        # Shadow
        p.setPen(QColor(0, 0, 0, 120))
        p.drawText(QPointF(x + 3, y + 3), text)

        # Gradient text via clip path
        path = QPainterPath()
        path.addText(QPointF(x, y), font, text)
        p.fillPath(path, QBrush(grad))

        p.end()


class _TaglineWidget(QWidget):
    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self._text = text
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont("Segoe UI", 11)
        font.setItalic(True)
        p.setFont(font)
        p.setPen(QColor(200, 200, 255, 180))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)
        p.end()

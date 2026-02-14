"""
ToolPanel and ToolState.

ToolState is a shared QObject that both the ToolPanel widget and the
UVEditorWidget reference so they stay in sync without direct coupling.

ToolPanel itself is a lightweight container that owns ToolState and exposes
two sub-widgets for placement anywhere in the main window:

  tool_strip()   — compact horizontal bar with layer selector, tool buttons
                   and brush size; lives below the 2D UV editor
  color_panel()  — right-side panel with the color picker and recent swatches
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Qt, QRect
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QButtonGroup, QSlider, QCheckBox,
    QSizePolicy, QFrame,
)

from minepainter.tools.color_picker import ColorPickerWidget


# ---------------------------------------------------------------------------
# ToolState: shared mutable tool settings
# ---------------------------------------------------------------------------

class ToolState(QObject):
    tool_changed        = Signal(str)
    color_changed       = Signal(tuple)         # (r, g, b, a)
    brush_size_changed  = Signal(int)
    layer_changed       = Signal(str)           # "base" | "armor"

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.active_tool:  str                        = "brush"
        self.active_color: tuple[int, int, int, int]  = (0, 0, 0, 255)
        self.brush_size:   int                        = 1
        self.active_layer: str                        = "base"

    def set_tool(self, tool: str) -> None:
        if self.active_tool != tool:
            self.active_tool = tool
            self.tool_changed.emit(tool)

    def set_color(self, rgba: tuple[int, int, int, int]) -> None:
        self.active_color = rgba
        self.color_changed.emit(rgba)

    def set_brush_size(self, size: int) -> None:
        self.brush_size = size
        self.brush_size_changed.emit(size)

    def set_layer(self, layer: str) -> None:
        if self.active_layer != layer:
            self.active_layer = layer
            self.layer_changed.emit(layer)


class ArmorMiniSelector(QWidget):
    """Clickable mini armor silhouette used to toggle armor-piece visibility."""
    part_toggled = Signal(str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode: str = "armor"  # "armor" | "base"
        self._visible: dict[str, bool] = {
            "helmet": True,
            "chest": True,
            "head": True,
            "body": True,
            "l_arm": True,
            "r_arm": True,
            "l_leg": True,
            "r_leg": True,
            "l_boot": True,
            "r_boot": True,
        }
        self.setFixedSize(98, 84)
        self.setToolTip("Click armor parts to show/hide")

    def set_mode(self, mode: str) -> None:
        self._mode = mode if mode in ("armor", "base") else "armor"
        self.update()

    def _hit_regions(self) -> list[tuple[QRect, str]]:
        if self._mode == "base":
            return [
                (QRect(35, 2, 28, 16), "head"),
                (QRect(34, 22, 30, 21), "body"),
                (QRect(18, 23, 14, 24), "l_arm"),
                (QRect(66, 23, 14, 24), "r_arm"),
                (QRect(35, 47, 12, 33), "l_leg"),
                (QRect(51, 47, 12, 33), "r_leg"),
            ]
        # Split left/right limbs so each side can be toggled independently.
        return [
            (QRect(35, 2, 28, 16), "helmet"),
            (QRect(34, 22, 30, 21), "chest"),
            (QRect(18, 23, 14, 24), "l_arm"),
            (QRect(66, 23, 14, 24), "r_arm"),
            (QRect(35, 47, 12, 23), "l_leg"),
            (QRect(51, 47, 12, 23), "r_leg"),
            (QRect(35, 70, 12, 10), "l_boot"),
            (QRect(51, 70, 12, 10), "r_boot"),
        ]

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position().toPoint()
        for rect, group in self._hit_regions():
            if rect.contains(pos):
                new_value = not self._visible[group]
                self._visible[group] = new_value
                self.part_toggled.emit(group, new_value)
                self.update()
                return

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        p.fillRect(self.rect(), QColor(40, 44, 54))
        p.setPen(QPen(QColor(85, 92, 107)))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        on_fill = QColor(70, 208, 214)
        off_fill = QColor(68, 76, 89)
        on_edge = QColor(0, 116, 121)
        off_edge = QColor(36, 41, 48)

        def _draw_piece(rect: QRect, key: str) -> None:
            is_on = self._visible[key]
            p.setBrush(on_fill if is_on else off_fill)
            p.setPen(QPen(on_edge if is_on else off_edge))
            p.drawRect(rect)
            if not is_on:
                p.setPen(QPen(QColor(180, 188, 200)))
                p.drawLine(rect.left(), rect.top(), rect.right(), rect.bottom())
                p.drawLine(rect.right(), rect.top(), rect.left(), rect.bottom())

        if self._mode == "base":
            _draw_piece(QRect(35, 2, 28, 16), "head")
            _draw_piece(QRect(34, 22, 30, 21), "body")
            _draw_piece(QRect(18, 23, 14, 24), "l_arm")
            _draw_piece(QRect(66, 23, 14, 24), "r_arm")
            _draw_piece(QRect(35, 47, 12, 33), "l_leg")
            _draw_piece(QRect(51, 47, 12, 33), "r_leg")
        else:
            _draw_piece(QRect(35, 2, 28, 16), "helmet")
            _draw_piece(QRect(34, 22, 30, 21), "chest")
            _draw_piece(QRect(18, 23, 14, 24), "l_arm")
            _draw_piece(QRect(66, 23, 14, 24), "r_arm")
            _draw_piece(QRect(35, 47, 12, 23), "l_leg")
            _draw_piece(QRect(51, 47, 12, 23), "r_leg")
            _draw_piece(QRect(35, 70, 12, 10), "l_boot")
            _draw_piece(QRect(51, 70, 12, 10), "r_boot")


# ---------------------------------------------------------------------------
# ToolPanel: owner of ToolState + factory for the two sub-widgets
# ---------------------------------------------------------------------------

class ToolPanel(QWidget):
    """Invisible container that owns ToolState and builds the two sub-widgets."""
    armor_part_visibility_changed = Signal(str, bool)   # armor part key, visible
    base_part_visibility_changed = Signal(str, bool)    # base part key, visible
    spread_out_mode_changed = Signal(bool)
    pose_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.tool_state = ToolState(self)
        self._recent_colors: list[tuple[int, int, int, int]] = []
        self._recent_buttons: list[QPushButton] = []
        self._tool_buttons: dict[str, QPushButton] = {}
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)

        # Build the two sub-widgets eagerly so main_window can place them
        self._tool_strip  = self._build_tool_strip()
        self._color_panel = self._build_color_panel()

        # Sync picker when color changes from outside (e.g. dropper)
        self.tool_state.color_changed.connect(self._on_state_color_changed)
        self.tool_state.layer_changed.connect(self._on_state_layer_changed)
        self._update_piece_selector_mode(self.tool_state.active_layer)

    # ------------------------------------------------------------------
    # Public accessors for main_window layout
    # ------------------------------------------------------------------

    def tool_strip(self) -> QWidget:
        """Horizontal strip: layer selector | tools | brush size."""
        return self._tool_strip

    def color_panel(self) -> QWidget:
        """Right-side panel: color picker + recent colors."""
        return self._color_panel

    # ------------------------------------------------------------------
    # Sub-widget builders
    # ------------------------------------------------------------------

    def _build_tool_strip(self) -> QWidget:
        """Compact horizontal bar that sits below the UV editor."""
        w = QWidget()
        w.setFixedHeight(112)
        # Keep full tool controls visible; parent scroll area handles overflow.
        w.setMinimumWidth(1020)
        w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(w)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(10)

        # ── Layer selector ─────────────────────────────────────────────
        layer_w = QWidget()
        layer_w.setFixedWidth(150)
        lv = QVBoxLayout(layer_w)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(3)
        lv.addWidget(QLabel("Paint layer:"))
        self._layer_combo = QComboBox()
        self._layer_combo.addItem("Base skin",     "base")
        self._layer_combo.addItem("Armor overlay", "armor")
        self._layer_combo.currentIndexChanged.connect(self._on_layer_changed)
        lv.addWidget(self._layer_combo)
        lv.addStretch()
        layout.addWidget(layer_w)
        layout.addWidget(self._vsep())

        # ── Tool buttons (2 rows of 4 / 3) ────────────────────────────
        tool_w = QWidget()
        tool_w.setMinimumWidth(330)
        tv = QVBoxLayout(tool_w)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(3)
        tv.addWidget(QLabel("Tool:"))

        row1 = QHBoxLayout()
        row1.setSpacing(2)
        row2 = QHBoxLayout()
        row2.setSpacing(2)

        row1_tools = [
            ("Brush",     "brush",        "Paint pixels freehand"),
            ("Eraser",    "eraser",       "Erase pixels"),
            ("Fill",      "fill",         "Flood-fill a region"),
            ("Dropper",   "dropper",      "Pick a color from the canvas"),
        ]
        row2_tools = [
            ("Line",      "line",         "Draw a straight line"),
            ("Rect",      "rect_outline", "Draw a rectangle outline"),
            ("Rect Fill", "rect_filled",  "Draw a filled rectangle"),
        ]

        for label, name, tip in row1_tools:
            row1.addWidget(self._make_tool_btn(label, name, tip))
        for label, name, tip in row2_tools:
            row2.addWidget(self._make_tool_btn(label, name, tip))

        self._tool_buttons["brush"].setChecked(True)
        self._tool_group.buttonClicked.connect(self._on_tool_clicked)

        tv.addLayout(row1)
        tv.addLayout(row2)
        layout.addWidget(tool_w)
        layout.addWidget(self._vsep())

        # ── Brush size ─────────────────────────────────────────────────
        brush_w = QWidget()
        brush_w.setFixedWidth(170)
        bv = QVBoxLayout(brush_w)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(3)
        self._brush_label = QLabel("Brush size: 1")
        bv.addWidget(self._brush_label)
        self._brush_slider = QSlider(Qt.Orientation.Horizontal)
        self._brush_slider.setRange(1, 16)
        self._brush_slider.setValue(1)
        self._brush_slider.valueChanged.connect(self._on_brush_changed)
        bv.addWidget(self._brush_slider)
        bv.addStretch()
        layout.addWidget(brush_w)
        layout.addWidget(self._vsep())

        # ── Armor piece visibility ────────────────────────────────────
        armor_w = QWidget()
        armor_w.setFixedWidth(150)
        av = QVBoxLayout(armor_w)
        av.setContentsMargins(0, 0, 0, 0)
        av.setSpacing(3)
        self._parts_label = QLabel("Armor pieces:")
        av.addWidget(self._parts_label)
        self._armor_selector = ArmorMiniSelector()
        self._armor_selector.part_toggled.connect(self._on_part_toggled)
        av.addWidget(self._armor_selector, alignment=Qt.AlignmentFlag.AlignLeft)
        av.addStretch()
        layout.addWidget(armor_w)
        layout.addWidget(self._vsep())

        # ── View mode ─────────────────────────────────────────────────
        mode_w = QWidget()
        mode_w.setFixedWidth(210)
        mv = QVBoxLayout(mode_w)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(3)
        mv.addWidget(QLabel("View mode:"))
        self._spread_out_check = QCheckBox("Spread out mode")
        self._spread_out_check.setChecked(False)
        self._spread_out_check.toggled.connect(self.spread_out_mode_changed.emit)
        mv.addWidget(self._spread_out_check)
        mv.addWidget(QLabel("Pose:"))
        self._pose_combo = QComboBox()
        self._pose_combo.addItem("Stand", "stand")
        self._pose_combo.addItem("Walk", "walk")
        self._pose_combo.addItem("Run", "run")
        self._pose_combo.addItem("Fly", "fly")
        self._pose_combo.currentIndexChanged.connect(
            lambda _i: self.pose_changed.emit(self._pose_combo.currentData())
        )
        mv.addWidget(self._pose_combo)
        mv.addStretch()
        layout.addWidget(mode_w)

        layout.addStretch()
        return w

    def _build_color_panel(self) -> QWidget:
        """Right-side fixed-width panel: color picker + recent colors."""
        w = QWidget()
        w.setFixedWidth(220)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        self._color_picker = ColorPickerWidget()
        self._color_picker.color_selected.connect(self._on_color_picked)
        layout.addWidget(self._color_picker)

        layout.addWidget(self._hsep())
        layout.addWidget(QLabel("Recent colors:"))
        layout.addWidget(self._build_recent_colors())
        layout.addStretch()
        return w

    def _make_tool_btn(self, label: str, name: str, tip: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setProperty("tool_name", name)
        btn.setToolTip(tip)
        btn.setFixedWidth(70)
        self._tool_group.addButton(btn)
        self._tool_buttons[name] = btn
        return btn

    def _build_recent_colors(self) -> QWidget:
        w = QWidget()
        grid = QHBoxLayout(w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(3)
        for _ in range(10):
            btn = QPushButton()
            btn.setFixedSize(18, 18)
            btn.setStyleSheet("background-color: #2b2b2b; border: 1px solid #555;")
            btn.clicked.connect(self._on_recent_clicked)
            self._recent_buttons.append(btn)
            grid.addWidget(btn)
        return w

    def _vsep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        return sep

    def _hsep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        return sep

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_layer_changed(self, index: int) -> None:
        self.tool_state.set_layer(self._layer_combo.currentData())
        self._update_piece_selector_mode(self.tool_state.active_layer)

    def _on_state_layer_changed(self, layer: str) -> None:
        self._update_piece_selector_mode(layer)

    def _update_piece_selector_mode(self, layer: str) -> None:
        if layer == "base":
            self._parts_label.setText("Body pieces:")
            self._armor_selector.set_mode("base")
        else:
            self._parts_label.setText("Armor pieces:")
            self._armor_selector.set_mode("armor")

    def _on_part_toggled(self, key: str, visible: bool) -> None:
        if self.tool_state.active_layer == "base":
            self.base_part_visibility_changed.emit(key, visible)
        else:
            self.armor_part_visibility_changed.emit(key, visible)

    def _on_tool_clicked(self, btn: QPushButton) -> None:
        self.tool_state.set_tool(btn.property("tool_name"))

    def _on_brush_changed(self, value: int) -> None:
        self._brush_label.setText(f"Brush size: {value}")
        self.tool_state.set_brush_size(value)

    def _on_color_picked(self, rgba: tuple) -> None:
        self.tool_state.set_color(rgba)
        self._push_recent(rgba)

    def _on_state_color_changed(self, rgba: tuple) -> None:
        self._color_picker.set_color(rgba)

    def _on_recent_clicked(self) -> None:
        btn = self.sender()
        data = btn.property("rgba")
        if data:
            self.tool_state.set_color(data)

    def _push_recent(self, rgba: tuple) -> None:
        if rgba in self._recent_colors:
            return
        self._recent_colors.insert(0, rgba)
        self._recent_colors = self._recent_colors[:10]
        for btn, color in zip(self._recent_buttons, self._recent_colors):
            r, g, b, a = color
            btn.setStyleSheet(
                f"background-color: rgba({r},{g},{b},{a}); border: 1px solid #888;"
            )
            btn.setProperty("rgba", color)

    # ------------------------------------------------------------------
    # External API
    # ------------------------------------------------------------------

    def receive_dropper_color(self, rgba: tuple) -> None:
        self.tool_state.set_color(rgba)
        self._color_picker.set_color(rgba)
        self._push_recent(rgba)

    def sync_tool_button(self, tool: str) -> None:
        btn = self._tool_buttons.get(tool)
        if btn and not btn.isChecked():
            btn.setChecked(True)

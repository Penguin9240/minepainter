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

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QButtonGroup, QSlider,
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


# ---------------------------------------------------------------------------
# ToolPanel: owner of ToolState + factory for the two sub-widgets
# ---------------------------------------------------------------------------

class ToolPanel(QWidget):
    """Invisible container that owns ToolState and builds the two sub-widgets."""

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
        w.setFixedHeight(90)
        w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(w)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(10)

        # ── Layer selector ─────────────────────────────────────────────
        layer_w = QWidget()
        layer_w.setFixedWidth(130)
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
        tv = QVBoxLayout(tool_w)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(3)
        tv.addWidget(QLabel("Tool:"))

        row1 = QHBoxLayout()
        row1.setSpacing(3)
        row2 = QHBoxLayout()
        row2.setSpacing(3)

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
        brush_w.setFixedWidth(160)
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

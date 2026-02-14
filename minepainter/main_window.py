"""
MainWindow: top-level Qt window.

Layout:
    QMainWindow
    ├── AppToolBar         (top)
    ├── QSplitter          (central, horizontal)
    │   ├── UVEditorWidget (left  — 2D pixel grid for painting)
    │   ├── ViewportWidget (centre — 3D OpenGL preview)
    │   └── ToolPanel      (right — tools, color picker)
    └── QStatusBar         (bottom)
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QFileDialog, QMessageBox, QStatusBar,
    QWidget, QVBoxLayout,
)

from minepainter.document import SkinDocument
from minepainter.home_screen import register_skin_path
from minepainter.toolbar import AppToolBar
from minepainter.viewport.viewport_widget import ViewportWidget
from minepainter.uv_editor.uv_editor_widget import UVEditorWidget
from minepainter.tools.tool_panel import ToolPanel


class MainWindow(QMainWindow):
    home_requested = Signal()   # emitted when the user clicks ⌂ Home

    def __init__(self, start_layer: str = "base") -> None:
        super().__init__()
        self.setWindowTitle("MinePainter")

        self.document = SkinDocument()

        # --- Toolbar ---
        self._toolbar = AppToolBar(self)
        self.addToolBar(self._toolbar)

        # --- Tool panel (must exist before UV editor, which needs ToolState) ---
        self._tool_panel = ToolPanel()

        # --- UV editor ---
        self._uv_editor = UVEditorWidget(
            self.document, self._tool_panel.tool_state
        )

        # --- 3D viewport (needs tool_state for painting) ---
        self._viewport = ViewportWidget(self.document, self._tool_panel.tool_state)

        # --- Layout ---
        # Left column: UV editor on top, tool strip below it
        left_col = QWidget()
        left_vbox = QVBoxLayout(left_col)
        left_vbox.setContentsMargins(0, 0, 0, 0)
        left_vbox.setSpacing(0)
        left_vbox.addWidget(self._uv_editor, stretch=1)
        left_vbox.addWidget(self._tool_panel.tool_strip(), stretch=0)

        # Main horizontal splitter: left col | viewport | color panel
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_col)
        splitter.addWidget(self._viewport)
        splitter.addWidget(self._tool_panel.color_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 0)
        self.setCentralWidget(splitter)

        # --- Status bar ---
        self._status = QStatusBar()
        self.setStatusBar(self._status)

        # --- Pre-select the layer the user chose on the home screen ---
        if start_layer == "armor":
            # Switch tool state to armor layer
            self._tool_panel.tool_state.set_layer("armor")
            # Also update the combo box so the UI is consistent
            combo = self._tool_panel._layer_combo
            idx = combo.findData("armor")
            if idx >= 0:
                combo.setCurrentIndex(idx)
            # Show the armor stand in the 3D viewport
            self._viewport.set_show_stand(True)
            # Fill armor with grey default so the stand looks clothed from the start
            self.document.armor_image = self.document._blank_white_armor()
            # Hide the base skin layer BEFORE the GL context initializes so the
            # renderer picks up base_visible=False from the document on first paint.
            # Also uncheck the toolbar toggle so the UI is consistent.
            self.document.base_visible = False
            self._toolbar.set_base_visible(False)
            self._status.showMessage("Ready — Armor overlay selected.")
        else:
            self._status.showMessage("Ready — New skin created.")

        # --- Wire signals ---
        self._connect_signals()

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        tb = self._toolbar
        tb.home_requested.connect(self._on_home)
        tb.new_requested.connect(self._on_new)
        tb.open_requested.connect(self._on_open)
        tb.save_requested.connect(self._on_save)
        tb.save_as_requested.connect(self._on_save_as)
        tb.reset_requested.connect(self._on_reset)
        tb.undo_requested.connect(self._on_undo)
        tb.base_visibility_toggled.connect(
            lambda v: self.document.set_layer_visible("base", v)
        )
        tb.armor_visibility_toggled.connect(
            lambda v: self.document.set_layer_visible("armor", v)
        )
        tb.skin_type_changed.connect(self._on_skin_type_changed)

        self.document.dirty_changed.connect(self._update_title)

        # Dropper result from UV editor → tool panel
        self._uv_editor.color_picked.connect(
            self._tool_panel.receive_dropper_color
        )
        # Sync tool button when dropper switches back to brush
        self._tool_panel.tool_state.tool_changed.connect(
            self._tool_panel.sync_tool_button
        )

    # ------------------------------------------------------------------
    # Toolbar action handlers
    # ------------------------------------------------------------------

    def _on_home(self) -> None:
        """Return to the home screen (prompts if there are unsaved changes)."""
        if self.document.dirty:
            answer = QMessageBox.question(
                self, "Unsaved changes",
                "Current skin has unsaved changes. Go to home screen anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.home_requested.emit()

    def _on_new(self) -> None:
        if self.document.dirty:
            answer = QMessageBox.question(
                self, "Unsaved changes",
                "Current skin has unsaved changes. Discard and create new skin?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.document.new()
        self._status.showMessage("New skin created.")
        self._update_title(False)

    def _on_reset(self) -> None:
        """Reset the base skin to solid white, keep the armor layer."""
        from minepainter.document import SkinDocument
        self.document.push_undo_snapshot("base")
        self.document.base_image = SkinDocument._blank_white_skin()
        self.document.layer_replaced.emit("base")
        self.document._mark_dirty()
        self._status.showMessage("Skin reset to white.")

    def _on_undo(self) -> None:
        """Undo the last paint stroke."""
        undone = self.document.undo()
        if undone:
            self._status.showMessage("Undone.")
        else:
            self._status.showMessage("Nothing to undo.")

    def _on_open(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open Skin PNG", "", "PNG files (*.png)"
        )
        if not path_str:
            return
        try:
            self.document.load_from_file(Path(path_str))
            register_skin_path(Path(path_str))
            self._status.showMessage(f"Opened: {path_str}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open file:\n{e}")

    def _on_save(self) -> None:
        if self.document.filepath is None:
            self._on_save_as()
            return
        try:
            self.document.save_to_file(self.document.filepath)
            register_skin_path(self.document.filepath)
            self._status.showMessage(f"Saved: {self.document.filepath}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")

    def _on_save_as(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Save Skin PNG", "", "PNG files (*.png)"
        )
        if not path_str:
            return
        if not path_str.lower().endswith(".png"):
            path_str += ".png"
        try:
            self.document.save_to_file(Path(path_str))
            register_skin_path(Path(path_str))
            self._status.showMessage(f"Saved: {path_str}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")

    def _on_skin_type_changed(self, skin_type: str) -> None:
        self.document.skin_type = skin_type
        self._viewport.rebuild_meshes(skin_type)
        self._status.showMessage(f"Switched to {skin_type.capitalize()} model.")

    # ------------------------------------------------------------------
    # Title bar
    # ------------------------------------------------------------------

    def _update_title(self, dirty: bool) -> None:
        name = (
            self.document.filepath.name
            if self.document.filepath
            else "Untitled"
        )
        marker = " *" if dirty else ""
        self.setWindowTitle(f"MinePainter — {name}{marker}")

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
    QApplication, QDialog, QDialogButtonBox, QFormLayout,
    QRadioButton, QButtonGroup, QHBoxLayout, QLineEdit, QCheckBox,
)

from minepainter.document import SkinDocument
from minepainter.app_settings import (
    load_theme,
    save_theme,
    load_openai_api_key,
    save_openai_api_key,
    load_debug_mode,
    save_debug_mode,
    THEME_DARK,
    THEME_LIGHT,
)
from minepainter.home_screen import register_skin_path
from minepainter.toolbar import AppToolBar
from minepainter.viewport.viewport_widget import ViewportWidget
from minepainter.uv_editor.uv_editor_widget import UVEditorWidget
from minepainter.tools.ai_chat_panel import AIChatPanel
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
        self._ai_panel = AIChatPanel(self.document)

        # --- Layout ---
        # Left column: UV editor on top, tool strip below it
        left_col = QWidget()
        left_col.setFixedWidth(360)
        left_vbox = QVBoxLayout(left_col)
        left_vbox.setContentsMargins(0, 0, 0, 0)
        left_vbox.setSpacing(0)
        self._uv_editor.setFixedSize(336, 336)
        self._uv_editor.set_corner_locked_view(True)
        left_vbox.addWidget(
            self._uv_editor,
            stretch=0,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )
        left_vbox.addWidget(
            self._tool_panel.tool_strip(),
            stretch=0,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )
        left_vbox.addStretch(1)

        # Main horizontal splitter: left col | viewport | ai chat | color panel
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_col)
        splitter.addWidget(self._viewport)
        splitter.addWidget(self._ai_panel)
        splitter.addWidget(self._tool_panel.color_panel())
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(0)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setStretchFactor(3, 0)
        splitter.setSizes([420, 880, 360, 240])
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
            # Keep a clean "invisible player" preview (no stand rods/base)
            self._viewport.set_show_stand(False)
            # Fill armor with a detailed diamond preset so armor mode starts styled
            self.document.armor_image = self.document._blank_white_armor("diamond")
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
        tb.open_armor_main_requested.connect(self._on_open_armor_main)
        tb.open_armor_leggings_requested.connect(self._on_open_armor_leggings)
        tb.save_requested.connect(self._on_save)
        tb.save_as_requested.connect(self._on_save_as)
        tb.reset_requested.connect(self._on_reset)
        tb.undo_requested.connect(self._on_undo)
        tb.redo_requested.connect(self._on_redo)
        tb.settings_requested.connect(self._on_settings)
        tb.base_visibility_toggled.connect(
            lambda v: self.document.set_layer_visible("base", v)
        )
        tb.armor_visibility_toggled.connect(
            lambda v: self.document.set_layer_visible("armor", v)
        )
        tb.skin_type_changed.connect(self._on_skin_type_changed)

        self.document.dirty_changed.connect(self._update_title)
        self._tool_panel.armor_part_visibility_changed.connect(
            self._viewport.set_armor_part_visible
        )
        self._tool_panel.base_part_visibility_changed.connect(
            self._viewport.set_base_part_visible
        )
        self._tool_panel.spread_out_mode_changed.connect(
            self._viewport.set_spread_out_mode
        )
        self._tool_panel.pose_changed.connect(
            self._viewport.set_pose
        )

        # Dropper result from UV editor → tool panel
        self._uv_editor.color_picked.connect(
            self._tool_panel.receive_dropper_color
        )
        # Sync tool button when dropper switches back to brush
        self._tool_panel.tool_state.tool_changed.connect(
            self._tool_panel.sync_tool_button
        )
        self._ai_panel.apply_armor_state_requested.connect(self._on_ai_apply_armor_state)
        self._ai_panel.status_message.connect(self._status.showMessage)

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

    def _on_redo(self) -> None:
        """Redo the most recently undone paint stroke."""
        redone = self.document.redo()
        if redone:
            self._status.showMessage("Redone.")
        else:
            self._status.showMessage("Nothing to redo.")

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

    def _on_open_armor_main(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open Armor Main PNG (64x32)", "", "PNG files (*.png)"
        )
        if not path_str:
            return
        try:
            self.document.load_armor_main_file(Path(path_str))
            self._tool_panel.tool_state.set_layer("armor")
            self._status.showMessage(f"Loaded armor main: {path_str}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open armor main file:\n{e}")

    def _on_open_armor_leggings(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open Leggings PNG (64x32)", "", "PNG files (*.png)"
        )
        if not path_str:
            return
        try:
            self.document.load_armor_leggings_file(Path(path_str))
            self._tool_panel.tool_state.set_layer("armor")
            self._status.showMessage(f"Loaded leggings: {path_str}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open leggings file:\n{e}")

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

    def _on_ai_apply_armor_state(self, armor_state_text: str) -> None:
        try:
            # Push undo so Ctrl+Z removes AI-applied armor updates.
            self.document.apply_armor_state_text(armor_state_text, push_undo=True)
            self._tool_panel.tool_state.set_layer("armor")
        except Exception as e:
            QMessageBox.critical(self, "AI Armor Error", f"Could not apply AI armor state:\n{e}")

    def _on_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.resize(460, 280)
        dialog.setMinimumSize(420, 240)
        layout = QFormLayout(dialog)

        current = load_theme()
        theme_row = QWidget(dialog)
        theme_row_layout = QHBoxLayout(theme_row)
        theme_row_layout.setContentsMargins(0, 0, 0, 0)
        theme_row_layout.setSpacing(12)
        theme_dark = QRadioButton("Dark", theme_row)
        theme_light = QRadioButton("Light", theme_row)
        theme_group = QButtonGroup(theme_row)
        theme_group.addButton(theme_dark)
        theme_group.addButton(theme_light)
        if current == THEME_LIGHT:
            theme_light.setChecked(True)
        else:
            theme_dark.setChecked(True)
        theme_row_layout.addWidget(theme_dark)
        theme_row_layout.addWidget(theme_light)
        theme_row_layout.addStretch(1)
        layout.addRow("Theme:", theme_row)

        api_key_input = QLineEdit(dialog)
        api_key_input.setPlaceholderText("sk-...")
        api_key_input.setText(load_openai_api_key())
        api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("OpenAI API key:", api_key_input)

        debug_check = QCheckBox("Enable debug mode (AI logs to terminal)", dialog)
        debug_check.setChecked(load_debug_mode())
        layout.addRow("Debug mode:", debug_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        layout.addRow(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        theme = THEME_LIGHT if theme_light.isChecked() else THEME_DARK
        save_theme(theme)
        save_openai_api_key(api_key_input.text())
        save_debug_mode(debug_check.isChecked())

        app = QApplication.instance()
        if app is None:
            return
        dark_css = app.property("mp_dark_stylesheet")
        light_css = app.property("mp_light_stylesheet")
        if theme == THEME_LIGHT:
            app.setStyleSheet(str(light_css) if light_css is not None else "")
            self._status.showMessage("Settings saved: Light mode")
        else:
            app.setStyleSheet(str(dark_css) if dark_css is not None else "")
            self._status.showMessage("Settings saved: Dark mode")

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

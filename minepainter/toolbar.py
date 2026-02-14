"""
AppToolBar: the main window's top toolbar.

Actions: New, Open, Save, separator,
         Toggle base skin visibility (checkable),
         Toggle armor overlay visibility (checkable),
         separator, Skin type combo (Steve / Alex).
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QToolBar, QComboBox, QLabel
from PySide6.QtGui import QAction


class AppToolBar(QToolBar):
    new_requested          = Signal()
    open_requested         = Signal()
    open_armor_main_requested = Signal()
    open_armor_leggings_requested = Signal()
    save_requested         = Signal()
    save_as_requested      = Signal()
    reset_requested        = Signal()
    undo_requested         = Signal()
    settings_requested     = Signal()
    home_requested         = Signal()
    base_visibility_toggled  = Signal(bool)
    armor_visibility_toggled = Signal(bool)
    skin_type_changed        = Signal(str)   # "steve" | "alex"

    def __init__(self, parent=None) -> None:
        super().__init__("Main", parent)
        self.setMovable(False)

        self._act_home = QAction("⌂ Home", self)
        self._act_home.setToolTip("Return to the home screen")
        self._act_home.triggered.connect(self.home_requested)
        self.addAction(self._act_home)

        self.addSeparator()

        self._act_new = QAction("New", self)
        self._act_new.setShortcut("Ctrl+N")
        self._act_new.triggered.connect(self.new_requested)
        self.addAction(self._act_new)

        self._act_reset = QAction("Reset", self)
        self._act_reset.setToolTip("Reset the skin back to solid white")
        self._act_reset.triggered.connect(self.reset_requested)
        self.addAction(self._act_reset)

        self._act_undo = QAction("Undo", self)
        self._act_undo.setShortcut("Ctrl+Z")
        self._act_undo.setToolTip("Undo the last paint stroke (Ctrl+Z)")
        self._act_undo.triggered.connect(self.undo_requested)
        self.addAction(self._act_undo)

        self._act_open = QAction("Open…", self)
        self._act_open.setShortcut("Ctrl+O")
        self._act_open.triggered.connect(self.open_requested)
        self.addAction(self._act_open)

        self._act_open_armor_main = QAction("Open Armor Main…", self)
        self._act_open_armor_main.setToolTip("Load a 64x32 main armor file into armor rows 0..31")
        self._act_open_armor_main.triggered.connect(self.open_armor_main_requested)
        self.addAction(self._act_open_armor_main)

        self._act_open_armor_leggings = QAction("Open Leggings…", self)
        self._act_open_armor_leggings.setToolTip("Load a 64x32 leggings file into armor rows 32..63")
        self._act_open_armor_leggings.triggered.connect(self.open_armor_leggings_requested)
        self.addAction(self._act_open_armor_leggings)

        self._act_settings = QAction("Settings", self)
        self._act_settings.setToolTip("Open application settings")
        self._act_settings.triggered.connect(self.settings_requested)
        self.addAction(self._act_settings)

        self._act_save = QAction("Save", self)
        self._act_save.setShortcut("Ctrl+S")
        self._act_save.triggered.connect(self.save_requested)
        self.addAction(self._act_save)

        self.addSeparator()

        self._act_base = QAction("Base skin", self)
        self._act_base.setCheckable(True)
        self._act_base.setChecked(True)
        self._act_base.setToolTip("Show / hide the base skin layer")
        self._act_base.toggled.connect(self.base_visibility_toggled)
        self.addAction(self._act_base)

        self._act_armor = QAction("Armor overlay", self)
        self._act_armor.setCheckable(True)
        self._act_armor.setChecked(True)
        self._act_armor.setToolTip("Show / hide the armor overlay layer")
        self._act_armor.toggled.connect(self.armor_visibility_toggled)
        self.addAction(self._act_armor)

        self.addSeparator()

        self.addWidget(QLabel(" Skin type: "))
        self._skin_combo = QComboBox()
        self._skin_combo.addItem("Steve (4-wide arms)", "steve")
        self._skin_combo.addItem("Alex (3-wide arms)",  "alex")
        self._skin_combo.currentIndexChanged.connect(self._on_skin_type)
        self.addWidget(self._skin_combo)

    def _on_skin_type(self, _index: int) -> None:
        self.skin_type_changed.emit(self._skin_combo.currentData())

    def set_base_visible(self, visible: bool) -> None:
        self._act_base.setChecked(visible)

    def set_armor_visible(self, visible: bool) -> None:
        self._act_armor.setChecked(visible)

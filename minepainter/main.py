"""
MinePainter entry point.

Sets up the Qt application with an OpenGL 3.3 core-profile surface format,
then shows the main window.

Run with:
    uv run minepainter
  or:
    uv run python -m minepainter.main
"""
import sys

from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

from minepainter.main_window import MainWindow
from minepainter.home_screen import HomeScreen


_STYLESHEET = """
/* ------------------------------------------------------------------ */
/* Base — dark navy matching the home screen background                */
/* ------------------------------------------------------------------ */
QWidget {
    background-color: #12122a;
    color: #dde3f0;
    font-size: 12px;
}

/* ------------------------------------------------------------------ */
/* Main window chrome                                                  */
/* ------------------------------------------------------------------ */
QMainWindow {
    background-color: #0d0d20;
}
QSplitter::handle {
    background-color: #1e1e3a;
    width: 3px;
    height: 3px;
}

/* ------------------------------------------------------------------ */
/* Toolbar                                                             */
/* ------------------------------------------------------------------ */
QToolBar {
    background-color: #1a1a38;
    border-bottom: 1px solid #3a3a6a;
    spacing: 4px;
    padding: 2px 6px;
}
QToolBar QToolButton, QToolBar QPushButton {
    background-color: #252550;
    border: 1px solid #3a3a6a;
    border-radius: 4px;
    padding: 3px 10px;
    color: #dde3f0;
}
QToolBar QToolButton:checked, QToolBar QPushButton:checked {
    background-color: #3498db;
    color: #ffffff;
    border-color: #2176ae;
}
QToolBar QToolButton:hover, QToolBar QPushButton:hover {
    background-color: #2e2e60;
    border-color: #5555aa;
}
QToolBar QToolButton:pressed, QToolBar QPushButton:pressed {
    background-color: #1e1e48;
}
QToolBar::separator {
    background-color: #3a3a6a;
    width: 1px;
    margin: 4px 4px;
}

/* ------------------------------------------------------------------ */
/* Regular buttons (tool panel)                                        */
/* ------------------------------------------------------------------ */
QPushButton {
    background-color: #1e1e42;
    border: 1px solid #3a3a6a;
    border-radius: 4px;
    padding: 4px 12px;
    color: #dde3f0;
}
QPushButton:checked {
    background-color: #3498db;
    color: #ffffff;
    border-color: #2176ae;
}
QPushButton:hover {
    background-color: #2a2a58;
    border-color: #5555aa;
}
QPushButton:pressed {
    background-color: #161630;
}

/* ------------------------------------------------------------------ */
/* Combo box                                                           */
/* ------------------------------------------------------------------ */
QComboBox {
    background-color: #1e1e42;
    border: 1px solid #3a3a6a;
    border-radius: 4px;
    padding: 3px 8px;
    color: #dde3f0;
}
QComboBox::drop-down {
    border: none;
}
QComboBox QAbstractItemView {
    background-color: #1e1e42;
    border: 1px solid #3a3a6a;
    selection-background-color: #3498db;
    selection-color: #ffffff;
    color: #dde3f0;
}

/* ------------------------------------------------------------------ */
/* Slider                                                              */
/* ------------------------------------------------------------------ */
QSlider::groove:horizontal {
    height: 4px;
    background: #2a2a52;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #3498db;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #3498db;
    border: 2px solid #2176ae;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background: #5bb8f5;
}

/* ------------------------------------------------------------------ */
/* Status bar                                                          */
/* ------------------------------------------------------------------ */
QStatusBar {
    background-color: #1a1a38;
    color: #8899bb;
    border-top: 1px solid #3a3a6a;
}

/* ------------------------------------------------------------------ */
/* Labels                                                              */
/* ------------------------------------------------------------------ */
QLabel {
    background-color: transparent;
    color: #dde3f0;
}

/* ------------------------------------------------------------------ */
/* Separators                                                          */
/* ------------------------------------------------------------------ */
QFrame[frameShape="4"], QFrame[frameShape="5"] {
    color: #2e2e5e;
}

/* ------------------------------------------------------------------ */
/* Message / dialog boxes                                              */
/* ------------------------------------------------------------------ */
QMessageBox {
    background-color: #12122a;
    color: #dde3f0;
}
QMessageBox QPushButton {
    min-width: 72px;
}

/* ------------------------------------------------------------------ */
/* File dialogs                                                        */
/* ------------------------------------------------------------------ */
QFileDialog {
    background-color: #12122a;
    color: #dde3f0;
}
QFileDialog QListView, QFileDialog QTreeView {
    background-color: #1a1a38;
    color: #dde3f0;
    border: 1px solid #3a3a6a;
}
QFileDialog QLineEdit {
    background-color: #1e1e42;
    color: #dde3f0;
    border: 1px solid #3a3a6a;
    border-radius: 3px;
    padding: 2px 6px;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #1a1a38;
    border: none;
    width: 8px;
    height: 8px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #3a3a6a;
    border-radius: 4px;
    min-height: 20px;
    min-width: 20px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: #5555aa;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0; height: 0;
}
"""


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("MinePainter")
    app.setOrganizationName("MinePainter")
    app.setStyleSheet(_STYLESHEET)

    # Request an OpenGL 3.3 core-profile context for all QOpenGLWidgets.
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setSamples(0)   # No multisampling — we want crisp pixel art edges
    QSurfaceFormat.setDefaultFormat(fmt)

    # -----------------------------------------------------------------
    # Show the home screen first; open the editor when a mode is chosen.
    # -----------------------------------------------------------------
    home = HomeScreen()
    home.setWindowTitle("MinePainter")
    home.resize(860, 700)
    home.setMinimumSize(700, 620)

    _window:    list[MainWindow] = []   # mutable container so the closure can replace the window
    _normal_geo: list = []              # stores the non-fullscreen geometry

    def _on_home_requested() -> None:
        """Close the current editor and bring the home screen back."""
        if _window:
            w = _window.pop()
            # Use the saved normal (non-fullscreen) geometry, not the current one,
            # so that going fullscreen → Home doesn't blow up the window size.
            geo = _normal_geo.pop() if _normal_geo else w.geometry()
            w.close()
            home.setGeometry(geo)
        home.show()

    def _launch(start_layer: str) -> None:
        # Capture the normal (non-fullscreen) geometry of the home screen
        geo = home.normalGeometry() if home.isMaximized() or home.isFullScreen() \
              else home.geometry()
        home.hide()
        w = MainWindow(start_layer=start_layer)
        w.setGeometry(geo)
        _normal_geo.clear()
        _normal_geo.append(geo)   # remember it for when we return home

        # Keep _normal_geo updated whenever the window moves/resizes while not fullscreen
        def _track_geo() -> None:
            if not (w.isMaximized() or w.isFullScreen()):
                if _normal_geo:
                    _normal_geo[0] = w.geometry()

        # QMainWindow emits no dedicated "normalGeometry changed" signal, so use moveEvent
        # and resizeEvent via an event filter workaround — simplest: poll on a short timer
        from PySide6.QtCore import QTimer
        _geo_timer = QTimer(w)
        _geo_timer.timeout.connect(_track_geo)
        _geo_timer.start(500)   # check every 500 ms

        w.home_requested.connect(_on_home_requested)
        _window.append(w)
        w.show()

    def _launch_with_file(path_str: str) -> None:
        """Open the editor and immediately load a skin from path_str."""
        geo = home.normalGeometry() if home.isMaximized() or home.isFullScreen() \
              else home.geometry()
        home.hide()
        w = MainWindow(start_layer="base")
        w.setGeometry(geo)
        _normal_geo.clear()
        _normal_geo.append(geo)

        # Load the skin file
        from pathlib import Path
        from minepainter.home_screen import register_skin_path
        try:
            w.document.load_from_file(Path(path_str))
            register_skin_path(Path(path_str))
            w._status.showMessage(f"Opened: {path_str}")
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(w, "Error", f"Could not open file:\n{e}")

        def _track_geo() -> None:
            if not (w.isMaximized() or w.isFullScreen()):
                if _normal_geo:
                    _normal_geo[0] = w.geometry()

        from PySide6.QtCore import QTimer
        _geo_timer = QTimer(w)
        _geo_timer.timeout.connect(_track_geo)
        _geo_timer.start(500)

        w.home_requested.connect(_on_home_requested)
        _window.append(w)
        w.show()

    home.skin_chosen.connect(lambda: _launch("base"))
    home.armor_chosen.connect(lambda: _launch("armor"))
    home.open_skin_chosen.connect(_launch_with_file)

    home.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

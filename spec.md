

## Modules


### 1. `document.py`


*   **SkinDocument**: This class is the central data model. It holds the skin and armor image data as NumPy arrays. It uses Qt signals to communicate changes to the 2D UV editor and the 3D viewport.
*   Provides methods for pixel access, layer visibility control, file I/O, and undo support.


### 2. `home_screen.py`


*   **HomeScreen**: Defines the splash screen/landing page of the application.
*   Allows users to select between painting a skin or painting armor.
*   Includes a gallery of recent skins.


### 3. `io/skin_io.py`


*   **SkinIO**: Handles loading and saving Minecraft skin PNG files.
*   Includes legacy 64x32 skin conversion to modern 64x64 format and skin type detection (Steve/Alex).


### 4. `toolbar.py`


*   **AppToolBar**: Defines the main application toolbar with actions for creating new skins, opening existing ones, saving, undo/redo, and toggling layer visibility.


### 5. `tools/`


*   **tool_panel.py**: Defines the `ToolPanel` widget, which contains the tool selection buttons, color picker, and brush size controls.
*   **color_picker.py**: Defines the `ColorPickerWidget` for selecting colors.


### 6. `uv_editor/uv_editor_widget.py`


*   **UVEditorWidget**: Implements the 2D UV editor where users can paint directly on the skin.


### 7. `viewport/`


*   **viewport_widget.py**: Implements the `ViewportWidget`, an OpenGL widget that renders the 3D Minecraft character model.
*   **mesh_builder.py**: Contains functions to build the 3D character meshes.
*   **renderer.py**:  Handles the OpenGL rendering of the 3D model.


### 8. `skin_constants.py`


*   Defines constants related to skin UV mapping, such as the coordinates of different body parts on the skin texture.


### 9. `main_window.py`


*   **MainWindow**: Defines the top-level application window, which contains the toolbar, UV editor, viewport, and tool panel.


### 10. `main.py`


*   The application's entry point.


## Workflow


1.  The application starts with the `HomeScreen`, where the user can choose to paint a skin or armor, or open a recent skin.
2.  Upon choosing a mode, the `MainWindow` is opened, containing the `UVEditorWidget`, `ViewportWidget`, and `ToolPanel`.
3.  The `SkinDocument` stores the skin and armor data and emits signals when changes occur.
4.  The `UVEditorWidget` and `ViewportWidget` observe the `SkinDocument` and update their views accordingly.
5.  Users can paint on the 2D UV editor, and the changes are reflected in the 3D viewport in real-time.
6.  The `ToolPanel` provides tools for selecting colors, brush sizes, and different painting tools.
7.  The `AppToolBar` provides actions for file I/O, undo/redo, and layer visibility.


## Key Classes and Data Structures


*   **SkinDocument**: Manages skin and armor data (NumPy arrays) and provides signals for UI updates.
*   **ToolState**:  A shared QObject that manages the current tool, color, brush size, and active layer.
*   **NumPy arrays**: Used to store the pixel data of the skin and armor textures.
*   **Qt Signals/Slots**: Used for communication between different parts of the application, enabling real-time updates.

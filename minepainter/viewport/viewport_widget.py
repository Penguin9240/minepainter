"""
ViewportWidget: a QOpenGLWidget that renders the 3D Minecraft character model.

Mouse controls:
  Left click / drag  → paint on the 3D model (using the active tool)
  Right drag         → orbit (yaw/pitch)
  Scroll             → zoom FOV
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, QPoint
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtGui import QMouseEvent, QWheelEvent

from minepainter.document import SkinDocument
from minepainter.viewport import mesh_builder
from minepainter.viewport.mesh_builder import (
    build_stand_meshes,
    build_stand_body_meshes,
)
from minepainter.viewport.renderer import ModelRenderer
from minepainter.viewport.math_utils import look_at, perspective
from minepainter.viewport.ray_cast import ray_from_screen, hit_mesh
from minepainter.uv_editor.paint_engine import PaintEngine
from minepainter.skin_constants import BASE_PARTS


class ViewportWidget(QOpenGLWidget):
    def __init__(self, document: SkinDocument, tool_state, parent=None) -> None:
        super().__init__(parent)
        self.document = document
        self.tool_state = tool_state
        self.renderer: Optional[ModelRenderer] = None
        self._engine = PaintEngine(document)
        self._show_stand: bool = False   # set True for armor editing mode
        self._spread_out_mode: bool = False
        self._pose: str = "stand"
        self._base_part_visibility: dict[str, bool] = {
            "head": True,
            "body": True,
            "r_arm": True,
            "l_arm": True,
            "r_leg": True,
            "l_leg": True,
        }
        self._armor_part_visibility: dict[str, bool] = {
            "helmet": True,
            "chest": True,
            "r_arm": True,
            "l_arm": True,
            "r_leg": True,
            "l_leg": True,
            "r_boot": True,
            "l_boot": True,
        }

        # CPU-side mesh data for ray casting (kept in sync with skin_type)
        self._meshes: dict[str, object] = {}

        # Camera orbit state
        self.yaw: float      = 30.0    # degrees, rotation around Y axis
        self.pitch: float    = -15.0   # degrees, tilt up/down
        self.zoom_fov: float = 45.0    # FOV in degrees

        # Right-drag orbit tracking
        self._orbit_last: Optional[QPoint] = None

        # Left-drag painting tracking
        self._paint_last: Optional[tuple[int, int]] = None      # last skin pixel painted
        self._paint_last_part: Optional[str]        = None      # which part was last hit
        self._paint_last_face: Optional[str]        = None      # which face was last hit

        self.setMinimumSize(300, 400)

    # ------------------------------------------------------------------
    # OpenGL lifecycle
    # ------------------------------------------------------------------

    def _build_meshes(self) -> dict:
        """Build all meshes, applying armor-stand arm poses if stand mode is on."""
        meshes = mesh_builder.build_all_meshes(
            self.document.skin_type,
            spread_out=self._spread_out_mode,
            pose=self._pose,
        )
        meshes.update(build_stand_meshes())
        if self._show_stand:
            # Replace outer body meshes with posed (arms-out) versions
            meshes.update(
                build_stand_body_meshes(
                    self.document.skin_type,
                    spread_out=self._spread_out_mode,
                    pose=self._pose,
                )
            )
        return meshes

    def initializeGL(self) -> None:
        try:
            self._meshes = self._build_meshes()

            self.renderer = ModelRenderer()
            self.renderer.initialize(self._meshes)
            self.renderer.set_show_stand(self._show_stand)
            for group, visible in self._base_part_visibility.items():
                self.renderer.set_base_part_visible(group, visible)
            for group, visible in self._armor_part_visibility.items():
                self.renderer.set_armor_part_visible(group, visible)

            # Sync visibility from document (may have been set before GL context existed)
            self.renderer.set_layer_visible("base",  self.document.base_visible)
            self.renderer.set_layer_visible("armor", self.document.armor_visible)

            # Upload initial texture content (may be blank on new document)
            self.renderer.upload_texture("base",  self.document.base_image)
            self.renderer.upload_texture("armor", self.document.armor_image)

            # Stay in sync with document changes
            self.document.pixel_changed.connect(self._on_pixel_changed)
            self.document.layer_replaced.connect(self._on_layer_replaced)
            self.document.visibility_changed.connect(self._on_visibility_changed)
        except Exception as e:
            import traceback
            print("initializeGL ERROR:", e)
            traceback.print_exc()

    def paintGL(self) -> None:
        if self.renderer is None:
            return
        w, h = self.width(), self.height()
        view = self._view_matrix()
        proj = self._proj_matrix(w, h)
        self.renderer.draw(view, proj)

    def resizeGL(self, w: int, h: int) -> None:
        if self.renderer:
            self.renderer.set_viewport(w, h)

    # ------------------------------------------------------------------
    # Camera matrices
    # ------------------------------------------------------------------

    def _view_matrix(self):
        yaw_r   = math.radians(self.yaw)
        pitch_r = math.radians(self.pitch)
        dist = 80.0
        eye_x = dist * math.sin(yaw_r) * math.cos(pitch_r)
        eye_y = 18.0 + dist * math.sin(pitch_r)
        eye_z = dist * math.cos(yaw_r) * math.cos(pitch_r)
        return look_at(
            eye    = [eye_x, eye_y, eye_z],
            target = [0.0, 18.0, 0.0],
            up     = [0.0, 1.0, 0.0],
        )

    def _proj_matrix(self, w: int, h: int):
        aspect = w / max(h, 1)
        return perspective(
            fov_rad = math.radians(self.zoom_fov),
            aspect  = aspect,
            near    = 0.1,
            far     = 500.0,
        )

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._orbit_last = event.position().toPoint()
        elif event.button() == Qt.MouseButton.LeftButton:
            self._paint_at(event.position().x(), event.position().y(), first=True)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        # Right drag → orbit
        if (event.buttons() & Qt.MouseButton.RightButton) and self._orbit_last:
            delta = event.position().toPoint() - self._orbit_last
            self._orbit_last = event.position().toPoint()
            self.yaw   += delta.x() * 0.5
            self.pitch -= delta.y() * 0.5
            self.pitch = max(-89.0, min(89.0, self.pitch))
            self.update()

        # Left drag → continuous paint
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._paint_at(event.position().x(), event.position().y(), first=False)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._orbit_last = None
        if event.button() == Qt.MouseButton.LeftButton:
            self._paint_last = None
            self._paint_last_part = None
            self._paint_last_face = None

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y() / 120
        self.zoom_fov -= delta * 3.0
        self.zoom_fov = max(10.0, min(120.0, self.zoom_fov))
        self.update()

    # ------------------------------------------------------------------
    # 3D painting
    # ------------------------------------------------------------------

    def _paint_at(self, mx: float, my: float, first: bool) -> None:
        """Cast a ray from screen pixel (mx, my) and paint the hit point."""
        if not self._meshes:
            return

        w, h = self.width(), self.height()
        view = self._view_matrix()
        proj = self._proj_matrix(w, h)

        origin, direction = ray_from_screen(mx, my, w, h, view, proj)

        # Only ray-test the mesh parts that correspond to the active paint layer.
        # Testing both layers at once caused the ray to hit the (inflated) outer
        # mesh and return its UV coords while painting was still writing to the
        # base layer — producing marks in completely wrong texture regions.
        layer = self.tool_state.active_layer
        if layer == "base":
            if self.document.base_visible:
                parts = []
                for part in BASE_PARTS:
                    if self._base_part_visibility.get(part, True):
                        parts.append(part)
            else:
                parts = []
        else:
            if self.document.armor_visible:
                parts = []
                if self._armor_part_visibility["helmet"]:
                    parts.append("head_outer")
                if self._armor_part_visibility["chest"]:
                    parts.append("body_outer")
                if self._armor_part_visibility["r_arm"]:
                    parts.append("r_arm_outer")
                if self._armor_part_visibility["l_arm"]:
                    parts.append("l_arm_outer")
                if self._armor_part_visibility["r_leg"]:
                    parts.append("r_leg_outer")
                if self._armor_part_visibility["l_leg"]:
                    parts.append("l_leg_outer")
                if self._armor_part_visibility["r_boot"]:
                    parts.append("r_boot_outer")
                if self._armor_part_visibility["l_boot"]:
                    parts.append("l_boot_outer")
            else:
                parts = []

        hit = hit_mesh(origin, direction, self._meshes, parts)
        if hit is None:
            # Mouse moved off the model — reset line start so no jump on re-entry
            self._paint_last = None
            self._paint_last_part = None
            self._paint_last_face = None
            return

        hit_part, hit_face, px, py = hit
        color = self.tool_state.active_color
        size  = self.tool_state.brush_size
        tool  = self.tool_state.active_tool

        if tool == "dropper":
            picked = self._engine.pick_color(layer, px, py)
            self.tool_state.set_color(picked)
            self.tool_state.set_tool("brush")
            return

        # Only interpolate a Bresenham line when the ray stays on the exact
        # same face of the same part — this avoids UV-space jumps at every
        # face/part seam which were causing erratic strokes.
        same_face = (
            self._paint_last_part == hit_part
            and self._paint_last_face == hit_face
        )

        if first:
            # Snapshot the layer at stroke start so the whole stroke can be undone at once
            self.document.push_undo_snapshot(layer)

        if first or self._paint_last is None:
            # First click of a stroke — always paint a single point.
            if tool == "brush":
                self._engine.paint(layer, px, py, color, size)
            elif tool == "eraser":
                self._engine.erase(layer, px, py, size)
        elif same_face:
            # Continuing on the same face — draw a Bresenham line to fill gaps.
            lx, ly = self._paint_last
            if tool == "brush":
                self._engine.paint_line(layer, lx, ly, px, py, color, size)
            elif tool == "eraser":
                self._engine.erase_line(layer, lx, ly, px, py, size)
        # else: face/part seam transition mid-stroke — skip painting this frame
        # so stray dots are not scattered across disconnected UV regions.
        # _paint_last is updated below so the stroke resumes correctly.

        self._paint_last = (px, py)
        self._paint_last_part = hit_part
        self._paint_last_face = hit_face

    # ------------------------------------------------------------------
    # Document signal handlers
    # ------------------------------------------------------------------

    def _on_pixel_changed(
        self, layer: str, x: int, y: int, rgba: object
    ) -> None:
        if self.renderer is None:
            return
        self.makeCurrent()
        self.renderer.update_texture_pixel(layer, x, y, tuple(rgba))
        self.doneCurrent()
        self.update()

    def _on_layer_replaced(self, layer: str) -> None:
        if self.renderer is None:
            return
        self.makeCurrent()
        self.renderer.upload_texture(layer, self.document.get_image(layer))
        self.doneCurrent()
        self.update()

    def _on_visibility_changed(self, layer: str, visible: bool) -> None:
        if self.renderer:
            self.renderer.set_layer_visible(layer, visible)
            self.update()

    # ------------------------------------------------------------------
    # Skin type change (called from MainWindow)
    # ------------------------------------------------------------------

    def set_show_stand(self, show: bool) -> None:
        """Show or hide the armor stand and apply stand arm poses. Call before or after initializeGL."""
        self._show_stand = show
        if self.renderer is not None:
            # Rebuild meshes so arm poses are applied (or removed)
            self._meshes = self._build_meshes()
            self.makeCurrent()
            self.renderer.cleanup()
            self.renderer.initialize(self._meshes)
            self.renderer.set_show_stand(show)
            for group, visible in self._base_part_visibility.items():
                self.renderer.set_base_part_visible(group, visible)
            for group, visible in self._armor_part_visibility.items():
                self.renderer.set_armor_part_visible(group, visible)
            self.renderer.upload_texture("base",  self.document.base_image)
            self.renderer.upload_texture("armor", self.document.armor_image)
            self.doneCurrent()
            self.update()

    def rebuild_meshes(self, skin_type: str) -> None:
        """Rebuild geometry when the user switches Steve ↔ Alex."""
        self._paint_last = None
        self._paint_last_part = None
        self._paint_last_face = None
        self._meshes = self._build_meshes()
        if self.renderer is not None:
            self.makeCurrent()
            self.renderer.cleanup()
            self.renderer.initialize(self._meshes)
            self.renderer.set_show_stand(self._show_stand)
            for group, visible in self._base_part_visibility.items():
                self.renderer.set_base_part_visible(group, visible)
            for group, visible in self._armor_part_visibility.items():
                self.renderer.set_armor_part_visible(group, visible)
            self.renderer.upload_texture("base",  self.document.base_image)
            self.renderer.upload_texture("armor", self.document.armor_image)
            self.doneCurrent()
        self.update()

    def set_armor_part_visible(self, group: str, visible: bool) -> None:
        aliases = {
            "arms": ("r_arm", "l_arm"),
            "legs": ("r_leg", "l_leg"),
            "boots": ("r_boot", "l_boot"),
        }
        if group in aliases:
            for key in aliases[group]:
                self._armor_part_visibility[key] = visible
            if self.renderer is not None:
                self.renderer.set_armor_part_visible(group, visible)
            self.update()
            return
        if group not in self._armor_part_visibility:
            return
        self._armor_part_visibility[group] = visible
        if self.renderer is not None:
            self.renderer.set_armor_part_visible(group, visible)
        self.update()

    def set_base_part_visible(self, group: str, visible: bool) -> None:
        aliases = {
            "arms": ("r_arm", "l_arm"),
            "legs": ("r_leg", "l_leg"),
        }
        if group in aliases:
            for key in aliases[group]:
                self._base_part_visibility[key] = visible
            if self.renderer is not None:
                self.renderer.set_base_part_visible(group, visible)
            self.update()
            return
        if group not in self._base_part_visibility:
            return
        self._base_part_visibility[group] = visible
        if self.renderer is not None:
            self.renderer.set_base_part_visible(group, visible)
        self.update()

    def set_spread_out_mode(self, enabled: bool) -> None:
        if self._spread_out_mode == enabled:
            return
        self._spread_out_mode = enabled
        self._paint_last = None
        self._paint_last_part = None
        self._paint_last_face = None
        self.rebuild_meshes(self.document.skin_type)

    def set_pose(self, pose: str) -> None:
        pose = (pose or "stand").lower()
        if pose == self._pose:
            return
        self._pose = pose
        self._paint_last = None
        self._paint_last_part = None
        self._paint_last_face = None
        self.rebuild_meshes(self.document.skin_type)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        self.makeCurrent()
        if self.renderer:
            self.renderer.cleanup()
        self.doneCurrent()
        super().closeEvent(event)

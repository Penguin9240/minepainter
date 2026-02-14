"""
File I/O for Minecraft skin PNGs.

Handles loading (including legacy 64×32 conversion) and saving.
Uses Pillow for robust PNG handling.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
from minepainter.skin_constants import OUTER_UV, BASE_UV


class SkinIO:
    VALID_SIZES = {(64, 64), (64, 32)}
    VALID_ARMOR_LAYER_SIZE = (64, 32)

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    @staticmethod
    def load(path: Path) -> tuple[np.ndarray, str]:
        """
        Load a skin PNG.

        Returns:
            (base_array, skin_type) where base_array is uint8 (64,64,4) RGBA
            and skin_type is "steve" or "alex".

        Raises:
            ValueError: if the image dimensions are not a valid skin size.
        """
        img = Image.open(path).convert("RGBA")
        w, h = img.size
        if (w, h) not in SkinIO.VALID_SIZES:
            raise ValueError(
                f"Invalid skin size {w}×{h}. Expected 64×64 or 64×32."
            )

        arr = np.array(img, dtype=np.uint8)  # shape: (h, w, 4)

        if h == 32:
            arr = SkinIO.convert_legacy_to_modern(arr)

        skin_type = SkinIO.detect_skin_type(arr)
        return arr, skin_type

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    @staticmethod
    def save(
        path: Path,
        base_array: np.ndarray,
        armor_array: Optional[np.ndarray] = None,
    ) -> None:
        """
        Save the base skin as a standard 64x64 RGBA PNG.

        If armor pixels exist, export two armor files:
          - '<stem>_armor_main.png'     (64x32: helmet + chestplate + arms + boots)
          - '<stem>_armor_leggings.png' (64x32: leggings only)
        """
        path = Path(path)
        base_rgba = SkinIO._normalize_rgba(base_array)
        Image.fromarray(base_rgba, mode="RGBA").save(path)

        if armor_array is not None:
            armor_rgba = SkinIO._normalize_rgba(armor_array)
            if armor_rgba[:, :, 3].any():
                # Split export is a direct 64x64 -> two 64x32 halves.
                # Top half stores helmet/chest/arms/boots.
                # Bottom half stores leggings.
                main_armor = armor_rgba[0:32, :, :].copy()
                leggings_armor = armor_rgba[32:64, :, :].copy()

                main_path = path.with_name(path.stem + "_armor_main" + path.suffix)
                Image.fromarray(main_armor, mode="RGBA").save(main_path)

                leggings_path = path.with_name(path.stem + "_armor_leggings" + path.suffix)
                Image.fromarray(leggings_armor, mode="RGBA").save(leggings_path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def load_armor_layer(path: Path, half: str | None = None) -> np.ndarray:
        """
        Load one armor layer as uint8 RGBA (32, 64, 4).

        Accepted source sizes:
          - 64x32: returned directly
          - 64x64: requires half='top' or half='bottom'
        """
        img = Image.open(path).convert("RGBA")
        w, h = img.size
        if (w, h) == SkinIO.VALID_ARMOR_LAYER_SIZE:
            return np.array(img, dtype=np.uint8)
        if (w, h) == (64, 64):
            arr = np.array(img, dtype=np.uint8)
            if half == "top":
                return arr[0:32, :, :].copy()
            if half == "bottom":
                return arr[32:64, :, :].copy()
            raise ValueError(
                "64x64 armor source requires half='top' or half='bottom'."
            )
        raise ValueError(
            f"Invalid armor layer size {w}x{h}. Expected 64x32 (or 64x64 with half)."
        )

    @staticmethod
    def save_armor_layer(path: Path, armor_layer: np.ndarray) -> None:
        """Save one legacy armor-layer PNG (expects shape 32x64x4 RGBA)."""
        arr = np.asarray(armor_layer)
        if arr.shape != (32, 64, 4):
            raise ValueError(
                f"Invalid armor layer shape {arr.shape}. Expected (32, 64, 4)."
            )
        if arr.dtype != np.uint8:
            arr = np.clip(arr, 0, 255).astype(np.uint8)
        Image.fromarray(arr, mode="RGBA").save(Path(path))

    @staticmethod
    def _normalize_rgba(image: np.ndarray) -> np.ndarray:
        """Return a clipped uint8 RGBA (64x64x4) array."""
        arr = np.asarray(image)
        if arr.shape != (64, 64, 4):
            raise ValueError(f"Invalid image shape {arr.shape}. Expected (64, 64, 4).")
        if arr.dtype != np.uint8:
            arr = np.clip(arr, 0, 255).astype(np.uint8)
        return arr

    @staticmethod
    def _sanitize_armor_uv(armor: np.ndarray) -> np.ndarray:
        """
        Keep armor pixels only inside valid OUTER_UV faces so exported files are
        always correctly formatted for Minecraft armor overlays.
        """
        out = np.zeros_like(armor, dtype=np.uint8)
        for part_uv in OUTER_UV.values():
            for px, py, pw, ph in part_uv.values():
                out[py:py + ph, px:px + pw] = armor[py:py + ph, px:px + pw]
        return out

    @staticmethod
    def _merge_face(src_primary: np.ndarray, src_secondary: np.ndarray) -> np.ndarray:
        """Overlay secondary onto transparent pixels of primary."""
        out = src_primary.copy()
        mask = out[:, :, 3] == 0
        out[mask] = src_secondary[mask]
        return out

    @staticmethod
    def _copy_face(src: np.ndarray, dst: np.ndarray, src_uv: tuple[int, int, int, int], dst_uv: tuple[int, int, int, int]) -> None:
        sx, sy, sw, sh = src_uv
        dx, dy, dw, dh = dst_uv
        patch = src[sy:sy + sh, sx:sx + sw]
        if (sw, sh) != (dw, dh):
            # Nearest-neighbor scale for safety; normal armor UVs are already 1:1.
            ys = (np.linspace(0, sh - 1, dh)).astype(int)
            xs = (np.linspace(0, sw - 1, dw)).astype(int)
            patch = patch[np.ix_(ys, xs)]
        dst[dy:dy + dh, dx:dx + dw] = patch

    @staticmethod
    def _split_armor_layers_64x32(armor: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """
        Convert 64x64 skin-overlay armor into two 64x32 armor layer textures:
          main: helmet + chestplate + arms + boots
          leggings: leggings-only
        """
        main = np.zeros((32, 64, 4), dtype=np.uint8)
        leggings = np.zeros((32, 64, 4), dtype=np.uint8)

        # Head and chest map directly to legacy top-half UV positions.
        for face in ("top", "bottom", "right", "front", "left", "back"):
            SkinIO._copy_face(armor, main, OUTER_UV["head"][face], BASE_UV["head"][face])
            SkinIO._copy_face(armor, main, OUTER_UV["body"][face], BASE_UV["body"][face])

        # Arms: legacy armor layer uses one arm template; merge right+left.
        for face in ("top", "bottom", "right", "front", "left", "back"):
            rx, ry, rw, rh = OUTER_UV["r_arm"][face]
            lx, ly, lw, lh = OUTER_UV["l_arm"][face]
            r_patch = armor[ry:ry + rh, rx:rx + rw]
            l_patch = armor[ly:ly + lh, lx:lx + lw]
            merged = SkinIO._merge_face(r_patch, l_patch)
            dx, dy, dw, dh = BASE_UV["r_arm"][face]
            main[dy:dy + dh, dx:dx + dw] = merged

        # Legs: split into leggings (top 8 rows) and boots (bottom 4 rows),
        # then merge right+left into the single legacy leg template.
        for face in ("front", "back", "right", "left"):
            rx, ry, rw, rh = OUTER_UV["r_leg"][face]
            lx, ly, lw, lh = OUTER_UV["l_leg"][face]
            r_patch = armor[ry:ry + rh, rx:rx + rw]
            l_patch = armor[ly:ly + lh, lx:lx + lw]
            merged = SkinIO._merge_face(r_patch, l_patch)  # 4x12

            dx, dy, dw, dh = BASE_UV["r_leg"][face]
            # Leggings-only top 8 rows
            leggings[dy:dy + 8, dx:dx + dw] = merged[:8, :]
            # Boots-only bottom 4 rows
            main[dy + 8:dy + 12, dx:dx + dw] = merged[8:12, :]

        # Leg top cap -> leggings layer, leg bottom cap -> boots in main layer.
        r_top = armor[
            OUTER_UV["r_leg"]["top"][1]:OUTER_UV["r_leg"]["top"][1] + OUTER_UV["r_leg"]["top"][3],
            OUTER_UV["r_leg"]["top"][0]:OUTER_UV["r_leg"]["top"][0] + OUTER_UV["r_leg"]["top"][2],
        ]
        l_top = armor[
            OUTER_UV["l_leg"]["top"][1]:OUTER_UV["l_leg"]["top"][1] + OUTER_UV["l_leg"]["top"][3],
            OUTER_UV["l_leg"]["top"][0]:OUTER_UV["l_leg"]["top"][0] + OUTER_UV["l_leg"]["top"][2],
        ]
        top_merged = SkinIO._merge_face(r_top, l_top)
        dx, dy, dw, dh = BASE_UV["r_leg"]["top"]
        leggings[dy:dy + dh, dx:dx + dw] = top_merged

        r_bottom = armor[
            OUTER_UV["r_leg"]["bottom"][1]:OUTER_UV["r_leg"]["bottom"][1] + OUTER_UV["r_leg"]["bottom"][3],
            OUTER_UV["r_leg"]["bottom"][0]:OUTER_UV["r_leg"]["bottom"][0] + OUTER_UV["r_leg"]["bottom"][2],
        ]
        l_bottom = armor[
            OUTER_UV["l_leg"]["bottom"][1]:OUTER_UV["l_leg"]["bottom"][1] + OUTER_UV["l_leg"]["bottom"][3],
            OUTER_UV["l_leg"]["bottom"][0]:OUTER_UV["l_leg"]["bottom"][0] + OUTER_UV["l_leg"]["bottom"][2],
        ]
        bottom_merged = SkinIO._merge_face(r_bottom, l_bottom)
        dx, dy, dw, dh = BASE_UV["r_leg"]["bottom"]
        main[dy:dy + dh, dx:dx + dw] = bottom_merged

        return main, leggings

    @staticmethod
    def detect_skin_type(image: np.ndarray) -> str:
        """
        Detect whether a skin uses the Steve or Alex arm model.

        Alex arms are 3 pixels wide instead of 4.  In the standard 64×64
        layout, the pixels at x=50..52, y=16..19 are part of the right-arm
        top face for Steve (4-wide) but lie *outside* the arm region for
        Alex (3-wide) and are typically left transparent.

        Returns "alex" if those pixels are all transparent, "steve" otherwise.
        """
        # Check the extra column that exists in Steve but not Alex
        region = image[16:20, 50:54, 3]  # alpha channel
        return "alex" if region.max() == 0 else "steve"

    @staticmethod
    def convert_legacy_to_modern(image_64x32: np.ndarray) -> np.ndarray:
        """
        Expand a legacy 64×32 skin to the modern 64×64 format.

        The lower half of the modern format contains separate UV regions for
        the left arm and left leg.  In the legacy format these were mirrored
        from the right side at runtime by the game.  We replicate that here:
          - Left leg (row 3, cols 0-15) mirrors right leg (row 1, cols 0-15)
          - Left arm (row 3, cols 32-47) mirrors right arm (row 1, cols 40-55)
        """
        modern = np.zeros((64, 64, 4), dtype=np.uint8)
        modern[:32, :, :] = image_64x32

        # Mirror right leg → left leg position in modern layout
        # Right leg base UV region: x 0-15, y 16-31  (cols 0..15, rows 16..31)
        # Left leg base UV region in modern: x 16-31, y 48-63 for skin pixels
        # Simpler: copy and flip the right-side panels horizontally.

        def copy_and_mirror(
            src: np.ndarray,
            src_x: int, src_y: int, src_w: int, src_h: int,
            dst: np.ndarray,
            dst_x: int, dst_y: int,
            flip_h: bool = True,
        ) -> None:
            patch = src[src_y:src_y + src_h, src_x:src_x + src_w]
            if flip_h:
                patch = np.fliplr(patch)
            dst[dst_y:dst_y + src_h, dst_x:dst_x + src_w] = patch

        # Right leg (base) -> Left leg (modern positions, rows 48-63)
        # Source: (x=0,y=16) 16×16 block  (includes top/bottom + 4 faces)
        copy_and_mirror(modern, 0, 16, 16, 16, modern, 16, 48)

        # Right arm (base) -> Left arm (modern positions, rows 48-63)
        # Source: (x=40,y=16) 16×16 block
        copy_and_mirror(modern, 40, 16, 16, 16, modern, 32, 48)

        return modern

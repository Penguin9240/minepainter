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


class SkinIO:
    VALID_SIZES = {(64, 64), (64, 32)}

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
        Save the base skin as a standard 64×64 RGBA PNG.
        If an armor array with any non-transparent pixels is provided,
        it is saved alongside as '<stem>_armor.png'.
        """
        path = Path(path)
        Image.fromarray(base_array, mode="RGBA").save(path)

        if armor_array is not None and armor_array[:, :, 3].any():
            armor_path = path.with_name(path.stem + "_armor" + path.suffix)
            Image.fromarray(armor_array, mode="RGBA").save(armor_path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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

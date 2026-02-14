from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from minepainter.document import SkinDocument
from minepainter.io.skin_io import SkinIO


class ArmorExportRoundTripTests(unittest.TestCase):
    @staticmethod
    def _reference_paths(repo_root: Path) -> tuple[Path, Path]:
        preferred = (
            repo_root / "DiamondReference1_armor_main.png",
            repo_root / "DiamondReference1_armor_leggings.png",
        )
        fallback = (
            repo_root / "DiamondReference1.png",
            repo_root / "DiamondReference2.png",
        )
        if preferred[0].exists() and preferred[1].exists():
            return preferred
        return fallback

    def test_reference_armor_files_load_save_without_changes(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        ref_main_path, ref_leggings_path = self._reference_paths(repo_root)

        self.assertTrue(ref_main_path.exists(), f"Missing {ref_main_path}")
        self.assertTrue(ref_leggings_path.exists(), f"Missing {ref_leggings_path}")

        ref_main = SkinIO.load_armor_layer(ref_main_path, half="top")
        ref_leggings = SkinIO.load_armor_layer(ref_leggings_path, half="bottom")
        self.assertEqual(ref_main.shape, (32, 64, 4))
        self.assertEqual(ref_leggings.shape, (32, 64, 4))

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_main_path = Path(tmp_dir) / "roundtrip_armor_main.png"
            out_leggings_path = Path(tmp_dir) / "roundtrip_armor_leggings.png"
            SkinIO.save_armor_layer(out_main_path, ref_main)
            SkinIO.save_armor_layer(out_leggings_path, ref_leggings)

            out_main = SkinIO.load_armor_layer(out_main_path)
            out_leggings = SkinIO.load_armor_layer(out_leggings_path)

        np.testing.assert_array_equal(out_main, ref_main)
        np.testing.assert_array_equal(out_leggings, ref_leggings)

    def test_reference_files_load_into_correct_armor_halves(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        ref_main_path, ref_leggings_path = self._reference_paths(repo_root)

        ref_main = SkinIO.load_armor_layer(ref_main_path, half="top")
        ref_leggings = SkinIO.load_armor_layer(ref_leggings_path, half="bottom")

        doc = SkinDocument()
        doc.armor_image = np.zeros((64, 64, 4), dtype=np.uint8)
        doc.load_armor_main_file(ref_main_path)
        doc.load_armor_leggings_file(ref_leggings_path)

        np.testing.assert_array_equal(doc.armor_image[0:32, :, :], ref_main)
        np.testing.assert_array_equal(doc.armor_image[32:64, :, :], ref_leggings)

    def test_save_splits_armor_as_direct_top_and_bottom_halves(self) -> None:
        # Build a synthetic armor overlay with unique values in top and bottom
        # halves so we can verify exact split output.
        armor = np.zeros((64, 64, 4), dtype=np.uint8)
        armor[0:32, :, :] = (10, 20, 30, 40)
        armor[32:64, :, :] = (50, 60, 70, 80)
        base = np.zeros((64, 64, 4), dtype=np.uint8)

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_base = Path(tmp_dir) / "splitcheck.png"
            SkinIO.save(out_base, base, armor)
            main = SkinIO.load_armor_layer(Path(tmp_dir) / "splitcheck_armor_main.png")
            legs = SkinIO.load_armor_layer(Path(tmp_dir) / "splitcheck_armor_leggings.png")

        np.testing.assert_array_equal(main, armor[0:32, :, :])
        np.testing.assert_array_equal(legs, armor[32:64, :, :])


if __name__ == "__main__":
    unittest.main()

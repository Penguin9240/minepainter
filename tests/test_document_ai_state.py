from __future__ import annotations

import unittest

import numpy as np

from minepainter.document import SkinDocument


class DocumentAIStateTests(unittest.TestCase):
    def test_armor_state_text_roundtrip(self) -> None:
        arr = np.zeros((64, 64, 4), dtype=np.uint8)
        # Points chosen inside mapped armor areas.
        arr[1, 9] = (11, 22, 33, 44)      # helmet top face
        arr[53, 5] = (201, 111, 50, 255)  # leggings front face (lower half)
        text = SkinDocument.encode_armor_state_text(arr)
        decoded = SkinDocument.decode_armor_state_text(text)
        np.testing.assert_array_equal(decoded, arr)

    def test_apply_armor_state_pushes_undo(self) -> None:
        doc = SkinDocument()
        original = doc.armor_image.copy()

        updated = np.zeros((64, 64, 4), dtype=np.uint8)
        updated[1, 9] = (1, 2, 3, 4)  # helmet top face
        state_text = doc.encode_armor_state_text(updated)
        doc.apply_armor_state_text(state_text, push_undo=True)

        np.testing.assert_array_equal(doc.armor_image, updated)
        self.assertTrue(doc.undo())
        np.testing.assert_array_equal(doc.armor_image, original)

    def test_state_text_contains_area_sections_and_rgba_arrays(self) -> None:
        arr = np.zeros((64, 64, 4), dtype=np.uint8)
        text = SkinDocument.encode_armor_state_text(arr)
        import json
        payload = json.loads(text)

        self.assertEqual(payload["version"], 2)
        self.assertEqual(payload["format"], "minepainter_armor_state_v2")
        areas = payload["areas"]
        self.assertIn("helmet", areas)
        self.assertIn("chestplate", areas)
        self.assertIn("arms", areas)
        self.assertIn("leggings", areas)
        self.assertIn("boots", areas)

        sample_face = areas["helmet"]["front"]
        self.assertIn("uv", sample_face)
        self.assertIn("pixels", sample_face)
        # One pixel must be RGBA list of length 4.
        self.assertEqual(len(sample_face["pixels"][0][0]), 4)


if __name__ == "__main__":
    unittest.main()

import unittest

from PIL import Image

from app.services.mask_edit import (
    BrushSelection,
    LassoSelection,
    MaskEditHistory,
    apply_mask_edit,
    selection_mask,
)


class MaskEditTests(unittest.TestCase):
    def setUp(self):
        self.original = Image.new("RGBA", (20, 20), (220, 30, 40, 255))
        self.current = Image.new("RGBA", (20, 20), (10, 20, 30, 255))
        self.lasso = LassoSelection(((5, 5), (14, 5), (14, 14), (5, 14)))

    def test_selection_mask_supports_lasso(self):
        mask = selection_mask((20, 20), LassoSelection(((2, 2), (17, 2), (10, 17))))
        self.assertEqual(mask.getpixel((10, 8)), 255)
        self.assertEqual(mask.getpixel((1, 1)), 0)

    def test_selection_mask_supports_brush_stroke(self):
        mask = selection_mask(
            (20, 20), BrushSelection(((4, 10), (16, 10)), radius=3)
        )
        self.assertEqual(mask.getpixel((10, 10)), 255)
        self.assertEqual(mask.getpixel((10, 12)), 255)
        self.assertEqual(mask.getpixel((10, 15)), 0)

    def test_keep_clears_pixels_outside_selection(self):
        result = apply_mask_edit(self.original, self.current, self.lasso, "keep")
        self.assertEqual(result.getchannel("A").getpixel((0, 0)), 0)
        self.assertEqual(result.getchannel("A").getpixel((10, 10)), 255)

    def test_erase_clears_selected_pixels(self):
        result = apply_mask_edit(self.original, self.current, self.lasso, "erase")
        self.assertEqual(result.getchannel("A").getpixel((10, 10)), 0)
        self.assertEqual(result.getchannel("A").getpixel((0, 0)), 255)

    def test_restore_uses_original_pixels_and_opacity(self):
        transparent = Image.new("RGBA", (20, 20), (10, 20, 30, 0))
        result = apply_mask_edit(self.original, transparent, self.lasso, "restore")
        self.assertEqual(result.getpixel((10, 10)), (220, 30, 40, 255))
        self.assertEqual(result.getchannel("A").getpixel((0, 0)), 0)

    def test_history_round_trip(self):
        history = MaskEditHistory(self.original, self.current)
        history.apply(self.lasso, "erase", 0)
        self.assertEqual(history.current.getchannel("A").getpixel((10, 10)), 0)
        history.undo()
        self.assertEqual(history.current.getchannel("A").getpixel((10, 10)), 255)
        history.redo()
        self.assertEqual(history.current.getchannel("A").getpixel((10, 10)), 0)


if __name__ == "__main__":
    unittest.main()

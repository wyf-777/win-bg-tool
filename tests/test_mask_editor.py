import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.services.mask_edit import BrushSelection, LassoSelection
from app.ui.mask_editor import MaskEditorDialog


class MaskEditorViewModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        original = Image.new("RGBA", (100, 80), (220, 30, 40, 255))
        result = Image.new("RGBA", (100, 80), (0, 0, 0, 0))
        self.dialog = MaskEditorDialog(original, result, "view-mode-test")
        self.dialog.resize(800, 600)
        self.dialog.show()
        self.app.processEvents()

    def tearDown(self):
        self.dialog.close()
        self.app.processEvents()

    def test_default_overlay_and_opacity_slider(self):
        self.assertEqual(self.dialog.canvas._overlay_opacity, 0.38)
        self.assertEqual(self.dialog.canvas._mode, "lasso")
        self.assertTrue(self.dialog.lasso_button.isChecked())
        self.assertFalse(hasattr(self.dialog, "result_view_button"))
        self.assertFalse(hasattr(self.dialog, "original_view_button"))
        self.assertFalse(hasattr(self.dialog, "rect_button"))
        self.assertFalse(hasattr(self.dialog, "circle_button"))
        self.assertFalse(hasattr(self.dialog, "ellipse_button"))

        self.dialog.overlay_strength.setValue(65)
        self.assertEqual(self.dialog.canvas._overlay_opacity, 0.65)

    def test_brush_tool_creates_a_sized_selection(self):
        QTest.mouseClick(self.dialog.brush_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.dialog.canvas._mode, "brush")
        self.assertTrue(self.dialog.brush_button.isChecked())
        self.assertTrue(self.dialog.brush_options.isVisible())

        self.dialog.brush_size.setValue(48)
        self.assertEqual(self.dialog.canvas._brush_radius, 24)

        x, y, width, height = self.dialog.canvas._image_rect()
        QTest.mouseClick(
            self.dialog.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(int(x + width / 2), int(y + height / 2)),
        )
        selection = self.dialog.canvas.selection()
        self.assertIsInstance(selection, BrushSelection)
        self.assertEqual(selection.radius, 24)
        self.assertEqual(len(selection.points), 1)

        self.dialog.brush_size.setValue(96)
        self.assertEqual(self.dialog.canvas.selection().radius, 24)

        QTest.mouseClick(self.dialog.lasso_button, Qt.MouseButton.LeftButton)
        self.assertTrue(self.dialog.brush_options.isHidden())

    def test_compact_layout_keeps_canvas_and_top_commands_separate(self):
        self.dialog.resize(720, 540)
        self.app.processEvents()

        self.assertTrue(self.dialog.top_bar.isVisible())
        self.assertTrue(self.dialog.sidebar.isVisible())
        self.assertTrue(self.dialog.canvas.isVisible())
        self.assertLess(
            self.dialog.sidebar.geometry().right(),
            self.dialog.canvas.geometry().left(),
        )
        self.assertLessEqual(
            self.dialog.top_bar.geometry().bottom(),
            self.dialog.canvas.geometry().top(),
        )
        self.assertFalse(self.dialog.undo_button.parentWidget() is self.dialog.top_bar)
        self.assertFalse(self.dialog.redo_button.parentWidget() is self.dialog.top_bar)

    def test_lasso_tool_creates_selection(self):
        x, y, width, height = self.dialog.canvas._image_rect()
        points = (
            QPoint(int(x + width * 0.2), int(y + height * 0.2)),
            QPoint(int(x + width * 0.8), int(y + height * 0.2)),
            QPoint(int(x + width * 0.8), int(y + height * 0.8)),
            QPoint(int(x + width * 0.2), int(y + height * 0.8)),
        )
        QTest.mousePress(
            self.dialog.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            points[0],
        )
        for point in points[1:]:
            QTest.mouseMove(self.dialog.canvas, point)
        QTest.mouseRelease(
            self.dialog.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            points[-1],
        )
        selection = self.dialog.canvas.selection()
        self.assertIsInstance(selection, LassoSelection)
        self.assertGreaterEqual(len(selection.points), 3)

    def test_polygon_lasso_closes_after_enter(self):
        QTest.mouseClick(self.dialog.polygon_button, Qt.MouseButton.LeftButton)
        x, y, width, height = self.dialog.canvas._image_rect()
        points = (
            QPoint(int(x + width * 0.2), int(y + height * 0.2)),
            QPoint(int(x + width * 0.8), int(y + height * 0.2)),
            QPoint(int(x + width * 0.5), int(y + height * 0.8)),
        )
        for point in points:
            QTest.mouseClick(
                self.dialog.canvas,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                point,
            )
        self.assertIsNone(self.dialog.canvas.selection())
        self.assertTrue(self.dialog.canvas.has_draft_selection)

        QTest.keyClick(self.dialog.canvas, Qt.Key.Key_Return)
        selection = self.dialog.canvas.selection()
        self.assertIsNotNone(selection)
        self.assertEqual(len(selection.points), 3)
        self.assertFalse(self.dialog.canvas.has_draft_selection)

    def test_polygon_lasso_supports_backspace_and_clicking_first_point(self):
        QTest.mouseClick(self.dialog.polygon_button, Qt.MouseButton.LeftButton)
        x, y, width, height = self.dialog.canvas._image_rect()
        first = QPoint(int(x + width * 0.2), int(y + height * 0.2))
        second = QPoint(int(x + width * 0.8), int(y + height * 0.2))
        third = QPoint(int(x + width * 0.5), int(y + height * 0.8))
        for point in (first, second, third):
            QTest.mouseClick(
                self.dialog.canvas,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                point,
            )

        QTest.keyClick(self.dialog.canvas, Qt.Key.Key_Backspace)
        self.assertEqual(len(self.dialog.canvas._polygon), 2)
        QTest.mouseClick(
            self.dialog.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            third,
        )
        QTest.mouseClick(
            self.dialog.canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            first,
        )
        self.assertIsNotNone(self.dialog.canvas.selection())
        self.assertFalse(self.dialog.canvas.has_draft_selection)

    def test_feather_can_adjust_the_last_applied_edit(self):
        QTest.mouseClick(self.dialog.polygon_button, Qt.MouseButton.LeftButton)
        x, y, width, height = self.dialog.canvas._image_rect()
        points = (
            QPoint(int(x + width * 0.35), int(y + height * 0.35)),
            QPoint(int(x + width * 0.65), int(y + height * 0.35)),
            QPoint(int(x + width * 0.65), int(y + height * 0.65)),
            QPoint(int(x + width * 0.35), int(y + height * 0.65)),
        )
        for point in points:
            QTest.mouseClick(
                self.dialog.canvas,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                point,
            )
        QTest.keyClick(self.dialog.canvas, Qt.Key.Key_Return)
        self.dialog.restore_button.click()
        first_result = self.dialog._history.current.tobytes()

        self.dialog.feather.setValue(16)
        self.assertNotEqual(self.dialog._history.current.tobytes(), first_result)

        self.dialog._undo()
        self.assertEqual(
            self.dialog._history.current.getchannel("A").getpixel((50, 40)), 0
        )


if __name__ == "__main__":
    unittest.main()

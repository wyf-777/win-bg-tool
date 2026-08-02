import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

from app.session.models import ImageItem, ItemStatus
from app.ui.main_window import MainWindow


class MainWindowRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.resize(800, 600)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        # MainWindow creates this attribute after its deferred warmup starts.
        # The test closes before that timer is due.
        self.window._warmup_thread = None
        self.window.close()
        self.app.processEvents()

    def test_completed_lightbox_item_can_be_repaired_while_batch_runs(self):
        completed = ImageItem(source_path=Path("completed.png"))
        completed.status = ItemStatus.DONE
        completed.result_image = Image.new("RGBA", (40, 30), (0, 0, 0, 255))
        pending = ImageItem(source_path=Path("pending.png"))
        pending.status = ItemStatus.QUEUED
        self.window.session.items = [completed, pending]
        self.window.workspace.set_items(self.window.session.items)

        self.window.workspace._show_lightbox(0)

        self.assertTrue(self.window.session.is_busy())
        self.assertEqual(self.window._resolve_copy_item().id, completed.id)
        self.assertTrue(self.window.btn_repair.isEnabled())

    def test_repair_opens_as_an_embedded_page_and_cancel_returns_home(self):
        with TemporaryDirectory() as directory:
            source_path = Path(directory) / "source.png"
            Image.new("RGBA", (40, 30), (220, 30, 40, 255)).save(source_path)
            item = ImageItem(source_path=source_path)
            item.status = ItemStatus.DONE
            item.result_image = Image.new("RGBA", (40, 30), (0, 0, 0, 0))
            self.window.session.items = [item]
            self.window.workspace.set_items(self.window.session.items)

            self.window.repair_current_result()

            page = self.window._repair_page
            self.assertIsNotNone(page)
            self.assertIs(self.window.root_stack.currentWidget(), page)
            self.assertFalse(page.isWindow())

            page.cancel_editing()
            self.app.processEvents()
            self.assertIsNone(self.window._repair_page)
            self.assertEqual(self.window.root_stack.currentIndex(), 0)

    def test_embedded_repair_completion_persists_the_edited_result(self):
        with TemporaryDirectory() as directory:
            source_path = Path(directory) / "source.png"
            Image.new("RGBA", (40, 30), (220, 30, 40, 255)).save(source_path)
            item = ImageItem(source_path=source_path)
            item.status = ItemStatus.DONE
            item.result_image = Image.new("RGBA", (40, 30), (0, 0, 0, 0))
            self.window.session.items = [item]
            self.window.workspace.set_items(self.window.session.items)

            self.window.repair_current_result()
            page = self.window._repair_page
            page.edited_image = Image.new("RGBA", (40, 30), (5, 10, 15, 255))
            page.completed.emit()
            self.app.processEvents()

            self.assertIsNone(self.window._repair_page)
            self.assertEqual(item.result_image.getpixel((10, 10)), (5, 10, 15, 255))


if __name__ == "__main__":
    unittest.main()

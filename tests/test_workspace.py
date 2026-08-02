import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

from app.session.models import ImageItem, ItemStatus
from app.ui.workspace import Workspace


class WorkspaceLightboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.workspace = Workspace()
        self.workspace.resize(800, 600)
        self.workspace.show()
        self.app.processEvents()
        self.items = []
        for index in range(2):
            item = ImageItem(source_path=Path(f"image-{index}.png"))
            item.status = ItemStatus.DONE
            item.result_image = Image.new("RGBA", (40, 30), (index * 80, 0, 0, 255))
            self.items.append(item)
        self.workspace.set_items(self.items)
        self.app.processEvents()

    def tearDown(self):
        self.workspace.close()
        self.app.processEvents()

    def test_lightbox_open_and_navigation_refresh_action_target(self):
        refreshes = []
        self.workspace.selection_changed.connect(lambda: refreshes.append(True))

        self.workspace._show_lightbox(0)
        self.assertEqual(self.workspace.item_for_copy().id, self.items[0].id)
        self.assertEqual(len(refreshes), 1)

        self.workspace._on_lightbox_nav(1)
        self.assertEqual(self.workspace.item_for_copy().id, self.items[1].id)
        self.assertEqual(len(refreshes), 2)

    def test_grid_tile_emits_reprocess_with_model_id(self):
        received = []
        self.workspace.reprocess_requested.connect(
            lambda iid, mid: received.append((iid, mid))
        )
        # Ensure multi grid is showing tiles
        self.workspace.stack.setCurrentWidget(self.workspace.grid_page)
        self.workspace._rebuild_grid()
        self.app.processEvents()

        tile = next(iter(self.workspace._tile_widgets.values()))
        item_id = tile._item_id
        tile.reprocess_requested.emit(item_id, "u2netp")
        self.assertEqual(received, [(item_id, "u2netp")])

    def test_single_canvas_context_menu_emits_reprocess(self):
        item = ImageItem(source_path=Path("solo.png"))
        item.status = ItemStatus.DONE
        item.result_image = Image.new("RGBA", (40, 30), (0, 100, 0, 255))
        self.workspace.set_items([item])
        self.app.processEvents()

        received = []
        self.workspace.reprocess_requested.connect(
            lambda iid, mid: received.append((iid, mid))
        )
        # Simulate menu pick path used by _on_single_context_menu
        self.workspace.reprocess_requested.emit(item.id, "isnet-general-use")
        self.assertEqual(received, [(item.id, "isnet-general-use")])
        self.assertIs(self.workspace.stack.currentWidget(), self.workspace.canvas)


if __name__ == "__main__":
    unittest.main()

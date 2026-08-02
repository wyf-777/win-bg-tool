import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image

from app.engines.local_rembg import LocalRembgEngine
from app.engines.models_catalog import is_model_downloaded
from app.session.batch_session import BatchSession
from app.session.models import ImageItem, ItemStatus


class ReprocessItemTests(unittest.TestCase):
    def setUp(self):
        self.engine = LocalRembgEngine(model_name="u2netp")
        self.session = BatchSession(self.engine)
        self.item = ImageItem(source_path=Path("a.png"))
        self.item.status = ItemStatus.DONE
        self.item.result_image = Image.new("RGBA", (8, 8), (0, 0, 0, 255))
        self.session.items = [self.item]

    def test_reject_when_running(self):
        self.item.status = ItemStatus.RUNNING
        ok, msg = self.session.reprocess_item(self.item.id, "u2netp")
        self.assertFalse(ok)
        self.assertIn("完成", msg)

    def test_reject_unknown_model(self):
        ok, msg = self.session.reprocess_item(self.item.id, "not-a-model")
        self.assertFalse(ok)

    def test_queue_when_model_downloaded(self):
        if not is_model_downloaded("u2netp"):
            self.skipTest("u2netp not on disk")
        # Do not actually start rembg: mark as would queue by stubbing pump
        pumped = []
        self.session._pump_queue = lambda: pumped.append(True)  # type: ignore
        ok, msg = self.session.reprocess_item(self.item.id, "u2netp")
        self.assertTrue(ok)
        self.assertEqual(self.item.status, ItemStatus.QUEUED)
        self.assertIsNone(self.item.result_image)
        self.assertTrue(pumped)


if __name__ == "__main__":
    unittest.main()

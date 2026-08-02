import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from app.services.folder_watch import (
    DEFAULT_ARCHIVE_SUBDIR,
    DEFAULT_FAIL_SUBDIR,
    DEFAULT_OUTPUT_SUBDIR,
    FolderWatchService,
)


class FolderWatchValidateTests(unittest.TestCase):
    def test_default_output_subdir(self):
        w = Path("D:/inbox")
        self.assertEqual(
            FolderWatchService.default_output_dir(w),
            w / DEFAULT_OUTPUT_SUBDIR,
        )

    def test_fail_and_archive_dirs(self):
        out = Path("D:/out")
        w = Path("D:/in")
        self.assertEqual(
            FolderWatchService.fail_dir_for_output(out),
            out / DEFAULT_FAIL_SUBDIR,
        )
        self.assertEqual(
            FolderWatchService.default_archive_dir(w),
            w / DEFAULT_ARCHIVE_SUBDIR,
        )

    def test_reject_same_watch_and_output(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            ok, msg = FolderWatchService.validate_dirs(root, root)
            self.assertFalse(ok)
            self.assertIn("相同", msg)

    def test_accept_subdir_output(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            out = root / DEFAULT_OUTPUT_SUBDIR
            out.mkdir()
            ok, msg = FolderWatchService.validate_dirs(root, out)
            self.assertTrue(ok, msg)

    def test_resolved_empty_output_uses_default(self):
        w = Path("/tmp/watch")
        self.assertEqual(
            FolderWatchService.resolved_output_dir(w, None),
            w / DEFAULT_OUTPUT_SUBDIR,
        )

    def test_ledger_outside_export_and_skip(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            out = root / DEFAULT_OUTPUT_SUBDIR
            out.mkdir()
            img = root / "a.png"
            Image.new("RGB", (8, 8), (1, 2, 3)).save(img)
            st = img.stat()

            class _E:
                pass

            svc = FolderWatchService(_E())  # type: ignore[arg-type]
            svc._watch_dir = root
            svc._output_dir = out
            svc._ledger = {
                str(img.resolve()).lower(): {
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                    "status": "ok",
                }
            }
            self.assertTrue(svc._should_skip_by_ledger(img))
            ledger_path = svc._ledger_path()
            self.assertIsNotNone(ledger_path)
            assert ledger_path is not None
            try:
                ledger_path.resolve().relative_to(out.resolve())
                self.fail("ledger must not live under export output folder")
            except ValueError:
                pass

    def test_list_skips_output_and_archive_trees(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            out = root / DEFAULT_OUTPUT_SUBDIR
            arch = root / DEFAULT_ARCHIVE_SUBDIR
            sub = root / "photos"
            out.mkdir()
            arch.mkdir()
            sub.mkdir()
            Image.new("RGB", (4, 4), (0, 0, 0)).save(root / "top.png")
            Image.new("RGB", (4, 4), (1, 0, 0)).save(sub / "nested.png")
            Image.new("RGB", (4, 4), (0, 1, 0)).save(out / "result.png")
            Image.new("RGB", (4, 4), (0, 0, 1)).save(arch / "old.png")

            class _E:
                pass

            svc = FolderWatchService(_E())  # type: ignore[arg-type]
            svc._watch_dir = root
            svc._output_dir = out
            svc._recursive = False
            names = {p.name for p in svc._list_watch_images()}
            self.assertIn("top.png", names)
            self.assertNotIn("result.png", names)
            self.assertNotIn("old.png", names)
            self.assertNotIn("nested.png", names)

            svc._recursive = True
            names_r = {p.name for p in svc._list_watch_images()}
            self.assertIn("top.png", names_r)
            self.assertIn("nested.png", names_r)
            self.assertNotIn("result.png", names_r)
            self.assertNotIn("old.png", names_r)

    def test_export_dir_preserves_relative_when_recursive(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            out = root / DEFAULT_OUTPUT_SUBDIR
            out.mkdir()
            nested = root / "a" / "b"
            nested.mkdir(parents=True)
            img = nested / "x.png"

            class _E:
                pass

            svc = FolderWatchService(_E())  # type: ignore[arg-type]
            svc._watch_dir = root
            svc._output_dir = out
            svc._recursive = True
            self.assertEqual(svc._export_dir_for(img), out / "a" / "b")
            svc._recursive = False
            self.assertEqual(svc._export_dir_for(img), out)

    def test_retry_failed_enqueues_existing_files(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            out = root / DEFAULT_OUTPUT_SUBDIR
            out.mkdir()
            img = root / "bad.png"
            Image.new("RGB", (4, 4), (9, 9, 9)).save(img)

            class _E:
                pass

            svc = FolderWatchService(_E())  # type: ignore[arg-type]
            svc._watch_dir = root
            svc._output_dir = out
            svc._enabled = True
            # Avoid starting a real QThread with a stub engine (keeps process alive)
            svc._pump = lambda: None  # type: ignore[method-assign]
            key = str(img.resolve()).lower()
            st = img.stat()
            svc._ledger[key] = {
                "size": st.st_size,
                "mtime": st.st_mtime,
                "status": "fail",
                "error": "x",
                "path": str(img.resolve()),
            }
            n = svc.retry_failed(limit=5)
            self.assertEqual(n, 1)
            pending_paths = [pf.path.resolve() for pf in svc._pending_stable.values()]
            queue_paths = [p.resolve() for p in svc._queue]
            self.assertTrue(
                img.resolve() in pending_paths
                or img.resolve() in queue_paths
                or svc._key(img) in svc._inflight,
                f"pending={pending_paths} queue={queue_paths} inflight={svc._inflight}",
            )

    def test_fail_ledger_skips_auto_retry_same_identity(self):
        """Failed files must not infinite-loop on every poll (blocks later files)."""
        with TemporaryDirectory() as d:
            root = Path(d)
            out = root / DEFAULT_OUTPUT_SUBDIR
            out.mkdir()
            img = root / "bad.png"
            Image.new("RGB", (4, 4), (9, 9, 9)).save(img)
            st = img.stat()

            class _E:
                pass

            svc = FolderWatchService(_E())  # type: ignore[arg-type]
            svc._watch_dir = root
            svc._output_dir = out
            key = str(img.resolve()).lower()
            svc._ledger[key] = {
                "size": st.st_size,
                "mtime": st.st_mtime,
                "status": "fail",
                "error": "x",
            }
            self.assertTrue(svc._should_skip_by_ledger(img))
            svc._enqueue_candidate(img, force=False)
            self.assertEqual(len(svc._pending_stable), 0)
            self.assertEqual(len(svc._queue), 0)

    def test_changed_file_after_fail_can_requeue(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            out = root / DEFAULT_OUTPUT_SUBDIR
            out.mkdir()
            img = root / "x.png"
            Image.new("RGB", (4, 4), (1, 1, 1)).save(img)
            st = img.stat()

            class _E:
                pass

            svc = FolderWatchService(_E())  # type: ignore[arg-type]
            svc._watch_dir = root
            svc._output_dir = out
            key = str(img.resolve()).lower()
            svc._ledger[key] = {
                "size": st.st_size,
                "mtime": st.st_mtime,
                "status": "fail",
            }
            # rewrite with different pixels → different size usually
            Image.new("RGB", (32, 32), (2, 2, 2)).save(img)
            self.assertFalse(svc._should_skip_by_ledger(img))
            svc._enqueue_candidate(img, force=False)
            self.assertTrue(
                img.resolve()
                in [pf.path.resolve() for pf in svc._pending_stable.values()]
                or img.resolve() in [p.resolve() for p in svc._queue]
            )


class FolderWatchRuntimeTests(unittest.TestCase):
    """Integration: successive new files must all be processed (F13 regression)."""

    def test_sequential_new_files_all_processed(self):
        import os
        import sys
        import time

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QCoreApplication

        from app.engines.base import EngineResult

        app = QCoreApplication.instance() or QCoreApplication(sys.argv)

        class Eng:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def remove(self, path, source_path=None):
                p = Path(path)
                self.calls.append(p.name)
                img = Image.open(p).convert("RGBA")
                return EngineResult(image=img, model_name="fake", source_path=p)

        with TemporaryDirectory() as d:
            root = Path(d)
            out = root / DEFAULT_OUTPUT_SUBDIR
            eng = Eng()
            svc = FolderWatchService(
                eng, get_export_fmt=lambda: ("png", "", "t_")  # type: ignore[arg-type]
            )
            svc.configure(
                watch_dir=root, output_dir=out, process_existing=False
            )
            ok, _msg = svc.start()
            self.assertTrue(ok)

            def drain(seconds: float = 2.5) -> None:
                t0 = time.time()
                while time.time() - t0 < seconds:
                    svc._on_poll()
                    app.processEvents()
                    time.sleep(0.05)

            Image.new("RGB", (8, 8), (1, 0, 0)).save(root / "a.png")
            drain(2.0)
            Image.new("RGB", (8, 8), (0, 1, 0)).save(root / "b.png")
            drain(2.0)
            Image.new("RGB", (8, 8), (0, 0, 1)).save(root / "c.png")
            drain(2.5)

            self.assertEqual(
                eng.calls.count("a.png"), 1, eng.calls
            )
            self.assertEqual(eng.calls.count("b.png"), 1, eng.calls)
            self.assertEqual(eng.calls.count("c.png"), 1, eng.calls)
            self.assertEqual(svc._stats.success, 3)
            self.assertEqual(svc._stats.failed, 0)
            outs = sorted(p.name for p in out.glob("*.png"))
            self.assertEqual(outs, ["t_a.png", "t_b.png", "t_c.png"])
            svc.stop()

    def test_dead_worker_ref_does_not_block_queue(self):
        """Regression: finished worker left in self._worker used to block forever."""
        import os
        import sys
        import time

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QCoreApplication

        from app.engines.base import EngineResult

        app = QCoreApplication.instance() or QCoreApplication(sys.argv)

        class Eng:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def remove(self, path, source_path=None):
                p = Path(path)
                self.calls.append(p.name)
                time.sleep(0.05)
                img = Image.open(p).convert("RGBA")
                return EngineResult(image=img, model_name="fake", source_path=p)

        with TemporaryDirectory() as d:
            root = Path(d)
            out = root / DEFAULT_OUTPUT_SUBDIR
            eng = Eng()
            svc = FolderWatchService(
                eng, get_export_fmt=lambda: ("png", "", "t_")  # type: ignore[arg-type]
            )
            svc.configure(
                watch_dir=root, output_dir=out, process_existing=False
            )
            svc.start()

            # After first job, leave a dead worker ref (old bug path)
            Image.new("RGB", (8, 8), (1, 0, 0)).save(root / "a.png")
            t0 = time.time()
            while time.time() - t0 < 3:
                svc._on_poll()
                app.processEvents()
                time.sleep(0.05)
                if eng.calls == ["a.png"] and not svc.is_busy():
                    break
            self.assertEqual(eng.calls, ["a.png"])

            # Ensure first job fully settled
            t1 = time.time()
            while time.time() - t1 < 2:
                app.processEvents()
                time.sleep(0.05)
                if not svc.is_busy() and svc._worker is None:
                    break

            Image.new("RGB", (8, 8), (0, 1, 0)).save(root / "b.png")
            t0 = time.time()
            while time.time() - t0 < 5:
                svc._on_poll()
                app.processEvents()
                time.sleep(0.05)
                if "b.png" in eng.calls and not svc.is_busy():
                    app.processEvents()
                    break
            self.assertIn("b.png", eng.calls, eng.calls)
            # Each file exactly once
            self.assertEqual(eng.calls.count("a.png"), 1)
            self.assertEqual(eng.calls.count("b.png"), 1)
            svc.stop()
            app.processEvents()
            time.sleep(0.1)

    def test_queue_advances_when_result_flag_missing(self):
        """待处理 N must not freeze if worker finished but result_handled was never set."""
        import os
        import sys
        import time

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QCoreApplication

        from app.engines.base import EngineResult
        from app.services import folder_watch as fw

        app = QCoreApplication.instance() or QCoreApplication(sys.argv)

        class Eng:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def remove(self, path, source_path=None):
                p = Path(path)
                self.calls.append(p.name)
                time.sleep(0.03)
                img = Image.open(p).convert("RGBA")
                return EngineResult(image=img, model_name="fake", source_path=p)

        with TemporaryDirectory() as d:
            root = Path(d)
            out = root / DEFAULT_OUTPUT_SUBDIR
            eng = Eng()
            svc = FolderWatchService(
                eng, get_export_fmt=lambda: ("png", "", "t_")  # type: ignore[arg-type]
            )
            # Short timeout so abandon unblocks quickly in test
            old_to = fw.JOB_RESULT_TIMEOUT_S
            fw.JOB_RESULT_TIMEOUT_S = 0.3
            try:
                for i in range(3):
                    Image.new("RGB", (8, 8), (i, 0, 0)).save(root / f"q{i}.png")
                svc.configure(
                    watch_dir=root, output_dir=out, process_existing=True
                )
                svc.start()
                # Simulate: after first job, result_handled stuck false but meta done
                t0 = time.time()
                while time.time() - t0 < 8:
                    app.processEvents()
                    time.sleep(0.05)
                    if len(eng.calls) >= 1:
                        break
                if svc._worker is not None:
                    # Force the bad state that used to freeze the queue
                    svc._worker.result_handled = False
                # Force abandon window to elapse
                for meta in svc._job_meta.values():
                    meta["t0"] = time.time() - 10
                t0 = time.time()
                while time.time() - t0 < 8:
                    svc._on_poll()
                    app.processEvents()
                    time.sleep(0.05)
                    if len(eng.calls) >= 3:
                        break
                self.assertGreaterEqual(
                    len(eng.calls), 3, f"queue stuck: {eng.calls}"
                )
            finally:
                fw.JOB_RESULT_TIMEOUT_S = old_to
                svc.stop()

    def test_clear_queue_requeues_folder_images(self):
        """清空队列 must re-scan folder and queue unprocessed images (not leave 待处理0)."""
        import os
        import sys
        import time

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QCoreApplication

        from app.engines.base import EngineResult

        app = QCoreApplication.instance() or QCoreApplication(sys.argv)

        class Eng:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def remove(self, path, source_path=None):
                p = Path(path)
                self.calls.append(p.name)
                time.sleep(0.03)
                img = Image.open(p).convert("RGBA")
                return EngineResult(image=img, model_name="fake", source_path=p)

        with TemporaryDirectory() as d:
            root = Path(d)
            out = root / DEFAULT_OUTPUT_SUBDIR
            eng = Eng()
            svc = FolderWatchService(
                eng, get_export_fmt=lambda: ("png", "", "t_")  # type: ignore[arg-type]
            )
            Image.new("RGB", (8, 8), (1, 0, 0)).save(root / "old.png")
            svc.configure(
                watch_dir=root, output_dir=out, process_existing=True
            )
            svc.start()
            t0 = time.time()
            while time.time() - t0 < 4:
                app.processEvents()
                time.sleep(0.05)
                if "old.png" in eng.calls and not svc.is_busy():
                    break
            self.assertIn("old.png", eng.calls)

            # Add new files while idle (simulate user drop without waiting for auto poll)
            for i in range(3):
                Image.new("RGB", (8, 8), (i, 1, 0)).save(root / f"new{i}.png")

            # User opens settings and clicks 清空队列
            svc.clear_pending_queue()
            app.processEvents()

            # Should have re-queued the 3 new images (old is ledger-skipped)
            pending_names = {p.name for p in svc._queue}
            pending_names |= {
                pf.path.name for pf in svc._pending_stable.values()
            }
            # Either already in queue or being processed / done shortly
            t0 = time.time()
            while time.time() - t0 < 6:
                app.processEvents()
                time.sleep(0.05)
                if all(f"new{i}.png" in eng.calls for i in range(3)):
                    break
            for i in range(3):
                self.assertIn(f"new{i}.png", eng.calls, eng.calls)
            svc.stop()

    def test_new_files_after_idle_are_processed(self):
        """After first batch finishes, newly dropped files must still be picked up."""
        import os
        import sys
        import time

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QCoreApplication

        from app.engines.base import EngineResult

        app = QCoreApplication.instance() or QCoreApplication(sys.argv)

        class Eng:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def remove(self, path, source_path=None):
                p = Path(path)
                self.calls.append(p.name)
                time.sleep(0.04)
                img = Image.open(p).convert("RGBA")
                return EngineResult(image=img, model_name="fake", source_path=p)

        with TemporaryDirectory() as d:
            root = Path(d)
            out = root / DEFAULT_OUTPUT_SUBDIR
            eng = Eng()
            svc = FolderWatchService(
                eng, get_export_fmt=lambda: ("png", "", "t_")  # type: ignore[arg-type]
            )
            Image.new("RGB", (8, 8), (1, 0, 0)).save(root / "first.png")
            svc.configure(
                watch_dir=root, output_dir=out, process_existing=True
            )
            svc.start()

            def wait_idle(timeout: float = 4.0) -> None:
                t0 = time.time()
                while time.time() - t0 < timeout:
                    app.processEvents()
                    time.sleep(0.05)
                    if (
                        eng.calls
                        and not svc.is_busy()
                        and not svc._queue
                        and not svc._pending_stable
                    ):
                        # drain a bit more so timers settle
                        for _ in range(5):
                            app.processEvents()
                            time.sleep(0.05)
                        return

            wait_idle()
            self.assertIn("first.png", eng.calls)
            self.assertTrue(svc._timer.isActive())

            # Idle, then drop new files — only Qt event loop / timers (no manual poll)
            Image.new("RGB", (8, 8), (0, 1, 0)).save(root / "second.png")
            Image.new("RGB", (8, 8), (0, 0, 1)).save(root / "third.png")
            t0 = time.time()
            while time.time() - t0 < 6.0:
                app.processEvents()
                time.sleep(0.05)
                if "second.png" in eng.calls and "third.png" in eng.calls:
                    break

            self.assertIn("second.png", eng.calls, eng.calls)
            self.assertIn("third.png", eng.calls, eng.calls)
            self.assertEqual(eng.calls.count("second.png"), 1)
            self.assertEqual(eng.calls.count("third.png"), 1)
            svc.stop()

    def test_fail_does_not_block_later_files(self):
        import os
        import sys
        import time

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QCoreApplication

        from app.engines.base import EngineResult

        app = QCoreApplication.instance() or QCoreApplication(sys.argv)

        class Eng:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def remove(self, path, source_path=None):
                p = Path(path)
                self.calls.append(p.name)
                if p.name == "bad.png":
                    raise RuntimeError("simulated fail")
                img = Image.open(p).convert("RGBA")
                return EngineResult(image=img, model_name="fake", source_path=p)

        with TemporaryDirectory() as d:
            root = Path(d)
            out = root / DEFAULT_OUTPUT_SUBDIR
            eng = Eng()
            svc = FolderWatchService(
                eng, get_export_fmt=lambda: ("png", "", "t_")  # type: ignore[arg-type]
            )
            svc.configure(
                watch_dir=root, output_dir=out, process_existing=False
            )
            svc.start()

            def drain(seconds: float = 2.5) -> None:
                t0 = time.time()
                while time.time() - t0 < seconds:
                    svc._on_poll()
                    app.processEvents()
                    time.sleep(0.05)

            Image.new("RGB", (8, 8), (1, 0, 0)).save(root / "bad.png")
            drain(2.0)
            # Must not keep retrying forever
            bad_count = eng.calls.count("bad.png")
            self.assertEqual(bad_count, 1, eng.calls)

            Image.new("RGB", (8, 8), (0, 1, 0)).save(root / "good.png")
            drain(2.5)
            self.assertIn("good.png", eng.calls)
            self.assertEqual(svc._stats.success, 1)
            self.assertEqual(svc._stats.failed, 1)
            # still only one attempt on bad
            self.assertEqual(eng.calls.count("bad.png"), 1)
            svc.stop()


if __name__ == "__main__":
    unittest.main()

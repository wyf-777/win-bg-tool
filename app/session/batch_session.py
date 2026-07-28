from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.engines.local_rembg import LocalRembgEngine
from app.session.limits import MAX_DROP, MAX_FILE_BYTES, MAX_SESSION
from app.session.models import ImageItem, ItemStatus
from app.session.paths import IMAGE_EXTENSIONS, is_supported_image
from app.ui.errors import friendly_error


class _ItemWorker(QThread):
    finished_ok = Signal(str, object, str)  # id, PIL image, model
    finished_err = Signal(str, str)  # id, message

    def __init__(self, engine: LocalRembgEngine, item_id: str, path: Path, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.item_id = item_id
        self.path = path

    def run(self) -> None:
        try:
            result = self.engine.remove(self.path, source_path=self.path)
            self.finished_ok.emit(self.item_id, result.image, result.model_name)
        except Exception as exc:
            self.finished_err.emit(self.item_id, friendly_error(exc))


class BatchSession(QObject):
    """In-memory multi-image session with serial rembg queue."""

    items_changed = Signal()
    item_updated = Signal(str)
    busy_changed = Signal(bool)
    status_message = Signal(str)
    model_name_changed = Signal(str)

    def __init__(
        self,
        engine: LocalRembgEngine,
        parent=None,
        *,
        export_prefix: str = "nobg_",
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self.items: List[ImageItem] = []
        self._worker: Optional[_ItemWorker] = None
        self._export_prefix = export_prefix or "nobg_"
        self._last_model = ""

    def set_export_prefix(self, prefix: str) -> None:
        self._export_prefix = (prefix or "nobg_").strip() or "nobg_"

    # ── queries ────────────────────────────────────────────

    def count(self) -> int:
        return len(self.items)

    def is_busy(self) -> bool:
        # Prefer item queue state — worker may still report isRunning() while
        # the last finished_ok slot runs, which used to keep Export disabled.
        if any(
            i.status in (ItemStatus.QUEUED, ItemStatus.RUNNING) for i in self.items
        ):
            return True
        if self._worker is not None and self._worker.isRunning():
            return True
        return False

    def done_count(self) -> int:
        return sum(1 for i in self.items if i.status == ItemStatus.DONE)

    def failed_count(self) -> int:
        return sum(1 for i in self.items if i.status == ItemStatus.FAILED)

    def selected_items(self) -> List[ImageItem]:
        return [i for i in self.items if i.selected]

    def get(self, item_id: str) -> Optional[ImageItem]:
        for i in self.items:
            if i.id == item_id:
                return i
        return None

    def index_of(self, item_id: str) -> int:
        for idx, i in enumerate(self.items):
            if i.id == item_id:
                return idx
        return -1

    # ── mutate ─────────────────────────────────────────────

    def clear(self, *, force: bool = False) -> None:
        if self.is_busy() and not force:
            self.status_message.emit("正在处理，无法清除，请等待完成。")
            return
        for i in self.items:
            self._cleanup_item_temp(i)
        self.items.clear()
        self.items_changed.emit()
        self.busy_changed.emit(False)
        if not force:
            self.status_message.emit("已清除全部")

    def clear_selected(self) -> Tuple[int, str]:
        """
        Remove checked items. Returns (removed_count, message).
        Single-image session with no checkbox: clears that one image.
        Multi with nothing selected: removes nothing and asks user to select.
        """
        if self.is_busy():
            msg = "正在处理，无法清除，请等待完成。"
            self.status_message.emit(msg)
            return 0, msg

        if not self.items:
            return 0, "没有可清除的图片。"

        targets = [i for i in self.items if i.selected]
        if not targets:
            if len(self.items) == 1:
                # Single preview has no multi-select UI — clear the only image
                targets = list(self.items)
            else:
                msg = "请先勾选要清除的图片（可全选后清除）。"
                self.status_message.emit(msg)
                return 0, msg

        remove_ids = {i.id for i in targets}
        for item in targets:
            self._cleanup_item_temp(item)
        self.items = [i for i in self.items if i.id not in remove_ids]
        self.items_changed.emit()
        n = len(targets)
        msg = f"已清除选中 {n} 张" if n > 1 or len(self.items) > 0 else "已清除"
        if not self.items:
            msg = f"已清除选中 {n} 张（列表已空）" if n > 1 else "已清除"
        self.status_message.emit(msg)
        return n, msg

    def set_selected(self, item_id: str, selected: bool) -> None:
        item = self.get(item_id)
        if item is None:
            return
        item.selected = selected
        self.item_updated.emit(item_id)

    def select_all(self, selected: bool = True) -> None:
        for i in self.items:
            i.selected = selected
        self.items_changed.emit()

    def add_paths(self, paths: Sequence[Path | str]) -> Tuple[int, str]:
        """
        Validate and append paths. Returns (added_count, user_message).
        Enforces busy lock, MAX_DROP, MAX_SESSION.
        """
        if self.is_busy():
            msg = "当前批次仍在处理，请等待全部完成后再添加图片。"
            self.status_message.emit(msg)
            return 0, msg

        # normalize unique existing files
        cleaned: List[Path] = []
        seen = set()
        for p in paths:
            path = Path(p)
            key = str(path.resolve()) if path.exists() else str(path)
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(path)

        if not cleaned:
            return 0, "没有可添加的图片。"

        # single-drop cap
        truncated_drop = False
        if len(cleaned) > MAX_DROP:
            cleaned = cleaned[:MAX_DROP]
            truncated_drop = True

        room = MAX_SESSION - len(self.items)
        if room <= 0:
            msg = f"已达到会话上限 {MAX_SESSION} 张，请先清除或导出后删除部分图片。"
            self.status_message.emit(msg)
            return 0, msg

        truncated_session = False
        if len(cleaned) > room:
            cleaned = cleaned[:room]
            truncated_session = True

        added = 0
        skipped_msgs: List[str] = []
        for path in cleaned:
            ok, reason = self._validate_path(path)
            if not ok:
                skipped_msgs.append(f"{path.name}: {reason}")
                continue
            self.items.append(ImageItem(source_path=path.resolve()))
            added += 1

        if added:
            self.items_changed.emit()
            self._pump_queue()

        parts: List[str] = []
        if added:
            parts.append(f"已添加 {added} 张，自动处理中…")
        if truncated_drop:
            parts.append(f"单次最多 {MAX_DROP} 张，已截取。")
        if truncated_session:
            parts.append(f"会话最多 {MAX_SESSION} 张，超出部分未加入。")
        if skipped_msgs and not added:
            parts.append(skipped_msgs[0])
        elif skipped_msgs:
            parts.append(f"跳过 {len(skipped_msgs)} 个无效文件。")

        msg = " ".join(parts) if parts else "没有可添加的图片。"
        self.status_message.emit(msg)
        return added, msg

    def _validate_path(self, path: Path) -> Tuple[bool, str]:
        if not path.is_file():
            return False, "文件不存在"
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            return False, "不支持的格式"
        if not is_supported_image(path):
            return False, "不是有效图片"
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                return False, "文件过大(>80MB)"
        except OSError as exc:
            return False, str(exc)
        # skip duplicates already in session (source or existing result file)
        resolved = path.resolve()
        for i in self.items:
            try:
                if i.source_path.resolve() == resolved:
                    return False, "已在列表中"
            except OSError:
                pass
            # Drag-out drops temp result PNG back into the window
            if i.result_path is not None:
                try:
                    if i.result_path.resolve() == resolved:
                        return False, "已是本会话结果"
                except OSError:
                    pass
        return True, ""

    # ── queue ──────────────────────────────────────────────

    def _pump_queue(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        next_item = next(
            (i for i in self.items if i.status == ItemStatus.QUEUED), None
        )
        if next_item is None:
            self.busy_changed.emit(False)
            done = self.done_count()
            fail = self.failed_count()
            self.status_message.emit(
                f"全部完成 — 成功 {done}，失败 {fail}。可拖入追加，或导出。"
            )
            return

        next_item.status = ItemStatus.RUNNING
        self.item_updated.emit(next_item.id)
        self.busy_changed.emit(True)
        total = len(self.items)
        running_idx = sum(
            1
            for i in self.items
            if i.status in (ItemStatus.DONE, ItemStatus.FAILED, ItemStatus.RUNNING)
        )
        model = self.engine.model_name
        if not self.engine.is_model_file_present():
            # First use: cancelable download; user can open settings → pick local model
            self.status_message.emit(
                f"正在下载模型「{model}」…（GitHub 源可能较慢，会试镜像）"
                f"可点设置换成已下载的模型以取消。完成后处理 {next_item.name}"
            )
        elif self.engine.is_loading():
            self.status_message.emit(
                f"正在加载模型「{model}」…完成后处理 {next_item.name}"
            )
        else:
            self.status_message.emit(
                f"处理中 {running_idx}/{total}：{next_item.name}"
            )

        worker = _ItemWorker(self.engine, next_item.id, next_item.source_path, self)
        self._worker = worker
        worker.finished_ok.connect(self._on_item_ok)
        worker.finished_err.connect(self._on_item_err)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    @Slot(str, object, str)
    def _on_item_ok(self, item_id: str, image, model_name: str) -> None:
        item = self.get(item_id)
        if item is None:
            self._worker = None
            self._pump_queue()
            return
        item.result_image = image
        item.status = ItemStatus.DONE
        item.error = None
        try:
            from tempfile import gettempdir

            out = Path(gettempdir()) / f"{self._export_prefix}{item.source_path.stem}_{item.id[:6]}.png"
            image.save(out, format="PNG")
            item.result_path = out
        except Exception as exc:
            item.status = ItemStatus.FAILED
            item.error = friendly_error(exc)
            item.result_image = None

        if model_name:
            self._last_model = model_name
            self.model_name_changed.emit(model_name)

        # Drop worker ref before UI refresh so is_busy() is accurate
        self._worker = None
        self.item_updated.emit(item_id)
        self._pump_queue()

    @Slot(str, str)
    def _on_item_err(self, item_id: str, message: str) -> None:
        item = self.get(item_id)
        if item is not None:
            item.status = ItemStatus.FAILED
            item.error = message
        self._worker = None
        if item is not None:
            self.item_updated.emit(item_id)
        self._pump_queue()

    def wait_worker(self, ms: int = 5000) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(ms)

    @staticmethod
    def _cleanup_item_temp(item: ImageItem) -> None:
        if item.result_path and item.result_path.is_file():
            try:
                item.result_path.unlink(missing_ok=True)  # type: ignore[arg-type]
            except Exception:
                pass
            item.result_path = None

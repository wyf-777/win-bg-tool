"""
F13 folder watch (hot folder) — v1.2

- Output default: {watch}/已抠图 (not the watch root)
- Does not add results to the main session grid
- Ledger in app data (never under the export folder)
- Serial processing via shared LocalRembgEngine
- After idle, new drops are discovered by poll + FS watcher + reconcile
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot

from app.engines.local_rembg import LocalRembgEngine
from app.services.export import export_image
from app.session.paths import IMAGE_EXTENSIONS, is_supported_image
from app.ui.errors import friendly_error

DEFAULT_OUTPUT_SUBDIR = "已抠图"
DEFAULT_FAIL_SUBDIR = "失败"
DEFAULT_ARCHIVE_SUBDIR = "已处理"
LEDGER_DIRNAME = "watch_ledger"
POLL_MS = 400
PUMP_MS = 300
STABILITY_TICKS = 1
# If a copy keeps growing (OneDrive/下载), still force-queue after this many polls
STABILITY_FORCE_TICKS = 20
MAX_QUEUE = 64
LEDGER_MAX_ENTRIES = 5000
# Max wait for finished_ok/err after the thread exits (seconds)
JOB_RESULT_TIMEOUT_S = 8.0
IDENT_EPS = 0.002

_RESERVED_NAMES = {
    DEFAULT_OUTPUT_SUBDIR.lower(),
    DEFAULT_ARCHIVE_SUBDIR.lower(),
    DEFAULT_FAIL_SUBDIR.lower(),
}


def _app_data_dir() -> Path:
    try:
        from PySide6.QtCore import QStandardPaths

        root = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
        if root:
            path = Path(root)
            path.mkdir(parents=True, exist_ok=True)
            return path
    except Exception:
        pass
    path = Path.home() / ".win-bg-tool"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class WatchStats:
    pending: int = 0
    success: int = 0
    failed: int = 0
    last_message: str = ""
    paused: bool = False


@dataclass
class _PendingFile:
    path: Path
    last_size: int = -1
    stable_ticks: int = 0


@dataclass
class _FileIdentity:
    size: int
    mtime: float


def _file_identity(path: Path) -> Optional[_FileIdentity]:
    try:
        st = path.stat()
        return _FileIdentity(size=int(st.st_size), mtime=float(st.st_mtime))
    except OSError:
        return None


def _ident_match(a: _FileIdentity, size: int, mtime: float) -> bool:
    return a.size == size and abs(a.mtime - mtime) < IDENT_EPS


def _unique_path(dest: Path) -> Path:
    """Return dest, or dest with _1, _2, … if it already exists."""
    if not dest.exists():
        return dest
    stem, suf = dest.stem, dest.suffix
    n = 1
    while True:
        cand = dest.with_name(f"{stem}_{n}{suf}")
        if not cand.exists():
            return cand
        n += 1


class _WatchWorker(QThread):
    finished_ok = Signal(str, str, str)  # source, dest, archived_or_empty
    finished_err = Signal(str, str)

    def __init__(
        self,
        engine: LocalRembgEngine,
        source: Path,
        export_dir: Path,
        fail_dir: Path,
        *,
        fmt_id: str,
        custom_ext: str,
        prefix: str,
        archive_to: Optional[Path] = None,
        job_key: str = "",
        watch_gen: int = 0,
    ) -> None:
        super().__init__(None)  # no parent — avoid lifetime fights with deleteLater
        self.engine = engine
        self.source = source
        self.export_dir = export_dir
        self.fail_dir = fail_dir
        self.fmt_id = fmt_id
        self.custom_ext = custom_ext
        self.prefix = prefix
        self.archive_to = archive_to
        self.job_key = job_key
        self.watch_gen = watch_gen
        self.result_handled = False

    def run(self) -> None:
        try:
            result = self.engine.remove(self.source, source_path=self.source)
            self.export_dir.mkdir(parents=True, exist_ok=True)
            dest = export_image(
                result.image,
                self.export_dir,
                fmt_id=self.fmt_id,
                custom_ext=self.custom_ext,
                prefix=self.prefix,
                source_name=self.source.name,
            )
            archived = ""
            if self.archive_to is not None:
                try:
                    self.archive_to.parent.mkdir(parents=True, exist_ok=True)
                    dest_arch = _unique_path(self.archive_to)
                    shutil.move(str(self.source), str(dest_arch))
                    archived = str(dest_arch)
                except Exception:
                    archived = ""
            self.finished_ok.emit(str(self.source), str(dest), archived)
        except Exception as exc:
            msg = friendly_error(exc)
            try:
                self.fail_dir.mkdir(parents=True, exist_ok=True)
                stem = self.source.stem
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                err_path = self.fail_dir / f"{stem}_{ts}_error.txt"
                err_path.write_text(
                    f"源文件: {self.source}\n时间: {ts}\n错误: {msg}\n",
                    encoding="utf-8",
                )
                dest_src = self.fail_dir / f"{stem}_{ts}{self.source.suffix.lower()}"
                if not dest_src.exists() and self.source.is_file():
                    shutil.copy2(self.source, dest_src)
            except Exception:
                pass
            self.finished_err.emit(str(self.source), msg)


class FolderWatchService(QObject):
    status_changed = Signal(str)
    stats_changed = Signal(int, int, int)
    enabled_changed = Signal(bool)
    paused_changed = Signal(bool)

    def __init__(
        self,
        engine: LocalRembgEngine,
        parent=None,
        *,
        get_export_fmt: Optional[Callable[[], Tuple[str, str, str]]] = None,
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self._get_export_fmt = get_export_fmt or (lambda: ("png", "", "nobg_"))

        self._enabled = False
        self._paused = False
        self._watch_dir: Optional[Path] = None
        self._output_dir: Optional[Path] = None
        self._process_existing = False
        self._recursive = False
        self._archive_sources = False

        self._inflight: Set[str] = set()
        self._queue: List[Path] = []
        self._pending_stable: Dict[str, _PendingFile] = {}
        self._ledger: Dict[str, Dict[str, Any]] = {}
        # Session memory so a completed job is not re-queued before ledger flush
        self._handled_ident: Dict[str, _FileIdentity] = {}
        # job_key → meta at job start (result slots must not rely on sender())
        self._job_meta: Dict[str, Dict[str, Any]] = {}

        self._worker: Optional[_WatchWorker] = None
        self._worker_gen = 0
        self._pump_guard = False
        self._stats = WatchStats()
        self._worker_refs: Set[_WatchWorker] = set()
        self._poll_n = 0

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.setSingleShot(False)
        self._timer.timeout.connect(self._on_poll)

        self._pump_timer = QTimer(self)
        self._pump_timer.setInterval(PUMP_MS)
        self._pump_timer.setSingleShot(False)
        self._pump_timer.timeout.connect(self._on_pump_timer)

        try:
            from PySide6.QtCore import QFileSystemWatcher

            self._fs_watcher = QFileSystemWatcher(self)
            self._fs_watcher.directoryChanged.connect(self._on_dir_changed)
        except Exception:
            self._fs_watcher = None

    # ── public API ─────────────────────────────────────────

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def is_paused(self) -> bool:
        return self._paused

    def is_busy(self) -> bool:
        return self._worker_is_live()

    def stats(self) -> WatchStats:
        return WatchStats(
            pending=len(self._queue)
            + len(self._pending_stable)
            + (1 if self.is_busy() else 0),
            success=self._stats.success,
            failed=self._stats.failed,
            last_message=self._stats.last_message,
            paused=self._paused,
        )

    def status_text(self) -> str:
        if not self._enabled or self._watch_dir is None:
            return "文件夹监视：关"
        out = self.resolved_output_dir(self._watch_dir, self._output_dir)
        st = self.stats()
        flag = "已暂停" if self._paused else "监视中"
        parts = [f"{flag}：{self._watch_dir.name} → {out.name}"]
        extras = []
        if self._recursive:
            extras.append("含子目录")
        if self._archive_sources:
            extras.append("成功后归档")
        if extras:
            parts[0] += f"（{' · '.join(extras)}）"
        parts.append(
            f"待处理 {st.pending} · 成功 {st.success} · 失败 {st.failed}"
        )
        try:
            in_folder, skipped_done, skipped_fail, need_queue = self._folder_counts()
            if in_folder:
                parts.append(f"夹内 {in_folder} 张")
            if need_queue:
                parts.append(f"待入队 {need_queue}")
            if skipped_done:
                parts.append(f"已处理过跳过 {skipped_done}")
            if skipped_fail:
                parts.append(f"失败待重试 {skipped_fail}")
        except Exception:
            pass
        if st.last_message:
            parts.append(st.last_message)
        return " · ".join(parts)

    def short_badge_text(self) -> str:
        if not self._enabled:
            return ""
        st = self.stats()
        if self._paused:
            return f"监视已暂停 · 待处理 {st.pending}"
        return (
            f"监视中 · 待处理 {st.pending} · 成功 {st.success} · 失败 {st.failed}"
        )

    @staticmethod
    def default_output_dir(watch_dir: Path) -> Path:
        return Path(watch_dir) / DEFAULT_OUTPUT_SUBDIR

    @staticmethod
    def default_archive_dir(watch_dir: Path) -> Path:
        return Path(watch_dir) / DEFAULT_ARCHIVE_SUBDIR

    @staticmethod
    def fail_dir_for_output(output_dir: Path) -> Path:
        return Path(output_dir) / DEFAULT_FAIL_SUBDIR

    @staticmethod
    def resolved_output_dir(watch_dir: Path, output_dir: Optional[Path]) -> Path:
        if output_dir is not None and str(output_dir).strip():
            return Path(output_dir)
        return FolderWatchService.default_output_dir(watch_dir)

    @staticmethod
    def validate_dirs(
        watch_dir: Optional[Path], output_dir: Optional[Path]
    ) -> Tuple[bool, str]:
        if watch_dir is None or not str(watch_dir).strip():
            return False, "请先选择要监视的文件夹。"
        w = Path(watch_dir)
        if not w.is_dir():
            return False, "监视文件夹不存在。"
        out = FolderWatchService.resolved_output_dir(w, output_dir)
        try:
            if w.resolve() == out.resolve():
                return False, "输出文件夹不能与监视文件夹相同（请用子文件夹「已抠图」）。"
        except OSError as exc:
            return False, f"路径无效：{exc}"
        return True, ""

    def configure(
        self,
        *,
        watch_dir: Optional[Path],
        output_dir: Optional[Path],
        process_existing: bool = False,
        recursive: bool = False,
        archive_sources: bool = False,
    ) -> None:
        self._watch_dir = Path(watch_dir) if watch_dir else None
        self._output_dir = (
            Path(output_dir) if output_dir and str(output_dir).strip() else None
        )
        self._process_existing = bool(process_existing)
        self._recursive = bool(recursive)
        self._archive_sources = bool(archive_sources)

    def start(self) -> Tuple[bool, str]:
        ok, msg = self.validate_dirs(self._watch_dir, self._output_dir)
        if not ok:
            return False, msg
        assert self._watch_dir is not None
        out = self.resolved_output_dir(self._watch_dir, self._output_dir)
        fail = self.fail_dir_for_output(out)
        try:
            out.mkdir(parents=True, exist_ok=True)
            fail.mkdir(parents=True, exist_ok=True)
            if self._archive_sources:
                self.default_archive_dir(self._watch_dir).mkdir(
                    parents=True, exist_ok=True
                )
        except OSError as exc:
            return False, f"无法创建输出文件夹：{exc}"

        self._reset_runtime_state(bump_gen=True)
        self._enabled = True
        self._paused = False
        self._stats = WatchStats(last_message="已开启")
        self._load_ledger()

        existing = self._list_watch_images()
        n = 0
        skipped = 0
        for p in existing:
            key = self._key(p)
            if self._process_existing and key in self._ledger:
                del self._ledger[key]
            if self._should_skip_by_ledger(p):
                skipped += 1
                continue
            self._enqueue_candidate(p, force=True)
            n += 1
        if self._process_existing:
            self._save_ledger()
            self._set_msg(f"已排队约 {n} 张（含重处理已有）")
        elif n:
            extra = f"，跳过已记录 {skipped} 张" if skipped else ""
            self._set_msg(f"已排队约 {n} 张未处理图片{extra}")
        else:
            extra = (
                f"（已跳过记录 {skipped} 张）"
                if skipped
                else "，放入新图即可"
            )
            self._set_msg(f"监视中：夹内暂无新任务{extra}")

        self._refresh_fs_watcher()
        self._ensure_timers()
        self.enabled_changed.emit(True)
        self.paused_changed.emit(False)
        self._emit_status()
        self._discover_and_run()
        return True, self._stats.last_message

    def stop(self) -> None:
        self._enabled = False
        self._paused = False
        self._worker_gen += 1
        self._timer.stop()
        self._pump_timer.stop()
        self._clear_fs_watcher()
        self._reset_runtime_state(bump_gen=False)
        self._stats.last_message = "已关闭"
        self.enabled_changed.emit(False)
        self.paused_changed.emit(False)
        self._emit_status()

    def set_paused(self, paused: bool) -> None:
        if not self._enabled:
            return
        self._paused = bool(paused)
        self._set_msg("已暂停" if self._paused else "已继续")
        self.paused_changed.emit(self._paused)
        self._emit_status()
        if not self._paused:
            self._discover_and_run()

    def clear_pending_queue(self) -> int:
        """Clear waiting items, then re-queue unprocessed images still in the folder."""
        n = len(self._queue) + len(self._pending_stable)
        self._clear_wait_lists()
        self._abandon_stuck_jobs(force_all=True)
        self._set_msg(f"已清空待处理 {n} 项，正在重新扫描…")
        self._emit_status()
        queued = self.requeue_unprocessed(reason="清空后重扫")
        if queued:
            self._set_msg(f"已清空 {n} 项，重新排队未处理 {queued} 张")
        else:
            self._set_msg(f"已清空 {n} 项" + ("（夹内无待处理新图）" if n else ""))
        self._emit_status()
        return n

    def requeue_unprocessed(self, *, reason: str = "") -> int:
        """Force-queue every unhandled image in the watch folder. Returns count added."""
        if not self._enabled or self._watch_dir is None or self._paused:
            return 0
        self._ensure_timers()
        self._abandon_stuck_jobs(force_all=False)
        added = 0
        for p in self._list_watch_images():
            if self._push_path(p, force=True):
                added += 1
        if added:
            tip = f"发现待处理 {added} 张"
            if reason:
                tip = f"{reason}：{tip}"
            self._set_msg(tip)
            self._emit_status()
            self._pump()
        return added

    def list_failed_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        fails: List[Dict[str, Any]] = []
        for k, v in self._ledger.items():
            if (v or {}).get("status") != "fail":
                continue
            ent = dict(v or {})
            ent["path"] = k
            fails.append(ent)
        fails.sort(key=lambda e: float(e.get("mtime", 0)), reverse=True)
        return fails[:limit]

    def retry_failed(self, limit: int = 20) -> int:
        if not self._enabled or self._watch_dir is None:
            return 0
        n = 0
        for ent in self.list_failed_entries(limit=limit * 2):
            if n >= limit:
                break
            raw = (ent.get("path") or "").strip()
            if not raw:
                continue
            p = Path(raw)
            if not p.is_file():
                continue
            key = self._key(p)
            self._ledger.pop(key, None)
            if raw != key:
                self._ledger.pop(raw, None)
            self._handled_ident.pop(key, None)
            if self._push_path(p, force=True):
                n += 1
        if n:
            self._save_ledger()
            self._set_msg(f"已重新排队失败 {n} 项")
            self._emit_status()
            self._discover_and_run()
        return n

    def open_fail_dir(self) -> Optional[Path]:
        if self._watch_dir is None:
            return None
        out = self.resolved_output_dir(self._watch_dir, self._output_dir)
        fail = self.fail_dir_for_output(out)
        fail.mkdir(parents=True, exist_ok=True)
        return fail

    def open_output_dir(self) -> Optional[Path]:
        if self._watch_dir is None:
            return None
        out = self.resolved_output_dir(self._watch_dir, self._output_dir)
        out.mkdir(parents=True, exist_ok=True)
        return out

    def open_archive_dir(self) -> Optional[Path]:
        if self._watch_dir is None:
            return None
        d = self.default_archive_dir(self._watch_dir)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def notify_engine_idle(self) -> None:
        if self._enabled and not self._paused:
            self._discover_and_run()

    # ── internal: lifecycle helpers ────────────────────────

    def _reset_runtime_state(self, *, bump_gen: bool) -> None:
        if bump_gen:
            self._worker_gen += 1
        self._queue.clear()
        self._pending_stable.clear()
        self._inflight.clear()
        self._handled_ident.clear()
        self._job_meta.clear()
        old = self._worker
        self._worker = None
        if old is not None:
            self._worker_refs.discard(old)

    def _clear_wait_lists(self) -> None:
        for p in self._queue:
            self._inflight.discard(self._key(p))
        for key in self._pending_stable:
            self._inflight.discard(key)
        self._queue.clear()
        self._pending_stable.clear()

    def _set_msg(self, msg: str) -> None:
        self._stats.last_message = msg

    def _emit_status(self) -> None:
        self._emit_stats()
        self.status_changed.emit(self.status_text())

    def _emit_stats(self) -> None:
        st = self.stats()
        self.stats_changed.emit(st.pending, st.success, st.failed)

    def _ensure_timers(self) -> None:
        if not self._enabled:
            return
        if not self._timer.isActive():
            self._timer.start(POLL_MS)
        if not self._pump_timer.isActive():
            self._pump_timer.start(PUMP_MS)

    def _schedule_discover(self) -> None:
        if self._enabled and not self._paused:
            QTimer.singleShot(0, self._discover_and_run)

    def _discover_and_run(self) -> None:
        if not self._enabled or self._paused:
            return
        self._ensure_timers()
        self._abandon_stuck_jobs(force_all=False)
        self._cleanup_idle_inflight()
        self._scan_new_files()
        self._tick_stability()
        if (
            not self._queue
            and not self._pending_stable
            and not self._worker_is_live()
        ):
            try:
                *_rest, need = self._folder_counts()
            except Exception:
                need = 0
            if need > 0:
                self.requeue_unprocessed(reason="自动补扫")
                return
        self._pump()

    # ── ledger ─────────────────────────────────────────────

    def _ledger_path(self) -> Optional[Path]:
        if self._watch_dir is None:
            return None
        try:
            w = str(self._watch_dir.resolve()).lower()
            o = str(
                self.resolved_output_dir(self._watch_dir, self._output_dir).resolve()
            ).lower()
        except OSError:
            w = str(self._watch_dir).lower()
            o = str(self.resolved_output_dir(self._watch_dir, self._output_dir)).lower()
        digest = hashlib.sha1(f"{w}|{o}".encode("utf-8")).hexdigest()[:16]
        folder = _app_data_dir() / LEDGER_DIRNAME
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{digest}.json"

    def _load_ledger(self) -> None:
        self._ledger = {}
        path = self._ledger_path()
        if path is None or not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entries = data.get("entries") or {}
            if isinstance(entries, dict):
                self._ledger = {str(k).lower(): v for k, v in entries.items()}
        except Exception:
            self._ledger = {}

    def _save_ledger(self) -> None:
        path = self._ledger_path()
        if path is None:
            return
        if len(self._ledger) > LEDGER_MAX_ENTRIES:
            items = sorted(
                self._ledger.items(),
                key=lambda kv: float((kv[1] or {}).get("mtime", 0)),
                reverse=True,
            )
            self._ledger = dict(items[: LEDGER_MAX_ENTRIES // 2])
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {"version": 1, "entries": self._ledger},
                    ensure_ascii=False,
                    indent=0,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _should_skip_by_ledger(self, path: Path) -> bool:
        """Skip when this exact size+mtime was already ok/fail."""
        key = self._key(path)
        ident = _file_identity(path)
        if ident is None:
            return False
        handled = self._handled_ident.get(key)
        if handled is not None and _ident_match(handled, ident.size, ident.mtime):
            return True
        ent = self._ledger.get(key)
        if not ent or ent.get("status") not in ("ok", "fail"):
            return False
        try:
            return _ident_match(
                _FileIdentity(int(ent.get("size", -1)), float(ent.get("mtime", 0))),
                ident.size,
                ident.mtime,
            )
        except (TypeError, ValueError):
            return False

    def _mark_handled(
        self,
        path: Path,
        *,
        status: str,
        dest: str = "",
        error: str = "",
        job_key: str = "",
    ) -> None:
        key = (job_key or self._key(path)).lower()
        meta = self._job_meta.pop(key, None) or {}
        ident = meta.get("ident")
        if not isinstance(ident, _FileIdentity):
            ident = _file_identity(path)
        if ident is not None:
            self._handled_ident[key] = ident
        self._ledger[key] = {
            "size": ident.size if ident else 0,
            "mtime": ident.mtime if ident else 0.0,
            "status": status,
            "dest": dest,
            "error": error,
            "name": path.name,
        }
        self._save_ledger()

    # ── paths / scan ───────────────────────────────────────

    def _key(self, path: Path) -> str:
        try:
            return str(path.resolve()).lower()
        except OSError:
            return str(path).lower()

    @staticmethod
    def _is_under(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _is_reserved_tree(self, path: Path) -> bool:
        if self._watch_dir is None:
            return False
        try:
            wr = self._watch_dir.resolve()
            pr = path.resolve()
        except OSError:
            return False
        out = self.resolved_output_dir(self._watch_dir, self._output_dir)
        try:
            or_ = out.resolve()
            if pr == or_ or self._is_under(pr, or_):
                return True
        except OSError:
            pass
        for name in (DEFAULT_ARCHIVE_SUBDIR, DEFAULT_OUTPUT_SUBDIR, DEFAULT_FAIL_SUBDIR):
            try:
                sub = (wr / name).resolve()
                if pr == sub or self._is_under(pr, sub):
                    return True
            except OSError:
                continue
        return False

    def _list_watch_images(self) -> List[Path]:
        if self._watch_dir is None or not self._watch_dir.is_dir():
            return []
        results: List[Path] = []
        try:
            iterator = (
                self._watch_dir.rglob("*")
                if self._recursive
                else self._watch_dir.iterdir()
            )
            for p in iterator:
                if not is_supported_image(p):
                    continue
                if self._is_reserved_tree(p):
                    continue
                try:
                    rel = p.relative_to(self._watch_dir)
                    if any(part.lower() in _RESERVED_NAMES for part in rel.parts[:-1]):
                        continue
                except ValueError:
                    pass
                results.append(p)
        except OSError:
            pass
        return results

    def _export_dir_for(self, source: Path) -> Path:
        assert self._watch_dir is not None
        out_root = self.resolved_output_dir(self._watch_dir, self._output_dir)
        if not self._recursive:
            return out_root
        try:
            return out_root / source.relative_to(self._watch_dir).parent
        except ValueError:
            return out_root

    def _archive_path_for(self, source: Path) -> Optional[Path]:
        if not self._archive_sources or self._watch_dir is None:
            return None
        arch_root = self.default_archive_dir(self._watch_dir)
        try:
            return arch_root / source.relative_to(self._watch_dir)
        except ValueError:
            return arch_root / source.name

    def _folder_counts(self) -> Tuple[int, int, int, int]:
        """(in_folder, skipped_done, skipped_fail, need_queue)."""
        in_folder = skipped_done = skipped_fail = need_queue = 0
        busy = self._busy_keys()
        for p in self._list_watch_images():
            in_folder += 1
            key = self._key(p)
            if self._should_skip_by_ledger(p):
                ent = self._ledger.get(key) or {}
                if ent.get("status") == "fail":
                    skipped_fail += 1
                else:
                    skipped_done += 1
                continue
            if key not in busy:
                need_queue += 1
        return in_folder, skipped_done, skipped_fail, need_queue

    def _busy_keys(self) -> Set[str]:
        keys = set(self._pending_stable.keys())
        keys |= {self._key(p) for p in self._queue}
        if self._worker_is_live() and isinstance(self._worker, _WatchWorker):
            if self._worker.job_key:
                keys.add(self._worker.job_key)
        return keys

    def _path_already_waiting(self, key: str) -> bool:
        if key in self._pending_stable:
            return True
        if any(self._key(q) == key for q in self._queue):
            return True
        if (
            self._worker_is_live()
            and isinstance(self._worker, _WatchWorker)
            and self._worker.job_key == key
        ):
            return True
        if key in self._inflight:
            return True
        return False

    def _push_path(self, path: Path, *, force: bool) -> bool:
        """Try to place path into pending/queue. Returns True if newly accepted."""
        key = self._key(path)
        if self._path_already_waiting(key):
            return False
        if self._should_skip_by_ledger(path):
            return False
        try:
            size = path.stat().st_size
        except OSError:
            return False
        if size <= 0:
            return False
        if force:
            if len(self._queue) < MAX_QUEUE:
                self._queue.append(path)
                self._inflight.add(key)
            else:
                self._pending_stable[key] = _PendingFile(
                    path=path, last_size=size, stable_ticks=STABILITY_TICKS
                )
            return True
        self._pending_stable[key] = _PendingFile(
            path=path, last_size=size, stable_ticks=0
        )
        return True

    def _enqueue_candidate(self, path: Path, *, force: bool) -> None:
        """Public-ish helper used by start/retry; wraps _push_path."""
        self._push_path(path, force=force)

    # ── FS watcher / timers ────────────────────────────────

    def _refresh_fs_watcher(self) -> None:
        self._clear_fs_watcher()
        if self._fs_watcher is None or self._watch_dir is None:
            return
        try:
            paths = [str(self._watch_dir.resolve())]
            if self._recursive:
                for p in self._watch_dir.iterdir():
                    if (
                        p.is_dir()
                        and p.name.lower() not in _RESERVED_NAMES
                        and not self._is_reserved_tree(p)
                    ):
                        paths.append(str(p.resolve()))
            self._fs_watcher.addPaths(paths)
        except Exception:
            pass

    def _clear_fs_watcher(self) -> None:
        if self._fs_watcher is None:
            return
        try:
            watched = list(self._fs_watcher.directories() or [])
            if watched:
                self._fs_watcher.removePaths(watched)
        except Exception:
            pass

    @Slot(str)
    def _on_dir_changed(self, _path: str) -> None:
        if self._enabled and not self._paused:
            try:
                self._discover_and_run()
            except Exception as exc:
                self._set_msg(f"监视目录变更异常：{exc}")
                self._emit_stats()

    @Slot()
    def _on_poll(self) -> None:
        if not self._enabled:
            return
        if self._paused:
            if self._worker is not None and not self._worker_is_live():
                self._retire_worker(self._worker)
            return
        try:
            self._poll_n += 1
            if self._poll_n % 25 == 0:
                self._refresh_fs_watcher()
            self._discover_and_run()
        except Exception as exc:
            self._set_msg(f"监视扫描异常：{exc}")
            self._emit_stats()
            self._ensure_timers()

    @Slot()
    def _on_pump_timer(self) -> None:
        if not self._enabled or self._paused:
            return
        try:
            # Always try to advance — _pump handles stuck-worker recovery
            self._tick_stability()
            self._pump()
            if not self._queue and not self._pending_stable and not self._worker_is_live():
                self._scan_new_files()
                self._tick_stability()
                self._pump()
        except Exception:
            pass

    def _scan_new_files(self) -> None:
        found = 0
        idle = not self._worker_is_live() and not self._queue
        for p in self._list_watch_images():
            if self._push_path(p, force=idle):
                found += 1
        if found and not self.is_busy():
            self._set_msg(f"发现新图 {found} 张，准备处理…")
            self._emit_status()

    def _tick_stability(self) -> None:
        done_keys: List[str] = []
        for key, pf in list(self._pending_stable.items()):
            try:
                if not pf.path.is_file():
                    done_keys.append(key)
                    continue
                size = int(pf.path.stat().st_size)
            except OSError:
                done_keys.append(key)
                continue
            if size <= 0:
                pf.stable_ticks = 0
                pf.last_size = size
                continue
            # age every poll so downloads that keep growing still eventually queue
            pf.stable_ticks += 1
            size_stable = size == pf.last_size
            pf.last_size = size
            ready = size_stable and pf.stable_ticks >= STABILITY_TICKS
            if not ready and pf.stable_ticks >= STABILITY_FORCE_TICKS:
                ready = True  # force after ~8s of waiting
            if not ready:
                continue
            if len(self._queue) < MAX_QUEUE:
                self._queue.append(pf.path)
                self._inflight.add(key)
                done_keys.append(key)
            else:
                self._set_msg(f"队列已满（{MAX_QUEUE}），稍后自动继续")
        for k in done_keys:
            self._pending_stable.pop(k, None)
        if done_keys:
            self._emit_stats()

    # ── worker pipeline ────────────────────────────────────

    def _worker_is_live(self) -> bool:
        w = self._worker
        if w is None:
            return False
        try:
            return bool(w.isRunning())
        except RuntimeError:
            self._worker = None
            return False

    def _job_still_waiting(self, key: str) -> bool:
        meta = self._job_meta.get(key)
        return bool(meta) and not meta.get("done")

    def _mark_worker_result_handled(self, key: str) -> None:
        """Flag every worker object for this job (sender() is unreliable)."""
        for w in list(self._worker_refs):
            if isinstance(w, _WatchWorker) and w.job_key == key:
                w.result_handled = True
        if (
            isinstance(self._worker, _WatchWorker)
            and self._worker.job_key == key
        ):
            self._worker.result_handled = True

    def _abandon_stuck_jobs(self, *, force_all: bool) -> None:
        """Free jobs whose result callback never arrived (unblocks 待处理 N 空转)."""
        now = time.time()
        freed = False
        for key, meta in list(self._job_meta.items()):
            if meta.get("done"):
                # Keep done entries briefly; drop when worker cleared
                continue
            started = float(meta.get("t0", 0) or 0)
            aged = (now - started) if started else JOB_RESULT_TIMEOUT_S + 1
            if force_all or aged >= JOB_RESULT_TIMEOUT_S:
                self._job_meta.pop(key, None)
                self._inflight.discard(key)
                self._mark_worker_result_handled(key)
                freed = True
        if self._worker is not None and not self._worker_is_live():
            w = self._worker
            if force_all:
                self._retire_worker(w)
            elif isinstance(w, _WatchWorker):
                # Retire if result applied or job no longer waiting
                if w.result_handled or not self._job_still_waiting(w.job_key):
                    self._retire_worker(w)
        if freed and self._queue:
            self._set_msg("任务结果超时，继续处理队列…")

    def _cleanup_idle_inflight(self) -> None:
        if self._worker_is_live():
            return
        awaiting = {k for k, m in self._job_meta.items() if not m.get("done")}
        live = (
            {self._key(p) for p in self._queue}
            | set(self._pending_stable.keys())
            | awaiting
        )
        if isinstance(self._worker, _WatchWorker) and self._worker.job_key:
            live.add(self._worker.job_key)
        orphan = self._inflight - live
        if orphan:
            self._inflight -= orphan
        if self._worker is not None and not self._worker_is_live():
            w = self._worker
            if isinstance(w, _WatchWorker) and (
                w.result_handled or not self._job_still_waiting(w.job_key)
            ):
                self._retire_worker(w)

    def _retire_worker(self, worker: Optional[object]) -> None:
        if worker is None:
            return
        if self._worker is worker:
            self._worker = None
        if isinstance(worker, _WatchWorker):
            self._worker_refs.discard(worker)
        try:
            worker.deleteLater()  # type: ignore[union-attr]
        except (RuntimeError, AttributeError):
            pass

    def _pump(self) -> None:
        if not self._enabled or self._paused or self._pump_guard:
            return
        self._pump_guard = True
        try:
            self._ensure_timers()
            # Always try to free timed-out jobs first (was: early-return deadlock)
            self._abandon_stuck_jobs(force_all=False)

            if self._worker is not None and not self._worker_is_live():
                w = self._worker
                if isinstance(w, _WatchWorker) and self._job_still_waiting(w.job_key):
                    # finished_ok/err still in flight — wait (until timeout above)
                    self._set_msg(f"等待结果回调…（队列 {len(self._queue)}）")
                    return
                self._retire_worker(w)

            if self._worker_is_live():
                return
            if any(not m.get("done") for m in self._job_meta.values()):
                # Undone meta without a live worker — only block briefly
                self._abandon_stuck_jobs(force_all=False)
                if any(not m.get("done") for m in self._job_meta.values()):
                    return
            if not self._queue or self._watch_dir is None:
                return

            path = self._queue.pop(0)
            key = self._key(path)
            if not path.is_file() or self._should_skip_by_ledger(path):
                self._inflight.discard(key)
                self._emit_stats()
                self._schedule_discover()
                return

            export_dir = self._export_dir_for(path)
            fail = self.fail_dir_for_output(
                self.resolved_output_dir(self._watch_dir, self._output_dir)
            )
            fmt_id, custom_ext, prefix = self._get_export_fmt()
            archive_to = self._archive_path_for(path)
            self._set_msg(f"处理中 {path.name}")
            self._emit_status()

            self._job_meta[key] = {
                "gen": self._worker_gen,
                "ident": _file_identity(path),
                "done": False,
                "t0": time.time(),
            }
            worker = _WatchWorker(
                self.engine,
                path,
                export_dir,
                fail,
                fmt_id=fmt_id,
                custom_ext=custom_ext,
                prefix=prefix,
                archive_to=archive_to,
                job_key=key,
                watch_gen=self._worker_gen,
            )
            self._worker = worker
            self._worker_refs.add(worker)
            worker.finished_ok.connect(self._on_ok, Qt.ConnectionType.QueuedConnection)
            worker.finished_err.connect(self._on_err, Qt.ConnectionType.QueuedConnection)
            worker.finished.connect(
                self._on_worker_thread_finished, Qt.ConnectionType.QueuedConnection
            )
            worker.start()
        finally:
            self._pump_guard = False

    def _consume_job_result(self, source: str) -> Optional[str]:
        key = self._key(Path(source))
        meta = self._job_meta.get(key)
        if not meta or meta.get("done"):
            return None
        if meta.get("gen") != self._worker_gen:
            self._job_meta.pop(key, None)
            self._inflight.discard(key)
            return None
        meta["done"] = True
        return key

    @Slot(str, str, str)
    def _on_ok(self, source: str, dest: str, archived: str) -> None:
        key = self._consume_job_result(source)
        if key is None:
            return
        self._mark_worker_result_handled(key)
        sp = Path(source)
        self._inflight.discard(key)
        self._mark_handled(sp, status="ok", dest=dest, job_key=key)
        if archived:
            self._mark_handled(Path(archived), status="ok", dest=dest)
        self._stats.success += 1
        self._set_msg(f"完成 {sp.name}")
        self._emit_status()
        # Free worker so next item can start immediately
        if (
            isinstance(self._worker, _WatchWorker)
            and self._worker.job_key == key
            and not self._worker_is_live()
        ):
            self._retire_worker(self._worker)
        self._schedule_discover()

    @Slot(str, str)
    def _on_err(self, source: str, message: str) -> None:
        key = self._consume_job_result(source)
        if key is None:
            return
        self._mark_worker_result_handled(key)
        sp = Path(source)
        self._inflight.discard(key)
        self._mark_handled(sp, status="fail", error=message, job_key=key)
        self._stats.failed += 1
        self._set_msg(f"失败 {sp.name}：{message}")
        self._emit_status()
        if (
            isinstance(self._worker, _WatchWorker)
            and self._worker.job_key == key
            and not self._worker_is_live()
        ):
            self._retire_worker(self._worker)
        self._schedule_discover()

    @Slot()
    def _on_worker_thread_finished(self) -> None:
        """
        Thread ended. Do NOT clear job_meta here — finished can race ahead of
        finished_ok/err; popping meta early caused lost results and stuck queues.
        """
        worker = self.sender()
        if not isinstance(worker, _WatchWorker):
            worker = self._worker if isinstance(self._worker, _WatchWorker) else None
        self._ensure_timers()
        if worker is None:
            QTimer.singleShot(0, self._pump)
            return
        # If result already applied, drop worker and continue queue now
        if worker.result_handled or (
            worker.job_key and not self._job_still_waiting(worker.job_key)
        ):
            self._retire_worker(worker)
            if self._queue:
                QTimer.singleShot(0, self._pump)
            else:
                QTimer.singleShot(0, self._discover_and_run)
            return
        # Result callback still pending: leave meta/worker until ok/err or timeout
        QTimer.singleShot(100, self._pump)

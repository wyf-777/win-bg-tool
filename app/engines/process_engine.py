"""
UI-side engine: subprocess host for rembg.

Self-healing (Chrome-like process model, simplified):
- Detect worker death on RPC / spawn
- Auto-restart with short backoff (max N times per window)
- Circuit open → surface error; next user action can try again
- Intentional kills (model cancel, app exit) do not count as crashes
- After heal, clear session so next warmup/remove reloads the model
"""

from __future__ import annotations

import atexit
import io
import multiprocessing as mp
import threading
import time
from pathlib import Path
from queue import Empty
from typing import Callable, List, Optional, Union

from PIL import Image

from app.engines.base import BackgroundEngine, EngineResult
from app.engines.models_catalog import DEFAULT_MODEL_ID, product_default_model_id
from app.engines.process_worker import run_worker
from app.runtime_paths import models_dir as default_models_dir

ProgressCb = Callable[[str], None]
# event: restarting | recovered | gave_up | info
HealthCb = Callable[[str, str], None]

_RPC_TIMEOUT = 600.0
_POLL = 0.25

# Supervisor limits (mature apps: finite restarts, not infinite loops)
_MAX_CRASHES = 3
_CRASH_WINDOW_SEC = 90.0
_BACKOFF_SEC = (0.25, 0.6, 1.2)


class ProcessRembgEngine(BackgroundEngine):
    """BackgroundEngine backed by a dedicated inference process + supervisor."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        *,
        models_dir: Optional[Path] = None,
        post_process_mask: bool = True,
        alpha_matting: bool = False,
        prefer_accel: bool = False,
    ) -> None:
        self._requested_model = (
            model_name or product_default_model_id() or DEFAULT_MODEL_ID
        ).strip()
        self._active_model: Optional[str] = None
        self._models_dir = Path(models_dir) if models_dir else default_models_dir()
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self.post_process_mask = post_process_mask
        self.alpha_matting = alpha_matting
        self._prefer_accel = bool(prefer_accel)
        self._device_label = "普通模式"
        self._last_accel_note = ""
        self._loading = False
        self._loading_op: Optional[str] = None  # "warmup" | "remove" | None
        self._progress_cb: Optional[ProgressCb] = None
        self._health_cb: Optional[HealthCb] = None
        self._config_gen = 0

        self._ctx = mp.get_context("spawn")
        self._req_q: mp.Queue = self._ctx.Queue()
        self._res_q: mp.Queue = self._ctx.Queue()
        self._proc: Optional[mp.Process] = None
        self._rpc_lock = threading.RLock()
        self._next_id = 0
        self._started = False
        self._shutting_down = False

        # Supervisor state
        self._last_kill_intentional = False
        self._crash_times: List[float] = []
        self._restart_count_total = 0
        self._circuit_open = False
        self._had_live_process = False  # True after first successful hello

        atexit.register(self.shutdown)

    # ── health / supervisor ────────────────────────────────

    def set_health_callback(self, cb: Optional[HealthCb]) -> None:
        """UI hook: (event, message) from any thread."""
        self._health_cb = cb

    def _notify_health(self, event: str, message: str) -> None:
        cb = self._health_cb
        if cb:
            try:
                cb(event, message)
            except Exception:
                pass

    def reset_circuit(self) -> None:
        """User-driven recovery after gave_up (e.g. drop image / apply model)."""
        self._circuit_open = False
        self._crash_times.clear()

    def _prune_crashes(self) -> None:
        now = time.monotonic()
        self._crash_times = [
            t for t in self._crash_times if now - t < _CRASH_WINDOW_SEC
        ]

    def _register_unexpected_death(self) -> bool:
        """
        Record a crash. Returns True if auto-restart is still allowed.
        """
        if self._shutting_down or self._last_kill_intentional:
            self._last_kill_intentional = False
            return True  # intentional / exit — allow next ensure without counting
        self._prune_crashes()
        self._crash_times.append(time.monotonic())
        self._restart_count_total += 1
        if len(self._crash_times) > _MAX_CRASHES:
            self._circuit_open = True
            return False
        return True

    def _backoff_seconds(self) -> float:
        n = max(0, len(self._crash_times) - 1)
        if n >= len(_BACKOFF_SEC):
            return _BACKOFF_SEC[-1]
        return _BACKOFF_SEC[n]

    # ── lifecycle ──────────────────────────────────────────

    def _kill_process(self, *, intentional: bool = True) -> None:
        self._last_kill_intentional = intentional
        proc = self._proc
        self._proc = None
        self._started = False
        if proc is None:
            return
        try:
            if proc.is_alive():
                try:
                    self._req_q.put_nowait({"cmd": "shutdown"})
                except Exception:
                    pass
                proc.join(timeout=0.15)
                if proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=0.15)
                if proc.is_alive():
                    try:
                        proc.kill()
                    except Exception:
                        pass
        except Exception:
            pass

    def _spawn_process(self) -> None:
        self._req_q = self._ctx.Queue()
        self._res_q = self._ctx.Queue()
        self._proc = self._ctx.Process(
            target=run_worker,
            args=(
                self._req_q,
                self._res_q,
                str(self._models_dir.resolve()),
                self._requested_model,
                self._prefer_accel,
            ),
            name="peel-engine-worker",
            daemon=True,
        )
        self._proc.start()

    def _wait_hello(self) -> None:
        for _ in range(max(int(_RPC_TIMEOUT / _POLL), 1)):
            if self._shutting_down:
                raise RuntimeError("引擎正在关闭")
            try:
                msg = self._res_q.get(timeout=_POLL)
            except Empty:
                if self._proc is None or not self._proc.is_alive():
                    raise RuntimeError("推理进程意外退出")
                continue
            if msg.get("type") == "progress":
                self._emit_progress(msg.get("message") or "")
                continue
            if msg.get("type") == "hello":
                if not msg.get("ok"):
                    raise RuntimeError(msg.get("error") or "推理进程启动失败")
                self._started = True
                self._had_live_process = True
                self._active_model = None  # cold process — must re-warm
                return
        raise TimeoutError("推理进程启动超时")

    def _ensure_process(self) -> None:
        if self._shutting_down:
            raise RuntimeError("引擎正在关闭")
        if self._proc is not None and self._proc.is_alive():
            return

        # Dead after we once had a live worker, and not an intentional kill → crash
        intentional = self._last_kill_intentional
        self._last_kill_intentional = False
        recovering = self._had_live_process and not intentional and not self._shutting_down

        if recovering:
            if self._circuit_open:
                raise RuntimeError(
                    "推理引擎多次异常退出，已暂停自动恢复。"
                    "请稍后重试（再拖入图片或重新应用模型）。"
                )
            if not self._register_unexpected_death():
                self._notify_health(
                    "gave_up",
                    "推理引擎反复崩溃，已停止自动重启。请重启 Peel 或稍后再试。",
                )
                raise RuntimeError(
                    "推理引擎多次异常退出，已暂停自动恢复。请重启 Peel。"
                )
            attempt = len(self._crash_times)
            delay = self._backoff_seconds()
            self._notify_health(
                "restarting",
                f"推理进程异常，正在自动恢复（{attempt}/{_MAX_CRASHES}）…",
            )
            time.sleep(delay)

        if self._circuit_open:
            raise RuntimeError(
                "推理引擎已熔断，请稍后重试或重启 Peel。"
            )

        own_loading = self._loading_op is None
        if own_loading:
            self._loading = True
            self._loading_op = "warmup"
        try:
            self._spawn_process()
            self._wait_hello()
            if recovering:
                self._notify_health(
                    "recovered",
                    "推理进程已恢复，将重新加载模型…",
                )
        finally:
            if own_loading:
                self._loading = False
                self._loading_op = None

    def shutdown(self) -> None:
        self._shutting_down = True
        self._config_gen += 1
        try:
            self._kill_process(intentional=True)
        except Exception:
            pass

    def shutdown_async(self) -> None:
        self._shutting_down = True
        self._config_gen += 1

        def _run() -> None:
            try:
                self._kill_process(intentional=True)
            except Exception:
                pass

        threading.Thread(target=_run, name="peel-engine-shutdown", daemon=True).start()

    def _emit_progress(self, msg: str) -> None:
        cb = self._progress_cb
        if cb and msg:
            try:
                cb(msg)
            except Exception:
                pass

    def _is_process_death_error(self, exc: BaseException) -> bool:
        text = str(exc)
        return any(
            k in text
            for k in (
                "意外退出",
                "已退出",
                "启动失败",
                "启动超时",
                "熔断",
                "多次异常",
            )
        )

    def _rpc(
        self,
        cmd: str,
        *,
        expect_gen: Optional[int] = None,
        _retry: bool = True,
        **kwargs,
    ) -> dict:
        try:
            return self._rpc_once(cmd, expect_gen=expect_gen, **kwargs)
        except Exception as exc:
            if (
                not _retry
                or self._shutting_down
                or not self._is_process_death_error(exc)
            ):
                raise
            # Heal once and retry the same command (Chrome-style one-shot recovery)
            self._active_model = None
            self._started = False
            self._proc = None
            self._notify_health(
                "restarting",
                "推理进程无响应，正在自动恢复并重试…",
            )
            # ensure_process will spawn; mark as unexpected if not intentional
            self._last_kill_intentional = False
            return self._rpc_once(cmd, expect_gen=expect_gen, **kwargs)

    def _rpc_once(
        self, cmd: str, *, expect_gen: Optional[int] = None, **kwargs
    ) -> dict:
        self._ensure_process()
        with self._rpc_lock:
            if expect_gen is not None and expect_gen != self._config_gen:
                raise RuntimeError("操作已取消（配置已变更）")
            self._next_id += 1
            rid = self._next_id
            try:
                self._req_q.put({"id": rid, "cmd": cmd, **kwargs})
            except Exception as exc:
                raise RuntimeError(f"无法向推理进程发送命令: {exc}") from exc
            for _ in range(max(int(_RPC_TIMEOUT / _POLL), 1)):
                if expect_gen is not None and expect_gen != self._config_gen:
                    raise RuntimeError("操作已取消（配置已变更）")
                if self._shutting_down:
                    raise RuntimeError("引擎正在关闭")
                try:
                    msg = self._res_q.get(timeout=_POLL)
                except Empty:
                    if self._proc is None or not self._proc.is_alive():
                        raise RuntimeError("推理进程已退出")
                    continue
                if msg.get("type") == "progress":
                    self._emit_progress(str(msg.get("message") or ""))
                    continue
                if msg.get("type") == "hello":
                    continue
                if msg.get("id") != rid:
                    continue
                if not msg.get("ok"):
                    raise RuntimeError(msg.get("error") or f"{cmd} failed")
                return msg
            # Timeout — treat as death for heal path
            if self._proc is not None and self._proc.is_alive():
                self._kill_process(intentional=False)
            raise RuntimeError("推理进程已退出")

    # ── BackgroundEngine API ───────────────────────────────

    def set_progress_callback(self, cb: Optional[ProgressCb]) -> None:
        self._progress_cb = cb

    @property
    def model_name(self) -> str:
        return self._active_model or self._requested_model or DEFAULT_MODEL_ID

    @property
    def models_dir(self) -> Path:
        return self._models_dir

    @property
    def device_label(self) -> str:
        return self._device_label or "普通模式"

    @property
    def last_accel_note(self) -> str:
        return self._last_accel_note or ""

    def is_loading(self) -> bool:
        return self._loading

    def model_path(self, model_name: Optional[str] = None) -> Path:
        name = (model_name or self._requested_model or DEFAULT_MODEL_ID).strip()
        return self._models_dir / f"{name}.onnx"

    def is_model_file_present(self, model_name: Optional[str] = None) -> bool:
        path = self.model_path(model_name)
        try:
            return path.is_file() and path.stat().st_size > 1024
        except OSError:
            return False

    def set_model(self, model_name: str) -> None:
        name = (model_name or DEFAULT_MODEL_ID).strip()
        if name == self._requested_model:
            return
        self._requested_model = name

        if self._loading_op == "remove":
            return

        self._active_model = None
        if self._loading_op == "warmup":
            self._config_gen += 1
            threading.Thread(
                target=lambda: self._kill_process(intentional=True),
                name="peel-cancel-warmup",
                daemon=True,
            ).start()

    def set_alpha_matting(self, enabled: bool) -> None:
        self.alpha_matting = bool(enabled)

    def set_prefer_accel(self, enabled: bool) -> None:
        on = bool(enabled)
        if on == self._prefer_accel:
            return
        self._prefer_accel = on
        if self._loading_op == "remove":
            return
        self._active_model = None
        if self._loading_op == "warmup":
            self._config_gen += 1
            threading.Thread(
                target=lambda: self._kill_process(intentional=True),
                name="peel-cancel-accel",
                daemon=True,
            ).start()

    def warmup(self) -> None:
        self.reset_circuit()  # user/system intent to use engine again
        while not self._shutting_down:
            gen = self._config_gen
            model = self._requested_model
            self._loading = True
            self._loading_op = "warmup"
            try:
                msg = self._rpc(
                    "warmup",
                    expect_gen=gen,
                    model=model,
                    prefer_accel=self._prefer_accel,
                    alpha_matting=self.alpha_matting,
                )
                if gen != self._config_gen:
                    continue
                self._active_model = str(msg.get("model") or model)
                self._device_label = str(msg.get("device_label") or "普通模式")
                self._last_accel_note = str(msg.get("accel_note") or "")
                return
            except RuntimeError as exc:
                text = str(exc)
                if self._shutting_down:
                    raise
                if gen != self._config_gen or "已取消" in text:
                    if gen != self._config_gen:
                        continue
                if self._is_process_death_error(exc) and not self._circuit_open:
                    # _rpc already retried once; if still failing, surface
                    raise
                raise
            finally:
                if self._loading_op == "warmup":
                    self._loading = False
                    self._loading_op = None

    def remove(
        self,
        source: Union[str, Path, bytes, Image.Image],
        *,
        source_path: Optional[Path] = None,
    ) -> EngineResult:
        if isinstance(source, Image.Image):
            raise TypeError("ProcessRembgEngine.remove 需要文件路径，不支持内存图像")
        if isinstance(source, (bytes, bytearray)):
            raise TypeError("ProcessRembgEngine.remove 需要文件路径，不支持 bytes")
        path = Path(source_path or source)

        self.reset_circuit()
        self._loading = True
        self._loading_op = "remove"
        try:
            if self._active_model != self._requested_model:
                self._warm_for_remove(self._requested_model)

            msg = self._rpc(
                "remove",
                path=str(path.resolve()),
                post_process_mask=self.post_process_mask,
                alpha_matting=self.alpha_matting,
            )
            png = msg.get("png") or b""
            img = Image.open(io.BytesIO(png))
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            model = str(msg.get("model") or self.model_name)
            self._active_model = model
            return EngineResult(image=img, model_name=model, source_path=path)
        finally:
            self._loading = False
            self._loading_op = None

    def _warm_for_remove(self, model: str) -> None:
        gen = self._config_gen
        msg = self._rpc(
            "warmup",
            expect_gen=gen,
            model=model,
            prefer_accel=self._prefer_accel,
            alpha_matting=self.alpha_matting,
        )
        self._active_model = str(msg.get("model") or model)
        self._device_label = str(msg.get("device_label") or "普通模式")
        self._last_accel_note = str(msg.get("accel_note") or "")

"""
Inference worker process — the ONLY place rembg/onnx should be imported.

UI process talks via multiprocessing queues so CPython GIL import stalls
never freeze the Qt main thread.
"""

from __future__ import annotations

import io
import traceback
from pathlib import Path
from typing import Any


def run_worker(
    req_q: Any,
    res_q: Any,
    models_dir: str,
    model_name: str,
    prefer_accel: bool,
) -> None:
    """Blocking loop: read commands, run LocalRembgEngine, write responses."""
    try:
        # Heavy imports isolated to this process
        from app.engines.local_rembg import LocalRembgEngine

        engine = LocalRembgEngine(
            model_name=model_name or "u2netp",
            models_dir=Path(models_dir),
            prefer_accel=bool(prefer_accel),
        )

        def _progress(msg: str) -> None:
            try:
                res_q.put({"type": "progress", "message": str(msg)})
            except Exception:
                pass

        engine.set_progress_callback(_progress)
        res_q.put(
            {
                "type": "hello",
                "ok": True,
                "model": engine.model_name,
            }
        )
    except Exception as exc:
        res_q.put(
            {
                "type": "hello",
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc(),
            }
        )
        return

    while True:
        try:
            req = req_q.get()
        except Exception:
            break
        if req is None:
            break
        if not isinstance(req, dict):
            continue
        if req.get("cmd") == "shutdown":
            break

        rid = req.get("id")
        cmd = req.get("cmd")
        try:
            if cmd == "warmup":
                if req.get("model"):
                    engine.set_model(str(req["model"]))
                if "prefer_accel" in req:
                    engine.set_prefer_accel(bool(req["prefer_accel"]))
                if "alpha_matting" in req:
                    engine.set_alpha_matting(bool(req["alpha_matting"]))
                engine.warmup()
                res_q.put(
                    {
                        "id": rid,
                        "ok": True,
                        "cmd": "warmup",
                        "model": engine.model_name,
                        "device_label": engine.device_label,
                        "accel_note": engine.last_accel_note,
                    }
                )
            elif cmd == "remove":
                path = Path(str(req["path"]))
                if "post_process_mask" in req:
                    engine.post_process_mask = bool(req["post_process_mask"])
                if "alpha_matting" in req:
                    engine.alpha_matting = bool(req["alpha_matting"])
                result = engine.remove(path, source_path=path)
                buf = io.BytesIO()
                result.image.save(buf, format="PNG")
                res_q.put(
                    {
                        "id": rid,
                        "ok": True,
                        "cmd": "remove",
                        "png": buf.getvalue(),
                        "model": result.model_name,
                    }
                )
            elif cmd == "set_model":
                engine.set_model(str(req.get("model") or "u2netp"))
                res_q.put({"id": rid, "ok": True, "cmd": "set_model"})
            elif cmd == "set_prefer_accel":
                engine.set_prefer_accel(bool(req.get("enabled")))
                res_q.put({"id": rid, "ok": True, "cmd": "set_prefer_accel"})
            elif cmd == "set_alpha":
                engine.set_alpha_matting(bool(req.get("enabled")))
                res_q.put({"id": rid, "ok": True, "cmd": "set_alpha"})
            elif cmd == "ping":
                res_q.put(
                    {
                        "id": rid,
                        "ok": True,
                        "cmd": "ping",
                        "model": engine.model_name,
                        "device_label": engine.device_label,
                        "loading": engine.is_loading(),
                    }
                )
            else:
                res_q.put(
                    {
                        "id": rid,
                        "ok": False,
                        "error": f"unknown cmd: {cmd}",
                    }
                )
        except Exception as exc:
            res_q.put(
                {
                    "id": rid,
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "trace": traceback.format_exc(),
                }
            )

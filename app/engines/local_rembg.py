from __future__ import annotations

import hashlib
import io
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional, Union

from PIL import Image

from app.engines.models_catalog import DEFAULT_MODEL_ID, FALLBACK_MODEL_IDS
from app.engines.runtime_accel import (
    CPU_PROVIDERS,
    describe_active_providers,
    is_accel_provider_list,
    resolve_providers,
)
from .base import BackgroundEngine, EngineResult

ProgressCb = Callable[[str], None]


class DownloadCancelled(Exception):
    """Model download aborted because the user switched models (or gen bumped)."""


def _project_models_dir() -> Path:
    root = Path(__file__).resolve().parents[2]
    path = root / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def model_part_path(model_id: str, models_dir: Optional[Path] = None) -> Path:
    """Path of in-progress download for a model (.onnx.part)."""
    d = Path(models_dir) if models_dir else _project_models_dir()
    return d / f"{(model_id or '').strip()}.onnx.part"


def partial_download_bytes(
    model_id: str, models_dir: Optional[Path] = None
) -> int:
    """Bytes already saved in .part (0 if none). Used for resume / UI."""
    p = model_part_path(model_id, models_dir)
    try:
        if p.is_file():
            return int(p.stat().st_size)
    except OSError:
        pass
    return 0


def is_model_partial(
    model_id: str, models_dir: Optional[Path] = None
) -> bool:
    """True if a non-empty incomplete download exists (can resume)."""
    return partial_download_bytes(model_id, models_dir) > 1024


def cleanup_interrupted_downloads(models_dir: Optional[Path] = None) -> int:
    """
    Startup cleanup: remove pooch tmp* and *empty* .part files only.
    Non-empty .part files are kept so the next launch can resume.
    """
    d = Path(models_dir) if models_dir else _project_models_dir()
    if not d.is_dir():
        return 0
    removed = 0
    for p in d.iterdir():
        if not p.is_file():
            continue
        name = p.name
        try:
            if name.startswith("tmp") and p.suffix == "":
                p.unlink()
                removed += 1
            elif name.endswith(".part") and p.stat().st_size <= 1024:
                p.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def delete_incomplete_downloads(models_dir: Optional[Path] = None) -> int:
    """
    User-requested: delete all incomplete downloads (*.part) so they restart
    from zero next time. Does not delete finished .onnx files.
    """
    d = Path(models_dir) if models_dir else _project_models_dir()
    if not d.is_dir():
        return 0
    removed = 0
    for p in d.iterdir():
        if not p.is_file():
            continue
        name = p.name
        if name.endswith(".part") or (name.startswith("tmp") and p.suffix == ""):
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def _mirror_urls(url: str) -> List[str]:
    """
    Candidate URLs. For GitHub Releases, try mirrors *first* — direct github.com
    often stalls at 0 bytes in some networks and never fails until timeout.
    """
    custom: List[str] = []
    raw = (os.environ.get("PEEL_MODEL_MIRROR") or "").strip()
    if raw:
        if raw.endswith("/") and url.startswith("http"):
            custom.append(raw + url)
        elif "{url}" in raw:
            custom.append(raw.replace("{url}", url))
        else:
            custom.append(raw.rstrip("/") + "/" + url)

    mirrors: List[str] = []
    if "github.com" in url:
        for prefix in (
            "https://ghfast.top/",
            "https://gh-proxy.com/",
            "https://mirror.ghproxy.com/",
            "https://gitdl.cn/",
        ):
            mirrors.append(prefix + url)

    # Default: mirrors → direct. PEEL_MODEL_DIRECT_FIRST=1 → direct first.
    direct_first = (os.environ.get("PEEL_MODEL_DIRECT_FIRST") or "").strip() in (
        "1",
        "true",
        "yes",
    )
    if direct_first:
        ordered = custom + [url] + mirrors
    else:
        ordered = custom + mirrors + [url]

    # de-dupe preserve order
    seen = set()
    out: List[str] = []
    for u in ordered:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _file_md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _parse_known_hash(known_hash: Optional[str]) -> Optional[tuple[str, str]]:
    if not known_hash:
        return None
    if ":" in known_hash:
        algo, value = known_hash.split(":", 1)
        return algo.lower(), value.lower()
    return "md5", known_hash.lower()


def _hash_matches(path: Path, known_hash: Optional[str]) -> bool:
    parsed = _parse_known_hash(known_hash)
    if parsed is None:
        return True
    algo, expect = parsed
    if algo != "md5":
        return True
    try:
        return _file_md5(path) == expect
    except OSError:
        return False


def _apply_socket_timeout(resp, timeout: float) -> None:
    """Best-effort: set read timeout on the underlying socket."""
    try:
        sock = resp.fp.raw._sock  # type: ignore[attr-defined]
        sock.settimeout(timeout)
    except Exception:
        try:
            resp.fp.raw._sock.settimeout(timeout)  # type: ignore[attr-defined]
        except Exception:
            pass


def _parse_content_range_total(header: Optional[str]) -> int:
    """Parse total size from Content-Range: bytes start-end/total."""
    if not header:
        return 0
    # e.g. "bytes 100-200/5000" or "bytes 100-200/*"
    try:
        total_s = header.strip().split("/")[-1]
        if total_s == "*":
            return 0
        return int(total_s)
    except (ValueError, IndexError):
        return 0


def _download_url_to(
    url: str,
    dest: Path,
    *,
    cancel_check: Callable[[], bool],
    progress_cb: Optional[ProgressCb] = None,
    # Small chunks so slow links (10–30 KB/s) still complete each read
    # before stall_timeout; large chunks were mis-detected as “卡住”.
    chunk_size: int = 64 * 1024,
    connect_timeout: float = 20.0,
    stall_timeout: float = 90.0,
) -> None:
    """
    Stream download with cancel, stall timeout, progress, and **resume**.
    Incomplete data is kept in ``dest.part`` so the next run / next mirror
    can continue with HTTP Range (if the server supports it).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    existing = 0
    if part.is_file():
        try:
            existing = int(part.stat().st_size)
        except OSError:
            existing = 0
        if existing <= 0:
            try:
                part.unlink()
            except OSError:
                pass
            existing = 0

    headers = {
        "User-Agent": "Peel-win-bg-tool/1.0 (model-download)",
        "Accept": "*/*",
    }
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"

    req = urllib.request.Request(url, headers=headers, method="GET")
    fname = dest.name
    try:
        with urllib.request.urlopen(req, timeout=connect_timeout) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            # Server ignored Range → full body; restart file
            if existing > 0 and code == 200:
                print(
                    f"[Peel] 源不支持断点，重新下载 {fname}",
                    flush=True,
                )
                existing = 0
                try:
                    part.unlink()
                except OSError:
                    pass
            elif existing > 0 and code not in (206, 200):
                raise RuntimeError(f"断点续传失败 HTTP {code}")

            total = 0
            if code == 206:
                total = _parse_content_range_total(
                    resp.headers.get("Content-Range")
                )
                if total <= 0:
                    try:
                        remain = int(resp.headers.get("Content-Length") or 0)
                        total = existing + remain if remain else 0
                    except (TypeError, ValueError):
                        total = 0
            else:
                try:
                    total = int(resp.headers.get("Content-Length") or 0)
                except (TypeError, ValueError):
                    total = 0

            _apply_socket_timeout(resp, stall_timeout)
            done = existing  # absolute bytes on disk
            session_got = 0  # bytes in this HTTP response
            last_log = 0.0
            t0 = time.monotonic()
            mode = "ab" if existing > 0 and code == 206 else "wb"
            if mode == "wb":
                done = 0
                existing = 0

            with part.open(mode) as out:
                while True:
                    if cancel_check():
                        # Keep .part for resume next time
                        raise DownloadCancelled(
                            "已暂停下载（下次继续或可清理未完成）"
                        )
                    try:
                        chunk = resp.read(chunk_size)
                    except socket.timeout as exc:
                        raise TimeoutError(
                            f"超过 {stall_timeout:.0f}s 无数据，换源重试"
                        ) from exc
                    except TimeoutError:
                        raise
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    session_got += len(chunk)
                    now = time.monotonic()
                    if now - last_log >= 1.2:
                        last_log = now
                        elapsed = max(now - t0, 0.001)
                        speed = session_got / elapsed  # B/s this session
                        tag = "续传" if existing > 0 else "下载"
                        if total > 0:
                            pct = 100.0 * done / total
                            msg = (
                                f"{tag} {fname}: {done / 1e6:.1f}/{total / 1e6:.1f} MB"
                                f" ({pct:.0f}%)  {speed / 1024:.0f} KB/s"
                            )
                        else:
                            msg = (
                                f"{tag} {fname}: {done / 1e6:.1f} MB"
                                f"  {speed / 1024:.0f} KB/s"
                            )
                        print(f"[Peel] {msg}", flush=True)
                        if progress_cb:
                            try:
                                progress_cb(msg)
                            except Exception:
                                pass

            if done <= 0 and session_got <= 0:
                raise RuntimeError("服务器返回空文件")
            if total > 0 and done < total * 0.98:
                # Keep .part — incomplete, will resume
                raise RuntimeError(
                    f"下载不完整: {done}/{total} bytes，保留进度换源/下次续传"
                )

        if dest.exists():
            try:
                dest.unlink()
            except OSError:
                pass
        part.replace(dest)
    except DownloadCancelled:
        # Intentionally keep .part for resume
        raise
    except Exception:
        # Keep non-empty .part so we can resume; drop useless empty files
        try:
            if part.is_file() and part.stat().st_size <= 1024:
                part.unlink()
        except OSError:
            pass
        raise


def _cancelable_pooch_retrieve(
    url: str,
    known_hash: Optional[str] = None,
    fname: Optional[str] = None,
    path: Optional[Union[str, os.PathLike]] = None,
    processor=None,
    downloader=None,
    progressbar: bool = False,
    *,
    cancel_check: Callable[[], bool],
    progress_cb: Optional[ProgressCb] = None,
) -> str:
    """
    Drop-in replacement for pooch.retrieve used while loading rembg sessions.
    Supports cancel + GitHub mirrors (mirrors first) + stall failover.
    """
    del processor, downloader, progressbar
    if not fname:
        fname = url.rstrip("/").split("/")[-1]
    base = Path(path) if path else _project_models_dir()
    dest = base / fname

    if dest.is_file() and dest.stat().st_size > 1024 and _hash_matches(dest, known_hash):
        return str(dest)

    if dest.is_file() and not _hash_matches(dest, known_hash):
        try:
            dest.unlink()
        except OSError:
            pass

    errors: List[str] = []
    candidates = _mirror_urls(url)
    for i, try_url in enumerate(candidates, 1):
        if cancel_check():
            raise DownloadCancelled("用户切换了模型，已取消下载")
        try:
            line = f"[Peel] 下载模型: {fname}  ({i}/{len(candidates)})\n       ← {try_url}"
            print(line, flush=True)
            if progress_cb:
                try:
                    progress_cb(f"下载 {fname}… 源 {i}/{len(candidates)}")
                except Exception:
                    pass
            _download_url_to(
                try_url,
                dest,
                cancel_check=cancel_check,
                progress_cb=progress_cb,
            )
            if known_hash and not _hash_matches(dest, known_hash):
                try:
                    dest.unlink()
                except OSError:
                    pass
                errors.append(f"{try_url}: 校验失败")
                print(f"[Peel] 校验失败，换源…", flush=True)
                continue
            print(
                f"[Peel] 下载完成: {dest} ({dest.stat().st_size} bytes)",
                flush=True,
            )
            if progress_cb:
                try:
                    progress_cb(f"模型已下载: {fname}")
                except Exception:
                    pass
            return str(dest)
        except DownloadCancelled:
            raise
        except Exception as exc:
            errors.append(f"{try_url}: {exc}")
            print(f"[Peel] 该源失败，换下一个: {exc}", flush=True)
            continue

    raise RuntimeError(
        "模型下载失败（已尝试镜像与直连）。\n" + "\n".join(errors[:8])
    )


class LocalRembgEngine(BackgroundEngine):
    """On-device background removal via rembg + ONNX Runtime."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        *,
        models_dir: Optional[Path] = None,
        post_process_mask: bool = True,
        alpha_matting: bool = False,
        prefer_accel: bool = False,
    ) -> None:
        self._requested_model = model_name or DEFAULT_MODEL_ID
        self._active_model: Optional[str] = None
        self._session = None
        self._session_gen = 0  # bump on set_model to discard stale warmup loads
        self._models_dir = Path(models_dir) if models_dir else _project_models_dir()
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self.post_process_mask = post_process_mask
        self.alpha_matting = alpha_matting
        # F14: soft preference; never hard-fail if GPU missing
        self._prefer_accel = bool(prefer_accel)
        self._force_cpu = False  # set after a failed GPU session load this run
        self._active_providers: list[str] = list(CPU_PROVIDERS)
        self._last_accel_note = ""  # short status for UI
        os.environ.setdefault("U2NET_HOME", str(self._models_dir.resolve()))
        # Serialize download + ONNX load: warmup and worker must not download in parallel
        self._load_lock = threading.RLock()
        # Serialize inference so session UI queue and folder-watch never run remove() together
        self._infer_lock = threading.RLock()
        self._loading = False
        self._download_note = ""  # last human-readable download status
        self._progress_cb: Optional[ProgressCb] = None

    def set_progress_callback(self, cb: Optional[ProgressCb]) -> None:
        """Optional UI hook: receives short Chinese progress strings (any thread)."""
        self._progress_cb = cb

    @property
    def model_name(self) -> str:
        return self._active_model or self._requested_model or DEFAULT_MODEL_ID

    @property
    def models_dir(self) -> Path:
        return self._models_dir

    def is_loading(self) -> bool:
        return self._loading

    def model_path(self, model_name: Optional[str] = None) -> Path:
        """Expected ONNX path under U2NET_HOME (rembg/pooch naming)."""
        name = (model_name or self._requested_model or DEFAULT_MODEL_ID).strip()
        return self._models_dir / f"{name}.onnx"

    def is_model_file_present(self, model_name: Optional[str] = None) -> bool:
        path = self.model_path(model_name)
        try:
            return path.is_file() and path.stat().st_size > 1024
        except OSError:
            return False

    def set_model(self, model_name: str) -> None:
        """
        Switch model; drops current ONNX session so next remove reloads.
        Bumping gen cancels any in-flight download within one chunk (~256KB).
        """
        name = (model_name or DEFAULT_MODEL_ID).strip()
        if name == self._requested_model and self._session is not None:
            return
        self._requested_model = name
        self._session = None
        self._active_model = None
        self._session_gen += 1  # cancel current download

    def set_alpha_matting(self, enabled: bool) -> None:
        self.alpha_matting = bool(enabled)

    def set_prefer_accel(self, enabled: bool) -> None:
        """Soft GPU preference. Drops session so next remove reloads providers."""
        on = bool(enabled)
        if on == self._prefer_accel and self._session is not None and not self._force_cpu:
            return
        self._prefer_accel = on
        # Allow retry of GPU after user re-enables or toggles
        if on:
            self._force_cpu = False
        self._session = None
        self._active_model = None
        self._session_gen += 1
        self._last_accel_note = ""

    @property
    def prefer_accel(self) -> bool:
        return self._prefer_accel

    @property
    def active_providers(self) -> list[str]:
        return list(self._active_providers)

    @property
    def device_label(self) -> str:
        """Short Chinese label for chrome (普通模式 / 加速 · …)."""
        return describe_active_providers(self._active_providers)

    @property
    def last_accel_note(self) -> str:
        return self._last_accel_note or ""

    def warmup(self) -> None:
        self._ensure_session()

    def _create_session(self, name: str, providers: list[str]):
        from rembg import new_session

        return new_session(name, providers=list(providers))

    def _ensure_session(self):
        # Fast path
        if self._session is not None:
            return self._session

        with self._load_lock:
            if self._session is not None:
                return self._session

            import pooch

            candidates: list[str] = []
            if self._requested_model:
                candidates.append(self._requested_model)
            for name in FALLBACK_MODEL_IDS:
                if name not in candidates:
                    candidates.append(name)

            gen = self._session_gen
            last_error: Optional[Exception] = None
            self._loading = True
            original_retrieve = pooch.retrieve

            def cancel_check() -> bool:
                return gen != self._session_gen

            def retrieve_proxy(*args, **kwargs):
                return _cancelable_pooch_retrieve(
                    *args,
                    **kwargs,
                    cancel_check=cancel_check,
                    progress_cb=self._progress_cb,
                )

            providers = resolve_providers(
                self._prefer_accel, force_cpu=self._force_cpu
            )

            try:
                pooch.retrieve = retrieve_proxy  # type: ignore[assignment]
                for name in candidates:
                    if cancel_check():
                        # Model switched mid-ensure — load the new request
                        return self._ensure_session()
                    try:
                        self._purge_bad_model_file(name)
                        self._download_note = f"loading:{name}"
                        session = None
                        used_providers = list(providers)
                        try:
                            session = self._create_session(name, used_providers)
                        except Exception as gpu_exc:
                            # Soft fallback: accel request failed → pure CPU once
                            if is_accel_provider_list(used_providers):
                                print(
                                    f"[Peel] 加速加载失败，改用普通模式: {gpu_exc}",
                                    flush=True,
                                )
                                self._force_cpu = True
                                used_providers = list(CPU_PROVIDERS)
                                self._last_accel_note = (
                                    "加速不可用，已自动改用普通模式（不影响使用）。"
                                )
                                if self._progress_cb:
                                    try:
                                        self._progress_cb(self._last_accel_note)
                                    except Exception:
                                        pass
                                session = self._create_session(name, used_providers)
                            else:
                                raise
                        if gen != self._session_gen:
                            try:
                                del session
                            except Exception:
                                pass
                            return self._ensure_session()
                        self._session = session
                        self._active_model = name
                        self._active_providers = used_providers
                        self._download_note = ""
                        if not self._last_accel_note:
                            if is_accel_provider_list(used_providers):
                                self._last_accel_note = (
                                    f"已启用{describe_active_providers(used_providers)}。"
                                )
                            else:
                                self._last_accel_note = "当前为普通模式。"
                        return self._session
                    except DownloadCancelled:
                        if gen != self._session_gen:
                            return self._ensure_session()
                        last_error = DownloadCancelled("下载已取消")
                        continue
                    except Exception as exc:
                        last_error = exc
                        self._session = None
                        self._active_model = None
                        self._purge_bad_model_file(name, force=True)
                        continue
            finally:
                pooch.retrieve = original_retrieve  # type: ignore[assignment]
                self._loading = False

            raise RuntimeError(
                f"无法加载 rembg 模型（尝试: {', '.join(candidates)}）。"
                f" 最后错误: {last_error}"
            )

    def _purge_bad_model_file(self, model_name: str, *, force: bool = False) -> None:
        """Remove empty/tiny/force-corrupt onnx so the next download is clean."""
        path = self.model_path(model_name)
        if not path.is_file():
            return
        try:
            size = path.stat().st_size
        except OSError:
            return
        if force or size < 1_000_000:
            try:
                path.unlink()
            except OSError:
                pass

    def remove(
        self,
        source: Union[str, Path, bytes, Image.Image],
        *,
        source_path: Optional[Path] = None,
    ) -> EngineResult:
        from rembg import remove

        with self._infer_lock:
            session = self._ensure_session()
            image, path = self._load_image(source, source_path)

            out = remove(
                image,
                session=session,
                post_process_mask=self.post_process_mask,
                alpha_matting=self.alpha_matting,
            )
            if not isinstance(out, Image.Image):
                out = Image.open(io.BytesIO(out))
            if out.mode != "RGBA":
                out = out.convert("RGBA")

            return EngineResult(
                image=out,
                model_name=self.model_name,
                source_path=path,
            )

    @staticmethod
    def _load_image(
        source: Union[str, Path, bytes, Image.Image],
        source_path: Optional[Path],
    ) -> tuple[Image.Image, Optional[Path]]:
        if isinstance(source, Image.Image):
            img = source.convert("RGBA") if source.mode != "RGBA" else source.copy()
            return img, source_path

        if isinstance(source, (bytes, bytearray)):
            img = Image.open(io.BytesIO(source))
            img = _exif_transpose(img)
            return img.convert("RGBA"), source_path

        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"找不到图片: {path}")
        img = Image.open(path)
        img = _exif_transpose(img)
        return img.convert("RGBA"), path.resolve()


def _exif_transpose(img: Image.Image) -> Image.Image:
    from PIL import ImageOps

    try:
        return ImageOps.exif_transpose(img)
    except Exception:
        return img

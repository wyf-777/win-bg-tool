"""
GPU / accel detection for ONNX Runtime — user-facing, fail-safe.

Design:
  - Default path is always CPU (everyone works).
  - Prefer-GPU is a soft preference: if accel is missing or fails, use CPU.
  - No CUDA jargon in user-facing strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

# Prefer order when multiple are present
_ACCEL_PROVIDER_ORDER: Tuple[str, ...] = (
    "CUDAExecutionProvider",  # NVIDIA
    "DmlExecutionProvider",  # Windows DirectML (AMD / Intel / some NVIDIA)
    "ROCMExecutionProvider",  # AMD ROCm
    "CoreMLExecutionProvider",  # Apple
)

_PROVIDER_LABELS = {
    "CUDAExecutionProvider": "独立显卡（NVIDIA）",
    "DmlExecutionProvider": "图形加速（DirectML）",
    "ROCMExecutionProvider": "独立显卡（AMD ROCm）",
    "CoreMLExecutionProvider": "Apple 加速",
    "CPUExecutionProvider": "普通模式",
}

CPU_PROVIDERS: List[str] = ["CPUExecutionProvider"]


@dataclass(frozen=True)
class AccelStatus:
    """Snapshot of what this machine can do right now."""

    available: bool
    providers: Tuple[str, ...]  # accel providers only (no CPU)
    all_providers: Tuple[str, ...]
    # Short Chinese for UI (no jargon)
    summary: str
    detail: str


def _safe_available_providers() -> List[str]:
    try:
        import onnxruntime as ort

        return list(ort.get_available_providers() or [])
    except Exception:
        return list(CPU_PROVIDERS)


def list_accel_providers(available: Optional[Sequence[str]] = None) -> List[str]:
    """Accel providers present on this install, in preference order."""
    avail = list(available) if available is not None else _safe_available_providers()
    found: List[str] = []
    for name in _ACCEL_PROVIDER_ORDER:
        if name in avail:
            found.append(name)
    return found


def provider_label(provider: str) -> str:
    return _PROVIDER_LABELS.get(provider, provider)


def detect_accel() -> AccelStatus:
    """
    Silent capability probe. Safe to call at startup / settings open.
    Does not load models or touch the GPU heavily.
    """
    all_p = tuple(_safe_available_providers())
    accel = tuple(list_accel_providers(all_p))
    if not accel:
        return AccelStatus(
            available=False,
            providers=(),
            all_providers=all_p,
            summary="普通模式",
            detail=(
                "当前未检测到可用的加速组件，将使用普通模式处理。"
                "这是默认且最稳妥的方式，所有电脑都可正常使用。"
            ),
        )
    labels = "、".join(provider_label(p) for p in accel)
    return AccelStatus(
        available=True,
        providers=accel,
        all_providers=all_p,
        summary=f"可加速（{labels}）",
        detail=(
            f"检测到：{labels}。"
            "开启「更快处理」后，抠图会尽量用加速；若失败会自动改回普通模式。"
        ),
    )


def resolve_providers(
    prefer_accel: bool,
    *,
    force_cpu: bool = False,
) -> List[str]:
    """
    Providers list for rembg new_session(..., providers=...).

    prefer_accel=False or force_cpu → CPU only.
    prefer_accel=True and accel present → [accel..., CPU] (CPU as fallback chain).
    prefer_accel=True but no accel → CPU only.
    """
    if force_cpu or not prefer_accel:
        return list(CPU_PROVIDERS)
    accel = list_accel_providers()
    if not accel:
        return list(CPU_PROVIDERS)
    # ORT tries providers in order; keep CPU last as safety net
    out = list(accel)
    if "CPUExecutionProvider" not in out:
        out.append("CPUExecutionProvider")
    return out


def is_accel_provider_list(providers: Sequence[str]) -> bool:
    """True if the list intends to use something beyond pure CPU-first."""
    if not providers:
        return False
    return providers[0] != "CPUExecutionProvider"


def describe_active_providers(providers: Sequence[str]) -> str:
    if not providers:
        return "普通模式"
    first = providers[0]
    if first == "CPUExecutionProvider":
        return "普通模式"
    return f"加速 · {provider_label(first)}"

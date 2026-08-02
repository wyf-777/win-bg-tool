"""Catalog of rembg models exposed in Settings (id + Chinese description)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence


@dataclass(frozen=True)
class ModelInfo:
    id: str
    label: str
    skill: str  # what it's good at
    note: str = ""  # size / speed / caveats


# Order = display order in settings. First is product default recommendation.
# Exclude *custom* and sam (need extra paths / prompts).
MODEL_CATALOG: Sequence[ModelInfo] = (
    ModelInfo(
        "isnet-general-use",
        "ISNet 通用（推荐）",
        "日常通用抠图：商品、人物、静物都较稳，边缘通常比经典 u2net 更好。",
        "体积较大；首次使用需下载模型。",
    ),
    ModelInfo(
        "u2net",
        "U²-Net 经典通用",
        "经典通用分割，兼容性好，适合大多数场景的保底选择。",
        "效果略逊于 ISNet / BiRefNet 新模型。",
    ),
    ModelInfo(
        "u2netp",
        "U²-Net 轻量",
        "更快、更小，适合预览、批量赶速度或机器配置较低时。",
        "细节和边缘通常弱于完整 u2net。",
    ),
    ModelInfo(
        "silueta",
        "Silueta 精简通用",
        "体积更小的通用模型，在效果与体积之间折中。",
        "约数十 MB 级。",
    ),
    ModelInfo(
        "u2net_human_seg",
        "U²-Net 人像",
        "专为人像/半身像优化，证件照、人像抠图优先试这个。",
        "非人主体（纯商品、风景）可能不如通用模型。",
    ),
    ModelInfo(
        "isnet-anime",
        "ISNet 动漫",
        "二次元/插画角色分割，线条与色块边界更合适。",
        "写实照片请用通用或人像模型。",
    ),
    ModelInfo(
        "u2net_cloth_seg",
        "U²-Net 服装解析",
        "服装区域解析（上装/下装/全身等），适合服饰类图，不是普通整图抠背景。",
        "用途特殊，普通去背景请用通用模型。",
    ),
    ModelInfo(
        "birefnet-general",
        "BiRefNet 通用",
        "新一代通用高质分割，复杂边缘、精细主体往往更干净。",
        "模型更大、首次下载更久。",
    ),
    ModelInfo(
        "birefnet-general-lite",
        "BiRefNet 通用轻量",
        "BiRefNet 的轻量版，在速度与质量间折中。",
        "比完整 BiRefNet 更快一些。",
    ),
    ModelInfo(
        "birefnet-portrait",
        "BiRefNet 肖像",
        "肖像/人像专用，发丝与面部轮廓表现通常更好。",
        "偏人像场景。",
    ),
    ModelInfo(
        "birefnet-dis",
        "BiRefNet DIS",
        "二值/显著物体分割（DIS 路线），主体与背景对比清晰时效果好。",
        "适合前景主体明确的图。",
    ),
    ModelInfo(
        "birefnet-hrsod",
        "BiRefNet 高分辨率显著物",
        "高分辨率显著物体检测场景，大图细节更友好。",
        "大图、细节多时可试。",
    ),
    ModelInfo(
        "birefnet-cod",
        "BiRefNet 隐蔽物体",
        "隐蔽/低对比主体（COD），主体与背景颜色接近时可能更好。",
        "普通高对比图用通用即可。",
    ),
    ModelInfo(
        "birefnet-massive",
        "BiRefNet 大规模训练",
        "更大数据集训练的通用向模型，追求极限质量时可对比试用。",
        "体积与下载成本更高。",
    ),
    ModelInfo(
        "bria-rmbg",
        "BRIA RMBG",
        "BRIA 背景去除向模型，商用抠图观感，通用去背景质量高。",
        "首次需下载；体积可能较大。",
    ),
)

DEFAULT_MODEL_ID = "isnet-general-use"

# Fallback chain when requested model fails to load
FALLBACK_MODEL_IDS: Sequence[str] = (
    "isnet-general-use",
    "u2net",
    "u2netp",
)


def catalog_ids() -> List[str]:
    return [m.id for m in MODEL_CATALOG]


def get_model_info(model_id: str) -> Optional[ModelInfo]:
    for m in MODEL_CATALOG:
        if m.id == model_id:
            return m
    return None


def is_known_model(model_id: str) -> bool:
    return get_model_info(model_id) is not None


def default_models_dir() -> Path:
    """Project models/ directory (same as rembg U2NET_HOME for this app)."""
    # app/engines/models_catalog.py → project root / models
    root = Path(__file__).resolve().parents[2]
    path = root / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_model_downloaded(
    model_id: str, models_dir: Optional[Path] = None
) -> bool:
    """True if rembg onnx file for *model_id* is already on disk."""
    mid = (model_id or "").strip()
    if not mid:
        return False
    d = Path(models_dir) if models_dir else default_models_dir()
    path = d / f"{mid}.onnx"
    try:
        return path.is_file() and path.stat().st_size > 1024
    except OSError:
        return False


def is_model_partial(
    model_id: str, models_dir: Optional[Path] = None
) -> bool:
    """True if incomplete .part exists (resume available)."""
    mid = (model_id or "").strip()
    if not mid or is_model_downloaded(mid, models_dir):
        return False
    d = Path(models_dir) if models_dir else default_models_dir()
    part = d / f"{mid}.onnx.part"
    try:
        return part.is_file() and part.stat().st_size > 1024
    except OSError:
        return False


def model_download_status(
    model_id: str, models_dir: Optional[Path] = None
) -> str:
    """One of: downloaded | partial | missing."""
    if is_model_downloaded(model_id, models_dir):
        return "downloaded"
    if is_model_partial(model_id, models_dir):
        return "partial"
    return "missing"


def model_combo_label(info: ModelInfo, *, status: Optional[str] = None) -> str:
    """
    Display label for settings combo.
    Status prefix first so first CJK char aligns (all prefixes 3 chars):
    已下载 / 未下完 / 未下载
    """
    st = status or model_download_status(info.id)
    if st == "downloaded":
        prefix = "已下载"
    elif st == "partial":
        prefix = "未下完"
    else:
        prefix = "未下载"
    return f"{prefix}  ·  {info.label}"

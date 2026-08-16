use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

pub const DEFAULT_MODEL: &str = "u2netp";
pub const MAX_SESSION: usize = 48;
pub const MAX_DROP: usize = 24;
pub const MAX_FILE_BYTES: u64 = 80 * 1024 * 1024;

pub const IMAGE_EXTENSIONS: &[&str] = &["png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff", "gif"];

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum ItemStatus {
    Queued,
    Running,
    Done,
    Failed,
}

#[derive(Debug, Clone)]
pub struct ItemRecord {
    pub id: String,
    pub source_path: PathBuf,
    pub status: ItemStatus,
    /// One-shot model selection used by a manual reprocess request.
    pub model_override: Option<String>,
    pub error: Option<String>,
    pub result_path: Option<PathBuf>,
    pub source_preview: String,
    pub result_preview: Option<String>,
    pub model: Option<String>,
    pub width: u32,
    pub height: u32,
    pub selected: bool,
    pub hidden: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct ItemView {
    pub id: String,
    pub name: String,
    pub source_path: String,
    pub result_path: Option<String>,
    pub status: ItemStatus,
    pub error: Option<String>,
    pub source_preview: String,
    pub result_preview: Option<String>,
    pub model: Option<String>,
    pub width: u32,
    pub height: u32,
    pub selected: bool,
    pub hidden: bool,
}

impl ItemRecord {
    pub fn view(&self) -> ItemView {
        ItemView {
            id: self.id.clone(),
            name: self
                .source_path
                .file_name()
                .and_then(|name| name.to_str())
                .unwrap_or("未命名图片")
                .to_owned(),
            source_path: self.source_path.to_string_lossy().into_owned(),
            result_path: self
                .result_path
                .as_ref()
                .map(|path| path.to_string_lossy().into_owned()),
            status: self.status.clone(),
            error: self.error.clone(),
            source_preview: self.source_preview.clone(),
            result_preview: self.result_preview.clone(),
            model: self.model.clone(),
            width: self.width,
            height: self.height,
            selected: self.selected,
            hidden: self.hidden,
        }
    }

    pub fn watch_item(&self) -> bool {
        self.hidden
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Settings {
    pub model: String,
    pub export_prefix_enabled: bool,
    pub export_prefix: String,
    pub export_format: String,
    pub custom_extension: String,
    pub alpha_matting: bool,
    pub prefer_accel: bool,
    pub watch_enabled: bool,
    pub watch_dir: String,
    pub watch_output_dir: String,
    pub watch_process_existing: bool,
    pub watch_recursive: bool,
    pub watch_archive_sources: bool,
    pub watch_minimize_to_tray: bool,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            model: DEFAULT_MODEL.to_owned(),
            export_prefix_enabled: true,
            export_prefix: "nobg_".to_owned(),
            export_format: "png".to_owned(),
            custom_extension: "png".to_owned(),
            alpha_matting: false,
            prefer_accel: false,
            watch_enabled: false,
            watch_dir: String::new(),
            watch_output_dir: String::new(),
            watch_process_existing: true,
            watch_recursive: false,
            watch_archive_sources: false,
            watch_minimize_to_tray: true,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct ModelInfo {
    pub id: String,
    pub label: String,
    pub skill: String,
    pub note: String,
    pub status: String,
    pub size_bytes: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct AccelerationInfo {
    pub available: bool,
    pub label: String,
    pub detail: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct AppInfo {
    pub settings: Settings,
    pub models: Vec<ModelInfo>,
    pub models_dir: String,
    pub acceleration: AccelerationInfo,
    pub watch: WatchSummary,
    pub version: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct QueueSummary {
    pub total: usize,
    pub queued: usize,
    pub running: usize,
    pub done: usize,
    pub failed: usize,
    pub processing: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct WatchSummary {
    pub enabled: bool,
    pub paused: bool,
    pub status: String,
    pub queued: usize,
    pub success: usize,
    pub failed: usize,
}

pub fn is_supported_image(path: &Path) -> bool {
    path.is_file()
        && path
            .extension()
            .and_then(|ext| ext.to_str())
            .map(|ext| {
                IMAGE_EXTENSIONS
                    .iter()
                    .any(|value| value.eq_ignore_ascii_case(ext))
            })
            .unwrap_or(false)
}

pub fn is_valid_model_id(model_id: &str) -> bool {
    !model_id.is_empty()
        && model_id
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || ch == '-' || ch == '_')
}

/// Public model files that follow the same NCHW saliency contract as U^2-Net.
/// Newer rembg models are intentionally left as manual-import-only until their
/// ONNX input/output contract is verified by the Rust engine.
pub fn model_download_url(model_id: &str) -> Option<&'static str> {
    match model_id {
        "u2net" => Some("https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx"),
        "u2netp" => {
            Some("https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx")
        }
        "silueta" => {
            Some("https://github.com/danielgatis/rembg/releases/download/v0.0.0/silueta.onnx")
        }
        "u2net_human_seg" => Some(
            "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx",
        ),
        "u2net_cloth_seg" => Some(
            "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_cloth_seg.onnx",
        ),
        "isnet-general-use" => {
            Some("https://github.com/xuebinqin/DIS/releases/download/v0.0.1/isnet-general-use.onnx")
        }
        "isnet-anime" => {
            Some("https://github.com/xuebinqin/DIS/releases/download/v0.0.1/isnet-anime.onnx")
        }
        _ => None,
    }
}

pub fn model_catalog(models_dir: &Path) -> Vec<ModelInfo> {
    let entries = [
        (
            "isnet-general-use",
            "ISNet 通用（推荐）",
            "日常通用抠图：商品、人物、静物都较稳，边缘通常比经典 U²-Net 更好。",
            "体积较大；需要导入对应 ONNX 模型。",
        ),
        (
            "u2net",
            "U²-Net 经典通用",
            "经典通用分割，兼容性好，适合大多数场景的保底选择。",
            "效果略逊于 ISNet / BiRefNet 新模型。",
        ),
        (
            "u2netp",
            "U²-Net 轻量（内置）",
            "更快、更小，适合预览、批量处理或配置较低的电脑。",
            "随项目提供，首次启动即可离线使用。",
        ),
        (
            "silueta",
            "Silueta 精简通用",
            "体积更小的通用模型，在效果与体积之间折中。",
            "需要导入对应 ONNX 模型。",
        ),
        (
            "u2net_human_seg",
            "U²-Net 人像",
            "专为人像和半身像优化，证件照、人像抠图优先试这个。",
            "非人主体可能不如通用模型。",
        ),
        (
            "isnet-anime",
            "ISNet 动漫",
            "适合二次元角色、插画和色块边界。",
            "写实照片请使用通用或人像模型。",
        ),
        (
            "u2net_cloth_seg",
            "U²-Net 服装解析",
            "服装区域解析，适合服饰类图像。",
            "用途特殊，不是普通整图去背景。",
        ),
        (
            "birefnet-general",
            "BiRefNet 通用",
            "新一代通用高质量分割，复杂边缘和细节通常更干净。",
            "模型更大，需要导入对应 ONNX 模型。",
        ),
        (
            "birefnet-general-lite",
            "BiRefNet 通用轻量",
            "BiRefNet 的轻量版本，在速度与质量之间折中。",
            "需要导入对应 ONNX 模型。",
        ),
        (
            "birefnet-portrait",
            "BiRefNet 肖像",
            "肖像和人像专用，发丝与面部轮廓通常更好。",
            "偏人像场景。",
        ),
        (
            "birefnet-dis",
            "BiRefNet DIS",
            "二值或显著物体分割，适合前景主体明确的图像。",
            "普通高对比图像可优先试通用模型。",
        ),
        (
            "birefnet-hrsod",
            "BiRefNet 高分辨率显著物",
            "高分辨率显著物体检测场景，大图细节更友好。",
            "大图、细节较多时可试。",
        ),
        (
            "birefnet-cod",
            "BiRefNet 隐蔽物体",
            "隐蔽或低对比主体分割，适合主体与背景颜色接近的图像。",
            "普通高对比图像使用通用模型即可。",
        ),
        (
            "birefnet-massive",
            "BiRefNet 大规模训练",
            "更大数据集训练的通用向模型，追求更高质量时可对比。",
            "体积与处理成本更高。",
        ),
        (
            "bria-rmbg",
            "BRIA RMBG",
            "BRIA 背景去除模型，通用去背景质量较高。",
            "需要导入对应 ONNX 模型。",
        ),
    ];

    entries
        .into_iter()
        .map(|(id, label, skill, note)| {
            let path = models_dir.join(format!("{id}.onnx"));
            let partial_path = models_dir.join(format!("{id}.onnx.part"));
            let size_bytes = path
                .metadata()
                .map(|metadata| metadata.len())
                .ok()
                .filter(|size| *size > 1024)
                .or_else(|| {
                    partial_path
                        .metadata()
                        .map(|metadata| metadata.len())
                        .ok()
                        .filter(|size| *size > 1024)
                })
                .unwrap_or(0);
            let status = if path
                .metadata()
                .map(|metadata| metadata.len() > 1024)
                .unwrap_or(false)
            {
                "downloaded"
            } else if partial_path
                .metadata()
                .map(|metadata| metadata.len() > 1024)
                .unwrap_or(false)
            {
                "partial"
            } else {
                "missing"
            };
            ModelInfo {
                id: id.to_owned(),
                label: label.to_owned(),
                skill: skill.to_owned(),
                note: note.to_owned(),
                status: status.to_owned(),
                size_bytes,
            }
        })
        .collect()
}

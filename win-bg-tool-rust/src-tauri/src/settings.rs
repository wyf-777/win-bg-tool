use std::fs;
use std::path::Path;

use crate::models::{DEFAULT_MODEL, Settings, is_valid_model_id};

pub fn load(path: &Path) -> Settings {
    let Ok(text) = fs::read_to_string(path) else {
        return Settings::default();
    };
    let mut settings: Settings = serde_json::from_str(&text).unwrap_or_default();
    normalize(&mut settings);
    settings
}

pub fn save(path: &Path, settings: &mut Settings) -> Result<(), String> {
    normalize(settings);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| format!("创建设置目录失败：{error}"))?;
    }
    let text = serde_json::to_string_pretty(settings)
        .map_err(|error| format!("序列化设置失败：{error}"))?;
    fs::write(path, text).map_err(|error| format!("保存设置失败：{error}"))
}

pub fn normalize(settings: &mut Settings) {
    if !is_valid_model_id(&settings.model) {
        settings.model = DEFAULT_MODEL.to_owned();
    }
    settings.export_format = match settings.export_format.as_str() {
        "png" | "webp" | "jpg" | "bmp" | "tiff" | "custom" => settings.export_format.clone(),
        _ => "png".to_owned(),
    };
    settings.custom_extension = settings
        .custom_extension
        .trim()
        .trim_start_matches('.')
        .chars()
        .filter(|ch| ch.is_ascii_alphanumeric())
        .collect();
    if settings.custom_extension.is_empty() {
        settings.custom_extension = "png".to_owned();
    }
    settings.export_prefix = settings.export_prefix.trim().to_owned();
    settings.watch_dir = settings.watch_dir.trim().to_owned();
    settings.watch_output_dir = settings.watch_output_dir.trim().to_owned();
}

pub fn effective_prefix(settings: &Settings) -> &str {
    if settings.export_prefix_enabled {
        &settings.export_prefix
    } else {
        ""
    }
}

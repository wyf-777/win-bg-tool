use std::fs::{self, File};
use std::path::{Path, PathBuf};

use image::{DynamicImage, ImageFormat};
use serde::Deserialize;

use crate::image_engine::white_background;

#[derive(Debug, Clone, Deserialize)]
pub struct ExportOptions {
    pub directory: String,
    pub prefix: String,
    pub format: String,
    pub custom_extension: String,
}

pub fn extension(options: &ExportOptions) -> String {
    if options.format == "custom" {
        sanitize_extension(&options.custom_extension)
    } else {
        match options.format.as_str() {
            "jpg" => "jpg".to_owned(),
            "webp" => "webp".to_owned(),
            "bmp" => "bmp".to_owned(),
            "tiff" => "tiff".to_owned(),
            "gif" => "gif".to_owned(),
            _ => "png".to_owned(),
        }
    }
}

pub fn export_image(
    image: &DynamicImage,
    source: &Path,
    options: &ExportOptions,
) -> Result<PathBuf, String> {
    let directory = PathBuf::from(options.directory.trim());
    if directory.as_os_str().is_empty() {
        return Err("请选择输出文件夹".to_owned());
    }
    fs::create_dir_all(&directory).map_err(|error| format!("创建输出目录失败：{error}"))?;
    let stem = source
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("image");
    let prefix = options.prefix.trim();
    let ext = extension(options);
    let mut index = 0_u32;
    let target = loop {
        let suffix = if index == 0 {
            String::new()
        } else {
            format!("_{index}")
        };
        let candidate = directory.join(format!("{prefix}{stem}{suffix}.{ext}"));
        if !candidate.exists() {
            break candidate;
        }
        index += 1;
    };

    export_image_to_file(image, &target, options)
}

pub fn export_image_to_file(
    image: &DynamicImage,
    target: &Path,
    options: &ExportOptions,
) -> Result<PathBuf, String> {
    let mut target = target.to_path_buf();
    if target.as_os_str().is_empty() {
        return Err("请选择输出文件".to_owned());
    }
    let extension = extension(options);
    target.set_extension(extension);
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|error| format!("创建输出目录失败：{error}"))?;
    }
    let format = image_format(options);
    let to_write = if matches!(options.format.as_str(), "jpg" | "bmp") {
        DynamicImage::ImageRgba8(white_background(image))
    } else {
        image.clone()
    };
    let mut file = File::create(&target).map_err(|error| format!("创建导出文件失败：{error}"))?;
    to_write
        .write_to(&mut file, format)
        .map_err(|error| format!("导出图片失败：{error}"))?;
    Ok(target)
}

fn sanitize_extension(raw: &str) -> String {
    let value: String = raw
        .trim()
        .trim_start_matches('.')
        .chars()
        .filter(|ch| ch.is_ascii_alphanumeric())
        .collect();
    if value.is_empty() {
        "png".to_owned()
    } else {
        value.to_lowercase()
    }
}

fn image_format(options: &ExportOptions) -> ImageFormat {
    let format = if options.format == "custom" {
        sanitize_extension(&options.custom_extension)
    } else {
        options.format.to_lowercase()
    };
    match format.as_str() {
        "jpg" | "jpeg" => ImageFormat::Jpeg,
        "webp" => ImageFormat::WebP,
        "bmp" => ImageFormat::Bmp,
        "tif" | "tiff" => ImageFormat::Tiff,
        "gif" => ImageFormat::Gif,
        _ => ImageFormat::Png,
    }
}

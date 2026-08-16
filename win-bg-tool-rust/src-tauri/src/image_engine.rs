use std::fs;
use std::io::Cursor;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use base64::Engine as _;
use image::{DynamicImage, GenericImageView, ImageBuffer, ImageFormat, Rgba, RgbaImage};
use ort::ep::ExecutionProvider;
use ort::session::{Session, builder::GraphOptimizationLevel};
use ort::value::Tensor;

const MODEL_SIZE: u32 = 320;
static ORT_INITIALIZED: OnceLock<bool> = OnceLock::new();

pub struct BackgroundEngine {
    pub requested_model: String,
    pub active_model: Option<String>,
    pub models_dir: PathBuf,
    session: Option<Session>,
    pub prefer_accel: bool,
    pub alpha_matting: bool,
    active_accel: bool,
    accel_fallback: bool,
}

impl BackgroundEngine {
    pub fn new(
        models_dir: PathBuf,
        model: String,
        prefer_accel: bool,
        alpha_matting: bool,
    ) -> Self {
        Self {
            requested_model: model,
            active_model: None,
            models_dir,
            session: None,
            prefer_accel,
            alpha_matting,
            active_accel: false,
            accel_fallback: false,
        }
    }

    pub fn set_model(&mut self, model: String) -> Result<(), String> {
        if model.trim().is_empty() {
            return Err("模型名称不能为空".to_owned());
        }
        if model != self.requested_model {
            self.requested_model = model;
            self.reset_session();
        }
        Ok(())
    }

    pub fn set_prefer_accel(&mut self, prefer_accel: bool) {
        if self.prefer_accel != prefer_accel {
            self.prefer_accel = prefer_accel;
            self.reset_session();
        }
    }

    pub fn reset_session(&mut self) {
        self.session = None;
        self.active_model = None;
        self.active_accel = false;
        self.accel_fallback = false;
    }

    pub fn model_path(&self) -> PathBuf {
        self.models_dir
            .join(format!("{}.onnx", self.requested_model))
    }

    pub fn warmup(&mut self) -> Result<String, String> {
        self.ensure_session()?;
        Ok(format!(
            "模型 {} 已就绪 · {}",
            self.active_model
                .as_deref()
                .unwrap_or(&self.requested_model),
            self.device_label()
        ))
    }

    pub fn device_label(&self) -> String {
        if self.active_accel {
            "更快处理（图形加速）".to_owned()
        } else if self.accel_fallback {
            "普通模式（加速不可用，已自动回退）".to_owned()
        } else if self.prefer_accel && !acceleration_available() {
            "普通模式（未检测到加速组件）".to_owned()
        } else {
            "普通模式".to_owned()
        }
    }

    pub fn acceleration_status(prefer_accel: bool) -> (bool, String, String) {
        let available = acceleration_available();
        if available {
            let label = if prefer_accel {
                "可加速 · 已开启更快处理".to_owned()
            } else {
                "可加速 · 当前使用普通模式".to_owned()
            };
            let detail =
                "检测到 Windows 图形加速组件；启用后会优先尝试，失败自动回退普通模式。".to_owned();
            (true, label, detail)
        } else {
            let label = if prefer_accel {
                "普通模式 · 已记住更快处理，当前只能普通模式".to_owned()
            } else {
                "普通模式 · 人人可用".to_owned()
            };
            let detail = "当前未检测到可用的图形加速组件，将使用普通模式处理。".to_owned();
            (false, label, detail)
        }
    }

    pub fn remove(&mut self, path: &Path) -> Result<DynamicImage, String> {
        let original = image::open(path).map_err(|error| format!("无法读取图片：{error}"))?;
        let (width, height) = original.dimensions();
        if width == 0 || height == 0 {
            return Err("图片尺寸无效".to_owned());
        }

        self.ensure_session()?;
        let rgb = original.to_rgb8();
        let (model_width, model_height) = self.input_dimensions();
        let resized = DynamicImage::ImageRgb8(rgb.clone()).resize_exact(
            model_width,
            model_height,
            image::imageops::FilterType::Lanczos3,
        );
        let resized_rgb = resized.to_rgb8();
        let mut input = vec![0.0_f32; (3 * model_width * model_height) as usize];
        let mean = [0.485_f32, 0.456, 0.406];
        let std = [0.229_f32, 0.224, 0.225];
        let plane = (model_width * model_height) as usize;
        for y in 0..model_height {
            for x in 0..model_width {
                let pixel = resized_rgb.get_pixel(x, y);
                let offset = (y * model_width + x) as usize;
                for channel in 0..3 {
                    let value = f32::from(pixel[channel]) / 255.0;
                    input[channel * plane + offset] = (value - mean[channel]) / std[channel];
                }
            }
        }

        let session = self
            .session
            .as_mut()
            .ok_or_else(|| "推理会话尚未加载".to_owned())?;
        let tensor = Tensor::<f32>::from_array((
            [1_usize, 3, model_height as usize, model_width as usize],
            input,
        ))
        .map_err(|error| format!("创建模型输入失败：{error}"))?;
        let outputs = session
            .run(ort::inputs![tensor])
            .map_err(|error| format!("模型推理失败：{error}"))?;
        let (output_shape, values) = outputs[0]
            .try_extract_tensor::<f32>()
            .map_err(|error| format!("读取模型输出失败：{error}"))?;
        if values.is_empty() {
            return Err("模型没有返回有效蒙版".to_owned());
        }

        let mut minimum = f32::INFINITY;
        let mut maximum = f32::NEG_INFINITY;
        for &value in values {
            minimum = minimum.min(value);
            maximum = maximum.max(value);
        }
        let (mask_width, mask_height) =
            output_dimensions(output_shape, values.len()).unwrap_or((model_width, model_height));
        let already_normalized = minimum >= -0.01 && maximum <= 1.01;
        let range = (maximum - minimum).max(f32::EPSILON);
        let mut mask = image::GrayImage::new(mask_width, mask_height);
        for (index, pixel) in mask.pixels_mut().enumerate() {
            let value = values.get(index).copied().unwrap_or(0.0);
            let normalized = if already_normalized {
                value.clamp(0.0, 1.0)
            } else if minimum < 0.0 {
                1.0 / (1.0 + (-value).exp())
            } else {
                ((value - minimum) / range).clamp(0.0, 1.0)
            };
            pixel[0] = (normalized * 255.0).round() as u8;
        }
        let mask = DynamicImage::ImageLuma8(mask)
            .resize_exact(width, height, image::imageops::FilterType::Lanczos3)
            .to_luma8();
        let mask = if self.alpha_matting {
            refine_alpha(&mask, &original)
        } else {
            mask
        };

        let mut result = original.to_rgba8();
        for (pixel, alpha) in result.pixels_mut().zip(mask.pixels()) {
            pixel[3] = alpha[0];
        }
        Ok(DynamicImage::ImageRgba8(result))
    }

    fn ensure_session(&mut self) -> Result<(), String> {
        if self.session.is_some()
            && self.active_model.as_deref() == Some(self.requested_model.as_str())
        {
            return Ok(());
        }
        let model_path = self.model_path();
        if !model_path.is_file() {
            return Err(format!(
                "模型尚未就绪：{}\n请在设置中导入 {}.onnx，或将模型放入 models 目录。",
                self.requested_model, self.requested_model
            ));
        }
        initialize_ort();
        let wants_accel = self.prefer_accel && acceleration_available();
        self.accel_fallback = false;
        let session = match self.commit_session(&model_path, wants_accel) {
            Ok(session) => {
                self.active_accel = wants_accel;
                session
            }
            Err(accel_error) if wants_accel => {
                self.accel_fallback = true;
                self.active_accel = false;
                self.commit_session(&model_path, false).map_err(|cpu_error| {
                    format!(
                        "加速模式加载失败，普通模式也无法加载：{cpu_error}\n加速错误：{accel_error}"
                    )
                })?
            }
            Err(error) => return Err(error),
        };
        self.session = Some(session);
        self.active_model = Some(self.requested_model.clone());
        Ok(())
    }

    fn commit_session(&self, model_path: &Path, use_accel: bool) -> Result<Session, String> {
        let builder = Session::builder()
            .map_err(|error| format!("创建推理会话失败：{error}"))?
            .with_optimization_level(GraphOptimizationLevel::Level3)
            .map_err(|error| format!("配置推理优化失败：{error}"))?
            .with_inter_threads(1)
            .map_err(|error| format!("推理并行线程配置失败：{error}"))?
            .with_intra_threads(
                std::thread::available_parallelism()
                    .map(|n| n.get().saturating_sub(2).clamp(1, 4))
                    .unwrap_or(2),
            )
            .map_err(|error| format!("配置推理线程失败：{error}"))?;
        let mut builder = if use_accel {
            builder
                .with_execution_providers([
                    ort::ep::DirectML::default().build().error_on_failure(),
                    ort::ep::CPU::default().build(),
                ])
                .map_err(|error| format!("启用图形加速失败：{error}"))?
        } else {
            builder
                .with_execution_providers([ort::ep::CPU::default().build()])
                .map_err(|error| format!("配置普通模式失败：{error}"))?
        };
        builder
            .commit_from_file(model_path)
            .map_err(|error| format!("加载模型失败：{error}"))
    }

    fn input_dimensions(&self) -> (u32, u32) {
        let Some(session) = self.session.as_ref() else {
            return (MODEL_SIZE, MODEL_SIZE);
        };
        let Some(shape) = session
            .inputs()
            .first()
            .and_then(|input| input.dtype().tensor_shape())
        else {
            return (MODEL_SIZE, MODEL_SIZE);
        };
        let dims = shape.as_ref();
        if dims.len() < 2 {
            return (MODEL_SIZE, MODEL_SIZE);
        }
        let height = dims[dims.len() - 2];
        let width = dims[dims.len() - 1];
        if (128..=2048).contains(&width) && (128..=2048).contains(&height) {
            (width as u32, height as u32)
        } else {
            (MODEL_SIZE, MODEL_SIZE)
        }
    }
}

fn acceleration_available() -> bool {
    #[cfg(target_os = "windows")]
    {
        initialize_ort();
        return ort::ep::DirectML::default().is_available().unwrap_or(false);
    }
    #[cfg(not(target_os = "windows"))]
    {
        false
    }
}

fn output_dimensions(shape: &[i64], value_count: usize) -> Option<(u32, u32)> {
    for index in (0..shape.len().saturating_sub(1)).rev() {
        let height = shape[index];
        let width = shape[index + 1];
        if height > 0
            && width > 0
            && (height as usize).saturating_mul(width as usize) == value_count
            && height <= 4096
            && width <= 4096
        {
            return Some((width as u32, height as u32));
        }
    }
    None
}

fn refine_alpha(mask: &image::GrayImage, original: &DynamicImage) -> image::GrayImage {
    let blurred = image::imageops::blur(mask, 1.15);
    let source = original.to_rgba8();
    let mut refined = mask.clone();
    for y in 0..mask.height() {
        for x in 0..mask.width() {
            let current = f32::from(mask.get_pixel(x, y)[0]);
            if current <= 8.0 || current >= 247.0 {
                refined.put_pixel(x, y, image::Luma([if current <= 8.0 { 0 } else { 255 }]));
                continue;
            }
            let left = source.get_pixel(x.saturating_sub(1), y);
            let right = source.get_pixel((x + 1).min(source.width() - 1), y);
            let top = source.get_pixel(x, y.saturating_sub(1));
            let bottom = source.get_pixel(x, (y + 1).min(source.height() - 1));
            let gradient = color_distance(left, right).max(color_distance(top, bottom));
            let blend = (0.28 + gradient / 255.0 * 0.42).clamp(0.28, 0.7);
            let soft = f32::from(blurred.get_pixel(x, y)[0]);
            let value = (current * (1.0 - blend) + soft * blend).round() as u8;
            refined.put_pixel(x, y, image::Luma([value]));
        }
    }
    refined
}

fn color_distance(left: &image::Rgba<u8>, right: &image::Rgba<u8>) -> f32 {
    let dr = f32::from(left[0]) - f32::from(right[0]);
    let dg = f32::from(left[1]) - f32::from(right[1]);
    let db = f32::from(left[2]) - f32::from(right[2]);
    (dr * dr + dg * dg + db * db).sqrt().min(255.0)
}

fn initialize_ort() {
    ORT_INITIALIZED.get_or_init(|| ort::init().with_name("peel").with_telemetry(false).commit());
}

pub fn encode_png(image: &DynamicImage) -> Result<Vec<u8>, String> {
    let mut buffer = Cursor::new(Vec::new());
    image
        .write_to(&mut buffer, ImageFormat::Png)
        .map_err(|error| format!("编码 PNG 失败：{error}"))?;
    Ok(buffer.into_inner())
}

pub fn encode_data_url(image: &DynamicImage, max_edge: Option<u32>) -> Result<String, String> {
    let preview = max_edge
        .map(|edge| image.thumbnail(edge, edge))
        .unwrap_or_else(|| image.clone());
    let bytes = encode_png(&preview)?;
    Ok(format!(
        "data:image/png;base64,{}",
        base64::engine::general_purpose::STANDARD.encode(bytes)
    ))
}

pub fn load_preview(path: &Path, max_edge: u32) -> Result<(String, u32, u32), String> {
    let image = image::open(path).map_err(|error| format!("无法读取图片：{error}"))?;
    let (width, height) = image.dimensions();
    Ok((encode_data_url(&image, Some(max_edge))?, width, height))
}

#[allow(dead_code)]
pub fn load_full_data_url(path: &Path) -> Result<String, String> {
    let image = image::open(path).map_err(|error| format!("无法读取图片：{error}"))?;
    encode_data_url(&image, None)
}

pub fn write_png(path: &Path, image: &DynamicImage) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| format!("创建输出目录失败：{error}"))?;
    }
    let bytes = encode_png(image)?;
    fs::write(path, bytes).map_err(|error| format!("写入图片失败：{error}"))
}

pub fn white_background(image: &DynamicImage) -> RgbaImage {
    let rgba = image.to_rgba8();
    let mut background =
        ImageBuffer::from_pixel(rgba.width(), rgba.height(), Rgba([255, 255, 255, 255]));
    image::imageops::overlay(&mut background, &rgba, 0, 0);
    background
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bundled_u2netp_produces_rgba_result() {
        let model_dir = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .join("models");
        let model_path = model_dir.join("u2netp.onnx");
        assert!(
            model_path.is_file(),
            "bundled model is missing: {}",
            model_path.display()
        );

        let source_path =
            std::env::temp_dir().join(format!("peel-engine-test-{}.png", std::process::id()));
        let source = RgbaImage::from_fn(96, 72, |x, y| {
            if x > 18 && x < 78 && y > 10 && y < 62 {
                Rgba([225, 75, 60, 255])
            } else {
                Rgba([32, 120, 150, 255])
            }
        });
        source.save(&source_path).expect("write test image");

        let mut engine = BackgroundEngine::new(model_dir, "u2netp".to_owned(), false, false);
        let result = engine.remove(&source_path).expect("run bundled ONNX model");
        assert_eq!(result.dimensions(), (96, 72));
        assert!(result.to_rgba8().pixels().any(|pixel| pixel[3] > 0));
        let _ = fs::remove_file(source_path);
    }
}

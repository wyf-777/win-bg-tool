use image::{DynamicImage, GenericImageView, GrayImage, ImageBuffer, Luma, RgbaImage};
use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
pub struct Point {
    pub x: f32,
    pub y: f32,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Selection {
    pub kind: String,
    pub points: Vec<Point>,
    pub radius: Option<f32>,
}

pub fn apply_mask_edit(
    original: &DynamicImage,
    current: &DynamicImage,
    selection: &Selection,
    operation: &str,
    feather: u32,
) -> Result<DynamicImage, String> {
    if original.dimensions() != current.dimensions() {
        return Err("原图与结果尺寸不一致".to_owned());
    }
    let mask = selection_mask(current.width(), current.height(), selection, feather)?;
    let original = original.to_rgba8();
    let current = current.to_rgba8();
    let mut result = current.clone();
    for (index, pixel) in result.pixels_mut().enumerate() {
        let mask_value = mask.as_raw()[index];
        match operation {
            "keep" => {
                pixel[3] = multiply_alpha(pixel[3], mask_value);
            }
            "erase" => {
                pixel[3] = multiply_alpha(pixel[3], 255 - mask_value);
            }
            "restore" => {
                let source = original.as_raw()[index * 4..index * 4 + 4].to_owned();
                let old = current.as_raw()[index * 4..index * 4 + 4].to_owned();
                for channel in 0..3 {
                    pixel[channel] = blend(source[channel], old[channel], mask_value);
                }
                pixel[3] = pixel[3].max(mask_value);
            }
            _ => return Err("不支持的蒙版操作".to_owned()),
        }
    }
    Ok(DynamicImage::ImageRgba8(result))
}

pub fn selection_mask(
    width: u32,
    height: u32,
    selection: &Selection,
    feather: u32,
) -> Result<GrayImage, String> {
    if width == 0 || height == 0 {
        return Err("图片尺寸无效".to_owned());
    }
    let mut mask = ImageBuffer::from_pixel(width, height, Luma([0_u8]));
    match selection.kind.as_str() {
        "lasso" => {
            if selection.points.len() < 3 {
                return Err("套索至少需要三个点".to_owned());
            }
            let (min_x, max_x, min_y, max_y) = bounds(&selection.points, 0.0, width, height);
            for y in min_y..=max_y {
                for x in min_x..=max_x {
                    if point_in_polygon(x as f32 + 0.5, y as f32 + 0.5, &selection.points) {
                        mask.put_pixel(x, y, Luma([255]));
                    }
                }
            }
        }
        "brush" => {
            if selection.points.is_empty() {
                return Err("画笔至少需要一个点".to_owned());
            }
            let radius = selection.radius.unwrap_or(24.0).max(0.5);
            let (min_x, max_x, min_y, max_y) = bounds(&selection.points, radius, width, height);
            for y in min_y..=max_y {
                for x in min_x..=max_x {
                    let px = x as f32 + 0.5;
                    let py = y as f32 + 0.5;
                    let hit =
                        selection.points.iter().any(|point| {
                            squared_distance(px, py, point.x, point.y) <= radius * radius
                        }) || selection
                            .points
                            .windows(2)
                            .any(|pair| distance_to_segment(px, py, &pair[0], &pair[1]) <= radius);
                    if hit {
                        mask.put_pixel(x, y, Luma([255]));
                    }
                }
            }
        }
        _ => return Err("未知选择工具".to_owned()),
    }
    if feather > 0 {
        mask = DynamicImage::ImageLuma8(mask)
            .blur(feather as f32)
            .to_luma8();
    }
    Ok(mask)
}

fn bounds(points: &[Point], padding: f32, width: u32, height: u32) -> (u32, u32, u32, u32) {
    let min_x = points
        .iter()
        .map(|point| point.x)
        .fold(f32::INFINITY, f32::min)
        - padding;
    let max_x = points
        .iter()
        .map(|point| point.x)
        .fold(f32::NEG_INFINITY, f32::max)
        + padding;
    let min_y = points
        .iter()
        .map(|point| point.y)
        .fold(f32::INFINITY, f32::min)
        - padding;
    let max_y = points
        .iter()
        .map(|point| point.y)
        .fold(f32::NEG_INFINITY, f32::max)
        + padding;
    (
        min_x.floor().max(0.0).min(width.saturating_sub(1) as f32) as u32,
        max_x.ceil().max(0.0).min(width.saturating_sub(1) as f32) as u32,
        min_y.floor().max(0.0).min(height.saturating_sub(1) as f32) as u32,
        max_y.ceil().max(0.0).min(height.saturating_sub(1) as f32) as u32,
    )
}

fn point_in_polygon(x: f32, y: f32, points: &[Point]) -> bool {
    let mut inside = false;
    let mut previous = &points[points.len() - 1];
    for current in points {
        let crosses = (current.y > y) != (previous.y > y)
            && x < (previous.x - current.x) * (y - current.y) / (previous.y - current.y)
                + current.x;
        if crosses {
            inside = !inside;
        }
        previous = current;
    }
    inside
}

fn squared_distance(x: f32, y: f32, px: f32, py: f32) -> f32 {
    let dx = x - px;
    let dy = y - py;
    dx * dx + dy * dy
}

fn distance_to_segment(x: f32, y: f32, start: &Point, end: &Point) -> f32 {
    let dx = end.x - start.x;
    let dy = end.y - start.y;
    let length_squared = dx * dx + dy * dy;
    if length_squared <= f32::EPSILON {
        return squared_distance(x, y, start.x, start.y).sqrt();
    }
    let t = (((x - start.x) * dx + (y - start.y) * dy) / length_squared).clamp(0.0, 1.0);
    squared_distance(x, y, start.x + t * dx, start.y + t * dy).sqrt()
}

fn multiply_alpha(left: u8, right: u8) -> u8 {
    ((u16::from(left) * u16::from(right) + 127) / 255) as u8
}

fn blend(source: u8, current: u8, amount: u8) -> u8 {
    ((u16::from(source) * u16::from(amount) + u16::from(current) * u16::from(255 - amount) + 127)
        / 255) as u8
}

pub fn image_from_rgba(width: u32, height: u32, bytes: Vec<u8>) -> Result<DynamicImage, String> {
    let image = RgbaImage::from_raw(width, height, bytes)
        .ok_or_else(|| "RGBA 数据尺寸不匹配".to_owned())?;
    Ok(DynamicImage::ImageRgba8(image))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lasso_erase_removes_only_the_selection() {
        let original = DynamicImage::ImageRgba8(RgbaImage::from_pixel(
            10,
            10,
            image::Rgba([10, 20, 30, 255]),
        ));
        let current = original.clone();
        let selection = Selection {
            kind: "lasso".to_owned(),
            points: vec![
                Point { x: 1.0, y: 1.0 },
                Point { x: 8.0, y: 1.0 },
                Point { x: 8.0, y: 8.0 },
                Point { x: 1.0, y: 8.0 },
            ],
            radius: None,
        };
        let edited =
            apply_mask_edit(&original, &current, &selection, "erase", 0).expect("apply mask");
        assert_eq!(edited.to_rgba8().get_pixel(4, 4)[3], 0);
        assert_eq!(edited.to_rgba8().get_pixel(0, 0)[3], 255);
    }
}

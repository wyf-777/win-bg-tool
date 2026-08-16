#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod export;
mod image_engine;
mod mask;
mod models;
mod settings;
mod watch;

use std::collections::HashMap;
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::{
    Mutex,
    atomic::{AtomicBool, Ordering},
};
use std::thread;
use std::time::Instant;

use arboard::Clipboard;
use serde::Serialize;
use tauri::{
    Emitter, Manager, State, WindowEvent,
    menu::{MenuBuilder, MenuItemBuilder},
    tray::TrayIconBuilder,
};
use uuid::Uuid;

use crate::export::{ExportOptions, export_image, export_image_to_file};
use crate::image_engine::{BackgroundEngine, encode_data_url, load_preview, write_png};
use crate::models::{
    AccelerationInfo, AppInfo, ItemRecord, ItemStatus, ItemView, MAX_DROP, MAX_FILE_BYTES,
    MAX_SESSION, QueueSummary, Settings, WatchSummary, is_valid_model_id, model_catalog,
};

struct AppState {
    data_dir: PathBuf,
    models_dir: PathBuf,
    settings_path: PathBuf,
    settings: Mutex<Settings>,
    items: Mutex<Vec<ItemRecord>>,
    engine: Mutex<BackgroundEngine>,
    processing: AtomicBool,
    watcher: Mutex<Option<watch::WatchHandle>>,
    watch_summary: Mutex<WatchSummary>,
    histories: Mutex<HashMap<String, History>>,
}

const TRAY_ID: &str = "main-tray";
const TRAY_SHOW_ID: &str = "tray-show";
const TRAY_PAUSE_ID: &str = "tray-pause";
const TRAY_QUIT_ID: &str = "tray-quit";

#[derive(Debug, Default)]
struct History {
    width: u32,
    height: u32,
    undo: Vec<Vec<u8>>,
    redo: Vec<Vec<u8>>,
}

#[derive(Debug, Clone, Serialize)]
struct StatusEvent {
    message: String,
}

#[derive(Debug, Clone, Serialize)]
struct AddResult {
    added: usize,
    message: String,
    items: Vec<ItemView>,
}

#[derive(Debug, Clone, Serialize)]
struct ExportResult {
    exported: usize,
    failed: Vec<String>,
    message: String,
}

#[derive(Debug, Clone, Serialize)]
struct RepairImage {
    id: String,
    original: String,
    result: String,
    width: u32,
    height: u32,
}

impl AppState {
    fn new(data_dir: PathBuf, models_dir: PathBuf) -> Self {
        let settings_path = data_dir.join("settings.json");
        let settings = settings::load(&settings_path);
        let engine = BackgroundEngine::new(
            models_dir.clone(),
            settings.model.clone(),
            settings.prefer_accel,
            settings.alpha_matting,
        );
        Self {
            data_dir,
            models_dir,
            settings: Mutex::new(settings),
            settings_path,
            items: Mutex::new(Vec::new()),
            engine: Mutex::new(engine),
            processing: AtomicBool::new(false),
            watcher: Mutex::new(None),
            watch_summary: Mutex::new(WatchSummary {
                enabled: false,
                paused: false,
                status: "尚未开启监视".to_owned(),
                queued: 0,
                success: 0,
                failed: 0,
            }),
            histories: Mutex::new(HashMap::new()),
        }
    }
}

fn app_info(state: &AppState) -> AppInfo {
    let settings = state
        .settings
        .lock()
        .map(|value| value.clone())
        .unwrap_or_default();
    let watch = state
        .watch_summary
        .lock()
        .map(|value| value.clone())
        .unwrap_or(WatchSummary {
            enabled: false,
            paused: false,
            status: "尚未开启监视".to_owned(),
            queued: 0,
            success: 0,
            failed: 0,
        });
    let (available, label, detail) = BackgroundEngine::acceleration_status(settings.prefer_accel);
    AppInfo {
        settings,
        models: model_catalog(&state.models_dir),
        models_dir: state.models_dir.to_string_lossy().into_owned(),
        acceleration: AccelerationInfo {
            available,
            label,
            detail,
        },
        watch,
        version: env!("CARGO_PKG_VERSION").to_owned(),
    }
}

fn watch_configuration_changed(previous: &Settings, next: &Settings) -> bool {
    previous.watch_enabled != next.watch_enabled
        || previous.watch_dir != next.watch_dir
        || previous.watch_output_dir != next.watch_output_dir
        || previous.watch_process_existing != next.watch_process_existing
        || previous.watch_recursive != next.watch_recursive
        || previous.watch_archive_sources != next.watch_archive_sources
}

fn queue_views(state: &AppState) -> Vec<ItemView> {
    state
        .items
        .lock()
        .map(|items| items.iter().map(ItemRecord::view).collect())
        .unwrap_or_default()
}

fn queue_summary(state: &AppState) -> QueueSummary {
    let items = state
        .items
        .lock()
        .map(|items| items.clone())
        .unwrap_or_default();
    QueueSummary {
        total: items.iter().filter(|item| !item.watch_item()).count(),
        queued: items
            .iter()
            .filter(|item| !item.watch_item() && item.status == ItemStatus::Queued)
            .count(),
        running: items
            .iter()
            .filter(|item| !item.watch_item() && item.status == ItemStatus::Running)
            .count(),
        done: items
            .iter()
            .filter(|item| !item.watch_item() && item.status == ItemStatus::Done)
            .count(),
        failed: items
            .iter()
            .filter(|item| !item.watch_item() && item.status == ItemStatus::Failed)
            .count(),
        processing: state.processing.load(Ordering::SeqCst),
    }
}

fn emit_queue(app: &tauri::AppHandle, state: &AppState) {
    let _ = app.emit("queue-updated", queue_views(state));
    emit_queue_summary(app, state);
}

fn emit_queue_summary(app: &tauri::AppHandle, state: &AppState) {
    let _ = app.emit("queue-summary", queue_summary(state));
}

fn emit_item_updated(app: &tauri::AppHandle, state: &AppState, id: &str) {
    let view = state.items.lock().ok().and_then(|items| {
        items
            .iter()
            .find(|item| item.id == id)
            .map(ItemRecord::view)
    });
    if let Some(view) = view {
        let _ = app.emit("item-updated", view);
    }
}

fn start_preview_loader(app: &tauri::AppHandle, jobs: Vec<(String, PathBuf)>) {
    if jobs.is_empty() {
        return;
    }
    let app = app.clone();
    let _ = thread::Builder::new()
        .name("peel-preview-loader".to_owned())
        .spawn(move || {
            lower_processing_thread_priority();
            for (id, path) in jobs {
                let Ok((preview, width, height)) = load_preview(&path, 1280) else {
                    continue;
                };
                let state = app.state::<AppState>();
                let updated = state
                    .items
                    .lock()
                    .ok()
                    .map(|mut items| {
                        if let Some(item) = items.iter_mut().find(|item| item.id == id) {
                            item.source_preview = preview;
                            item.width = width;
                            item.height = height;
                            true
                        } else {
                            false
                        }
                    })
                    .unwrap_or(false);
                if updated {
                    emit_item_updated(&app, &state, &id);
                }
            }
        });
}

fn emit_status(app: &tauri::AppHandle, message: impl Into<String>) {
    let _ = app.emit(
        "status-message",
        StatusEvent {
            message: message.into(),
        },
    );
}

fn emit_watch(app: &tauri::AppHandle, state: &AppState) {
    if let Ok(summary) = state.watch_summary.lock() {
        let _ = app.emit("watch-updated", summary.clone());
    }
}

fn tray_should_be_visible(state: &AppState) -> bool {
    let tray_enabled = state
        .settings
        .lock()
        .map(|settings| settings.watch_minimize_to_tray)
        .unwrap_or(false);
    let watch_enabled = state
        .watch_summary
        .lock()
        .map(|summary| summary.enabled)
        .unwrap_or(false);
    tray_enabled && watch_enabled
}

fn sync_tray_visibility(app: &tauri::AppHandle) {
    if let Some(tray) = app.tray_by_id(TRAY_ID) {
        let state = app.state::<AppState>();
        let _ = tray.set_visible(tray_should_be_visible(&state));
    }
}

fn install_tray(app: &mut tauri::App) -> tauri::Result<()> {
    let show = MenuItemBuilder::with_id(TRAY_SHOW_ID, "打开 Peel").build(app)?;
    let pause = MenuItemBuilder::with_id(TRAY_PAUSE_ID, "暂停/继续监视").build(app)?;
    let quit = MenuItemBuilder::with_id(TRAY_QUIT_ID, "退出 Peel").build(app)?;
    let menu = MenuBuilder::new(app)
        .items(&[&show, &pause, &quit])
        .build()?;
    let mut builder = TrayIconBuilder::with_id(TRAY_ID)
        .menu(&menu)
        .tooltip("Peel")
        .show_menu_on_left_click(true)
        .on_menu_event(|app, event| match event.id().as_ref() {
            TRAY_SHOW_ID => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.unminimize();
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            TRAY_PAUSE_ID => {
                let state = app.state::<AppState>();
                let paused = state
                    .watch_summary
                    .lock()
                    .map(|summary| summary.paused)
                    .unwrap_or(false);
                if let Ok(watcher) = state.watcher.lock() {
                    if let Some(watcher) = watcher.as_ref() {
                        watcher.pause(!paused);
                    }
                }
                if let Ok(mut summary) = state.watch_summary.lock() {
                    summary.paused = !paused;
                    summary.status = if summary.paused {
                        "文件夹监视已暂停".to_owned()
                    } else {
                        "文件夹监视中".to_owned()
                    };
                }
                emit_status(
                    app,
                    if !paused {
                        "文件夹监视已暂停"
                    } else {
                        "文件夹监视中"
                    },
                );
                emit_watch(app, &state);
            }
            TRAY_QUIT_ID => app.exit(0),
            _ => {}
        });
    if let Some(icon) = app.default_window_icon().cloned() {
        builder = builder.icon(icon);
    }
    let tray = builder.build(app)?;
    let state = app.handle().state::<AppState>();
    tray.set_visible(tray_should_be_visible(&state))?;
    Ok(())
}

fn install_window_close_behavior(app: &tauri::AppHandle) {
    let app_handle = app.clone();
    if let Some(window) = app.get_webview_window("main") {
        window.on_window_event(move |event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                let state = app_handle.state::<AppState>();
                if tray_should_be_visible(&state) {
                    api.prevent_close();
                    if let Some(window) = app_handle.get_webview_window("main") {
                        let _ = window.hide();
                    }
                }
            }
        });
    }
}

fn normalize_input_path(path: &Path) -> PathBuf {
    path.canonicalize().unwrap_or_else(|_| path.to_path_buf())
}

fn enqueue_paths(
    app: &tauri::AppHandle,
    state: &AppState,
    paths: Vec<PathBuf>,
    hidden: bool,
) -> AddResult {
    if state.processing.load(Ordering::SeqCst) && !hidden {
        let result = AddResult {
            added: 0,
            message: "当前批次仍在处理，请等待全部完成后再添加图片。".to_owned(),
            items: queue_views(state),
        };
        emit_status(app, &result.message);
        return result;
    }

    let mut seen = std::collections::HashSet::new();
    let mut candidates = Vec::new();
    for path in paths {
        let normalized = normalize_input_path(&path);
        let key = normalized.to_string_lossy().to_lowercase();
        if seen.insert(key) {
            candidates.push(normalized);
        }
    }
    if !hidden && candidates.len() > MAX_DROP {
        candidates.truncate(MAX_DROP);
    }

    let existing: std::collections::HashSet<String> = state
        .items
        .lock()
        .map(|items| {
            items
                .iter()
                .map(|item| {
                    normalize_input_path(&item.source_path)
                        .to_string_lossy()
                        .to_lowercase()
                })
                .collect()
        })
        .unwrap_or_default();
    let room = if hidden {
        usize::MAX
    } else {
        MAX_SESSION.saturating_sub(existing.len())
    };
    let mut added = 0_usize;
    let mut skipped = Vec::new();
    let mut new_items = Vec::new();
    let mut preview_jobs = Vec::new();
    for path in candidates.into_iter().take(room) {
        let display_name = path
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("图片")
            .to_owned();
        if !crate::models::is_supported_image(&path) {
            skipped.push(format!("{display_name}：不支持的格式"));
            continue;
        }
        let size = match path.metadata() {
            Ok(metadata) => metadata.len(),
            Err(error) => {
                skipped.push(format!("{display_name}：无法读取文件（{error}）"));
                continue;
            }
        };
        if size > MAX_FILE_BYTES {
            skipped.push(format!("{display_name}：文件超过 80MB"));
            continue;
        }
        let key = path.to_string_lossy().to_lowercase();
        if existing.contains(&key) {
            skipped.push(format!("{display_name}：已在列表中"));
            continue;
        }
        let (width, height) = match image::image_dimensions(&path) {
            Ok(value) => value,
            Err(error) => {
                skipped.push(format!("{display_name}：{error}"));
                continue;
            }
        };
        let id = Uuid::new_v4().to_string();
        if !hidden {
            preview_jobs.push((id.clone(), path.clone()));
        }
        new_items.push(ItemRecord {
            id,
            source_path: path,
            status: ItemStatus::Queued,
            model_override: None,
            error: None,
            result_path: None,
            source_preview: String::new(),
            result_preview: None,
            model: None,
            width,
            height,
            selected: false,
            hidden,
        });
        added += 1;
    }

    if let Ok(mut items) = state.items.lock() {
        items.extend(new_items);
    }
    if hidden && added > 0 {
        if let Ok(mut summary) = state.watch_summary.lock() {
            summary.queued += added;
        }
        emit_watch(app, state);
    }

    if added > 0 {
        let message = if hidden {
            format!("文件夹监视已加入 {added} 张图片")
        } else {
            format!("已添加 {added} 张，自动处理中…")
        };
        emit_status(app, &message);
        emit_queue_summary(app, state);
        start_preview_loader(app, preview_jobs);
        start_processor(app);
    }
    let mut parts = Vec::new();
    if added > 0 {
        parts.push(if hidden {
            format!("监视已加入 {added} 张")
        } else {
            format!("已添加 {added} 张，自动处理中…")
        });
    }
    if !hidden && existing.len() >= MAX_SESSION {
        parts.push(format!(
            "会话最多保留 {MAX_SESSION} 张，请先清除已完成项目。"
        ));
    }
    parts.extend(skipped.into_iter().take(2));
    if parts.is_empty() {
        parts.push("没有可添加的图片。".to_owned());
    }
    AddResult {
        added,
        message: parts.join(" "),
        items: queue_views(state),
    }
}

fn start_processor(app: &tauri::AppHandle) {
    let state = app.state::<AppState>();
    if state.processing.swap(true, Ordering::SeqCst) {
        return;
    }
    let app = app.clone();
    let _ = thread::Builder::new()
        .name("peel-image-queue".to_owned())
        .spawn(move || {
            lower_processing_thread_priority();
            process_loop(&app);
            let state = app.state::<AppState>();
            state.processing.store(false, Ordering::SeqCst);
            emit_queue_summary(&app, &state);
            let summary = queue_summary(&state);
            emit_status(
                &app,
                format!("全部完成 · 成功 {}，失败 {}", summary.done, summary.failed),
            );
        });
}

fn lower_processing_thread_priority() {
    #[cfg(windows)]
    {
        use windows_sys::Win32::System::Threading::{
            GetCurrentThread, SetThreadPriority, THREAD_PRIORITY_BELOW_NORMAL,
        };

        unsafe {
            let _ = SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_BELOW_NORMAL);
        }
    }
}

fn process_loop(app: &tauri::AppHandle) {
    loop {
        let state = app.state::<AppState>();
        let next = state.items.lock().ok().and_then(|mut items| {
            let item = items
                .iter_mut()
                .find(|item| item.status == ItemStatus::Queued)?;
            item.status = ItemStatus::Running;
            Some((
                item.id.clone(),
                item.source_path.clone(),
                item.hidden,
                item.model_override.take(),
            ))
        });
        let Some((id, source_path, hidden, model_override)) = next else {
            break;
        };
        if !hidden {
            emit_item_updated(app, &state, &id);
        }
        emit_queue_summary(app, &state);
        if !hidden {
            emit_status(
                app,
                format!(
                    "处理中：{}",
                    source_path
                        .file_name()
                        .and_then(|value| value.to_str())
                        .unwrap_or("图片")
                ),
            );
        }

        let settings = state
            .settings
            .lock()
            .map(|value| value.clone())
            .unwrap_or_default();
        let requested_model = model_override.unwrap_or_else(|| settings.model.clone());
        let result = state
            .engine
            .lock()
            .map_err(|_| "推理引擎不可用".to_owned())
            .and_then(|mut engine| {
                engine.set_model(requested_model.clone())?;
                engine.set_prefer_accel(settings.prefer_accel);
                engine.alpha_matting = settings.alpha_matting;
                let image = engine.remove(&source_path)?;
                let model = engine
                    .active_model
                    .clone()
                    .unwrap_or_else(|| requested_model.clone());
                Ok((image, model))
            });

        match result {
            Ok((image, model)) => {
                let output = if hidden {
                    watcher_output(&state, &source_path, &settings, &image)
                } else {
                    let target = state.data_dir.join("results").join(format!("{id}.png"));
                    write_png(&target, &image).map(|_| target)
                };
                match output {
                    Ok(output_path) => {
                        let preview = if hidden {
                            None
                        } else {
                            encode_data_url(&image, Some(1280)).ok()
                        };
                        let mut archive_failed = None;
                        if hidden && settings.watch_archive_sources {
                            archive_failed = archive_watch_source(&source_path, &settings);
                        }
                        if let Ok(mut items) = state.items.lock() {
                            if let Some(item) = items.iter_mut().find(|item| item.id == id) {
                                item.status = ItemStatus::Done;
                                item.error = archive_failed.clone();
                                item.result_path = Some(output_path);
                                item.result_preview = preview;
                                item.model = Some(model);
                            }
                            if hidden {
                                items.retain(|item| item.id != id);
                            }
                        }
                        if hidden {
                            if let Ok(mut summary) = state.watch_summary.lock() {
                                summary.queued = summary.queued.saturating_sub(1);
                                summary.success += 1;
                            }
                            if let Ok(watcher) = state.watcher.lock() {
                                if let Some(watcher) = watcher.as_ref() {
                                    watcher.mark(&source_path, "done");
                                }
                            }
                            emit_watch(app, &state);
                        }
                        if !hidden {
                            emit_item_updated(app, &state, &id);
                        }
                        emit_queue_summary(app, &state);
                    }
                    Err(error) => mark_failed(app, &state, &id, &source_path, hidden, error),
                }
            }
            Err(error) => mark_failed(app, &state, &id, &source_path, hidden, error),
        }
    }
}

fn mark_failed(
    app: &tauri::AppHandle,
    state: &AppState,
    id: &str,
    source: &Path,
    hidden: bool,
    error: String,
) {
    if hidden {
        write_watch_failure(source, &error, state);
    }
    if let Ok(mut items) = state.items.lock() {
        if let Some(item) = items.iter_mut().find(|item| item.id == id) {
            item.status = ItemStatus::Failed;
            item.error = Some(error.clone());
        }
        if hidden {
            items.retain(|item| item.id != id);
        }
    }
    if hidden {
        if let Ok(mut summary) = state.watch_summary.lock() {
            summary.queued = summary.queued.saturating_sub(1);
            summary.failed += 1;
        }
        if let Ok(watcher) = state.watcher.lock() {
            if let Some(watcher) = watcher.as_ref() {
                watcher.mark(source, "failed");
            }
        }
        emit_watch(app, state);
    } else {
        emit_status(app, format!("处理失败：{error}"));
    }
    if !hidden {
        emit_item_updated(app, state, id);
    }
    emit_queue_summary(app, state);
}

fn write_watch_failure(source: &Path, error: &str, state: &AppState) {
    let settings = state
        .settings
        .lock()
        .map(|value| value.clone())
        .unwrap_or_default();
    let input = PathBuf::from(settings.watch_dir.trim());
    let output = if settings.watch_output_dir.trim().is_empty() {
        input.join("已抠图")
    } else {
        PathBuf::from(settings.watch_output_dir.trim())
    };
    let failure_dir = output.join("失败");
    if fs::create_dir_all(&failure_dir).is_err() {
        return;
    }
    let stem = source
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("image");
    let token = Uuid::new_v4().to_string();
    let extension = source
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("png");
    let copied_source = failure_dir.join(format!("{stem}_{token}.{extension}"));
    let error_file = failure_dir.join(format!("{stem}_{token}_error.txt"));
    let _ = fs::copy(source, copied_source);
    let report = format!("源文件: {}\n错误: {}\n", source.display(), error);
    let _ = fs::write(error_file, report);
}

fn watcher_output(
    state: &AppState,
    source: &Path,
    settings: &Settings,
    image: &image::DynamicImage,
) -> Result<PathBuf, String> {
    let input = PathBuf::from(&settings.watch_dir);
    let output = if settings.watch_output_dir.trim().is_empty() {
        input.join("已抠图")
    } else {
        PathBuf::from(&settings.watch_output_dir)
    };
    let options = ExportOptions {
        directory: crate::watch::output_dir_for(&input, &output, source, settings.watch_recursive)
            .to_string_lossy()
            .into_owned(),
        prefix: settings::effective_prefix(settings).to_owned(),
        format: settings.export_format.clone(),
        custom_extension: settings.custom_extension.clone(),
    };
    let _ = state;
    export_image(image, source, &options)
}

fn archive_watch_source(source: &Path, settings: &Settings) -> Option<String> {
    let input = PathBuf::from(&settings.watch_dir);
    let archive_dir = input.join("已处理");
    let archive_parent = if settings.watch_recursive {
        source
            .strip_prefix(&input)
            .ok()
            .map(Path::to_path_buf)
            .or_else(|| {
                let source = source.canonicalize().ok()?;
                let input = input.canonicalize().ok()?;
                source.strip_prefix(input).ok().map(Path::to_path_buf)
            })
            .and_then(|relative| relative.parent().map(Path::to_path_buf))
            .map(|parent| archive_dir.join(parent))
            .unwrap_or_else(|| archive_dir.clone())
    } else {
        archive_dir.clone()
    };
    fs::create_dir_all(&archive_parent).ok()?;
    let name = source.file_name()?.to_os_string();
    let mut target = archive_parent.join(&name);
    let stem = source
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("image");
    let ext = source
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("png");
    let mut index = 1;
    while target.exists() {
        target = archive_parent.join(format!("{stem}_{index}.{ext}"));
        index += 1;
    }
    fs::rename(source, target)
        .err()
        .map(|error| format!("结果已导出，但归档源文件失败：{error}"))
}

fn start_watcher(app: &tauri::AppHandle) -> Result<(), String> {
    let state = app.state::<AppState>();
    let settings = state
        .settings
        .lock()
        .map(|value| value.clone())
        .map_err(|_| "读取设置失败".to_owned())?;
    let input_dir = PathBuf::from(settings.watch_dir.trim());
    if !input_dir.is_dir() {
        return Err("监视文件夹不存在".to_owned());
    }
    let output_dir = if settings.watch_output_dir.trim().is_empty() {
        input_dir.join("已抠图")
    } else {
        PathBuf::from(settings.watch_output_dir.trim())
    };
    let config = watch::WatchConfig {
        input_dir: input_dir.clone(),
        output_dir: output_dir.clone(),
        recursive: settings.watch_recursive,
        process_existing: settings.watch_process_existing,
        ledger_path: state.data_dir.join("watch-ledger.json"),
    };
    let app_for_callback = app.clone();
    let handle = watch::start(config, move |path| {
        let state = app_for_callback.state::<AppState>();
        let _ = enqueue_paths(&app_for_callback, &state, vec![path], true);
    })?;
    if let Ok(mut watcher) = state.watcher.lock() {
        *watcher = Some(handle);
    }
    if let Ok(mut summary) = state.watch_summary.lock() {
        summary.enabled = true;
        summary.paused = false;
        summary.queued = 0;
        summary.success = 0;
        summary.failed = 0;
        summary.status = format!("监视中：{} → {}", input_dir.display(), output_dir.display());
    }
    emit_watch(app, &state);
    sync_tray_visibility(app);
    emit_status(app, "文件夹监视已开启");
    Ok(())
}

fn stop_watcher(app: &tauri::AppHandle) {
    let state = app.state::<AppState>();
    let handle = state
        .watcher
        .lock()
        .ok()
        .and_then(|mut watcher| watcher.take());
    if let Some(handle) = handle {
        handle.stop();
    }
    if let Ok(mut summary) = state.watch_summary.lock() {
        summary.enabled = false;
        summary.paused = false;
        summary.status = "文件夹监视已关闭".to_owned();
        summary.queued = 0;
    }
    emit_watch(app, &state);
    sync_tray_visibility(app);
}

#[tauri::command]
fn get_app_info(state: State<'_, AppState>) -> AppInfo {
    app_info(&state)
}

#[tauri::command]
fn window_minimize(app: tauri::AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "找不到主窗口".to_owned())?;
    #[cfg(target_os = "windows")]
    {
        let hwnd = window
            .hwnd()
            .map_err(|error| format!("获取窗口句柄失败：{error}"))?;
        unsafe {
            windows_sys::Win32::UI::WindowsAndMessaging::ShowWindow(
                hwnd.0,
                windows_sys::Win32::UI::WindowsAndMessaging::SW_MINIMIZE,
            );
        }
        return Ok(());
    }
    #[cfg(not(target_os = "windows"))]
    window
        .minimize()
        .map_err(|error| format!("最小化窗口失败：{error}"))
}

#[tauri::command]
fn window_toggle_maximize(app: tauri::AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "找不到主窗口".to_owned())?;
    let maximized = window
        .is_maximized()
        .map_err(|error| format!("读取窗口状态失败：{error}"))?;
    #[cfg(target_os = "windows")]
    {
        let hwnd = window
            .hwnd()
            .map_err(|error| format!("获取窗口句柄失败：{error}"))?;
        let command = if maximized {
            windows_sys::Win32::UI::WindowsAndMessaging::SW_RESTORE
        } else {
            windows_sys::Win32::UI::WindowsAndMessaging::SW_MAXIMIZE
        };
        unsafe {
            windows_sys::Win32::UI::WindowsAndMessaging::ShowWindow(hwnd.0, command);
        }
        return Ok(());
    }
    #[cfg(not(target_os = "windows"))]
    if maximized {
        window
            .unmaximize()
            .map_err(|error| format!("还原窗口失败：{error}"))
    } else {
        window
            .maximize()
            .map_err(|error| format!("最大化窗口失败：{error}"))
    }
}

#[tauri::command]
fn window_close(app: tauri::AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "找不到主窗口".to_owned())?;
    #[cfg(target_os = "windows")]
    {
        let hwnd = window
            .hwnd()
            .map_err(|error| format!("获取窗口句柄失败：{error}"))?;
        let posted = unsafe {
            windows_sys::Win32::UI::WindowsAndMessaging::PostMessageW(
                hwnd.0,
                windows_sys::Win32::UI::WindowsAndMessaging::WM_CLOSE,
                0,
                0,
            )
        };
        if posted == 0 {
            return Err("关闭窗口消息发送失败".to_owned());
        }
        return Ok(());
    }
    #[cfg(not(target_os = "windows"))]
    window
        .close()
        .map_err(|error| format!("关闭窗口失败：{error}"))
}

#[tauri::command]
fn pick_images() -> Vec<String> {
    rfd::FileDialog::new()
        .add_filter(
            "图片",
            &["png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff", "gif"],
        )
        .pick_files()
        .unwrap_or_default()
        .into_iter()
        .map(|path| path.to_string_lossy().into_owned())
        .collect()
}

#[tauri::command]
async fn add_images(app: tauri::AppHandle, paths: Vec<String>) -> Result<AddResult, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<AppState>();
        enqueue_paths(
            &app,
            &state,
            paths.into_iter().map(PathBuf::from).collect(),
            false,
        )
    })
    .await
    .map_err(|error| format!("添加图片失败：{error}"))
}

#[tauri::command]
fn set_item_selected(
    state: State<'_, AppState>,
    id: String,
    selected: bool,
) -> Result<Vec<ItemView>, String> {
    let mut items = state.items.lock().map_err(|_| "读取队列失败".to_owned())?;
    let item = items
        .iter_mut()
        .find(|item| item.id == id)
        .ok_or_else(|| "找不到图片".to_owned())?;
    item.selected = selected;
    Ok(items.iter().map(ItemRecord::view).collect())
}

#[tauri::command]
fn clear_items(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    ids: Vec<String>,
) -> Result<Vec<ItemView>, String> {
    if state.processing.load(Ordering::SeqCst) {
        return Err("正在处理，无法清除，请等待完成。".to_owned());
    }
    let mut items = state.items.lock().map_err(|_| "读取队列失败".to_owned())?;
    let normal_count = items.iter().filter(|item| !item.hidden).count();
    let targets: std::collections::HashSet<String> = if ids.is_empty() && normal_count == 1 {
        items
            .iter()
            .filter(|item| !item.hidden)
            .map(|item| item.id.clone())
            .collect()
    } else {
        ids.into_iter().collect()
    };
    if targets.is_empty() {
        return Err("请先勾选要清除的图片。".to_owned());
    }
    let mut removed = 0;
    items.retain(|item| {
        if targets.contains(&item.id) {
            removed += 1;
            if let Some(path) = &item.result_path {
                let _ = fs::remove_file(path);
            }
            false
        } else {
            true
        }
    });
    drop(items);
    emit_status(&app, format!("已清除 {removed} 张"));
    emit_queue(&app, &state);
    Ok(queue_views(&state))
}

#[tauri::command]
fn reprocess_item(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    id: String,
    model: String,
) -> Result<String, String> {
    if state.processing.load(Ordering::SeqCst) {
        return Err("正在处理，请等待当前批次完成后再重抠。".to_owned());
    }
    if !is_valid_model_id(&model) {
        return Err("模型名称无效".to_owned());
    }
    let model_path = state.models_dir.join(format!("{model}.onnx"));
    if !model_path.is_file() {
        return Err(format!(
            "模型 {model} 尚未导入，请先在设置中导入 ONNX 文件。"
        ));
    }
    let mut items = state.items.lock().map_err(|_| "读取队列失败".to_owned())?;
    let item = items
        .iter_mut()
        .find(|item| item.id == id)
        .ok_or_else(|| "找不到该图片".to_owned())?;
    if !matches!(item.status, ItemStatus::Done | ItemStatus::Failed) {
        return Err("只能对已完成或失败的图片重新抠图。".to_owned());
    }
    if let Some(path) = item.result_path.take() {
        let _ = fs::remove_file(path);
    }
    item.result_preview = None;
    item.error = None;
    item.model = None;
    item.model_override = Some(model.clone());
    item.status = ItemStatus::Queued;
    drop(items);
    if let Ok(mut engine) = state.engine.lock() {
        engine.set_model(model.clone())?;
    }
    let message = format!("使用 {model} 重新处理");
    emit_status(&app, &message);
    emit_item_updated(&app, &state, &id);
    emit_queue_summary(&app, &state);
    start_processor(&app);
    Ok(message)
}

#[tauri::command]
async fn export_items(
    state: State<'_, AppState>,
    ids: Vec<String>,
    options: ExportOptions,
) -> Result<ExportResult, String> {
    let items = state
        .items
        .lock()
        .map_err(|_| "读取队列失败".to_owned())?
        .clone();
    tauri::async_runtime::spawn_blocking(move || export_items_blocking(items, ids, options))
        .await
        .map_err(|error| format!("导出图片失败：{error}"))
}

fn export_items_blocking(
    items: Vec<ItemRecord>,
    ids: Vec<String>,
    options: ExportOptions,
) -> ExportResult {
    let selected: std::collections::HashSet<String> = ids.into_iter().collect();
    let mut exported = 0;
    let mut failed = Vec::new();
    for item in items.iter().filter(|item| {
        !item.hidden
            && item.status == ItemStatus::Done
            && (selected.is_empty() || selected.contains(&item.id))
    }) {
        let Some(result_path) = &item.result_path else {
            failed.push(item.source_path.to_string_lossy().into_owned());
            continue;
        };
        match image::open(result_path).and_then(|image| {
            export_image(&image, &item.source_path, &options)
                .map_err(|error| image::ImageError::IoError(std::io::Error::other(error)))
        }) {
            Ok(_) => exported += 1,
            Err(_) => failed.push(item.source_path.to_string_lossy().into_owned()),
        }
    }
    ExportResult {
        exported,
        message: if failed.is_empty() {
            format!("已导出 {exported} 张")
        } else {
            format!("已导出 {exported} 张，失败 {} 张", failed.len())
        },
        failed,
    }
}

#[tauri::command]
fn choose_directory() -> Option<String> {
    rfd::FileDialog::new()
        .pick_folder()
        .map(|path| path.to_string_lossy().into_owned())
}

#[tauri::command]
fn choose_save_file(source_name: String, options: ExportOptions) -> Option<String> {
    let stem = Path::new(&source_name)
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("image");
    let extension = export::extension(&options);
    let prefix = options.prefix.trim();
    let file_name = format!("{prefix}{stem}.{extension}");
    let dialog = rfd::FileDialog::new()
        .add_filter("当前格式", &[extension.clone()])
        .add_filter("所有文件", &["*"])
        .set_file_name(file_name);
    dialog
        .save_file()
        .map(|path| path.to_string_lossy().into_owned())
}

#[tauri::command]
async fn export_item_to_file(
    state: State<'_, AppState>,
    id: String,
    path: String,
    options: ExportOptions,
) -> Result<ExportResult, String> {
    let item = state
        .items
        .lock()
        .map_err(|_| "读取队列失败".to_owned())?
        .iter()
        .find(|item| item.id == id && !item.hidden)
        .cloned()
        .ok_or_else(|| "找不到要导出的图片".to_owned())?;
    if item.status != ItemStatus::Done {
        return Err("图片还没有处理完成".to_owned());
    }
    let target = PathBuf::from(path);
    tauri::async_runtime::spawn_blocking(move || {
        let result_path = item
            .result_path
            .ok_or_else(|| "图片没有可导出的结果".to_owned())?;
        let image = image::open(&result_path).map_err(|error| format!("读取结果失败：{error}"))?;
        export_image_to_file(&image, &target, &options)?;
        Ok(ExportResult {
            exported: 1,
            failed: Vec::new(),
            message: "已保存 1 张".to_owned(),
        })
    })
    .await
    .map_err(|error| format!("导出图片失败：{error}"))?
}

#[tauri::command]
fn import_model(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    model: Option<String>,
) -> Result<AppInfo, String> {
    let Some(path) = rfd::FileDialog::new()
        .add_filter("ONNX 模型", &["onnx"])
        .pick_file()
    else {
        return Ok(app_info(&state));
    };
    let expected_id = match model.as_deref() {
        Some(value) if models::is_valid_model_id(value) => Some(value),
        Some(_) => return Err("模型名称无效".to_owned()),
        None => None,
    };
    let id = import_model_file(&state.models_dir, &path, expected_id)?;
    if let Ok(settings) = state.settings.lock() {
        if settings.model == id {
            if let Ok(mut engine) = state.engine.lock() {
                engine.set_model(id.clone())?;
            }
        }
    }
    emit_status(&app, format!("已导入模型 {id}"));
    Ok(app_info(&state))
}

#[tauri::command]
async fn download_model(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    model: String,
) -> Result<AppInfo, String> {
    if !models::is_valid_model_id(&model) {
        return Err("模型名称无效".to_owned());
    }
    let models_dir = state.models_dir.clone();
    let model_for_task = model.clone();
    let app_for_task = app.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let target = models_dir.join(format!("{model_for_task}.onnx"));
        if model_file_ready(&target) {
            return Ok(());
        }
        if let Some(url) = models::model_download_url(&model_for_task) {
            match download_model_file(&app_for_task, &models_dir, &model_for_task, url) {
                Ok(()) => Ok(()),
                Err(download_error) => {
                    emit_status(
                        &app_for_task,
                        format!("模型下载失败，可改为导入本地 ONNX：{download_error}"),
                    );
                    let Some(path) = rfd::FileDialog::new()
                        .add_filter("ONNX 模型", &["onnx"])
                        .pick_file()
                    else {
                        return Err(download_error);
                    };
                    import_model_file(&models_dir, &path, Some(&model_for_task)).map(|_| ())
                }
            }
        } else {
            let Some(path) = rfd::FileDialog::new()
                .add_filter("ONNX 模型", &["onnx"])
                .pick_file()
            else {
                return Err("未选择 ONNX 模型".to_owned());
            };
            import_model_file(&models_dir, &path, Some(&model_for_task)).map(|_| ())
        }
    })
    .await
    .map_err(|error| format!("准备模型失败：{error}"))??;
    if let Ok(settings) = state.settings.lock() {
        if settings.model == model {
            if let Ok(mut engine) = state.engine.lock() {
                engine.set_model(model.clone())?;
            }
        }
    }
    emit_status(&app, format!("模型 {model} 已就绪"));
    Ok(app_info(&state))
}

fn model_file_ready(path: &Path) -> bool {
    path.metadata()
        .map(|metadata| metadata.len() > 1024)
        .unwrap_or(false)
}

fn import_model_file(
    models_dir: &Path,
    source: &Path,
    expected_id: Option<&str>,
) -> Result<String, String> {
    let id = source
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("");
    if !models::is_valid_model_id(id) {
        return Err("模型文件名只能包含英文、数字、短横线或下划线。".to_owned());
    }
    if let Some(expected_id) = expected_id {
        if id != expected_id {
            return Err(format!(
                "所选文件名为 {id}.onnx，与当前模型 {expected_id}.onnx 不一致。"
            ));
        }
    }
    fs::create_dir_all(models_dir).map_err(|error| format!("创建模型目录失败：{error}"))?;
    let target = models_dir.join(format!("{id}.onnx"));
    fs::copy(source, &target).map_err(|error| format!("导入模型失败：{error}"))?;
    if !model_file_ready(&target) {
        return Err("导入的模型文件太小或不完整。".to_owned());
    }
    let partial = models_dir.join(format!("{id}.onnx.part"));
    let _ = fs::remove_file(partial);
    Ok(id.to_owned())
}

fn download_model_file(
    app: &tauri::AppHandle,
    models_dir: &Path,
    model: &str,
    url: &str,
) -> Result<(), String> {
    fs::create_dir_all(models_dir).map_err(|error| format!("创建模型目录失败：{error}"))?;
    let target = models_dir.join(format!("{model}.onnx"));
    let part = models_dir.join(format!("{model}.onnx.part"));
    let mut existing = part.metadata().map(|metadata| metadata.len()).unwrap_or(0);
    let mut request = ureq::get(url)
        .header("User-Agent", "Peel-win-bg-tool/2.0")
        .header("Accept-Encoding", "identity");
    if existing > 0 {
        request = request.header("Range", format!("bytes={existing}-"));
    }
    let mut response = request
        .call()
        .map_err(|error| format!("下载模型失败：{error}"))?;
    let status = response.status().as_u16();
    let append = existing > 0 && status == 206;
    if existing > 0 && status == 200 {
        existing = 0;
    } else if !(200..300).contains(&status) {
        return Err(format!("下载模型失败：HTTP {status}"));
    }
    let remaining = response
        .headers()
        .get("content-length")
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(0);
    let total = if append && remaining > 0 {
        existing.saturating_add(remaining)
    } else {
        remaining
    };
    let mut file = OpenOptions::new()
        .create(true)
        .write(true)
        .append(append)
        .truncate(!append)
        .open(&part)
        .map_err(|error| format!("创建模型临时文件失败：{error}"))?;
    let mut reader = response.body_mut().as_reader();
    let mut buffer = [0_u8; 1024 * 256];
    let mut downloaded = existing;
    let mut last_report = Instant::now();
    loop {
        let count = reader
            .read(&mut buffer)
            .map_err(|error| format!("读取模型下载失败：{error}"))?;
        if count == 0 {
            break;
        }
        file.write_all(&buffer[..count])
            .map_err(|error| format!("写入模型临时文件失败：{error}"))?;
        downloaded = downloaded.saturating_add(count as u64);
        if last_report.elapsed().as_millis() >= 250 {
            let message = if total > 0 {
                format!(
                    "正在下载模型 {model}：{}%",
                    downloaded.saturating_mul(100) / total
                )
            } else {
                format!("正在下载模型 {model}：{} MB", downloaded / 1024 / 1024)
            };
            emit_status(app, message);
            last_report = Instant::now();
        }
    }
    file.flush()
        .map_err(|error| format!("保存模型失败：{error}"))?;
    file.sync_all()
        .map_err(|error| format!("保存模型失败：{error}"))?;
    if !model_file_ready(&part) {
        return Err("模型下载未完成或文件无效，已保留 .part 以便下次续传。".to_owned());
    }
    if target.exists() {
        fs::remove_file(&target).map_err(|error| format!("替换模型失败：{error}"))?;
    }
    fs::rename(&part, &target).map_err(|error| format!("完成模型下载失败：{error}"))?;
    Ok(())
}

#[tauri::command]
fn remove_model(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    model: String,
) -> Result<AppInfo, String> {
    if !models::is_valid_model_id(&model) {
        return Err("模型名称无效".to_owned());
    }
    if model == models::DEFAULT_MODEL {
        return Err("内置模型不能删除。".to_owned());
    }
    let fallback = state
        .settings
        .lock()
        .ok()
        .filter(|settings| settings.model == model)
        .and_then(|_| {
            model_catalog(&state.models_dir)
                .into_iter()
                .find(|candidate| candidate.id != model && candidate.status == "downloaded")
                .map(|candidate| candidate.id)
        });
    for path in [
        state.models_dir.join(format!("{model}.onnx")),
        state.models_dir.join(format!("{model}.onnx.part")),
    ] {
        if path.is_file() {
            fs::remove_file(path).map_err(|error| format!("删除模型失败：{error}"))?;
        }
    }
    if let Some(fallback) = fallback {
        let mut settings = state
            .settings
            .lock()
            .map_err(|_| "读取设置失败".to_owned())?
            .clone();
        settings.model = fallback.clone();
        settings::save(&state.settings_path, &mut settings)?;
        if let Ok(mut current) = state.settings.lock() {
            *current = settings;
        }
        if let Ok(mut engine) = state.engine.lock() {
            engine.set_model(fallback.clone())?;
        }
        emit_status(
            &app,
            format!("已卸载模型 {model}，当前模型切换为 {fallback}"),
        );
    } else {
        emit_status(&app, format!("已删除模型 {model}"));
    }
    Ok(app_info(&state))
}

#[tauri::command]
fn clear_partial_models(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> Result<AppInfo, String> {
    let mut removed = 0_usize;
    if state.models_dir.is_dir() {
        let entries = fs::read_dir(&state.models_dir)
            .map_err(|error| format!("读取模型目录失败：{error}"))?;
        for entry in entries.flatten() {
            let path = entry.path();
            let name = path
                .file_name()
                .and_then(|value| value.to_str())
                .unwrap_or("");
            let is_partial =
                name.ends_with(".part") || (name.starts_with("tmp") && path.extension().is_none());
            if is_partial && path.is_file() && fs::remove_file(&path).is_ok() {
                removed += 1;
            }
        }
    }
    emit_status(&app, format!("已清理 {removed} 个未完成模型文件"));
    Ok(app_info(&state))
}

#[tauri::command]
fn warmup_model(app: tauri::AppHandle, state: State<'_, AppState>) -> Result<(), String> {
    let state_handle = app.state::<AppState>();
    if state_handle.processing.load(Ordering::SeqCst) {
        return Ok(());
    }
    let app = app.clone();
    thread::spawn(move || {
        lower_processing_thread_priority();
        let state = app.state::<AppState>();
        let settings = state
            .settings
            .lock()
            .map(|value| value.clone())
            .unwrap_or_default();
        let result = state
            .engine
            .lock()
            .map_err(|_| "推理引擎不可用".to_owned())
            .and_then(|mut engine| {
                engine.set_model(settings.model)?;
                engine.set_prefer_accel(settings.prefer_accel);
                engine.alpha_matting = settings.alpha_matting;
                engine.warmup()
            });
        match result {
            Ok(message) => emit_status(&app, message),
            Err(error) => emit_status(&app, error),
        }
    });
    let _ = state;
    Ok(())
}

#[tauri::command]
fn save_settings(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    mut next: Settings,
) -> Result<AppInfo, String> {
    settings::normalize(&mut next);
    let previous = state
        .settings
        .lock()
        .map(|value| value.clone())
        .unwrap_or_default();
    let watcher_exists = state
        .watcher
        .lock()
        .map(|watcher| watcher.is_some())
        .unwrap_or(false);
    let watch_changed = watch_configuration_changed(&previous, &next);
    settings::save(&state.settings_path, &mut next)?;
    if let Ok(mut current) = state.settings.lock() {
        *current = next.clone();
    }
    if let Ok(mut engine) = state.engine.lock() {
        engine.set_prefer_accel(next.prefer_accel);
        engine.alpha_matting = next.alpha_matting;
        engine.set_model(next.model.clone())?;
    }
    let watcher_should_change = watch_changed
        || (next.watch_enabled && !watcher_exists)
        || (!next.watch_enabled && watcher_exists);
    if watcher_should_change {
        stop_watcher(&app);
    }
    if watcher_should_change && next.watch_enabled {
        let start_result = if next.watch_dir.trim().is_empty() {
            Err("请先选择要监视的文件夹".to_owned())
        } else {
            start_watcher(&app)
        };
        if let Err(error) = start_result {
            let mut disabled = next.clone();
            disabled.watch_enabled = false;
            if let Ok(mut current) = state.settings.lock() {
                *current = disabled.clone();
            }
            let mut persisted = disabled;
            let _ = settings::save(&state.settings_path, &mut persisted);
            if let Ok(mut summary) = state.watch_summary.lock() {
                summary.status = error.clone();
            }
            sync_tray_visibility(&app);
            return Err(error);
        }
    }
    sync_tray_visibility(&app);
    emit_queue(&app, &state);
    Ok(app_info(&state))
}

#[tauri::command]
fn watch_pause(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    paused: bool,
) -> Result<WatchSummary, String> {
    let watcher = state
        .watcher
        .lock()
        .map_err(|_| "读取监视状态失败".to_owned())?;
    let handle = watcher
        .as_ref()
        .ok_or_else(|| "文件夹监视尚未开启".to_owned())?;
    handle.pause(paused);
    drop(watcher);
    let mut summary = state
        .watch_summary
        .lock()
        .map_err(|_| "读取监视状态失败".to_owned())?;
    summary.paused = paused;
    summary.status = if paused {
        "文件夹监视已暂停".to_owned()
    } else {
        "文件夹监视中".to_owned()
    };
    let result = summary.clone();
    let status = summary.status.clone();
    drop(summary);
    emit_status(&app, status);
    emit_watch(&app, &state);
    Ok(result)
}

#[tauri::command]
fn watch_clear_queue(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> Result<WatchSummary, String> {
    if let Some(handle) = state
        .watcher
        .lock()
        .map_err(|_| "读取监视状态失败".to_owned())?
        .as_ref()
    {
        handle.clear_queued();
    }
    if let Ok(mut items) = state.items.lock() {
        items.retain(|item| !item.hidden || item.status == ItemStatus::Running);
    }
    if let Ok(mut summary) = state.watch_summary.lock() {
        summary.queued = 0;
        summary.status = "已清空监视队列".to_owned();
        let result = summary.clone();
        let status = summary.status.clone();
        drop(summary);
        emit_status(&app, status);
        emit_queue(&app, &state);
        emit_watch(&app, &state);
        return Ok(result);
    }
    Err("读取监视状态失败".to_owned())
}

#[tauri::command]
fn watch_retry_failed(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> Result<WatchSummary, String> {
    let paths = state
        .watcher
        .lock()
        .map_err(|_| "读取监视状态失败".to_owned())?
        .as_ref()
        .map(|handle| handle.retry_failed())
        .unwrap_or_default();
    if let Ok(mut summary) = state.watch_summary.lock() {
        summary.failed = 0;
        summary.status = format!("已重新加入 {} 张失败图片", paths.len());
    }
    for path in paths {
        let _ = enqueue_paths(&app, &state, vec![path], true);
    }
    emit_queue(&app, &state);
    emit_watch(&app, &state);
    state
        .watch_summary
        .lock()
        .map(|value| value.clone())
        .map_err(|_| "读取监视状态失败".to_owned())
}

#[tauri::command]
async fn get_repair_image(state: State<'_, AppState>, id: String) -> Result<RepairImage, String> {
    let item = state
        .items
        .lock()
        .map_err(|_| "读取队列失败".to_owned())?
        .iter()
        .find(|item| item.id == id)
        .cloned()
        .ok_or_else(|| "找不到图片".to_owned())?;
    let result_path = item
        .result_path
        .ok_or_else(|| "该图片还没有处理结果".to_owned())?;
    let source_path = item.source_path;
    let width = item.width;
    let height = item.height;
    tauri::async_runtime::spawn_blocking(move || {
        let (original, _, _) = load_preview(&source_path, 2048)?;
        let (result, _, _) = load_preview(&result_path, 2048)?;
        Ok(RepairImage {
            id,
            original,
            result,
            width,
            height,
        })
    })
    .await
    .map_err(|error| format!("加载修补图片失败：{error}"))?
}

#[tauri::command]
async fn apply_mask(
    app: tauri::AppHandle,
    id: String,
    selection: mask::Selection,
    operation: String,
    feather: u32,
) -> Result<ItemView, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<AppState>();
        apply_mask_blocking(&app, &state, id, selection, operation, feather)
    })
    .await
    .map_err(|error| format!("修补图片失败：{error}"))?
}

fn apply_mask_blocking(
    app: &tauri::AppHandle,
    state: &AppState,
    id: String,
    selection: mask::Selection,
    operation: String,
    feather: u32,
) -> Result<ItemView, String> {
    let (source, result_path, width, height) = {
        let items = state.items.lock().map_err(|_| "读取队列失败".to_owned())?;
        let item = items
            .iter()
            .find(|item| item.id == id)
            .ok_or_else(|| "找不到图片".to_owned())?;
        let result_path = item
            .result_path
            .clone()
            .ok_or_else(|| "该图片还没有处理结果".to_owned())?;
        (
            item.source_path.clone(),
            result_path,
            item.width,
            item.height,
        )
    };
    let original = image::open(&source).map_err(|error| format!("读取原图失败：{error}"))?;
    let current = image::open(&result_path).map_err(|error| format!("读取结果失败：{error}"))?;
    let edited = mask::apply_mask_edit(&original, &current, &selection, &operation, feather)?;
    if let Ok(mut histories) = state.histories.lock() {
        let history = histories.entry(id.clone()).or_default();
        history.width = width;
        history.height = height;
        history.undo.push(current.to_rgba8().into_raw());
        if history.undo.len() > 15 {
            history.undo.remove(0);
        }
        history.redo.clear();
    }
    write_png(&result_path, &edited)?;
    let preview = encode_data_url(&edited, Some(1280))?;
    let mut items = state.items.lock().map_err(|_| "读取队列失败".to_owned())?;
    let item = items
        .iter_mut()
        .find(|item| item.id == id)
        .ok_or_else(|| "找不到图片".to_owned())?;
    item.result_preview = Some(preview);
    let view = item.view();
    drop(items);
    let _ = app.emit("item-updated", &view);
    Ok(view)
}

#[tauri::command]
async fn mask_history(
    app: tauri::AppHandle,
    id: String,
    direction: String,
) -> Result<ItemView, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<AppState>();
        mask_history_blocking(&app, &state, id, direction)
    })
    .await
    .map_err(|error| format!("历史操作失败：{error}"))?
}

fn mask_history_blocking(
    app: &tauri::AppHandle,
    state: &AppState,
    id: String,
    direction: String,
) -> Result<ItemView, String> {
    let (result_path, current, width, height) = {
        let items = state.items.lock().map_err(|_| "读取队列失败".to_owned())?;
        let item = items
            .iter()
            .find(|item| item.id == id)
            .ok_or_else(|| "找不到图片".to_owned())?;
        let path = item
            .result_path
            .clone()
            .ok_or_else(|| "该图片还没有处理结果".to_owned())?;
        let image = image::open(&path).map_err(|error| format!("读取结果失败：{error}"))?;
        (path, image, item.width, item.height)
    };
    let mut histories = state
        .histories
        .lock()
        .map_err(|_| "读取编辑历史失败".to_owned())?;
    let history = histories.entry(id.clone()).or_default();
    history.width = width;
    history.height = height;
    let target_bytes = if direction == "undo" {
        let target = history
            .undo
            .pop()
            .ok_or_else(|| "没有可撤销的操作".to_owned())?;
        history.redo.push(current.to_rgba8().into_raw());
        target
    } else {
        let target = history
            .redo
            .pop()
            .ok_or_else(|| "没有可重做的操作".to_owned())?;
        history.undo.push(current.to_rgba8().into_raw());
        target
    };
    let target = mask::image_from_rgba(width, height, target_bytes)?;
    write_png(&result_path, &target)?;
    let preview = encode_data_url(&target, Some(1280))?;
    drop(histories);
    let mut items = state.items.lock().map_err(|_| "读取队列失败".to_owned())?;
    let item = items
        .iter_mut()
        .find(|item| item.id == id)
        .ok_or_else(|| "找不到图片".to_owned())?;
    item.result_preview = Some(preview);
    let view = item.view();
    drop(items);
    let _ = app.emit("item-updated", &view);
    Ok(view)
}

#[tauri::command]
fn copy_result(state: State<'_, AppState>, id: String) -> Result<(), String> {
    let result_path = state
        .items
        .lock()
        .map_err(|_| "读取队列失败".to_owned())?
        .iter()
        .find(|item| item.id == id)
        .and_then(|item| item.result_path.clone())
        .ok_or_else(|| "没有可复制的结果".to_owned())?;
    let image = image::open(result_path)
        .map_err(|error| format!("读取结果失败：{error}"))?
        .to_rgba8();
    let data = arboard::ImageData {
        width: image.width() as usize,
        height: image.height() as usize,
        bytes: std::borrow::Cow::Owned(image.into_raw()),
    };
    let mut clipboard = Clipboard::new().map_err(|error| format!("打开剪贴板失败：{error}"))?;
    clipboard
        .set_image(data)
        .map_err(|error| format!("复制图片失败：{error}"))
}

#[tauri::command]
fn paste_image(state: State<'_, AppState>) -> Result<Option<String>, String> {
    let mut clipboard = Clipboard::new().map_err(|error| format!("打开剪贴板失败：{error}"))?;
    let data = match clipboard.get_image() {
        Ok(data) => data,
        Err(_) => return Ok(None),
    };
    let width = u32::try_from(data.width).map_err(|_| "剪贴板图片宽度无效".to_owned())?;
    let height = u32::try_from(data.height).map_err(|_| "剪贴板图片高度无效".to_owned())?;
    let image = image::RgbaImage::from_raw(width, height, data.bytes.into_owned())
        .ok_or_else(|| "剪贴板图片数据无效".to_owned())?;
    let directory = state.data_dir.join("clipboard");
    fs::create_dir_all(&directory).map_err(|error| format!("创建剪贴板目录失败：{error}"))?;
    let path = directory.join(format!("clipboard-{}.png", Uuid::new_v4()));
    image
        .save(&path)
        .map_err(|error| format!("保存剪贴板图片失败：{error}"))?;
    Ok(Some(path.to_string_lossy().into_owned()))
}

#[tauri::command]
fn open_path(path: String) -> Result<(), String> {
    let path = PathBuf::from(path);
    if !path.exists() {
        return Err("路径不存在".to_owned());
    }
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("explorer")
            .arg(path)
            .spawn()
            .map_err(|error| format!("打开文件夹失败：{error}"))?;
    }
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(path)
            .spawn()
            .map_err(|error| error.to_string())?;
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        std::process::Command::new("xdg-open")
            .arg(path)
            .spawn()
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn open_url(url: String) -> Result<(), String> {
    if !(url.starts_with("https://") || url.starts_with("http://"))
        || url
            .chars()
            .any(|value| value == '\r' || value == '\n' || value == '"')
    {
        return Err("只允许打开 http 或 https 链接".to_owned());
    }
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("rundll32.exe")
            .arg("url.dll,FileProtocolHandler")
            .arg(&url)
            .spawn()
            .map_err(|error| format!("打开链接失败：{error}"))?;
    }
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(&url)
            .spawn()
            .map_err(|error| format!("打开链接失败：{error}"))?;
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        std::process::Command::new("xdg-open")
            .arg(&url)
            .spawn()
            .map_err(|error| format!("打开链接失败：{error}"))?;
    }
    Ok(())
}

fn prepare_models(app: &tauri::AppHandle, models_dir: &Path) -> Result<(), String> {
    fs::create_dir_all(models_dir).map_err(|error| format!("创建模型目录失败：{error}"))?;
    let target = models_dir.join("u2netp.onnx");
    if target
        .metadata()
        .map(|metadata| metadata.len() > 1024)
        .unwrap_or(false)
    {
        return Ok(());
    }
    let mut candidates = Vec::new();
    let project_models = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap_or(Path::new("."))
        .join("models/u2netp.onnx");
    candidates.push(project_models);
    if let Ok(resource_dir) = app.path().resource_dir() {
        candidates.push(resource_dir.join("u2netp.onnx"));
        candidates.push(resource_dir.join("models/u2netp.onnx"));
    }
    if let Some(source) = candidates.into_iter().find(|path| path.is_file()) {
        fs::copy(source, target).map_err(|error| format!("复制内置模型失败：{error}"))?;
    }
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let data_dir = app.path().app_data_dir().unwrap_or_else(|_| {
                std::env::current_exe()
                    .ok()
                    .and_then(|path| path.parent().map(|parent| parent.join("data")))
                    .unwrap_or_else(|| PathBuf::from("data"))
            });
            let models_dir = data_dir.join("models");
            prepare_models(&app.handle(), &models_dir)?;
            let state = AppState::new(data_dir, models_dir);
            let should_watch = state
                .settings
                .lock()
                .map(|settings| settings.watch_enabled && !settings.watch_dir.is_empty())
                .unwrap_or(false);
            app.manage(state);
            if should_watch {
                if let Err(error) = start_watcher(&app.handle()) {
                    let state = app.state::<AppState>();
                    if let Ok(mut settings) = state.settings.lock() {
                        settings.watch_enabled = false;
                        let mut persisted = settings.clone();
                        let _ = settings::save(&state.settings_path, &mut persisted);
                    }
                    if let Ok(mut summary) = state.watch_summary.lock() {
                        summary.status = error;
                    }
                }
            }
            install_tray(app)?;
            install_window_close_behavior(&app.handle());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_app_info,
            window_minimize,
            window_toggle_maximize,
            window_close,
            pick_images,
            add_images,
            set_item_selected,
            clear_items,
            reprocess_item,
            export_items,
            choose_directory,
            choose_save_file,
            export_item_to_file,
            import_model,
            download_model,
            remove_model,
            clear_partial_models,
            warmup_model,
            save_settings,
            watch_pause,
            watch_clear_queue,
            watch_retry_failed,
            get_repair_image,
            apply_mask,
            mask_history,
            copy_result,
            paste_image,
            open_path,
            open_url,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Peel");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recursive_watch_archive_preserves_relative_path() {
        let root = std::env::temp_dir().join(format!("peel-watch-test-{}", Uuid::new_v4()));
        let source = root.join("nested").join("images").join("sample.png");
        fs::create_dir_all(source.parent().expect("source parent")).expect("create source dir");
        fs::write(&source, b"test").expect("write source");

        let mut settings = Settings::default();
        settings.watch_dir = root.to_string_lossy().into_owned();
        settings.watch_recursive = true;
        assert!(archive_watch_source(&source, &settings).is_none());

        let archived = root
            .join("已处理")
            .join("nested")
            .join("images")
            .join("sample.png");
        assert!(archived.is_file());
        assert!(!source.exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn ordinary_settings_change_does_not_restart_watcher() {
        let previous = Settings::default();
        let mut next = previous.clone();
        next.export_prefix = "cut_".to_owned();
        next.prefer_accel = true;
        assert!(!watch_configuration_changed(&previous, &next));

        next.watch_recursive = true;
        assert!(watch_configuration_changed(&previous, &next));
    }
}

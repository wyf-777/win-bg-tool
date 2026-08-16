use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{
    Arc, Mutex,
    atomic::{AtomicBool, Ordering},
};
use std::thread::{self, JoinHandle};
use std::time::{Duration, UNIX_EPOCH};

use crate::models::is_supported_image;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct FileSignature {
    size: u64,
    modified_nanos: u128,
}

#[derive(Debug, Clone)]
pub struct WatchConfig {
    pub input_dir: PathBuf,
    pub output_dir: PathBuf,
    pub recursive: bool,
    pub process_existing: bool,
    pub ledger_path: PathBuf,
}

#[derive(Debug, Clone)]
pub struct WatchHandle {
    stop: Arc<AtomicBool>,
    paused: Arc<AtomicBool>,
    ledger: Arc<Mutex<HashMap<String, String>>>,
    ledger_path: PathBuf,
    join: Arc<Mutex<Option<JoinHandle<()>>>>,
}

impl WatchHandle {
    pub fn pause(&self, paused: bool) {
        self.paused.store(paused, Ordering::SeqCst);
    }

    pub fn mark(&self, path: &Path, status: &str) {
        let key = normalized(path);
        if let Ok(mut ledger) = self.ledger.lock() {
            ledger.insert(key, ledger_record(path, status));
            let _ = save_ledger(&self.ledger_path, &ledger);
        }
    }

    pub fn retry_failed(&self) -> Vec<PathBuf> {
        let mut result = Vec::new();
        if let Ok(mut ledger) = self.ledger.lock() {
            let failed = ledger
                .iter()
                .filter(|(_, status)| ledger_status(status) == "failed")
                .map(|(path, _)| PathBuf::from(path))
                .collect::<Vec<_>>();
            for candidate in failed {
                if candidate.is_file() {
                    ledger.insert(normalized(&candidate), ledger_record(&candidate, "queued"));
                    result.push(candidate);
                }
            }
            let _ = save_ledger(&self.ledger_path, &ledger);
        }
        result
    }

    pub fn clear_queued(&self) {
        if let Ok(mut ledger) = self.ledger.lock() {
            let queued = ledger
                .iter()
                .filter(|(_, status)| ledger_status(status) == "queued")
                .map(|(path, _)| path.clone())
                .collect::<Vec<_>>();
            for path in queued {
                let source = PathBuf::from(&path);
                if source.is_file() {
                    ledger.insert(path, ledger_record(&source, "ignored"));
                } else {
                    ledger.remove(&path);
                }
            }
            let _ = save_ledger(&self.ledger_path, &ledger);
        }
    }

    pub fn stop(&self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Ok(mut join) = self.join.lock() {
            if let Some(handle) = join.take() {
                let _ = handle.join();
            }
        }
    }
}

pub fn start<F>(config: WatchConfig, on_image: F) -> Result<WatchHandle, String>
where
    F: Fn(PathBuf) + Send + Sync + 'static,
{
    if !config.input_dir.is_dir() {
        return Err("监视文件夹不存在".to_owned());
    }
    if normalized(&config.input_dir) == normalized(&config.output_dir) {
        return Err("监视文件夹与输出文件夹不能相同".to_owned());
    }
    fs::create_dir_all(&config.output_dir)
        .map_err(|error| format!("创建监视输出目录失败：{error}"))?;
    if let Some(parent) = config.ledger_path.parent() {
        fs::create_dir_all(parent).map_err(|error| format!("创建监视清单目录失败：{error}"))?;
    }

    let ledger = Arc::new(Mutex::new(load_ledger(&config.ledger_path)));
    let initial = scan_images(&config.input_dir, &config.output_dir, config.recursive);
    if let Ok(mut entries) = ledger.lock() {
        if config.process_existing {
            for path in &initial {
                entries.remove(&normalized(path));
            }
        } else {
            for path in &initial {
                let key = normalized(path);
                if entries
                    .get(&key)
                    .map(|record| ledger_matches(record, path))
                    .unwrap_or(false)
                {
                    continue;
                }
                entries.insert(key, ledger_record(path, "ignored"));
            }
        }
        let _ = save_ledger(&config.ledger_path, &entries);
    }

    let stop = Arc::new(AtomicBool::new(false));
    let paused = Arc::new(AtomicBool::new(false));
    let ledger_for_thread = Arc::clone(&ledger);
    let stop_for_thread = Arc::clone(&stop);
    let paused_for_thread = Arc::clone(&paused);
    let input_dir = config.input_dir.clone();
    let output_dir = config.output_dir.clone();
    let ledger_path = config.ledger_path.clone();
    let recursive = config.recursive;
    let callback: Arc<dyn Fn(PathBuf) + Send + Sync> = Arc::new(on_image);
    let thread_callback = Arc::clone(&callback);

    let join = thread::Builder::new()
        .name("peel-folder-watch".to_owned())
        .spawn(move || {
            let mut pending: HashMap<String, (FileSignature, bool)> = HashMap::new();
            while !stop_for_thread.load(Ordering::SeqCst) {
                if !paused_for_thread.load(Ordering::SeqCst) {
                    let candidates = scan_images(&input_dir, &output_dir, recursive);
                    let mut live = HashSet::new();
                    for path in candidates {
                        let key = normalized(&path);
                        live.insert(key.clone());
                        let Some(signature) = file_signature(&path) else {
                            pending.remove(&key);
                            continue;
                        };
                        let should_enqueue = ledger_for_thread
                            .lock()
                            .map(|entries| {
                                entries
                                    .get(&key)
                                    .map(|record| !ledger_matches(record, &path))
                                    .unwrap_or(true)
                            })
                            .unwrap_or(false);
                        if !should_enqueue {
                            pending.remove(&key);
                            continue;
                        }
                        let stable = match pending.get_mut(&key) {
                            Some((previous, stable)) if *previous == signature => {
                                let was_stable = *stable;
                                *stable = true;
                                was_stable
                            }
                            Some(entry) => {
                                *entry = (signature, false);
                                false
                            }
                            None => {
                                pending.insert(key.clone(), (signature, false));
                                false
                            }
                        };
                        if stable {
                            pending.remove(&key);
                            if let Ok(mut entries) = ledger_for_thread.lock() {
                                if entries
                                    .get(&key)
                                    .map(|record| ledger_matches(record, &path))
                                    .unwrap_or(false)
                                {
                                    continue;
                                }
                                entries.insert(key, ledger_record(&path, "queued"));
                                let _ = save_ledger(&ledger_path, &entries);
                            }
                            thread_callback(path);
                        }
                    }
                    pending.retain(|key, _| live.contains(key));
                }
                for _ in 0..4 {
                    if stop_for_thread.load(Ordering::SeqCst) {
                        break;
                    }
                    thread::sleep(Duration::from_millis(100));
                }
            }
        })
        .map_err(|error| format!("启动文件夹监视失败：{error}"))?;

    Ok(WatchHandle {
        stop,
        paused,
        ledger,
        ledger_path: config.ledger_path,
        join: Arc::new(Mutex::new(Some(join))),
    })
}

pub fn output_dir_for(
    input_dir: &Path,
    output_dir: &Path,
    source: &Path,
    recursive: bool,
) -> PathBuf {
    if recursive {
        let relative = source
            .strip_prefix(input_dir)
            .ok()
            .map(Path::to_path_buf)
            .or_else(|| {
                let source = source.canonicalize().ok()?;
                let input = input_dir.canonicalize().ok()?;
                source.strip_prefix(input).ok().map(Path::to_path_buf)
            });
        if let Some(relative) = relative {
            if let Some(parent) = relative.parent() {
                return output_dir.join(parent);
            }
        }
    }
    output_dir.to_path_buf()
}

fn scan_images(input_dir: &Path, output_dir: &Path, recursive: bool) -> Vec<PathBuf> {
    let mut result = Vec::new();
    scan_into(input_dir, output_dir, recursive, &mut result);
    result.sort();
    result
}

fn scan_into(current: &Path, output_dir: &Path, recursive: bool, result: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(current) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if normalized(&path) == normalized(output_dir) {
            continue;
        }
        if path.is_dir() {
            let is_archive = path.file_name().and_then(|value| value.to_str()) == Some("已处理");
            if recursive && !is_archive {
                scan_into(&path, output_dir, recursive, result);
            }
        } else if is_supported_image(&path) {
            result.push(path);
        }
    }
}

fn normalized(path: &Path) -> String {
    path.canonicalize()
        .unwrap_or_else(|_| path.to_path_buf())
        .to_string_lossy()
        .to_lowercase()
}

fn file_signature(path: &Path) -> Option<FileSignature> {
    let metadata = fs::metadata(path).ok()?;
    let modified_nanos = metadata
        .modified()
        .ok()?
        .duration_since(UNIX_EPOCH)
        .ok()?
        .as_nanos();
    Some(FileSignature {
        size: metadata.len(),
        modified_nanos,
    })
}

fn ledger_record(path: &Path, status: &str) -> String {
    file_signature(path)
        .map(|signature| format!("{}|{}|{}", status, signature.size, signature.modified_nanos))
        .unwrap_or_else(|| status.to_owned())
}

fn ledger_status(record: &str) -> &str {
    record.split('|').next().unwrap_or(record)
}

fn ledger_matches(record: &str, path: &Path) -> bool {
    let mut parts = record.split('|');
    let _status = parts.next();
    let Some(size) = parts.next().and_then(|value| value.parse::<u64>().ok()) else {
        return true;
    };
    let Some(modified_nanos) = parts.next().and_then(|value| value.parse::<u128>().ok()) else {
        return true;
    };
    file_signature(path)
        .map(|signature| signature.size == size && signature.modified_nanos == modified_nanos)
        .unwrap_or(false)
}

fn load_ledger(path: &Path) -> HashMap<String, String> {
    fs::read_to_string(path)
        .ok()
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or_default()
}

fn save_ledger(path: &Path, entries: &HashMap<String, String>) -> Result<(), String> {
    let text = serde_json::to_string_pretty(entries).map_err(|error| error.to_string())?;
    fs::write(path, text).map_err(|error| error.to_string())
}

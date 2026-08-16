export type ItemStatus = "queued" | "running" | "done" | "failed";

export interface ImageItem {
  id: string;
  name: string;
  source_path: string;
  result_path: string | null;
  status: ItemStatus;
  error: string | null;
  source_preview: string;
  result_preview: string | null;
  model: string | null;
  width: number;
  height: number;
  selected: boolean;
  hidden: boolean;
}

export interface Settings {
  model: string;
  export_prefix_enabled: boolean;
  export_prefix: string;
  export_format: string;
  custom_extension: string;
  alpha_matting: boolean;
  prefer_accel: boolean;
  watch_enabled: boolean;
  watch_dir: string;
  watch_output_dir: string;
  watch_process_existing: boolean;
  watch_recursive: boolean;
  watch_archive_sources: boolean;
  watch_minimize_to_tray: boolean;
}

export interface ModelInfo {
  id: string;
  label: string;
  skill: string;
  note: string;
  status: "downloaded" | "partial" | "missing";
  size_bytes: number;
}

export interface AccelerationInfo {
  available: boolean;
  label: string;
  detail: string;
}

export interface WatchSummary {
  enabled: boolean;
  paused: boolean;
  status: string;
  queued: number;
  success: number;
  failed: number;
}

export interface AppInfo {
  settings: Settings;
  models: ModelInfo[];
  models_dir: string;
  acceleration: AccelerationInfo;
  watch: WatchSummary;
  version: string;
}

export interface QueueSummary {
  total: number;
  queued: number;
  running: number;
  done: number;
  failed: number;
  processing: boolean;
}

export interface AddResult {
  added: number;
  message: string;
  items: ImageItem[];
}

export interface ExportResult {
  exported: number;
  failed: string[];
  message: string;
}

export interface RepairImage {
  id: string;
  original: string;
  result: string;
  width: number;
  height: number;
}

export interface SelectionPoint {
  x: number;
  y: number;
}

export interface Selection {
  kind: "lasso" | "brush";
  points: SelectionPoint[];
  radius: number;
}

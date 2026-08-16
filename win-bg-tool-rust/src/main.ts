import "./styles.css";

import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";

import { call } from "./api";
import type {
  AddResult,
  AppInfo,
  ExportResult,
  ImageItem,
  ItemStatus,
  QueueSummary,
  RepairImage,
  Selection,
  Settings,
  WatchSummary,
} from "./types";

const rootElement = document.querySelector<HTMLDivElement>("#app");
if (!rootElement) throw new Error("应用根节点不存在");
const root = rootElement;

type View = "main" | "settings" | "repair";
type SettingsTab = "appearance" | "model" | "export" | "watch" | "hotkeys" | "faq";
type RepairMode = "lasso" | "polygon" | "brush";

let info: AppInfo | null = null;
let items: ImageItem[] = [];
let summary: QueueSummary = {
  total: 0,
  queued: 0,
  running: 0,
  done: 0,
  failed: 0,
  processing: false,
};
let view: View = "main";
let settingsTab: SettingsTab = "appearance";
let selectedId = "";
let lightboxIndex = -1;
let sideBySide = false;
let holdOriginal = false;
let starOpen = false;
let windowMaximized = false;
let windowActionBusy = false;
const pendingItemPayloads = new Map<string, ImageItem>();
let statusMessage = "界面已就绪 · 推理引擎后台准备中…";
let themePreference = localStorage.getItem("peel-theme") || "system";

let repairId = "";
let repairData: RepairImage | null = null;
let repairOriginalImage: HTMLImageElement | null = null;
let repairImage: HTMLImageElement | null = null;
let repairMode: RepairMode = "lasso";
let repairPoints: { x: number; y: number }[] = [];
let repairDrawing = false;
let repairPolygonClosed = false;
let repairBrushDiameter = 32;
let repairFeather = 4;
let repairOverlay = 38;
let toastTimer = 0;
let repairDrawFrame = 0;
let repairBaseCanvas: HTMLCanvasElement | null = null;
let modelSelection = "";

type HotkeyId = "open" | "export" | "copy" | "paste" | "settings" | "escape" | "lightbox_prev" | "lightbox_next" | "peek_original" | "side_by_side";
let hotkeyCaptureId: HotkeyId | null = null;
const defaultHotkeys: Record<HotkeyId, string> = {
  open: "Ctrl+O",
  export: "Ctrl+S",
  copy: "Ctrl+C",
  paste: "Ctrl+V",
  settings: "Ctrl+,",
  escape: "Escape",
  lightbox_prev: "ArrowLeft",
  lightbox_next: "ArrowRight",
  peek_original: "Space",
  side_by_side: "Ctrl+D",
};

const text = (value: unknown) => String(value ?? "");

function escapeHtml(value: unknown): string {
  return text(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function hotkeys(): Record<HotkeyId, string> {
  const stored = localStorage.getItem("peel-hotkeys");
  if (!stored) return { ...defaultHotkeys };
  try {
    const parsed = JSON.parse(stored) as Record<string, unknown>;
    const result = { ...defaultHotkeys };
    for (const id of Object.keys(defaultHotkeys) as HotkeyId[]) {
      if (typeof parsed[id] === "string" && parsed[id].trim()) result[id] = parsed[id].trim();
    }
    return result;
  } catch {
    return { ...defaultHotkeys };
  }
}

function hotkeyValue(id: HotkeyId): string {
  return hotkeys()[id];
}

function eventHotkey(event: KeyboardEvent): string {
  let key = event.key;
  if (key === " ") key = "Space";
  else if (key === "Escape") key = "Escape";
  else if (key.length === 1) key = key.toUpperCase();
  if (["Control", "Alt", "Shift", "Meta"].includes(key)) return "";
  const parts: string[] = [];
  if (event.ctrlKey) parts.push("Ctrl");
  if (event.altKey) parts.push("Alt");
  if (event.shiftKey) parts.push("Shift");
  if (event.metaKey) parts.push("Meta");
  return key ? [...parts, key].join("+") : "";
}

function hotkeyMatches(event: KeyboardEvent, id: HotkeyId): boolean {
  return eventHotkey(event) === hotkeyValue(id);
}

function saveHotkey(id: HotkeyId, value: string): boolean {
  const current = hotkeys();
  const conflict = (Object.keys(current) as HotkeyId[]).some((other) => other !== id && current[other] === value);
  if (conflict) {
    toast("这个快捷键已经被其他功能使用", true);
    return false;
  }
  current[id] = value;
  localStorage.setItem("peel-hotkeys", JSON.stringify(current));
  return true;
}

function formatBytes(bytes: number): string {
  if (!bytes) return "未下载";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function statusLabel(status: ItemStatus): string {
  return {
    queued: "等待",
    running: "处理中",
    done: "完成",
    failed: "失败",
  }[status];
}

function visibleItems(): ImageItem[] {
  return items.filter((item) => !item.hidden);
}

function currentItem(): ImageItem | undefined {
  const list = visibleItems();
  if (lightboxIndex >= 0 && lightboxIndex < list.length) return list[lightboxIndex];
  if (list.length === 1) return list[0];
  return list.find((item) => item.id === selectedId);
}

function doneItemForAction(): ImageItem | undefined {
  const list = visibleItems().filter((item) => item.status === "done" && item.result_preview);
  const current = currentItem();
  if (current && current.status === "done" && current.result_preview) return current;
  const selected = list.filter((item) => item.selected);
  if (selected.length === 1) return selected[0];
  return list.length === 1 ? list[0] : undefined;
}

function toast(message: string, danger = false): void {
  const node = document.querySelector<HTMLDivElement>("#toast");
  if (!node) return;
  node.textContent = message;
  node.className = `toast ${danger ? "danger" : ""} show`;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => node.classList.remove("show"), 3200);
}

function setItems(next: ImageItem[]): void {
  items = next.filter((item) => !item.hidden);
  for (const [id, payload] of pendingItemPayloads) {
    const index = items.findIndex((item) => item.id === id);
    if (index >= 0) {
      items[index] = payload;
      pendingItemPayloads.delete(id);
    }
  }
  if (items.length < 2) lightboxIndex = -1;
  if (selectedId && !items.some((item) => item.id === selectedId)) selectedId = "";
  if (!selectedId && items.length === 1) selectedId = items[0].id;
}

function applyItemPayload(payload: ImageItem): void {
  const index = items.findIndex((item) => item.id === payload.id);
  if (index >= 0) items[index] = payload;
  else pendingItemPayloads.set(payload.id, payload);
}

function resolvedTheme(): "light" | "dark" {
  if (themePreference === "dark") return "dark";
  if (themePreference === "light") return "light";
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function render(): void {
  root.dataset.theme = resolvedTheme();
  if (view === "settings") root.innerHTML = renderSettings();
  else if (view === "repair") root.innerHTML = renderRepair();
  else root.innerHTML = renderMain();
  wireRenderedView();
  if (view === "repair" && repairData) {
    window.requestAnimationFrame(() => setupRepairCanvas());
  }
}

function renderTitlebar(settingsBack = false): string {
  return `
    <header class="titlebar">
      <div class="title-leading">
        <button type="button" class="chrome-button" data-action="toggle-star" title="关于 / 反馈 / 支持" aria-label="关于 / 反馈 / 支持"><span class="icon icon-svg">${iconSvg("star")}</span></button>
        <span class="model-label">${escapeHtml(modelLabel())}</span>
        <button type="button" class="chrome-button title-settings" data-action="${settingsBack ? "back-main" : "settings"}" title="${settingsBack ? "返回主界面" : "设置"}" aria-label="${settingsBack ? "返回主界面" : "设置"}"><span class="icon icon-svg">${iconSvg(settingsBack ? "arrow-left" : "settings")}</span></button>
      </div>
      <div class="window-controls">
        <button type="button" class="chrome-button" data-window="minimize" title="最小化" aria-label="最小化"><span class="icon icon-svg">${iconSvg("min")}</span></button>
        <button type="button" class="chrome-button" data-window="maximize" title="${windowMaximized ? "还原" : "最大化"}" aria-label="${windowMaximized ? "还原" : "最大化"}"><span class="icon icon-svg">${iconSvg(windowMaximized ? "restore" : "max")}</span></button>
        <button type="button" class="chrome-button close-button" data-window="close" title="关闭" aria-label="关闭"><span class="icon icon-svg">${iconSvg("close")}</span></button>
      </div>
    </header>`;
}

type ChromeIcon = "star" | "settings" | "arrow-left" | "min" | "max" | "restore" | "close";

function iconSvg(kind: ChromeIcon): string {
  const stroke = 'fill="none" stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"';
  const body = {
    star: '<path d="M16 9.8l1.59 4.02 4.3.26-3.31 2.75 1.08 4.2L16 18.7l-3.66 2.33 1.08-4.2-3.31-2.75 4.3-.26L16 9.8z" />',
    settings: '<path d="M16 9.66l2.57 1.88 2.91-.71.71 2.91 1.88 2.57-1.88 2.57-.71 2.91-2.91-.71L16 23l-2.57-1.92-2.91.71-.71-2.91L7.93 16l1.88-2.57.71-2.91 2.91.71L16 9.66z" /><circle cx="16" cy="16" r="2.11" />',
    "arrow-left": '<path d="M11 16h10M11 16l3.8-3.8M11 16l3.8 3.8" />',
    min: '<path d="M11 16h10" />',
    max: '<rect x="11" y="11" width="10" height="10" rx="0.8" />',
    restore: '<path d="M13 12h8v8h-8zM11 14h-1v8h8v-1" />',
    close: '<path d="M11.4 11.4l9.2 9.2M20.6 11.4l-9.2 9.2" />',
  }[kind];
  return `<svg viewBox="0 0 32 32" aria-hidden="true" ${stroke}>${body}</svg>`;
}

function modelLabel(): string {
  if (!info) return "本机 · 引擎准备中…";
  return `本机 · ${info.settings.model} · ${info.acceleration.label}`;
}

function renderStatusbar(): string {
  return `<div class="statusbar">${escapeHtml(statusMessage)}</div>`;
}

function renderStarPanel(): string {
  return `
    <div class="star-panel-shell ${starOpen ? "open" : ""}" id="star-panel" aria-hidden="${!starOpen}">
      <section class="star-panel">
        <button class="star-row-button" data-action="copy-group">QQ交流群:912291243</button>
        <button class="star-row-button" data-action="open-bili">反馈 - 建议(B站私信)</button>
        <button class="star-row-button" data-action="open-github">反馈 - 建议(Github Issues)</button>
        <div class="star-caption">o(´^｀)o你不会想白嫖吧</div>
        <div class="qr-row">
          <div class="qr-column"><div class="qr-host"><img src="/assets/wechat_qr.png" alt="微信二维码" /></div><span>微信</span></div>
          <div class="qr-column"><div class="qr-host"><img src="/assets/alipay_qr.png" alt="支付宝二维码" /></div><span>支付宝</span></div>
        </div>
      </section>
    </div>`;
}

let mainPatchFrame = 0;
const pendingItemUpdates = new Set<string>();

function scheduleMainPatch(itemId?: string): void {
  if (itemId) pendingItemUpdates.add(itemId);
  if (mainPatchFrame) return;
  mainPatchFrame = window.requestAnimationFrame(() => {
    mainPatchFrame = 0;
    if (view !== "main") {
      pendingItemUpdates.clear();
      return;
    }

    const changedIds = [...pendingItemUpdates];
    pendingItemUpdates.clear();
    const workspace = root.querySelector<HTMLElement>(".workspace");
    if (workspace && changedIds.length) {
      if (lightboxIndex >= 0 || items.length < 2) {
        workspace.innerHTML = lightboxIndex >= 0 ? renderLightbox() : renderCanvas(items[0]);
      } else {
        for (const id of changedIds) {
          const item = items.find((candidate) => candidate.id === id);
          const tile = [...workspace.querySelectorAll<HTMLElement>("[data-item-id]")].find((candidate) => candidate.dataset.itemId === id);
          if (!item || !tile) continue;
          const template = document.createElement("template");
          template.innerHTML = renderGridTile(item);
          const nextTile = template.content.firstElementChild;
          if (nextTile) tile.replaceWith(nextTile);
        }
      }
    }
    patchMainFooter();
    wireRenderedView();
  });
}

function patchMainFooter(): void {
  if (view !== "main") return;
  const n = items.length;
  const multi = n >= 2;
  const done = items.filter((item) => item.status === "done" && item.result_preview).length;
  const selectedDone = items.filter((item) => item.selected && item.status === "done" && item.result_preview).length;
  const selected = items.filter((item) => item.selected).length;
  const allSelected = n > 0 && items.every((item) => item.selected);
  const repairEnabled = Boolean(doneItemForAction());
  const exportSuffix = (info?.settings.export_format || "png").replace("custom", info?.settings.custom_extension || "png").toUpperCase();

  root.querySelector<HTMLElement>(".batch-bar")?.classList.toggle("visible", multi);
  const batchInfo = root.querySelector<HTMLElement>(".batch-info");
  if (batchInfo) batchInfo.textContent = multi ? `${n} 张 ·  完成 ${done}  ·  已选 ${selected}` : "";

  const selectAll = root.querySelector<HTMLInputElement>("#select-all");
  if (selectAll) {
    selectAll.checked = allSelected;
    selectAll.disabled = summary.processing || !n;
  }
  const invert = root.querySelector<HTMLInputElement>("#invert-select");
  if (invert) invert.disabled = summary.processing || !n;

  const action = (name: string) => root.querySelector<HTMLButtonElement>(`[data-action="${name}"]`);
  const importButton = action("import");
  if (importButton) importButton.disabled = summary.processing;
  const clearButton = action("clear");
  if (clearButton) clearButton.disabled = !n || summary.processing;
  const repairButton = action("repair");
  if (repairButton) repairButton.disabled = !repairEnabled;
  const selectedExport = action("export-selected");
  if (selectedExport) {
    selectedExport.hidden = !multi;
    selectedExport.disabled = !selectedDone;
  }
  const exportButton = action("export-all");
  if (exportButton) {
    const label = exportButton.querySelector<HTMLElement>("span:last-child");
    if (label) label.textContent = multi ? "导出全部" : `导出 ${exportSuffix}`;
  }

  const watchStatus = root.querySelector<HTMLElement>(".watch-status");
  if (watchStatus) {
    watchStatus.classList.toggle("visible", Boolean(info?.watch.enabled));
    watchStatus.textContent = info?.watch.status || "";
  }
}

function renderMain(): string {
  const multi = items.length >= 2;
  const n = items.length;
  const done = items.filter((item) => item.status === "done" && item.result_preview).length;
  const selectedDone = items.filter((item) => item.selected && item.status === "done" && item.result_preview).length;
  const allSelected = n > 0 && items.every((item) => item.selected);
  const repairEnabled = Boolean(doneItemForAction());
  const exportSuffix = (info?.settings.export_format || "png").replace("custom", info?.settings.custom_extension || "png").toUpperCase();

  return `
    <div class="app-window">
      ${renderTitlebar()}
      <main class="main-page">
        <section class="workspace" data-drop-zone>
          ${lightboxIndex >= 0 ? renderLightbox() : multi ? renderGrid() : renderCanvas(items[0])}
        </section>
        <footer class="main-footer">
          <div class="batch-bar ${multi ? "visible" : ""}">
            <label class="batch-check"><input id="select-all" type="checkbox" ${allSelected ? "checked" : ""} ${summary.processing || !n ? "disabled" : ""}/><span class="checkbox-mark"></span><span>全选</span></label>
            <label class="batch-check"><input id="invert-select" type="checkbox" ${summary.processing || !n ? "disabled" : ""}/><span class="checkbox-mark"></span><span>反选</span></label>
            <span class="batch-spacer"></span>
            <span class="batch-info">${multi ? `${n} 张  ·  完成 ${done}  ·  已选 ${items.filter((item) => item.selected).length}` : ""}</span>
          </div>
          <div class="main-actions">
            <button class="capsule-btn open-capsule" data-action="import" ${summary.processing ? "disabled" : ""}><span class="btn-icon folder-icon"></span><span>打开…</span></button>
            <span class="actions-spacer"></span>
            <button class="capsule-btn clear-capsule" data-action="clear" ${!n || summary.processing ? "disabled" : ""}><span class="btn-icon broom-icon"></span><span>清除</span></button>
            <button class="capsule-btn repair-capsule" data-action="repair" ${repairEnabled ? "" : "disabled"}><span class="btn-icon brush-icon"></span><span>修补</span></button>
            <button class="action-btn export-selected" data-action="export-selected" ${multi ? "" : "hidden"} ${!selectedDone ? "disabled" : ""}>导出选中</button>
            <button class="capsule-btn export-capsule" data-action="export-all">${multi ? "" : ""}<span class="btn-icon arrow-icon"></span><span>${multi ? "导出全部" : `导出 ${exportSuffix}`}</span></button>
          </div>
          <div class="watch-status ${info?.watch.enabled ? "visible" : ""}">${escapeHtml(info?.watch.status || "")}</div>
        </footer>
      </main>
      ${renderStatusbar()}
      ${renderStarPanel()}
      <div id="toast" class="toast"></div>
    </div>`;
}

function renderCanvas(item?: ImageItem): string {
  if (!item) {
    return `<div class="drop-canvas idle-canvas" data-drop-zone>
      <div class="hero-block"><div class="hero-emoji">🥝</div><div class="hero-title">Peel</div><div class="hero-hint">拖入图片去背景<br/>或点击选择文件</div></div>
    </div>`;
  }
  if (item.status === "queued" || item.status === "running") {
    return `<div class="drop-canvas busy-canvas" data-drop-zone>
      <div class="hero-block"><div class="hero-emoji">🥝</div><div class="hero-title">Peel</div><div class="hero-hint">正在去除背景…<br/>（首次加载模型可能稍慢）</div></div>
    </div>`;
  }
  if (item.status === "failed") {
    const error = (item.error || "处理失败").slice(0, 280);
    return `<div class="drop-canvas error-canvas" data-drop-zone>
      <div class="hero-block"><div class="hero-emoji">🥝</div><div class="hero-title">Peel</div><div class="hero-hint error-text">出错了<br/>${escapeHtml(error)}<br/><br/>拖入或点击重试</div></div>
    </div>`;
  }
  return `<div class="drop-canvas result-canvas" data-drop-zone>
    <div class="single-result">
      <div class="result-viewer ${sideBySide && item.source_preview ? "side-by-side" : ""}">
        ${renderImagePane(item, Boolean(sideBySide && item.source_preview))}
      </div>
      ${item.source_preview ? `<div class="compare-bar"><button class="compare-button ${sideBySide ? "checked" : ""}" data-action="toggle-side">左右对照</button></div>` : ""}
      <div class="drag-out-hint">${item.source_preview ? "长按对照 · 拖出结果" : "拖移可拖出结果"}</div>
    </div>
  </div>`;
}

function renderImagePane(item: ImageItem, compare: boolean): string {
  const resultDragAttributes = item.result_path
    ? `draggable="true" data-result-drag-id="${escapeHtml(item.id)}"`
    : `draggable="false"`;
  if (compare) {
    return `<div class="compare-panes">
      <div class="compare-pane"><div class="pane-image plain-image"><img draggable="false" src="${item.source_preview}" alt="原图" /></div><span>原图</span></div>
      <div class="compare-pane"><div class="pane-image checkerboard"><img ${resultDragAttributes} src="${item.result_preview || ""}" alt="结果" /></div><span>结果</span></div>
    </div>`;
  }
  const src = holdOriginal && item.source_preview ? item.source_preview : item.result_preview || item.source_preview;
  return `<div class="single-image-wrap ${holdOriginal ? "show-original" : "checkerboard"}"><img ${resultDragAttributes} src="${src || ""}" alt="${escapeHtml(item.name)}"/>${holdOriginal ? '<span class="original-badge">原图</span>' : ""}</div>`;
}

function renderGrid(): string {
  return `<div class="grid-page"><div class="grid-host">${items.map(renderGridTile).join("")}</div></div>`;
}

function renderGridTile(item: ImageItem): string {
  const preview = item.status === "done" ? item.result_preview : item.source_preview;
  const name = item.name.length > 18 ? `${item.name.slice(0, 15)}…` : item.name;
  return `<article class="grid-tile" data-item-id="${escapeHtml(item.id)}" title="${escapeHtml(item.name)}">
    <div class="tile-top"><label class="tile-check"><input type="checkbox" data-select-id="${escapeHtml(item.id)}" ${item.selected ? "checked" : ""}/><span class="checkbox-mark"></span></label><span class="tile-badge status-${item.status}">${statusLabel(item.status)}</span></div>
    <div class="tile-thumb checkerboard">${preview ? `<img src="${preview}" alt=""/>` : `<span class="tile-placeholder">${item.status === "failed" ? "!" : "…"}</span>`}</div>
    <div class="tile-caption">${escapeHtml(name)}</div>
  </article>`;
}

function renderLightbox(): string {
  const list = visibleItems();
  const item = list[lightboxIndex];
  if (!item) return renderGrid();
  const compare = sideBySide && Boolean(item.source_preview);
  let body = "";
  if (item.status === "failed") body = `<div class="lightbox-message error-text">${escapeHtml(item.error || "失败")}</div>`;
  else if (item.status !== "done" || !item.result_preview) body = `<div class="lightbox-message">${item.status === "running" ? "处理中…" : "等待中…"}</div>`;
  else body = renderImagePane(item, compare);
  return `<div class="lightbox" tabindex="0">
    <div class="lightbox-title">${lightboxIndex + 1} / ${list.length}  ·  ${escapeHtml(item.name)}</div>
    <div class="lightbox-middle"><button class="lightbox-nav" data-action="lightbox-prev">←</button><div class="lightbox-preview ${compare ? "side-by-side" : "checkerboard"}">${body}</div><button class="lightbox-nav" data-action="lightbox-next">→</button></div>
    <div class="lightbox-chrome">${item.status === "done" && item.source_preview ? `<button class="compare-button ${compare ? "checked" : ""}" data-action="toggle-side">左右对照</button>` : ""}<span>长按对照 · 右键回网格 · 拖出</span></div>
  </div>`;
}

function settingsValue(id: string): HTMLInputElement | HTMLSelectElement | null {
  return document.querySelector<HTMLInputElement | HTMLSelectElement>(`#${id}`);
}

function renderSettings(): string {
  if (!info) return `<div class="app-window"><div class="loading-state">加载中…</div></div>`;
  const nav: [SettingsTab, string][] = [
    ["appearance", "外观"],
    ["model", "模型选择"],
    ["export", "导出"],
    ["watch", "文件夹"],
    ["hotkeys", "快捷键"],
    ["faq", "问题"],
  ];
  return `<div class="app-window settings-window">
    ${renderTitlebar(true)}
    <main class="settings-layout">
      <nav class="settings-nav">${nav.map(([id, label]) => `<button data-setting-tab="${id}" class="${settingsTab === id ? "selected" : ""}">${label}</button>`).join("")}</nav>
      <section class="settings-stack">${renderSettingsPage()}</section>
    </main>
    ${renderStatusbar()}
    ${renderStarPanel()}
    <div id="toast" class="toast"></div>
  </div>`;
}

function renderSettingsPage(): string {
  if (!info) return "";
  const page = settingsTab === "appearance" ? renderAppearancePage() : settingsTab === "model" ? renderModelPage() : settingsTab === "export" ? renderExportPage() : settingsTab === "watch" ? renderWatchPage() : settingsTab === "hotkeys" ? renderHotkeysPage() : renderFaqPage();
  return `<div class="settings-detail-scroll">${page}</div>`;
}

function renderAppearancePage(): string {
  return `<div class="settings-form"><div class="form-row"><label for="setting-theme">主题颜色</label><select id="setting-theme"><option value="light" ${themePreference === "light" ? "selected" : ""}>浅色</option><option value="dark" ${themePreference === "dark" ? "selected" : ""}>深色</option><option value="system" ${themePreference === "system" ? "selected" : ""}>跟随系统</option></select></div></div>`;
}

function renderModelPage(): string {
  const settings = info?.settings;
  if (!settings || !info) return "";
  const selectedId = modelSelection || settings.model;
  const selected = info.models.find((model) => model.id === selectedId) || info.models[0];
  return `<div class="settings-block model-settings-block">
    <div class="form-row model-select-row"><label for="setting-model">默认模型</label><select id="setting-model">${info.models.map((model) => `<option value="${escapeHtml(model.id)}" ${model.id === selectedId ? "selected" : ""}>${escapeHtml(model.label)}${model.status === "downloaded" ? " · 已下载" : model.status === "partial" ? " · 未下完" : " · 未下载"}</option>`).join("")}</select></div>
    <p class="settings-hint">下拉只用于查看与选择目标模型。未下载时点「应用为默认」会先自动下载；下载失败或没有地址时可导入同名 ONNX。已下载模型可应用或卸载。</p>
    <div class="settings-button-row"><button class="settings-control" data-action="apply-model">应用为默认</button><button class="settings-control" data-action="import-model">导入 ONNX</button><button class="settings-control" data-action="remove-model">卸载本地</button><button class="settings-control" data-action="clear-partials">清理未完成</button></div>
    <label class="settings-field-label">擅长</label><textarea class="settings-body-text" readonly>${escapeHtml(selected?.skill || "")}</textarea>
    <label class="settings-field-label">说明</label><textarea class="settings-body-text note-box" readonly>${escapeHtml(selected?.note || "")}</textarea>
    <div class="settings-hint model-status-line">${selected?.status === "downloaded" ? `已下载 · ${formatBytes(selected.size_bytes)}` : selected?.status === "partial" ? `存在未完成文件 · ${formatBytes(selected.size_bytes)}` : "未下载模型文件"}</div>
    <label class="check-line"><input type="checkbox" id="setting-alpha" ${settings.alpha_matting ? "checked" : ""}/><span class="checkbox-mark"></span><span>启用 Alpha Matting（边缘更细，更慢）</span></label>
    <label class="check-line"><input type="checkbox" id="setting-accel" ${settings.prefer_accel ? "checked" : ""}/><span class="checkbox-mark"></span><span>更快处理（有条件时用显卡加速）</span></label>
    <div class="settings-hint accel-status">${escapeHtml(info.acceleration.label)}<br/>${escapeHtml(info.acceleration.detail)}</div>
  </div>`;
}

function renderExportPage(): string {
  const settings = info?.settings;
  if (!settings) return "";
  return `<div class="settings-form export-settings-form">
    <div class="form-row"><label for="setting-format">默认导出格式</label><select id="setting-format"><option value="png" ${settings.export_format === "png" ? "selected" : ""}>PNG</option><option value="webp" ${settings.export_format === "webp" ? "selected" : ""}>WebP</option><option value="jpg" ${settings.export_format === "jpg" ? "selected" : ""}>JPEG</option><option value="bmp" ${settings.export_format === "bmp" ? "selected" : ""}>BMP</option><option value="tiff" ${settings.export_format === "tiff" ? "selected" : ""}>TIFF</option><option value="custom" ${settings.export_format === "custom" ? "selected" : ""}>自定义</option></select></div>
    <div class="form-row" data-custom-extension-row ${settings.export_format === "custom" ? "" : "hidden"}><label for="setting-extension">自定义扩展名</label><div class="extension-field"><span>.</span><input id="setting-extension" value="${escapeHtml(settings.custom_extension)}" placeholder="例如 heic 或 avif" maxlength="8"/></div></div>
    <p class="settings-hint form-hint-row">默认导出格式。PNG/WebP/TIFF 可保留透明；JPEG/BMP 会铺白底。</p>
    <div class="form-row"><label>文件名前缀</label><div class="prefix-field"><label class="check-line"><input type="checkbox" id="setting-prefix-enabled" ${settings.export_prefix_enabled ? "checked" : ""}/><span class="checkbox-mark"></span><span>使用文件名前缀</span></label><input id="setting-prefix" value="${escapeHtml(settings.export_prefix)}" placeholder="nobg_" maxlength="32" ${settings.export_prefix_enabled ? "" : "disabled"}/></div></div>
  </div>`;
}

function renderWatchPage(): string {
  const settings = info?.settings;
  const watch = info?.watch;
  if (!settings || !watch) return "";
  return `<div class="settings-block watch-settings-block">
    <p class="settings-hint watch-intro">选择监视文件夹与输出文件夹，点「应用」开启。之后放入图片会自动抠图并保存，不占用主界面列表。</p>
    <label class="settings-field-label">监视文件夹（进图 / 导入）</label><div class="path-row"><input id="setting-watch-dir" value="${escapeHtml(settings.watch_dir)}" placeholder="选择要监视的文件夹…"/><button class="settings-path-button" data-action="choose-watch-dir">浏览</button></div>
    <label class="settings-field-label">输出文件夹（结果）</label><div class="path-row"><input id="setting-watch-output" value="${escapeHtml(settings.watch_output_dir)}" placeholder="默认：监视文件夹下的「已抠图」"/><button class="settings-path-button" data-action="choose-watch-output">浏览</button><button class="settings-path-button" data-action="clear-watch-output">用默认</button></div>
    <label class="settings-field-label">选项</label>
    <div class="watch-options"><label class="check-line"><input type="checkbox" id="setting-watch-existing" ${settings.watch_process_existing ? "checked" : ""}/><span class="checkbox-mark"></span><span>开启时重新处理夹内图片（含此前已成功记录的）</span></label><label class="check-line"><input type="checkbox" id="setting-watch-recursive" ${settings.watch_recursive ? "checked" : ""}/><span class="checkbox-mark"></span><span>包含子文件夹</span></label><label class="check-line"><input type="checkbox" id="setting-watch-archive" ${settings.watch_archive_sources ? "checked" : ""}/><span class="checkbox-mark"></span><span>成功后把原图移到「已处理」</span></label><label class="check-line"><input type="checkbox" id="setting-watch-tray" ${settings.watch_minimize_to_tray ? "checked" : ""}/><span class="checkbox-mark"></span><span>监视开启时，关闭窗口最小化到托盘</span></label></div>
    <p class="settings-hint">输出默认在「已抠图」；失败在输出下的「失败」。导出格式与前缀跟「导出」页一致。</p>
    <label class="settings-field-label">运行状态</label><div class="settings-body-text watch-status-card">${escapeHtml(watch.status || "尚未开启监视").replaceAll(" · ", "<br/>")}<br/>${watch.queued} 张待处理 · ${watch.success} 张成功 · ${watch.failed} 张失败</div>
    <label class="settings-field-label">操作</label>
    <div class="watch-action-row"><button class="settings-control" data-action="watch-pause" ${watch.enabled ? "" : "disabled"}>${watch.paused ? "继续" : "暂停"}</button><button class="settings-control" data-action="watch-clear" ${watch.enabled ? "" : "disabled"}>清空队列</button><button class="settings-control" data-action="watch-retry" ${watch.enabled ? "" : "disabled"}>重试失败</button></div>
    <div class="watch-action-row"><button class="settings-control" data-action="open-watch-input">打开导入</button><button class="settings-control" data-action="open-watch-output">打开输出</button><button class="settings-control" data-action="open-watch-fail">打开失败</button></div>
    <div class="settings-footer-row"><button class="primary-button" data-action="save-settings">${watch.enabled ? "关闭应用" : "应用"}</button></div>
  </div>`;
}

const hotkeyRows: [HotkeyId, string, string][] = [
  ["open", "打开图片", "从文件选择并添加要去背景的图片"],
  ["export", "导出结果", "保存处理结果（单图另存 / 多图批量导出）"],
  ["copy", "复制结果", "把当前结果图复制到系统剪贴板，可到别处粘贴"],
  ["paste", "粘贴图片", "从剪贴板导入图片并加入处理"],
  ["settings", "打开设置", "进入设置页（外观、模型、导出、快捷键）"],
  ["escape", "返回上一级", "按界面层级回退：设置/修补→主界面；预览→网格"],
  ["lightbox_prev", "预览上一张", "多图预览中查看上一张"],
  ["lightbox_next", "预览下一张", "多图预览中查看下一张"],
  ["peek_original", "按住看原图", "按住快捷键时显示原图，松开恢复结果"],
  ["side_by_side", "左右对照", "单图预览时切换左原图 / 右结果并排"],
];

function renderHotkeysPage(): string {
  return `<div class="settings-block hotkeys-page"><p class="settings-hint">点击右侧按键框，再按下想要的组合键即可改绑。若与其它功能冲突会提示并保持原设置。鼠标操作固定在下方，不可改绑。</p><div class="hotkey-head"><strong>功能</strong><strong>按键 / 操作</strong></div><label class="settings-field-label">键盘快捷键</label>${hotkeyRows.map(([id, title, desc]) => `<div class="hotkey-row"><div><strong>${title}</strong><span>${desc}</span></div><button type="button" class="hotkey-chip" data-hotkey-id="${id}">${hotkeyCaptureId === id ? "请按下按键…" : hotkeyValue(id)}</button></div>`).join("")}<div class="settings-footer-row"><button class="primary-button" data-action="reset-hotkeys">恢复默认</button></div><div class="hotkey-separator"></div><label class="settings-field-label">对照 / 拖出（鼠标）</label>${renderGestureRow("左键长按（单图）", "显示原图；松开恢复结果", "鼠标 · 左键长按")}${renderGestureRow("左键长按（并排）", "并排时在一侧长按，该侧原位换成另一张", "鼠标 · 左键长按")}${renderGestureRow("左键拖移", "拖出结果文件到文件夹或其他软件", "鼠标 · 左键拖移")}<label class="settings-field-label">多图 / 预览（鼠标）</label>${renderGestureRow("点击缩略图", "进入单张预览", "鼠标 · 单击")}${renderGestureRow("右键（预览）", "返回网格", "鼠标 · 右键")}${renderGestureRow("右键（网格/单图）", "用已下载模型重抠", "鼠标 · 右键")}</div>`;
}

function renderGestureRow(title: string, desc: string, gesture: string): string {
  return `<div class="hotkey-row"><div><strong>${title}</strong><span>${desc}</span></div><span class="hotkey-chip">${gesture}</span></div>`;
}

function renderFaqPage(): string {
  const faq = [
    ["如何更换抠图模型？", "打开「模型选择」，在下拉框中预览各模型说明；选中后点「应用为默认」。本版本通过导入本地 ONNX 文件启用额外模型，未下载文件请先导入同名模型；未完成文件可在设置中清理。"],
    ["文件夹监视怎么用？", "在「文件夹」页选择监视目录与输出目录，点「应用」开启。之后把图片放进监视文件夹，会自动抠图并保存到输出目录，不占用主界面列表。"],
    ["为什么第一次点设置会稍顿一下？", "设置页在后台已建好，但首次显示时才做完整布局与绘制，并同步模型目录状态。应用会在空闲时预热缓存；第二次打开通常会更顺。"],
  ];
  return `<div class="settings-block faq-page">${faq.map(([question, answer], index) => `<details class="faq-item" ${index === -1 ? "open" : ""}><summary>${question}<span>›</span></summary><p>${answer}</p></details>`).join("")}</div>`;
}

function renderRepair(): string {
  const title = currentItem()?.name || "当前图片";
  return `<div class="app-window repair-window">
    ${renderTitlebar()}
    <main class="repair-page">
      <div class="repair-topbar"><button class="capsule-btn" data-action="cancel-repair"><span class="btn-icon back-icon">↩</span><span>返回</span></button><div class="repair-title">修补 · ${escapeHtml(title)}</div><button class="primary-button repair-finish" data-action="finish-repair"><span class="btn-icon check-icon">✓</span><span>完成</span></button></div>
      <div class="repair-content"><aside class="repair-sidebar">
        <label class="repair-section-label">工具</label><button class="repair-tool ${repairMode === "lasso" ? "selected" : ""}" data-repair-mode="lasso">自由套索</button><button class="repair-tool ${repairMode === "polygon" ? "selected" : ""}" data-repair-mode="polygon">多边形套索</button><button class="repair-tool ${repairMode === "brush" ? "selected" : ""}" data-repair-mode="brush">画笔</button>
        ${repairMode === "brush" ? `<div class="repair-slider-block"><label>画笔 ${repairBrushDiameter} px</label><input id="repair-brush-size" type="range" min="4" max="120" value="${repairBrushDiameter}"/></div>` : ""}
        <label class="repair-section-label">边缘</label><label class="slider-label">羽化 ${repairFeather} px</label><input id="repair-feather" type="range" min="0" max="24" value="${repairFeather}"/>
        <label class="repair-section-label">查看</label><label class="slider-label">叠加 ${repairOverlay}%</label><input id="repair-overlay" type="range" min="0" max="100" value="${repairOverlay}"/>
        <label class="repair-section-label">历史</label><div class="history-row"><button class="repair-tool" data-action="repair-undo">撤销</button><button class="repair-tool" data-action="repair-redo">重做</button></div>
        <label class="repair-section-label">操作</label><button class="repair-action" data-action="apply-repair" ${repairPoints.length < (repairMode === "polygon" ? 3 : 1) ? "disabled" : ""}>保留选区</button><button class="repair-action" data-action="erase-repair" ${repairPoints.length < (repairMode === "polygon" ? 3 : 1) ? "disabled" : ""}>删除选区</button><button class="repair-action" data-action="restore-repair" ${repairPoints.length < (repairMode === "polygon" ? 3 : 1) ? "disabled" : ""}>恢复选区</button><button class="repair-clear" data-action="repair-clear" ${repairPoints.length ? "" : "disabled"}>清除选区</button>
      </aside><section class="repair-canvas-area"><div class="selection-canvas-wrap"><canvas id="repair-canvas"></canvas><div class="canvas-loading" ${repairData ? "hidden" : ""}>加载中…</div></div></section></div>
    </main>
    ${renderStatusbar()}
    ${renderStarPanel()}
    <div id="toast" class="toast"></div>
  </div>`;
}

async function importImages(): Promise<void> {
  try {
    const paths = await call<string[]>("pick_images");
    if (paths.length) await addPaths(paths);
  } catch (error) {
    toast(text(error), true);
  }
}

async function addPaths(paths: string[]): Promise<void> {
  try {
    const result = await call<AddResult>("add_images", { paths });
    setItems(result.items);
    if (result.added && !selectedId) selectedId = visibleItems()[0]?.id || "";
    render();
    toast(result.message, result.added === 0);
  } catch (error) {
    toast(text(error), true);
  }
}

async function exportResults(selectedOnly = false): Promise<void> {
  if (!info) return;
  const selected = visibleItems().filter((item) => item.selected && item.status === "done" && item.result_path);
  const done = visibleItems().filter((item) => item.status === "done" && item.result_path);
  if (selectedOnly && selected.length === 0) {
    toast("请先勾选已完成的图片", true);
    return;
  }
  if (!selectedOnly && done.length === 0) {
    toast(summary.processing ? "还在处理，完成后再导出" : "还没有处理完成的图片", true);
    return;
  }
  const options = {
    directory: "",
    prefix: info.settings.export_prefix_enabled ? info.settings.export_prefix : "",
    format: info.settings.export_format,
    custom_extension: info.settings.custom_extension,
  };
  if (!selectedOnly && visibleItems().length === 1 && done.length === 1) {
    const item = done[0];
    try {
      const path = await call<string | null>("choose_save_file", { source_name: item.name, options });
      if (!path) return;
      const result = await call<ExportResult>("export_item_to_file", {
        id: item.id,
        path,
        options: { ...options, prefix: "" },
      });
      statusMessage = result.message;
      const statusbar = root.querySelector<HTMLElement>(".statusbar");
      if (statusbar) statusbar.textContent = statusMessage;
      toast(result.message, result.failed.length > 0);
    } catch (error) {
      toast(text(error), true);
    }
    return;
  }
  const ids = selectedOnly ? selected.map((item) => item.id) : [];
  try {
    const directory = await call<string | null>("choose_directory");
    if (!directory) return;
    const result = await call<ExportResult>("export_items", {
      ids,
      options: { ...options, directory },
    });
    statusMessage = result.message;
    render();
    toast(result.message, result.failed.length > 0);
  } catch (error) {
    toast(text(error), true);
  }
}

async function saveSettings(returnToMain = true, toggleWatch = false, includeModel = false): Promise<void> {
  if (!info) return;
  const next: Settings = { ...info.settings };
  const model = settingsValue("setting-model") as HTMLSelectElement | null;
  const format = settingsValue("setting-format") as HTMLSelectElement | null;
  const extension = settingsValue("setting-extension") as HTMLInputElement | null;
  const prefix = settingsValue("setting-prefix") as HTMLInputElement | null;
  const prefixEnabled = settingsValue("setting-prefix-enabled") as HTMLInputElement | null;
  const alpha = settingsValue("setting-alpha") as HTMLInputElement | null;
  const accel = settingsValue("setting-accel") as HTMLInputElement | null;
  const watchDir = settingsValue("setting-watch-dir") as HTMLInputElement | null;
  const watchOutput = settingsValue("setting-watch-output") as HTMLInputElement | null;
  const watchExisting = settingsValue("setting-watch-existing") as HTMLInputElement | null;
  const watchRecursive = settingsValue("setting-watch-recursive") as HTMLInputElement | null;
  const watchArchive = settingsValue("setting-watch-archive") as HTMLInputElement | null;
  const watchTray = settingsValue("setting-watch-tray") as HTMLInputElement | null;
  if (model && includeModel) next.model = model.value;
  if (format) next.export_format = format.value;
  if (extension) next.custom_extension = extension.value;
  if (prefix) next.export_prefix = prefix.value;
  if (prefixEnabled) next.export_prefix_enabled = prefixEnabled.checked;
  if (alpha) next.alpha_matting = alpha.checked;
  if (accel) next.prefer_accel = accel.checked;
  if (watchDir) next.watch_dir = watchDir.value;
  if (watchOutput) next.watch_output_dir = watchOutput.value;
  if (watchExisting) next.watch_process_existing = watchExisting.checked;
  if (watchRecursive) next.watch_recursive = watchRecursive.checked;
  if (watchArchive) next.watch_archive_sources = watchArchive.checked;
  if (watchTray) next.watch_minimize_to_tray = watchTray.checked;
  if (toggleWatch) next.watch_enabled = !info.watch.enabled;
  try {
    info = await call<AppInfo>("save_settings", { next });
    statusMessage = "设置已应用";
    if (returnToMain) {
      view = "main";
      render();
      toast("设置已应用");
    } else {
      const statusbar = root.querySelector<HTMLElement>(".statusbar");
      if (statusbar) statusbar.textContent = statusMessage;
    }
  } catch (error) {
    toast(text(error), true);
  }
}

async function openRepair(id?: string): Promise<void> {
  const target = id || doneItemForAction()?.id;
  if (!target) {
    toast("请先打开一张已经处理完成的图片", true);
    return;
  }
  repairId = target;
  repairData = null;
  repairOriginalImage = null;
  repairImage = null;
  repairPoints = [];
  repairMode = "lasso";
  repairPolygonClosed = false;
  view = "repair";
  render();
  try {
    repairData = await call<RepairImage>("get_repair_image", { id: target });
    setRepairImages(repairData);
    render();
  } catch (error) {
    toast(text(error), true);
    view = "main";
    render();
  }
}

function canvasPoint(canvas: HTMLCanvasElement, event: PointerEvent): { x: number; y: number } {
  const rect = canvas.getBoundingClientRect();
  return { x: ((event.clientX - rect.left) / rect.width) * canvas.width, y: ((event.clientY - rect.top) / rect.height) * canvas.height };
}

function repairDisplayScale(): { x: number; y: number } {
  if (!repairData) return { x: 1, y: 1 };
  const displayWidth = repairImage?.naturalWidth || repairData.width;
  const displayHeight = repairImage?.naturalHeight || repairData.height;
  return {
    x: repairData.width / Math.max(1, displayWidth),
    y: repairData.height / Math.max(1, displayHeight),
  };
}

function distance(left: { x: number; y: number }, right: { x: number; y: number }): number {
  return Math.hypot(left.x - right.x, left.y - right.y);
}

function setRepairImages(data: RepairImage): void {
  repairOriginalImage = new Image();
  repairOriginalImage.src = data.original;
  repairImage = new Image();
  repairImage.src = data.result;
  repairBaseCanvas = null;
  repairOriginalImage.addEventListener("load", () => {
    repairBaseCanvas = null;
    requestRepairDraw();
  }, { once: true });
}

function requestRepairDraw(): void {
  if (repairDrawFrame) return;
  repairDrawFrame = window.requestAnimationFrame(() => {
    repairDrawFrame = 0;
    const canvas = document.querySelector<HTMLCanvasElement>("#repair-canvas");
    if (canvas) drawRepairCanvas(canvas);
  });
}

function buildRepairBase(canvas: HTMLCanvasElement): HTMLCanvasElement | null {
  if (!repairImage?.complete || !repairImage.naturalWidth || !repairData) return null;
  const base = document.createElement("canvas");
  base.width = canvas.width;
  base.height = canvas.height;
  const ctx = base.getContext("2d");
  if (!ctx) return null;

  const tile = document.createElement("canvas");
  tile.width = 24;
  tile.height = 24;
  const tileContext = tile.getContext("2d");
  if (tileContext) {
    tileContext.fillStyle = "#f2f2f3";
    tileContext.fillRect(0, 0, 24, 24);
    tileContext.fillStyle = "#d6d6d8";
    tileContext.fillRect(0, 0, 12, 12);
    tileContext.fillRect(12, 12, 12, 12);
    const pattern = ctx.createPattern(tile, "repeat");
    if (pattern) {
      ctx.fillStyle = pattern;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
  }
  if (repairOriginalImage?.complete && repairOriginalImage.naturalWidth && repairOverlay > 0) {
    ctx.globalAlpha = repairOverlay / 100;
    ctx.drawImage(repairOriginalImage, 0, 0, canvas.width, canvas.height);
    ctx.globalAlpha = 1;
  }
  ctx.drawImage(repairImage, 0, 0, canvas.width, canvas.height);
  return base;
}

function drawRepairCanvas(canvas: HTMLCanvasElement): void {
  const ctx = canvas.getContext("2d");
  if (!ctx || !repairImage || !repairData || !repairImage.complete || !repairImage.naturalWidth) return;
  if (!repairBaseCanvas || repairBaseCanvas.width !== canvas.width || repairBaseCanvas.height !== canvas.height) {
    repairBaseCanvas = buildRepairBase(canvas);
  }
  if (!repairBaseCanvas) return;
  ctx.globalAlpha = 1;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(repairBaseCanvas, 0, 0);
  if (!repairPoints.length) return;
  ctx.save();
  ctx.strokeStyle = "#34c759";
  ctx.fillStyle = "rgba(52, 199, 89, .23)";
  ctx.lineWidth = Math.max(2, canvas.width / 900);
  ctx.setLineDash(repairMode === "brush" ? [] : [8, 5]);
  ctx.beginPath();
  ctx.moveTo(repairPoints[0].x, repairPoints[0].y);
  for (const point of repairPoints.slice(1)) ctx.lineTo(point.x, point.y);
  if (repairMode === "lasso" || (repairMode === "polygon" && repairPolygonClosed)) {
    ctx.closePath();
    ctx.fill();
  }
  ctx.stroke();
  if (repairMode === "brush") {
    const point = repairPoints[repairPoints.length - 1];
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.arc(point.x, point.y, repairBrushDiameter / 2, 0, Math.PI * 2);
    ctx.stroke();
  }
  if (repairMode === "polygon" && !repairPolygonClosed) {
    ctx.fillStyle = "#34c759";
    for (const point of repairPoints) {
      ctx.beginPath();
      ctx.arc(point.x, point.y, 3, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.restore();
}

function setupRepairCanvas(): void {
  const canvas = document.querySelector<HTMLCanvasElement>("#repair-canvas");
  if (!canvas || !repairData || !repairImage) return;
  const image = repairImage;
  const draw = () => {
    canvas.width = image.naturalWidth || repairData!.width;
    canvas.height = image.naturalHeight || repairData!.height;
    drawRepairCanvas(canvas);
  };
  if (image.complete) draw(); else image.addEventListener("load", draw, { once: true });
  canvas.onpointerdown = (event) => {
    const point = canvasPoint(canvas, event);
    if (repairMode === "polygon") {
      if (repairPolygonClosed) {
        repairPoints = [];
        repairPolygonClosed = false;
      }
      if (repairPoints.length >= 3 && distance(point, repairPoints[0]) < 12 * canvas.width / Math.max(1, canvas.clientWidth)) {
        repairPolygonClosed = true;
      } else repairPoints.push(point);
      drawRepairCanvas(canvas);
      renderRepairControlsOnly();
      return;
    }
    repairDrawing = true;
    canvas.setPointerCapture(event.pointerId);
    repairPoints = [point];
    drawRepairCanvas(canvas);
  };
  canvas.onpointermove = (event) => {
    if (repairMode === "polygon" && repairPoints.length && !repairPolygonClosed) {
      requestRepairDraw();
      return;
    }
    if (!repairDrawing) return;
    const point = canvasPoint(canvas, event);
    if (repairMode === "brush" || !repairPoints.length || distance(repairPoints[repairPoints.length - 1], point) > 1) repairPoints.push(point);
    requestRepairDraw();
  };
  canvas.onpointerup = () => {
    repairDrawing = false;
    requestRepairDraw();
    renderRepairControlsOnly();
  };
  canvas.ondblclick = () => {
    if (repairMode === "polygon" && repairPoints.length >= 3) {
      repairPolygonClosed = true;
      requestRepairDraw();
      renderRepairControlsOnly();
    }
  };
}

function renderRepairControlsOnly(): void {
  const sidebar = document.querySelector<HTMLElement>(".repair-sidebar");
  if (!sidebar) return;
  const scrollTop = sidebar.scrollTop;
  const page = renderRepair();
  const wrapper = document.createElement("template");
  wrapper.innerHTML = page;
  const nextSidebar = wrapper.content.querySelector<HTMLElement>(".repair-sidebar");
  if (nextSidebar) {
    sidebar.replaceWith(nextSidebar);
    nextSidebar.scrollTop = scrollTop;
  }
  requestRepairDraw();
  wireRenderedView();
}

async function applyRepair(operation: "keep" | "erase" | "restore"): Promise<void> {
  if (!repairId || !repairData) return;
  const minimum = repairMode === "polygon" ? 3 : 1;
  if (repairPoints.length < minimum) return;
  const scale = repairDisplayScale();
  const selection: Selection = {
    kind: repairMode === "polygon" ? "lasso" : repairMode,
    points: repairPoints.map((point) => ({ x: point.x * scale.x, y: point.y * scale.y })),
    radius: repairBrushDiameter / 2 * (scale.x + scale.y) / 2,
  };
  try {
    await call("apply_mask", { id: repairId, selection, operation, feather: Math.round(repairFeather * (scale.x + scale.y) / 2) });
    repairData = await call<RepairImage>("get_repair_image", { id: repairId });
    setRepairImages(repairData);
    repairPoints = [];
    repairPolygonClosed = false;
    render();
    toast("修补已应用");
  } catch (error) {
    toast(text(error), true);
  }
}

async function maskHistory(direction: "undo" | "redo"): Promise<void> {
  if (!repairId) return;
  try {
    await call("mask_history", { id: repairId, direction });
    repairData = await call<RepairImage>("get_repair_image", { id: repairId });
    setRepairImages(repairData);
    repairPoints = [];
    render();
  } catch (error) {
    toast(text(error), true);
  }
}

async function copyCurrent(): Promise<void> {
  const item = doneItemForAction();
  if (!item) return;
  try {
    await call("copy_result", { id: item.id });
    toast("已复制到剪贴板");
  } catch (error) {
    toast(text(error), true);
  }
}

async function pasteImage(): Promise<void> {
  if (summary.processing) {
    toast("正在处理，请稍候再粘贴", true);
    return;
  }
  try {
    const path = await call<string | null>("paste_image");
    if (path) await addPaths([path]);
    else toast("剪贴板中没有可用的图片", true);
  } catch (error) {
    toast(text(error), true);
  }
}

function removeReprocessMenu(): void {
  document.querySelector<HTMLElement>(".reprocess-menu")?.remove();
}

function showReprocessMenu(item: ImageItem, clientX: number, clientY: number): void {
  removeReprocessMenu();
  if (!info || !["done", "failed"].includes(item.status)) return;
  const models = info.models.filter((model) => model.status === "downloaded");
  const menu = document.createElement("div");
  menu.className = "reprocess-menu";
  const title = document.createElement("div");
  title.className = "reprocess-menu-title";
  title.textContent = "用已下载模型重抠";
  menu.append(title);
  if (!models.length) {
    const empty = document.createElement("div");
    empty.className = "reprocess-menu-empty";
    empty.textContent = "暂无已下载模型";
    menu.append(empty);
  }
  for (const model of models) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = model.label;
    button.title = model.skill || model.id;
    button.addEventListener("click", () => {
      removeReprocessMenu();
      void call<string>("reprocess_item", { id: item.id, model: model.id })
        .then((message) => toast(message))
        .catch((error) => toast(text(error), true));
    });
    menu.append(button);
  }
  document.body.append(menu);
  const gap = 6;
  const rect = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(gap, Math.min(clientX, window.innerWidth - rect.width - gap))}px`;
  menu.style.top = `${Math.max(gap, Math.min(clientY, window.innerHeight - rect.height - gap))}px`;
  window.setTimeout(() => document.addEventListener("pointerdown", removeReprocessMenu, { once: true }), 0);
}

async function openPath(id: string): Promise<void> {
  const base = info?.settings.watch_output_dir || (info?.settings.watch_dir ? `${info.settings.watch_dir}\\已抠图` : "");
  const path = id === "input" ? info?.settings.watch_dir : id === "output" ? base : base ? `${base}\\失败` : "";
  if (!path) return;
  try { await call("open_path", { path }); } catch (error) { toast(text(error), true); }
}

function fileUrl(path: string): string {
  const segments = path.replaceAll("\\", "/").split("/");
  const drive = segments.shift() || "";
  return `file:///${[drive, ...segments].map((segment, index) => index === 0 ? segment : encodeURIComponent(segment)).join("/")}`;
}

function wireResultDragOut(): void {
  root.querySelectorAll<HTMLImageElement>("[data-result-drag-id]").forEach((image) => {
    if (image.dataset.bound) return;
    image.dataset.bound = "1";
    image.addEventListener("dragstart", (event) => {
      const id = image.dataset.resultDragId;
      const item = id ? items.find((candidate) => candidate.id === id) : undefined;
      const path = item?.result_path;
      const transfer = event.dataTransfer;
      if (!path || !transfer) {
        event.preventDefault();
        return;
      }
      const uri = fileUrl(path);
      const name = path.split(/[\\/]/).pop() || `${item.name}.png`;
      transfer.effectAllowed = "copy";
      transfer.setData("text/uri-list", uri);
      transfer.setData("text/plain", path);
      transfer.setData("DownloadURL", `image/png:${name}:${uri}`);
    });
  });
}

async function handleWindowAction(action: string): Promise<void> {
  if (windowActionBusy) return;
  const win = getCurrentWindow();
  windowActionBusy = true;
  try {
    if (action === "minimize") {
      await call("window_minimize").catch(() => win.minimize());
      return;
    }
    if (action === "maximize") {
      await call("window_toggle_maximize").catch(() => win.toggleMaximize());
      windowMaximized = await win.isMaximized();
      render();
      return;
    }
    if (action === "close") {
      await call("window_close").catch(() => win.close());
    }
  } catch (error) {
    toast(`窗口操作失败：${text(error)}`, true);
  } finally {
    windowActionBusy = false;
  }
}

async function handleAction(action: string): Promise<void> {
  if (action === "import") return importImages();
  if (action === "settings") { settingsTab = "appearance"; view = "settings"; starOpen = false; return render(); }
  if (action === "back-main" || action === "cancel-repair") { view = "main"; repairData = null; repairOriginalImage = null; repairImage = null; repairId = ""; return render(); }
  if (action === "toggle-star") { starOpen = !starOpen; return render(); }
  if (action === "copy-group") {
    try {
      if (!navigator.clipboard) throw new Error("当前环境不允许访问剪贴板");
      await navigator.clipboard.writeText("912291243");
      toast("已复制 QQ 群号 912291243，可到 QQ 中搜索加群");
    } catch (error) {
      toast(`复制失败：${text(error)}`, true);
    }
    return;
  }
  if (action === "open-bili") {
    try { await call("open_url", { url: "https://space.bilibili.com/3546651731953873?spm_id_from=333.40164.0.0" }); } catch (error) { toast(text(error), true); }
    return;
  }
  if (action === "open-github") {
    try { await call("open_url", { url: "https://github.com/wyf-777/win-bg-tool/issues" }); } catch (error) { toast(text(error), true); }
    return;
  }
  if (action === "clear") {
    try {
      const ids = items.length > 1 ? items.filter((item) => item.selected).map((item) => item.id) : [];
      setItems(await call<ImageItem[]>("clear_items", { ids }));
      selectedId = "";
      render();
    } catch (error) { toast(text(error), true); }
    return;
  }
  if (action === "export-selected") return exportResults(true);
  if (action === "export-all") return exportResults(false);
  if (action === "repair") return openRepair();
  if (action === "toggle-side") { sideBySide = !sideBySide; render(); return; }
  if (action === "lightbox-prev" || action === "lightbox-next") {
    const length = visibleItems().length;
    if (length) lightboxIndex = (lightboxIndex + (action === "lightbox-prev" ? -1 : 1) + length) % length;
    return render();
  }
  if (action === "close-lightbox") { lightboxIndex = -1; return render(); }
  if (action === "save-settings") return saveSettings(true, true);
  if (action === "apply-model") {
    const model = settingsValue("setting-model") as HTMLSelectElement | null;
    if (model && info) {
      try {
        const selected = info.models.find((candidate) => candidate.id === model.value);
        if (selected && selected.status !== "downloaded") {
          info = await call<AppInfo>("download_model", { model: model.value });
          const downloaded = info.models.find((candidate) => candidate.id === model.value);
          if (!downloaded || downloaded.status !== "downloaded") {
            toast("未取得对应的 ONNX 模型", true);
            render();
            return;
          }
        }
        info = await call<AppInfo>("save_settings", { next: { ...info.settings, model: model.value } });
        modelSelection = "";
        statusMessage = "默认模型已应用";
        render();
      } catch (error) { toast(text(error), true); }
    }
    return;
  }
  if (action === "import-model") {
    const model = settingsValue("setting-model") as HTMLSelectElement | null;
    try {
      info = await call<AppInfo>("import_model", { model: model?.value || null });
      modelSelection = model?.value || "";
      render();
      toast("ONNX 模型已导入");
    } catch (error) {
      toast(text(error), true);
    }
    return;
  }
  if (action === "remove-model") {
    const model = settingsValue("setting-model") as HTMLSelectElement | null;
    if (!model) return;
    try { info = await call<AppInfo>("remove_model", { model: model.value }); render(); toast("本地模型已卸载"); } catch (error) { toast(text(error), true); }
    return;
  }
  if (action === "clear-partials") {
    try {
      info = await call<AppInfo>("clear_partial_models");
      render();
      toast("未完成模型文件已清理");
    } catch (error) { toast(text(error), true); }
    return;
  }
  if (action === "choose-watch-dir" || action === "choose-watch-output") {
    const path = await call<string | null>("choose_directory");
    if (path) {
      const input = document.querySelector<HTMLInputElement>(action === "choose-watch-dir" ? "#setting-watch-dir" : "#setting-watch-output");
      if (input) input.value = path;
    }
    return;
  }
  if (action === "clear-watch-output") { const input = document.querySelector<HTMLInputElement>("#setting-watch-output"); if (input) input.value = ""; return; }
  if (action === "watch-pause") {
    try { if (info) info.watch = await call<WatchSummary>("watch_pause", { paused: !info.watch.paused }); render(); } catch (error) { toast(text(error), true); }
    return;
  }
  if (action === "watch-clear") {
    try { if (info) info.watch = await call<WatchSummary>("watch_clear_queue"); render(); } catch (error) { toast(text(error), true); }
    return;
  }
  if (action === "watch-retry") {
    try { if (info) info.watch = await call<WatchSummary>("watch_retry_failed"); render(); } catch (error) { toast(text(error), true); }
    return;
  }
  if (action === "open-watch-input") { await openPath("input"); return; }
  if (action === "open-watch-output") { await openPath("output"); return; }
  if (action === "open-watch-fail") { await openPath("fail"); return; }
  if (action === "reset-hotkeys") {
    hotkeyCaptureId = null;
    localStorage.setItem("peel-hotkeys", JSON.stringify(defaultHotkeys));
    render();
    toast("已将全部快捷键恢复为默认");
    return;
  }
  if (action === "apply-repair") return applyRepair("keep");
  if (action === "erase-repair") return applyRepair("erase");
  if (action === "restore-repair") return applyRepair("restore");
  if (action === "repair-undo") return maskHistory("undo");
  if (action === "repair-redo") return maskHistory("redo");
  if (action === "repair-clear") { repairPoints = []; repairPolygonClosed = false; render(); return; }
  if (action === "finish-repair") { view = "main"; repairData = null; repairOriginalImage = null; repairImage = null; repairId = ""; render(); return; }
}

function wireRenderedView(): void {
  root.querySelectorAll<HTMLElement>("[data-setting-tab]").forEach((button) => {
    if (button.dataset.bound) return;
    button.dataset.bound = "1";
    button.addEventListener("click", () => { settingsTab = (button.dataset.settingTab || "appearance") as SettingsTab; render(); });
  });
  root.querySelectorAll<HTMLInputElement>("#repair-brush-size, #repair-feather, #repair-overlay").forEach((input) => {
    if (input.dataset.bound) return;
    input.dataset.bound = "1";
    input.addEventListener("input", () => {
      if (input.id === "repair-brush-size") repairBrushDiameter = Number(input.value);
      if (input.id === "repair-feather") repairFeather = Number(input.value);
      if (input.id === "repair-overlay") {
        repairOverlay = Number(input.value);
        repairBaseCanvas = null;
      }
      requestRepairDraw();
      if (input.id !== "repair-overlay") renderRepairControlsOnly();
    });
  });
  root.querySelectorAll<HTMLElement>("[data-repair-mode]").forEach((button) => {
    if (button.dataset.bound) return;
    button.dataset.bound = "1";
    button.addEventListener("click", () => { repairMode = (button.dataset.repairMode || "lasso") as RepairMode; repairPoints = []; repairPolygonClosed = false; render(); });
  });
  root.querySelectorAll<HTMLInputElement>("[data-select-id]").forEach((input) => {
    if (input.dataset.bound) return;
    input.dataset.bound = "1";
    input.addEventListener("change", () => {
      const id = input.dataset.selectId;
      if (!id) return;
      void call<ImageItem[]>("set_item_selected", { id, selected: input.checked }).then((next) => { setItems(next); render(); }).catch((error) => toast(text(error), true));
    });
  });
  const selectAll = document.querySelector<HTMLInputElement>("#select-all");
  if (selectAll && !selectAll.dataset.bound) selectAll.addEventListener("change", () => {
    const selected = selectAll.checked;
    void Promise.all(items.map((item) => call("set_item_selected", { id: item.id, selected })))
      .then(() => { items = items.map((item) => ({ ...item, selected })); render(); })
      .catch((error) => { selectAll.checked = !selected; toast(text(error), true); });
  });
  if (selectAll) selectAll.dataset.bound = "1";
  const invert = document.querySelector<HTMLInputElement>("#invert-select");
  if (invert && !invert.dataset.bound) invert.addEventListener("change", () => {
    if (!invert.checked) return;
    void Promise.all(items.map((item) => call("set_item_selected", { id: item.id, selected: !item.selected })))
      .then(() => { items = items.map((item) => ({ ...item, selected: !item.selected })); render(); })
      .catch((error) => { invert.checked = false; toast(text(error), true); });
  });
  if (invert) invert.dataset.bound = "1";
  const theme = document.querySelector<HTMLSelectElement>("#setting-theme");
  if (theme && !theme.dataset.bound) theme.addEventListener("change", () => { themePreference = theme.value; localStorage.setItem("peel-theme", themePreference); render(); });
  if (theme) theme.dataset.bound = "1";
  const format = document.querySelector<HTMLSelectElement>("#setting-format");
  if (format && !format.dataset.bound) format.addEventListener("change", () => {
    const row = root.querySelector<HTMLElement>("[data-custom-extension-row]");
    if (row) row.hidden = format.value !== "custom";
    void saveSettings(false);
  });
  if (format) format.dataset.bound = "1";
  const model = document.querySelector<HTMLSelectElement>("#setting-model");
  if (model && !model.dataset.bound) {
    model.dataset.bound = "1";
    model.addEventListener("change", () => {
      modelSelection = model.value;
      render();
    });
  }
  const prefixEnabled = document.querySelector<HTMLInputElement>("#setting-prefix-enabled");
  if (prefixEnabled && !prefixEnabled.dataset.bound) prefixEnabled.addEventListener("change", () => {
    const prefix = document.querySelector<HTMLInputElement>("#setting-prefix");
    if (prefix) prefix.disabled = !prefixEnabled.checked;
    void saveSettings(false);
  });
  if (prefixEnabled) prefixEnabled.dataset.bound = "1";
  root.querySelectorAll<HTMLInputElement>("#setting-extension, #setting-prefix, #setting-alpha, #setting-accel").forEach((input) => {
    if (input.dataset.bound) return;
    input.dataset.bound = "1";
    input.addEventListener("change", () => void saveSettings(false));
  });
  root.querySelectorAll<HTMLButtonElement>("[data-hotkey-id]").forEach((button) => {
    if (button.dataset.bound) return;
    button.dataset.bound = "1";
    button.addEventListener("click", () => {
      const id = button.dataset.hotkeyId as HotkeyId | undefined;
      if (!id) return;
      hotkeyCaptureId = hotkeyCaptureId === id ? null : id;
      render();
    });
  });
  root.querySelectorAll<HTMLElement>("[data-action]").forEach((button) => {
    if (button.dataset.bound) return;
    button.dataset.bound = "1";
    button.addEventListener("click", () => void handleAction(button.dataset.action || ""));
  });
  root.querySelectorAll<HTMLElement>("[data-window]").forEach((button) => {
    if (button.dataset.bound) return;
    button.dataset.bound = "1";
    button.addEventListener("pointerdown", (event) => event.stopPropagation());
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      void handleWindowAction(button.dataset.window || "");
    });
  });
  const titlebar = root.querySelector<HTMLElement>(".titlebar");
  if (titlebar && !titlebar.dataset.bound) {
    titlebar.dataset.bound = "1";
    titlebar.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      const target = event.target as HTMLElement;
      if (target.closest("button, input, select, textarea, a, [data-action], [data-window]")) return;
      event.preventDefault();
      void getCurrentWindow().startDragging().catch((error) => toast(`窗口拖动失败：${text(error)}`, true));
    });
    titlebar.addEventListener("dblclick", (event) => {
      const target = event.target as HTMLElement;
      if (target.closest("button, input, select, textarea, a, [data-action], [data-window]")) return;
      void handleWindowAction("maximize");
    });
  }
  wireResultDragOut();
  root.querySelectorAll<HTMLElement>("[data-item-id]").forEach((tile) => {
    if (tile.dataset.bound) return;
    tile.dataset.bound = "1";
    tile.addEventListener("click", (event) => {
      if ((event.target as HTMLElement).closest("input, label")) return;
      const id = tile.dataset.itemId;
      if (!id) return;
      const index = visibleItems().findIndex((item) => item.id === id);
      if (items.length >= 2 && index >= 0) { lightboxIndex = index; selectedId = id; render(); }
    });
    tile.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      const item = items.find((candidate) => candidate.id === tile.dataset.itemId);
      if (item) showReprocessMenu(item, event.clientX, event.clientY);
    });
  });
  const lightbox = root.querySelector<HTMLElement>(".lightbox");
  if (lightbox && !lightbox.dataset.bound) {
    lightbox.dataset.bound = "1";
    lightbox.addEventListener("contextmenu", (event) => { event.preventDefault(); lightboxIndex = -1; render(); });
  }
  const dropZones = root.querySelectorAll<HTMLElement>("[data-drop-zone]");
  dropZones.forEach((zone) => {
    if (zone.dataset.bound) return;
    zone.dataset.bound = "1";
    zone.addEventListener("dragenter", () => zone.classList.add("drag-over"));
    zone.addEventListener("dragover", (event) => event.preventDefault());
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("drop", (event) => { event.preventDefault(); zone.classList.remove("drag-over"); });
    zone.addEventListener("click", (event) => {
      if ((event.target as HTMLElement).closest("button, input, .grid-tile, .lightbox")) return;
      if (!items.length || items[0]?.status === "failed") void importImages();
    });
  });
  const resultCanvas = document.querySelector<HTMLElement>(".result-canvas");
  if (resultCanvas && currentItem()?.source_preview) {
    let timer = 0;
    resultCanvas.onpointerdown = () => { timer = window.setTimeout(() => { holdOriginal = true; render(); }, 180); };
    resultCanvas.onpointerup = () => { window.clearTimeout(timer); if (holdOriginal) { holdOriginal = false; render(); } };
    resultCanvas.onpointerleave = () => { window.clearTimeout(timer); if (holdOriginal) { holdOriginal = false; render(); } };
    resultCanvas.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      const item = currentItem();
      if (item) showReprocessMenu(item, event.clientX, event.clientY);
    });
  }
}

document.addEventListener("keydown", (event) => {
  if (!hotkeyCaptureId) return;
  const value = eventHotkey(event);
  event.preventDefault();
  event.stopPropagation();
  event.stopImmediatePropagation();
  if (!value) return;
  const id = hotkeyCaptureId;
  if (saveHotkey(id, value)) {
    hotkeyCaptureId = null;
    render();
  }
}, true);

root.addEventListener("keydown", (event) => {
  if (hotkeyMatches(event, "escape")) {
    if (starOpen) { starOpen = false; render(); return; }
    if (lightboxIndex >= 0) { lightboxIndex = -1; render(); return; }
    if (view !== "main") { view = "main"; render(); }
  }
});

document.addEventListener("keydown", (event) => {
  const target = event.target as HTMLElement | null;
  if (target?.closest("input, textarea, select, [contenteditable=\"true\"]")) return;
  if (hotkeyMatches(event, "open")) { event.preventDefault(); void importImages(); }
  if (hotkeyMatches(event, "export")) { event.preventDefault(); void exportResults(false); }
  if (hotkeyMatches(event, "copy")) { event.preventDefault(); void copyCurrent(); }
  if (hotkeyMatches(event, "paste")) { event.preventDefault(); void pasteImage(); }
  if (hotkeyMatches(event, "settings")) { event.preventDefault(); view = "settings"; settingsTab = "appearance"; render(); }
  if (hotkeyMatches(event, "side_by_side")) { event.preventDefault(); sideBySide = !sideBySide; render(); }
  if (hotkeyMatches(event, "lightbox_prev") && lightboxIndex >= 0) { event.preventDefault(); void handleAction("lightbox-prev"); }
  if (hotkeyMatches(event, "lightbox_next") && lightboxIndex >= 0) { event.preventDefault(); void handleAction("lightbox-next"); }
  if (hotkeyMatches(event, "peek_original") && view === "main" && !event.repeat && currentItem()?.source_preview) { event.preventDefault(); holdOriginal = true; render(); }
});

document.addEventListener("keyup", (event) => {
  if (hotkeyMatches(event, "peek_original") && holdOriginal) { holdOriginal = false; render(); }
});

async function initialize(): Promise<void> {
  try {
    info = await call<AppInfo>("get_app_info");
    await listen<ImageItem[]>("queue-updated", (event) => { setItems(event.payload); if (view === "main") render(); });
    await listen<QueueSummary>("queue-summary", (event) => { summary = event.payload; scheduleMainPatch(); });
    await listen<{ message: string }>("status-message", (event) => {
      const ready = event.payload.message.match(/^模型\s+(.+?)\s+已就绪/);
      statusMessage = ready ? `引擎就绪 · ${ready[1]}` : event.payload.message;
      const statusbar = root.querySelector<HTMLElement>(".statusbar");
      if (statusbar) statusbar.textContent = statusMessage;
    });
    await listen<ImageItem>("item-updated", (event) => {
      applyItemPayload(event.payload);
      scheduleMainPatch(event.payload.id);
    });
    await listen<WatchSummary>("watch-updated", (event) => {
      if (info) info.watch = event.payload;
      if (view === "main") scheduleMainPatch();
      else if (view === "settings" && settingsTab === "watch") render();
    });
    const win = getCurrentWindow();
    await win.onDragDropEvent((event) => {
      const payload = event.payload as { type: string; paths?: string[] };
      const zones = root.querySelectorAll<HTMLElement>("[data-drop-zone]");
      if (payload.type === "enter" || payload.type === "over") zones.forEach((zone) => zone.classList.add("drag-over"));
      if (payload.type === "leave" || payload.type === "drop") zones.forEach((zone) => zone.classList.remove("drag-over"));
      if (payload.type === "drop" && payload.paths?.length) void addPaths(payload.paths);
    });
    await win.onResized(async () => {
      const maximized = await win.isMaximized();
      if (maximized !== windowMaximized) {
        windowMaximized = maximized;
        render();
      }
    });
    windowMaximized = await win.isMaximized();
    render();
    void call("warmup_model");
  } catch (error) {
    root.innerHTML = `<div class="fatal-state"><div class="error-mark">!</div><h1>启动失败</h1><p>${escapeHtml(error)}</p></div>`;
  }
}

void initialize();

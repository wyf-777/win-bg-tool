# 项目总览与未来规划

最后更新：2026-08-02

## 1. 一句话

**Windows 本机图片去背景工具**（Peel 级使用强度，自有技术栈）。

## 2. 当前阶段

**主路径已完成，可日常使用。**

已具备：

- 本机 rembg 抠图（多模型；**不按图自动换模型**）  
- 单张 / 多图批处理、对照、剪贴板、手动修补  
- Edge 式设置（主题、模型、导出、Matting、更快处理、文件夹监视、快捷键）  
- 模型：确认下载 / 卸载；批处理中切模型不打断当前图  
- **UI 与推理分进程**（界面不卡）；引擎崩溃有限次自愈  
- **打包 exe**（默认自带 U²-Net 轻量 u2netp）  

**未做（可选）：** 在线 remove.bg。  

详见 [progress.md](progress.md)。

## 3. 产品边界

| 是 | 不是 |
|----|------|
| 本机默认、模型下好后可离线 | Glaze / 小应用商店 |
| 拖入、多图、导出、文件夹监视 | Mac dmg 移植 |
| 可选加速（失败回退） | 强迫用户装 CUDA |

## 4. 架构（简）

```
┌─ UI 进程 (PySide6) ─────────────────────────────┐
│  main_window / workspace / settings / title_bar   │
│  session/batch_session  (串行队列)                 │
│  services/*                                       │
│  engines/process_engine  ← 仅 IPC，不 import rembg │
└──────────────────────┬────────────────────────────┘
                       │ Queue: warmup / remove / progress
┌──────────────────────▼────────────────────────────┐
│  Worker 进程  process_worker + local_rembg         │
│  rembg + onnxruntime + 模型 session                │
│  崩溃 → supervisor 有限次重启 / 熔断               │
└───────────────────────────────────────────────────┘
```

路径约定见 `app/runtime_paths.py`；打包见 [packaging.md](packaging.md)；  
加载与自愈见 [architecture-loading.md](architecture-loading.md)。

## 5. 已完成 vs 剩余

| 已完成 | 剩余（可选） |
|--------|----------------|
| M0–M6 主线能力（除在线） | F11/F12 在线 |
| F15 打包 + packaging 文档 | 真机 exe 全路径回归 |
| 进程引擎 + 自愈 | 样张评测；设置懒加载 |
| 模型管理 UX | 下载进度条 UI |

## 6. 规划

| 阶段 | 内容 |
|------|------|
| **现在** | 稳定使用；按需修体验 |
| **分发前** | 打包回归（尤其多进程 spawn） |
| **更远** | 在线引擎；C++ ORT（未立项） |

## 7. 关键决策

- 不对齐 Glaze；在线无 Key 不做  
- 推理与 UI **分进程**，避免 GIL 冻界面  
- 批处理切模型：当前图做完，后续用新模型  
- 打包 onedir + 默认 u2netp；开发默认 isnet-general-use  
- 加速默认普通模式（[design-accel.md](design-accel.md)）  

## 8. 文档索引

| 文档 | 用途 |
|------|------|
| [progress.md](progress.md) | 进度、技术现状、变更日志 |
| [requirements.md](requirements.md) | 需求与验收 |
| [packaging.md](packaging.md) | 打包指南与踩坑 |
| [architecture-loading.md](architecture-loading.md) | 启动/加载/进程/自愈 |
| [design-accel.md](design-accel.md) | F14 |
| [design-folder-watch.md](design-folder-watch.md) | F13 |
| [design-multi-image.md](design-multi-image.md) | 多图 |
| [research-rembg.md](research-rembg.md) | rembg 调研 |
| [manual-mask-editor-plan.md](manual-mask-editor-plan.md) | 修补方案 |

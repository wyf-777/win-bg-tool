# 项目总览与未来规划

最后更新：2026-08-01（F14 文档完善）

## 1. 一句话

**Windows 本机图片去背景工具**（Peel 级使用强度，自有技术栈）。

## 2. 当前阶段

**主路径已完成，可日常使用。**

已具备：

- 本机 rembg 抠图（多模型可选；**不按图自动换模型**）  
- 单张 / 多图批处理  
- Edge 式设置（主题、模型、导出、Matting、**更快处理**、快捷键）  
- 剪贴板复制/粘贴、原图对照、手动修补  
- 单图/多图右键：用已下载模型重抠  
- Esc：**返回上一级**（设置/修补→主界面；灯箱→网格）  

**未做（可选）：** 在线抠图、打包 exe。  
**F13 文件夹监视 v1.2 已做**（递归/归档/重试失败/托盘）。

详见 [progress.md](progress.md)。

## 3. 产品边界

| 是 | 不是 |
|----|------|
| 本机默认、可离线（模型下好后） | Glaze 平台 / 小应用商店 |
| 拖入、多图网格、灯箱、导出 | Mac dmg 移植 |
| 设置里换模型与导出格式 | 默认上传云端 |
| 可选加速（失败回退普通模式） | 强迫用户懂 GPU / 安装 CUDA |

## 4. 架构（简）

```
UI (PySide6)
  main_window  ── stack: 主界面 | 全窗设置 | 修补页
  workspace      单张画布 / 多图网格 / 灯箱
       │
session/batch_session   串行队列、重抠、上限 48/24
       │
engines/local_rembg + models_catalog + runtime_accel
services/settings + export + clipboard + mask_edit + hotkeys
```

## 5. 已完成 vs 剩余

| 已完成 | 剩余（可选） |
|--------|----------------|
| 引擎、GUI、多图全套 | F11/F12 在线 remove.bg |
| 主题、Edge 设置、模型说明 | F15 打包 |
| 导出多格式 + 前缀 | 样张评测、调试残留清理 |
| F09 对照；F10 剪贴板 | |
| F13 文件夹监视 v1.2 | |
| F14 更快处理（软加速 + 回退） | |
| 手动修补、右键重抠、快捷键可改绑 | |

## 6. 规划

| 阶段 | 内容 |
|------|------|
| **现在** | 稳定使用；按需修体验 |
| **M6 剩余** | 在线 / 打包 |
| **更远** | 同壳其它小工具；未立项不排期 |

## 7. 关键决策

- 不对齐 Glaze 架构  
- 在线无 Key 不做  
- 多图：自动处理、单张整框、忙拒拖、完成可追加  
- 设置全窗；Esc 返回上一级  
- 默认模型 isnet-general-use  
- **加速：默认普通模式；可选偏好；自动检测与失败回退**（见 [design-accel.md](design-accel.md)）  
- F13 监视：默认输出「已抠图」、不入网格、只处理开启后新文件  

## 8. 文档索引

| 文档 | 用途 |
|------|------|
| [progress.md](progress.md) | 进度勾选与焦点 |
| [requirements.md](requirements.md) | 需求与验收 |
| [design-multi-image.md](design-multi-image.md) | 多图交互细则 |
| [design-accel.md](design-accel.md) | F14 更快处理设计与验收 |
| [design-folder-watch.md](design-folder-watch.md) | F13 文件夹监视 |
| [manual-mask-editor-plan.md](manual-mask-editor-plan.md) | 手动修补方案 |
| [research-rembg.md](research-rembg.md) | rembg 调研 |
| [../README.md](../README.md) | 启动与使用 |

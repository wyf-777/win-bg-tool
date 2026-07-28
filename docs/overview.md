# 项目总览与未来规划

最后更新：2026-07-27（全量进度审查）

## 1. 一句话

**Windows 本机图片去背景工具**（Peel 级使用强度，自有技术栈）。

## 2. 当前阶段

**主路径已完成，可日常使用。**

- 本机 rembg 抠图（多模型可选）  
- 单张 / 多图批处理  
- Edge 式设置（主题、模型、导出格式与前缀、Matting）  
- **未做：** 在线抠图、打包 exe、剪贴板、原图对照  

详见 [progress.md](progress.md)。

## 3. 产品边界

| 是 | 不是 |
|----|------|
| 本机默认、可离线（模型下好后） | Glaze 平台 / 小应用商店 |
| 拖入、多图网格、灯箱、导出 | Mac dmg 移植 |
| 设置里换模型与导出格式 | 默认上传云端 |

## 4. 架构（简）

```
UI (PySide6)
  main_window  ── stack: 主界面 | 全窗设置
  workspace      单张画布 / 多图网格 / 灯箱
       │
session/batch_session   串行队列、上限 48/24
       │
engines/local_rembg + models_catalog
services/settings + export
```

## 5. 已完成 vs 剩余

| 已完成 | 剩余（可选） |
|--------|----------------|
| 引擎、GUI、多图规则全套 | F10 剪贴板 |
| 主题、Edge 设置、模型说明 | F11/F12 在线 remove.bg |
| 导出多格式 + 前缀 | F14 GPU、F15 打包 |
| 灯箱、反选、选中导出 | 样张评测、仓库临时文件清理 |
| F09 原图/结果对照（单图+灯箱） | |
| 快捷键说明页 | |

## 6. 规划

| 阶段 | 内容 |
|------|------|
| **现在** | 稳定使用；按需修体验 |
| **M6 二期** | 剪贴板 / 在线 / GPU / 打包 |
| **更远** | 同壳其它小工具；未立项不排期 |

## 7. 关键决策

- 不对齐 Glaze 架构  
- 在线无 Key 不做  
- 多图：自动处理、单张整框、忙拒拖、完成可追加  
- 设置全窗展示；Esc 不误退设置  
- 默认模型 isnet-general-use  

## 8. 文档索引

| 文档 | 用途 |
|------|------|
| [progress.md](progress.md) | 进度勾选与焦点 |
| [requirements.md](requirements.md) | 需求与验收 |
| [design-multi-image.md](design-multi-image.md) | 多图交互细则 |
| [research-rembg.md](research-rembg.md) | rembg 调研 |
| ../README.md | 启动与使用 |

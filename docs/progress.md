# 进度与里程碑

最后更新：2026-08-02（进程引擎 + 自愈 + 文档整理）

## 总览

| 里程碑 | 目标 | 状态 |
|--------|------|------|
| M0 规划与文档 | 需求、范围、技术选型 | **已完成** |
| M0.5 rembg / GIMP 调研 | 本机引擎依据 | **已完成** |
| M1 本机引擎 | rembg + session 复用 | **已完成** |
| M2 桌面 MVP | 打开/拖入拖出/预览/导出 | **已完成** |
| M3 体验打磨 | 主题、错误、设置入口 | **已完成** |
| M4 多图批处理 | 网格/灯箱/追加/导出选中全部 | **已完成** |
| M5 设置增强 | 模型目录、格式、Edge 式设置页 | **已完成** |
| M6 二期 | 剪贴板、F13 监视、F14 加速、F15 打包 | **已完成（在线除外）** |
| M7 工程化 | 进程隔离推理、UI 不卡、引擎自愈 | **已完成** |

**当前焦点：** 主路径可用；可选做 exe 完整回归、样张评测、在线引擎。  
**全景：** [overview.md](overview.md) · **需求：** [requirements.md](requirements.md)

---

## 文档索引

| 文档 | 用途 |
|------|------|
| [overview.md](overview.md) | 产品总览与架构简图 |
| [requirements.md](requirements.md) | 需求与验收 |
| [packaging.md](packaging.md) | **打包 exe** 踩坑、清单、验收 |
| [architecture-loading.md](architecture-loading.md) | **加载/不卡 UI/进程隔离/自愈** |
| [design-accel.md](design-accel.md) | F14 更快处理 |
| [design-folder-watch.md](design-folder-watch.md) | F13 文件夹监视 |
| [design-multi-image.md](design-multi-image.md) | 多图交互 |
| [research-rembg.md](research-rembg.md) | rembg 调研 |
| [manual-mask-editor-plan.md](manual-mask-editor-plan.md) | 手动修补方案 |

---

## 已交付能力（对照需求）

### 核心抠图（P0）

| ID | 内容 | 状态 |
|----|------|------|
| F01–F07 | 打开/拖入/本机抠图/预览/导出/忙碌/友好错误 | **已做** |

### 体验 / 设置（P1）

| ID / 项 | 内容 | 状态 |
|---------|------|------|
| F08 | 导出前缀（可关） | 已做 |
| — | 多格式导出、主题、Edge 设置 | 已做 |
| — | 模型目录 + 确认下载 / 卸载 / 批处理中切模型不打断当前图 | 已做 |
| F09 / F10 | 对照、剪贴板 | 已做 |
| — | 快捷键可改绑、手动修补、右键重抠 | 已做 |
| F14 | 更快处理（软加速） | 已做 |

### 多图 / 二期

| ID | 内容 | 状态 |
|----|------|------|
| F16–F25 | 批处理、网格/灯箱、上限 | 已做 |
| F13 | 文件夹监视 v1.2 | 已做 |
| F15 | 打包 exe（默认 u2netp） | **已做**（见 packaging.md） |
| F11/F12 | 在线 remove.bg | **未做**（无 Key，延后） |

### 工程化（M7）

| 项 | 状态 |
|----|------|
| 无边框顶栏 + 系统拖动 | 已做 |
| UI 秒开 + 引擎就绪态（排队） | 已做 |
| `ProcessRembgEngine` 独立推理进程 | 已做 |
| 引擎 supervisor 自愈 / 熔断 | 已做 |

---

## 技术现状（简）

| 层 | 位置 | 说明 |
|----|------|------|
| 入口 | `app/main.py` | `python -m app.main`；`multiprocessing.freeze_support` |
| UI 引擎门面 | `engines/process_engine.py` | 队列 IPC；**UI 不 import rembg** |
| 推理 worker | `engines/process_worker.py` | 子进程内 `LocalRembgEngine` |
| 本机实现 | `engines/local_rembg.py` | 仅 worker 使用 |
| 模型/加速 | `models_catalog` / `runtime_accel` | 目录、下载态、providers |
| 会话 | `session/batch_session.py` | 串行队列、重抠 |
| 服务 | settings / export / clipboard / folder_watch / hotkeys | |
| UI | main_window / workspace / settings_dialog / title_bar / theme | |
| 打包 | `peel.spec` + `scripts/build_exe.bat` | 见 packaging.md |

- **开发默认模型：** `isnet-general-use`  
- **打包默认模型：** `u2netp`（内置）  
- **模型缓存：** `models/`（U2NET_HOME）  
- **选用策略：** 不按图片自动换模型；设置默认 + 右键重抠  

---

## 后续可选

| 优先级 | 项 |
|--------|-----|
| 高 | 真实 `Peel.exe` 全路径回归（多进程 spawn） |
| 中 | 样张评测；设置页懒加载；下载进度条 |
| 低 | F11/F12 在线；worker 空闲 ping；C++ ORT |

---

## 决策记录（摘）

| 决策 | 说明 |
|------|------|
| Windows 独立产品，不移植 Mac dmg | — |
| 本机 rembg；在线延后 | 无 Key |
| 推理与 UI **分进程** | 避免 GIL 冻界面 |
| 批处理中切模型：当前图做完，后续用新模型 | process_engine 约定 |
| 引擎崩溃：有限次自愈 + 熔断 | architecture-loading.md |
| 打包 onedir + collect_all 重型栈 | packaging.md |
| F14 默认普通模式 | design-accel.md |

---

## 变更日志

| 日期 | 说明 |
|------|------|
| 2026-07-27 | 初始化至多图、设置等 |
| 2026-08-01 | F10/F13/F14、修补与快捷键 |
| 2026-08-02 | F15 打包；rembg 打包修复；packaging.md |
| 2026-08-02 | 模型确认下载/卸载；设置性能 |
| 2026-08-02 | 无边框顶栏；UI 不卡；ProcessRembgEngine |
| 2026-08-02 | 批处理切模型不打断当前图；引擎自愈 |
| 2026-08-02 | 文档整理（progress / overview / README / architecture） |

## 如何更新本文档

1. 完成任务：改状态表与变更日志  
2. 重要决策：写入决策记录  
3. 改需求：先改 requirements.md  
4. 打包相关：同步 packaging.md  

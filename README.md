# win-bg-tool（Peel）

Windows **本机**图片去背景小工具。对标 Peel 的使用强度，**不**复刻 Glaze / Mac 架构。

## 当前阶段

**主路径已完成，可日常使用**（引擎 + GUI + 多图 + 设置 + 剪贴板 + 修补 + 加速 + 文件夹监视 + 打包 + 进程隔离推理）。

## 文档

| 文档 | 内容 |
|------|------|
| [docs/progress.md](docs/progress.md) | 进度、技术现状、变更日志 |
| [docs/overview.md](docs/overview.md) | 总览与架构简图 |
| [docs/requirements.md](docs/requirements.md) | 需求与验收 |
| [docs/packaging.md](docs/packaging.md) | **打包 exe** 踩坑与验收（必读） |
| [docs/architecture-loading.md](docs/architecture-loading.md) | **加载 / 不卡 UI / 进程隔离 / 自愈** |
| [docs/design-accel.md](docs/design-accel.md) | F14 更快处理 |
| [docs/design-folder-watch.md](docs/design-folder-watch.md) | F13 文件夹监视 |
| [docs/design-multi-image.md](docs/design-multi-image.md) | 多图交互 |
| [docs/research-rembg.md](docs/research-rembg.md) | rembg 调研 |

## 快速启动

### 开发运行

```bat
cd /d "项目根目录\win-bg-tool"
pip install -r requirements.txt
python -m app.main
```

或双击 `run.bat`。

### 打包 exe / 安装程序（测试 / 分发）

```bat
scripts\build_exe.bat
```

产物：`dist\Peel\Peel.exe`（**整文件夹** `dist\Peel\` 便携分发，**勿只拷单个 exe**）。

**推荐：生成可选安装路径的安装包**（需 [Inno Setup 6](https://jrsoftware.org/isinfo.php)）：

```bat
scripts\build_installer.bat
```

产物：`dist\Peel-Setup-1.0.0.exe`（向导里可选安装目录）。

**打包默认自带 U²-Net 轻量（`u2netp`）**  
- 权重打进包内，首次运行复制到 exe 旁 `models\`  
- 打包版默认可离线先抠图；其它模型可在设置中下载  

详细步骤、依赖收集、多进程验收、**当前版本重打 / 桌面图标 / 图标缓存**：**[docs/packaging.md](docs/packaging.md)**（§11–§12）。

## 使用要点

- **拖入** / **打开…**（可多选）；处理完可 **拖出** 或 **导出**  
- **设置**（全窗）：外观、模型、导出、文件夹监视、快捷键  
  - 模型：下拉仅预览；**下载并应用**需确认；可 **卸载** 本地模型  
  - 批处理中途换模型：当前图用原模型做完，后续图用新模型  
- **多图**：网格 / 灯箱；忙时拒拖；右键已下载模型重抠  
- **剪贴板**：默认 Ctrl+C / Ctrl+V（可改键）  
- **修补**：结果页可修蒙版  
- **文件夹监视**：设置 → 文件夹（已抠图 / 失败 / 可选归档与托盘）  
- **引擎状态**：顶栏「准备中…」→ 就绪；崩溃时会尝试自动恢复（详见 architecture-loading）  

首次使用某个未下载模型需联网一次。

### 模型怎么选？

- **不会**根据图片内容自动换模型  
- 设置默认模型 = 之后新任务默认用它  
- 右键重抠 = 对该张使用所选已下载模型再跑  

### 更快处理（可选）

- 默认普通模式；设置中可开「更快处理」，失败自动回退  
- 详见 [docs/design-accel.md](docs/design-accel.md)  

## 技术栈

| 层 | 选型 |
|----|------|
| 语言 | Python 3.11+（打包验证环境常用 3.12） |
| UI | PySide6 |
| 抠图 | rembg + onnxruntime（**子进程**内） |
| UI 引擎门面 | `ProcessRembgEngine`（队列 IPC + 自愈） |
| 加速 | 可选「更快处理」；探测 CUDA/DirectML 等 |
| 打包 | PyInstaller onedir（`peel.spec`） |
| 在线 | 未做（规划 remove.bg） |

## 目录结构

```
win-bg-tool/
├── README.md
├── requirements.txt
├── run.bat
├── peel.spec                 # PyInstaller
├── packaging/rembg_sessions/ # 打包用 sessions 防御覆盖
├── docs/                     # 见上表
├── app/
│   ├── main.py               # UI 入口 + freeze_support
│   ├── runtime_paths.py
│   ├── engines/
│   │   ├── process_engine.py # UI 侧 IPC + supervisor
│   │   ├── process_worker.py # 推理子进程
│   │   ├── local_rembg.py    # worker 内实现
│   │   ├── models_catalog.py
│   │   └── runtime_accel.py
│   ├── session/
│   ├── services/
│   └── ui/
├── models/                   # onnx 缓存 / 打包源
├── tests/
└── scripts/
    └── build_exe.bat
```

## 背景

参考 Glaze 上的 Peel（Mac：Vision 本机 / remove.bg 在线）。  
本仓库在 Windows 上用 rembg 重做本机能力，产品形态独立。

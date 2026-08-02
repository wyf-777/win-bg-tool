# win-bg-tool

Windows **本机**图片去背景小工具。对标 Peel 的使用强度，**不**复刻 Glaze / Mac 架构。

## 当前阶段

**主路径已完成，可日常使用**（引擎 + GUI + 多图 + 设置 + 剪贴板 + 修补 + 可选加速 + 文件夹监视）。

| 文档 | 内容 |
|------|------|
| [docs/progress.md](docs/progress.md) | 进度与里程碑 |
| [docs/overview.md](docs/overview.md) | 总览与规划 |
| [docs/requirements.md](docs/requirements.md) | 需求与验收 |
| [docs/design-accel.md](docs/design-accel.md) | **F14 更快处理**设计与逻辑 |
| [docs/design-folder-watch.md](docs/design-folder-watch.md) | **F13 文件夹监视** |
| [docs/design-multi-image.md](docs/design-multi-image.md) | 多图交互 |
| [docs/research-rembg.md](docs/research-rembg.md) | rembg 调研 |

## 快速启动

```bat
cd /d "项目根目录\win-bg-tool"
pip install -r requirements.txt
python -m app.main
```

或双击 `run.bat`。

### 使用要点

- **拖入**图片到中央区域，或点 **打开…**（可多选）  
- 处理完可 **拖出** 结果，或点 **导出**  
- **设置**（铺满窗口）：左侧分类，右侧明细  
  - 外观：主题  
  - 模型选择：默认模型、擅长/说明、Alpha Matting、**更快处理**  
  - 导出：格式与文件名前缀  
  - **文件夹**：监视进图目录，自动抠图到「已抠图」（可改）  
  - 快捷键：均可自定义（含 Esc 返回上一级、灯箱方向键、按住看原图）  
- **多图**：处理中不可再拖；完成后可追加；网格全选/反选/导出；点图灯箱；右键网格可 **换模型重抠**  
- **单图右键**：同样可用已下载模型重抠  
- **剪贴板**：`Ctrl+C` 复制结果；`Ctrl+V` 粘贴导入（可在设置中改键）  
- **修补**：结果出来后可进修补页修蒙版  
- **文件夹监视**：设置 → 文件夹  
  - 默认只处理开启后的新图；结果进「已抠图」，失败进「失败」  
  - 可选：含子目录、成功后原图移到「已处理」、关窗进托盘  
  - 暂停 / 清空队列 / 重试失败；主界面底部显示监视状态  

首次使用某个模型会下载到 `models/`（需联网一次）。

### 模型怎么选？

- **不会**根据图片内容自动换模型。  
- 设置里选的模型 = 之后默认一直用它，直到再改。  
- 右键「用已下载模型重抠」= 只对这一张用所选模型再跑一遍（会切换引擎当前模型，一般不改设置里的默认项）。  

### 更快处理（可选加速）

- **默认：普通模式**，人人可用，无需懂 CPU/GPU。  
- **设置 → 模型选择 → 更快处理**：有条件时尽量用显卡/图形加速；不支持或失败会 **自动普通模式**。  
- 逻辑与验收详见 [docs/design-accel.md](docs/design-accel.md)。  

**进阶（可选）：** 默认依赖是 CPU 版 `onnxruntime`。若本机有 NVIDIA 且自行安装了匹配的 `onnxruntime-gpu`（与 CPU 包通常 **二选一**），勾选「更快处理」后才可能真正走 CUDA。未安装 GPU 包 **不影响** 正常使用。

## 技术栈

| 层 | 选型 |
|----|------|
| 语言 | Python 3.11+ |
| 抠图 | rembg + onnxruntime（默认 isnet-general-use） |
| 加速 | 可选「更快处理」；探测 CUDA/DirectML 等；失败回退 |
| UI | PySide6 |
| 剪贴板 | 已做 |
| 在线 | 未做（规划 remove.bg） |
| 打包 | 未做 |

## 目录结构

```
win-bg-tool/
├── README.md
├── requirements.txt
├── run.bat
├── docs/
│   ├── overview.md
│   ├── progress.md
│   ├── requirements.md
│   ├── design-accel.md      # F14
│   ├── design-multi-image.md
│   ├── manual-mask-editor-plan.md
│   └── research-rembg.md
├── app/
│   ├── main.py
│   ├── engines/      # rembg、模型目录、runtime_accel
│   ├── session/      # 多图会话与队列
│   ├── services/     # 设置、导出、剪贴板、蒙版、快捷键
│   └── ui/           # 主窗、工作区、设置、修补、主题
├── models/           # onnx 缓存
├── tests/
└── scripts/
```

## 背景

参考 Glaze 上的 Peel（Mac：Vision 本机 / remove.bg 在线）。  
本仓库在 Windows 上用 rembg 重做本机能力，产品形态独立。

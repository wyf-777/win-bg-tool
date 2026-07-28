# win-bg-tool

Windows **本机**图片去背景小工具。对标 Peel 的使用强度，**不**复刻 Glaze / Mac 架构。

## 当前阶段

**主路径已完成，可日常使用**（引擎 + GUI + 多图 + Edge 式设置）。

- 进度详情：[docs/progress.md](docs/progress.md)  
- 全景规划：[docs/overview.md](docs/overview.md)  
- 需求列表：[docs/requirements.md](docs/requirements.md)  

## 快速启动

```bat
cd /d "E:\other\各种资源_Project\各种资源\win-bg-tool"
pip install -r requirements.txt
python -m app.main
```

或双击 `run.bat`。

### 使用要点

- **拖入**图片到中央区域，或点 **打开…**（可多选）  
- 处理完可 **拖出** 结果，或点 **导出**  
- **设置**（铺满窗口）：左侧分类，右侧明细  
  - 外观：主题  
  - 模型选择：默认模型 + 擅长/说明 + Alpha Matting  
  - 导出：默认格式（PNG/JPEG/WebP/BMP/TIFF/自定义）+ 文件名前缀  
- **多图**：处理中不可再拖；完成后可追加；网格支持全选/反选/导出选中/导出全部；点图放大，左右切换，右键回网格  

首次使用某个模型会下载到 `models/`（需联网一次）。

## 技术栈

| 层 | 选型 |
|----|------|
| 语言 | Python 3.11+ |
| 抠图 | rembg + onnxruntime（默认 isnet-general-use） |
| UI | PySide6 |
| 在线 | 未做（规划 remove.bg） |
| 打包 | 未做 |

## 文档

| 文档 | 内容 |
|------|------|
| [docs/overview.md](docs/overview.md) | 总览与规划 |
| [docs/progress.md](docs/progress.md) | 里程碑与剩余项 |
| [docs/requirements.md](docs/requirements.md) | 需求与验收 |
| [docs/design-multi-image.md](docs/design-multi-image.md) | 多图交互设计 |
| [docs/research-rembg.md](docs/research-rembg.md) | rembg 调研 |

## 目录结构

```
win-bg-tool/
├── README.md
├── requirements.txt
├── run.bat
├── docs/
├── app/
│   ├── main.py
│   ├── engines/      # rembg 引擎、模型目录
│   ├── session/      # 多图会话与队列
│   ├── services/     # 设置持久化、导出
│   └── ui/           # 主窗、工作区、设置页、主题
├── models/           # onnx 缓存（可 gitignore 大文件）
└── scripts/
```

## 背景

参考 Glaze 上的 Peel（Mac：Vision 本机 / remove.bg 在线）。  
本仓库在 Windows 上用 rembg 重做本机能力，产品形态独立。

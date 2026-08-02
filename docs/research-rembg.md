# 调研笔记：rembg 核心库 & GIMP + rembg 插件

日期：2026-07-27  
用途：指导 win-bg-tool 引擎与交互设计；**不**把 GIMP 当目标平台。

## 1. rembg 核心库（danielgatis/rembg）

| 项 | 内容 |
|----|------|
| 仓库 | https://github.com/danielgatis/rembg |
| 协议 | MIT |
| 定位 | 本机去背景：CLI / Python 库 / HTTP 服务 / Docker |
| 最新版（调研时） | PyPI **2.0.77**；本机环境曾装 **2.0.56**（模型列表以版本为准） |
| Python | **>=3.11, <3.14**（2.0.77 文档） |
| 推理 | **ONNX Runtime**（`onnxruntime` / `onnxruntime-gpu` / ROCm） |
| 依赖亮点 | Pillow、numpy、pooch（下模型）、**pymatting**（可选 alpha matting）、scipy、scikit-image；后处理用 OpenCV 形态学 |

### 1.1 架构（对我们最有用）

```
输入 bytes | PIL | ndarray
        ↓
  EXIF 方向修正
        ↓
  Session.predict()  →  ONNX 出 mask（灰度）
        ↓
  可选 post_process_mask（开运算 + 高斯）
        ↓
  可选 alpha_matting（pymatting，更慢、边缘更软）
        ↓
  naive_cutout / putalpha → RGBA
        ↓
  可选 bgcolor 铺底
        ↓
输出 同类型（bytes/PIL/ndarray）
```

关键 API：

```python
from rembg import remove, new_session

# 单次（每次可能重新加载模型，慢）
out = remove(image_bytes)

# 推荐：复用 session（GUI / 批量必须这样做）
session = new_session("isnet-general-use")  # 或 u2net 等
out = remove(image_bytes, session=session)

# 常用开关
out = remove(
    data,
    session=session,
    only_mask=False,           # True 则只返回 mask
    post_process_mask=False,   # mask 形态学平滑
    alpha_matting=False,       # 边缘细化（CPU 重）
    alpha_matting_foreground_threshold=240,
    alpha_matting_background_threshold=10,
    alpha_matting_erode_size=10,
    bgcolor=None,              # 如 (255,255,255,255) 白底
)
```

`new_session(model_name, providers=None)`：

- 内部 `ort.InferenceSession`，providers 默认可为机器上全部可用 provider  
- 环境变量 `OMP_NUM_THREADS` 可限制线程  

### 1.2 模型

- 首次使用自动下载到 **`U2NET_HOME`**，默认 **`~/.u2net/`**（Windows 即用户目录下 `.u2net`）  
- 可用 `MODEL_CHECKSUM_DISABLED=1` 跳过校验以使用自定义 onnx  

| 模型名 | 适用 | 备注 |
|--------|------|------|
| `u2net` | 通用默认 | 经典基线 |
| `u2netp` | 轻量/更快 | 效果通常弱于 u2net |
| `u2net_human_seg` | 人像 | |
| `u2net_cloth_seg` | 服装解析 | 上衣/下装/全身等，非单纯抠图 |
| `silueta` | 通用、体积更小 | ~43MB 级 |
| `isnet-general-use` | **通用增强** | 常作质量升级首选 |
| `isnet-anime` | 二次元 | |
| `sam` | 提示分割 | 需额外 point/box 参数，GUI 更复杂 |
| `birefnet-*` / `bria-rmbg` 等 | 新一代质量 | **较新 rembg 才有**；本机 2.0.56 未注册部分新模型 |

**本机 2.0.56 已注册：**  
`u2net`, `u2netp`, `u2net_human_seg`, `u2net_cloth_seg`, `silueta`, `isnet-general-use`, `isnet-anime`, `sam`, `u2net_custom`  

**建议项目依赖：** 锁定较新的 `rembg[cpu]`（或 gpu），以便用上 birefnet / bria 等。

### 1.3 CLI（GIMP 子进程模式会用到）

| 子命令 | 用途 |
|--------|------|
| `rembg i` | 单文件 |
| `rembg p` | 目录批量 / watch |
| `rembg s` | HTTP + 可选 Gradio |
| `rembg b` | RGB24 流（如 FFmpeg） |

示例：

```bash
rembg i -m isnet-general-use in.jpg out.png
rembg i -a -ae 15 in.jpg out.png          # alpha matting
rembg i -om in.jpg mask.png               # 仅 mask
rembg p input_dir output_dir
```

安装：

```bash
pip install "rembg[cpu]"        # 库
pip install "rembg[cpu,cli]"    # 库 + CLI
pip install "rembg[gpu]"        # NVIDIA，需匹配 CUDA/ORT
```

注意：`rembg[gpu]` 与 `onnxruntime` 冲突问题在社区 issue 中常见；**CPU/GPU 二选一装干净**。

### 1.3b 本项目 F14 落地（实现对照）

| 点 | 本项目做法 |
|----|------------|
| 默认 | CPU 包 + 普通模式，面向全体用户 |
| 产品开关 | 设置「更快处理」软偏好（`prefer_accel`），非强制 |
| 探测 | `app/engines/runtime_accel.py` → `get_available_providers()` |
| 会话 | `new_session(name, providers=[...])`，与 rembg BaseSession 一致 |
| 失败 | 捕获后强制 CPU 再加载，人话提示 |
| 文档 | [design-accel.md](design-accel.md) |

**不要**默认把 `onnxruntime-gpu` 写进全员 `requirements.txt`。

### 1.4 工程注意

1. **Session 必须复用** — 否则每张图重新 load onnx，GUI 会极慢  
2. **UI 线程禁止直接 `remove()`** — 推理阻塞，必须 worker 线程  
3. **模型目录** — 可用 `U2NET_HOME` 指到项目 `models/`，便于打包与便携  
4. **EXIF** — 库内已 `exif_transpose`，仍建议统一从 PIL 入口测一遍手机竖图  
5. **alpha_matting** — 默认关；发丝/半透明可开，耗时明显上升  
6. **only_mask** — 若以后做“蒙版层/可编辑边缘”，很有价值  
7. **协议 MIT** — 可商用集成，保留致谢为宜  
8. **加速** — providers 与偏好分离；见 F14 design-accel；勿每张图反复探测装包  

---

## 2. GIMP + rembg 插件（社区实现）

GIMP **不内置** rembg；社区插件把 GIMP 当壳，**真正抠图仍是系统/venv 里的 rembg**。

### 2.1 代表性仓库

| 仓库 | 目标 | 集成方式 | 要点 |
|------|------|----------|------|
| [Tech-Archive/gimp-rembg-plugin](https://github.com/Tech-Archive/gimp-rembg-plugin) | GIMP 2.10 + gimpfu | **子进程**调外部 Python：`python -m rembg.cli i ...` | 临时 jpg→png；可选 Mask / 白底合并 / 画布正方形 / 批量打开图；**硬编码本机 python 路径**（需改） |
| [gvardi/gimp-rembg-plugin](https://github.com/gvardi/gimp-rembg-plugin) | GIMP 3 | 同样 **subprocess + rembg.cli** | **config.ini** 配 python 路径与默认选项；结构更清晰 |
| [ismdevteam/gimp3-rembg-plugin](https://github.com/ismdevteam/gimp3-rembg-plugin) | GIMP 3 | **进程内** `from rembg import remove, new_session` | 导出层为 PNG → remove → 再打开结果；依赖 GIMP 所用 Python 能 import rembg（Flatpak/venv 路径麻烦） |

另有 **remove.bg 官方 GIMP 插件**（云端 API，不是 rembg）— 与 Peel online 类似，**别和 rembg 插件混淆**。

### 2.2 插件共性流程（可借鉴）

```
GIMP 当前图层
  → 导出到临时文件（jpg 或 png）
  → rembg 处理（CLI 或库）
  → 读回 PNG（透明）
  → 新图层 / Alpha 蒙版 / 或与白底合并
  → 删临时文件
  → undo group 包起来（可撤销）
```

对话框常见选项（与 rembg 能力对齐）：

- 模型下拉（u2net / isnet / sam…）  
- Alpha Matting 开关 + erode size  
- As Mask（非破坏编辑）  
- Make Square / 处理全部打开图像（产品增值，非 rembg 本身）

### 2.3 两种集成模式对比

| | 子进程 CLI | 进程内 import rembg |
|--|------------|---------------------|
| 优点 | Python 版本与 GIMP 解耦；崩了不拖死宿主 | 无编解码往返路径可更少；session 易持有 |
| 缺点 | 临时文件 + 启动进程开销；路径配置易错 | GIMP 的 Python 环境装 rembg 很痛（尤其 Windows/Flatpak） |
| **对我们** | 若引擎独立成 sidecar 可参考 | **独立桌面 App 应直接库调用**（我们选 PySide6，无 GIMP 约束） |

### 2.4 从插件学到的产品细节

1. **As Mask** 比直接拍扁图层更专业 — 我们 MVP 可先导出透明 PNG；P1 可考虑“同时导出 mask”  
2. **临时文件命名** 加时间戳/随机，避免并发冲突（gvardi 已改进）  
3. **外部 Python 路径可配置** — 打包后我们应自带 venv/嵌入解释器，避免用户手改路径  
4. **错误用宿主 message 展示 stderr** — 我们 UI 要捕获 rembg/ORT 异常并中文提示  
5. 插件默认模型列表偏旧 — 我们应暴露 **isnet-general-use** 并视版本加 birefnet  

---

## 3. 对 win-bg-tool 的落地建议

### 3.1 引擎层（M1）

```text
engines/local_rembg.py
  - 启动时或首次抠图：new_session(model_name)
  - 缓存 session（换模型时重建）
  - remove(pil_or_bytes, session=..., post_process_mask=..., alpha_matting=...)
  - U2NET_HOME → 项目 models/ 或用户数据目录
```

依赖建议：

```text
rembg[cpu]>=2.0.70   # 视锁定策略；尽量新以获得更多模型
Pillow
# 有 NVIDIA 再文档说明 rembg[gpu] 互斥安装
```

### 3.2 UI 层（M2）对齐插件但不绑 GIMP

| 插件能力 | 我们第一版 | 说明 |
|----------|------------|------|
| 选模型 | P1 可做下拉；MVP 可先写死 isnet 或 u2net | |
| Alpha matting | P1 高级选项 | 默认关 |
| 预览透明 | P0 棋盘格 | 强于插件“跑完才在画布上看” |
| 导出 PNG | P0 | |
| As Mask | 二期 only_mask 导出 | |
| 批量打开图 | 二期 | rembg `p` 或循环 + 同 session |

### 3.3 明确不采用

- 不依赖 GIMP 安装  
- 不把插件 GPLv3 代码直接拷进 MIT/自有项目而不审许可（插件多为 GPLv3；**我们用 rembg MIT API 自己写**）  
- 不在 UI 线程调 `remove`  
- 不每张图 `new_session`  

### 3.4 建议默认参数（起点）

| 参数 | 建议默认 | 理由 |
|------|----------|------|
| model | `isnet-general-use`（下载失败则回退 `u2net`） | 通用质量通常好于默认 u2net |
| post_process_mask | `True` 或可关 | 边缘略稳 |
| alpha_matting | `False` | 速度；高级里再开 |
| session | 全局单例按模型缓存 | 性能 |

---

## 4. 参考链接

- rembg：https://github.com/danielgatis/rembg  
- USAGE：仓库内 `USAGE.md`  
- GIMP 2.x 插件：https://github.com/Tech-Archive/gimp-rembg-plugin  
- GIMP 3 子进程版：https://github.com/gvardi/gimp-rembg-plugin  
- GIMP 3 库调用版：https://github.com/ismdevteam/gimp3-rembg-plugin  
- remove.bg 的 GIMP 插件（云端，非 rembg）：https://www.remove.bg/a/gimp-remove-background-plugin  

## 5. 调研结论（一句话）

**rembg = 成熟的本机 ONNX 抠图库（session 复用 + 多模型 + 可选 matting）；GIMP 插件 = 临时文件/子进程或 import 的薄壳。**  
我们项目应 **直接库集成 rembg**，吸收插件的选项与错误处理经验，做成独立 PySide6 工具，而不是 GIMP 插件。

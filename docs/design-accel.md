# F14 更快处理（加速）设计说明

状态：**已实现**  
最后更新：2026-08-01  
相关代码：`app/engines/runtime_accel.py`、`app/engines/local_rembg.py`、`app/services/settings.py`、`app/ui/settings_dialog.py`、`app/ui/main_window.py`

---

## 1. 一句话

**抠图算法不变；可选在有条件时用显卡/图形加速算得更快；默认普通模式（CPU），失败自动回退，用户无需懂硬件。**

---

## 2. 产品目标

| 目标 | 做法 |
|------|------|
| 所有人能用 | 默认 **普通模式**；不装 GPU 包也能完整使用 |
| 不懂 CPU/GPU | 文案用「更快处理 / 普通模式」，不暴露 CUDA 等术语 |
| 有加速条件时可更快 | 勾选偏好后，尽量走可用的 ORT accel provider |
| 失败不吓人 | 加速加载失败 → **自动 CPU**，状态栏一句人话提示 |
| 不强迫大依赖 | 默认 `requirements.txt` 仍为 CPU 版 `onnxruntime` |

**不是：** 新抠图模型、云端加速、按图片自动选模型。

---

## 3. 三层概念（实现与文案都要对齐）

| 层 | 含义 | 存储 / 位置 |
|----|------|-------------|
| **用户偏好** | 「我想更快」 | `settings`：`engine/prefer_accel`（默认 `false`） |
| **机器能力** | 「这台机有没有加速组件」 | 运行时探测 `onnxruntime.get_available_providers()` |
| **实际运行** | 「这次 session 真用了什么」 | 引擎 `_active_providers`；加载失败可 `_force_cpu` |

因此合法状态包括：

- 未勾选 → 始终普通模式  
- 勾选但无加速组件 → 偏好为真，**实际仍普通模式**（提示「已记住偏好，当前只能普通模式」）  
- 勾选且有组件、加载成功 → 加速  
- 勾选且加载失败 → 本轮强制 CPU，偏好可仍保留  

---

## 4. 用户路径

### 4.1 入口

**设置 → 模型选择 → 处理速度**

- 复选框：`更快处理（有条件时用显卡加速）`  
- 状态行：根据「能力 × 偏好」刷新人话说明  
- Tooltip：默认人人可用；失败自动退回  

### 4.2 主界面反馈

- 模型标签可带设备简述：`本机 · {model} · 普通模式` 或 `… · 加速 · …`  
- 预热/切换后状态栏可附带加速说明或回退提示  

### 4.3 与模型选择的关系

- **全局仍是一个当前引擎模型 + 一套 providers**  
- 设置里换模型、开关加速都会丢掉 ONNX session，下次抠图再加载  
- 右键「用已下载模型重抠」只换模型 id，不单独改加速偏好  

---

## 5. 技术设计

### 5.1 模块职责

| 文件 | 职责 |
|------|------|
| `engines/runtime_accel.py` | 探测能力、`resolve_providers`、人话标签 |
| `engines/local_rembg.py` | `prefer_accel` / `force_cpu`；`new_session(..., providers=)`；失败回退 |
| `services/settings.py` | `get/set_prefer_accel` |
| `ui/settings_dialog.py` | 开关 + 状态文案；`prefer_accel_changed` |
| `ui/main_window.py` | 接线、预热、状态栏 / 模型标签 |

### 5.2 Provider 解析

```
prefer_accel == false  或  force_cpu == true
    → ["CPUExecutionProvider"]

prefer_accel == true 且 无加速 provider
    → ["CPUExecutionProvider"]

prefer_accel == true 且 有加速 provider
    → [加速1, 加速2, …, "CPUExecutionProvider"]
```

加速 provider 优先顺序（有则加入）：

1. `CUDAExecutionProvider`（NVIDIA）  
2. `DmlExecutionProvider`（Windows DirectML）  
3. `ROCMExecutionProvider`  
4. `CoreMLExecutionProvider`  

与 rembg `BaseSession` 一致：`new_session(name, providers=[...])`。

### 5.3 加载与回退（引擎）

```
providers = resolve_providers(prefer_accel, force_cpu)
try:
    session = new_session(model, providers=providers)
except 且 本次试图用加速:
    force_cpu = True
    提示「加速不可用，已自动改用普通模式」
    session = new_session(model, providers=CPU_ONLY)
```

同一模型候选链（失败换备用模型名）逻辑与加速无关，仍走 `FALLBACK_MODEL_IDS`。

### 5.4 默认依赖策略

| 包 | 角色 |
|----|------|
| `onnxruntime`（requirements 默认） | 所有用户；通常仅 CPU（及部分 Azure 等） |
| `onnxruntime-gpu`（可选，进阶） | 与 CPU 包常冲突，**二选一**；装好且驱动匹配时 CUDA 才会出现在 providers |

**不**把 `onnxruntime-gpu` 写进默认 `requirements.txt`，避免小白安装失败。

---

## 6. 文案约定（产品）

| 场景 | 倾向文案 |
|------|----------|
| 无加速、未勾选 | 状态：普通模式 · 人人可用（未检测到加速组件） |
| 有加速、未勾选 | 状态：可加速（…）· 当前使用普通模式 |
| 有加速、已勾选 | 状态：可加速 · 已开启更快处理（失败会自动退回） |
| 无加速、已勾选 | 状态：普通模式 · 已记住「更快处理」，当前只能普通模式 |
| 加载回退 | 加速不可用，已自动改用普通模式（不影响使用） |

避免在主路径弹出：CUDA 版本、cuDNN、驱动命令行等。

---

## 7. 验收清单

1. 全新安装（仅 CPU 包）：不勾选即可抠图；主界面无错误弹窗。  
2. 勾选「更快处理」但无 GPU 包：仍可抠图；状态说明当前普通模式。  
3. 有可用 accel provider 且勾选：session 使用非纯 CPU-first providers（或至少尝试后成功）。  
4. 模拟加速 `new_session` 失败：自动 CPU 成功；有人话提示。  
5. 切换开关 / 换模型后：旧 session 丢弃，下次处理用新配置。  
6. 单元测试：`tests/test_runtime_accel.py` 覆盖 resolve / detect / 标记判断。  

---

## 8. 非目标（本版不做）

- 自动按图片类型选加速  
- 打包时内嵌完整 CUDA 运行时  
- 强制所有用户安装 GPU 包  
- 多卡选择、显存精细调参 UI  

---

## 9. 相关文档

| 文档 | 关系 |
|------|------|
| [requirements.md](requirements.md) | F14 需求条目 |
| [progress.md](progress.md) | 交付状态 |
| [research-rembg.md](research-rembg.md) | rembg / ORT 调研；CPU·GPU 包冲突注意 |
| [../README.md](../README.md) | 用户向使用说明 |

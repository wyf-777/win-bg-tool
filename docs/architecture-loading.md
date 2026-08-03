# 加载、不卡 UI、进程隔离与引擎自愈

最后更新：2026-08-02

本文说明：**重型推理库如何加载**、**为何会卡 UI**、**成熟应用怎么做**、**Peel 当前实现**。

相关代码：

| 路径 | 职责 |
|------|------|
| `app/main.py` | UI 进程入口（不 import rembg） |
| `app/engines/process_engine.py` | UI 侧引擎门面 + supervisor |
| `app/engines/process_worker.py` | 推理子进程（唯一 import rembg 处） |
| `app/engines/local_rembg.py` | 子进程内 rembg 实现 |
| `app/ui/main_window.py` | 就绪态、排队、健康状态文案 |

打包注意：子进程 spawn 需 `multiprocessing.freeze_support()`；见 [packaging.md](packaging.md)。

---

## 1. 问题本质

| 现象 | 原因 |
|------|------|
| 拖窗/点按钮突然顿一下 | UI 与 rembg/onnx **同进程**时，C 扩展 import 抢 **GIL** |
| 仅「后台线程」不够 | 线程仍共享解释器 GIL |
| 加载时间无法为零 | 只能换时机或隔离故障域 |

---

## 2. 成熟应用常见做法

| 做法 | 代表 | 要点 |
|------|------|------|
| **A. 启动闪屏** | PS / Office / 多数重应用 | 等待可预期，不在「已可点」时卡死 |
| **B. 壳先亮、引擎后就绪** | VS Code / Discord | 状态机；依赖引擎的功能等 ready |
| **C. 多进程** | Chrome / 商业 AI 桌面 | UI 永不加载推理库；worker 可崩可重启 |
| **D. 安装/首次准备** | 游戏等 | 重初始化挪出日常启动 |
| **E. 原生推理内核** | 部分 on-device 产品 | C++ ORT，UI 只 IPC |

**原则摘要：** UI 线程不做重活；等待可预期；能进程隔离就隔离；崩溃有限次自愈 + 熔断。

---

## 3. Peel 当前实现

### 3.1 进程模型（C）

```
UI 进程                         Worker 进程
────────                        ──────────
ProcessRembgEngine              run_worker()
  · set_model（本地）            · LocalRembgEngine
  · warmup / remove  ──Queue──►  · rembg / onnxruntime
  · supervisor 自愈              · 下载 / session
```

### 3.2 启动与就绪（B）

1. 主窗口**立刻**显示  
2. 状态：`引擎准备中…` → `加载模型…` → `就绪`  
3. 未就绪时打开/拖入图片：**排队**，就绪后自动处理  
4. 设置始终可用  

### 3.3 批处理中切换模型

| 情况 | 行为 |
|------|------|
| 正在 `remove` 的图 | **不中断**，用已加载 session 做完 |
| 队列中后续图 | 用新默认模型 |
| 仅在预热/下载大模型 | 可取消预热，改加载新模型 |

### 3.4 引擎自愈（supervisor）

| 规则 | 值 / 行为 |
|------|-----------|
| 崩溃检测 | RPC 发现进程死 / 超时 |
| 自动重启 | 90s 窗口内最多 **3** 次；退避 0.25 / 0.6 / 1.2s |
| 不计崩溃 | 切模型取消预热、App 退出（intentional kill） |
| 熔断 | 超限停止自动重启；提示用户 |
| 用户恢复 | 再拖图 / 再应用模型 → `reset_circuit()` |
| 恢复后 | 冷 worker → 自动 warmup；UI 显示 recovered |

健康事件（`engine_health`）：`restarting` | `recovered` | `gave_up` | `info`。

### 3.5 退出

- `shutdown_async()`：短超时 terminate，不堵 UI 数秒  
- 会话 worker 仅短暂 wait  

---

## 4. 对照表

| 层次 | 成熟应用 | Peel（当前） |
|------|----------|--------------|
| 不冻 UI | 重活不进 UI 进程 | ✅ 分进程 |
| 可预期 | Splash / 状态 / 禁用 | ✅ 就绪态 + 排队 |
| 可恢复 | 进程可重启 | ✅ 有限自愈 + 熔断 |
| 推理内核 | 常 C++ | Python ORT（worker 内） |

---

## 5. 仍可增强

1. 空闲定时 `ping` 发现假死  
2. 更细进度条（下载/加载）  
3. C++ ORT 小服务（包体与冷启动）  
4. 打包环境下 spawn 全路径回归  

---

## 6. 参考

- [PyQt splash while loading heavy libraries](https://stackoverflow.com/questions/876107/pyqt-splash-screen-while-loading-heavy-libraries)  
- [Qt QSplashScreen](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSplashScreen.html)  
- Chrome 多进程 / 有限重启思路（概念对齐）  
- [ONNX Runtime on-device notes](https://opensource.microsoft.com/blog/2023/02/08/performant-on-device-inferencing-with-onnx-runtime/)  

# Peel 打包指南（PyInstaller）

最后更新：2026-08-06

本文记录 **F15 打包 exe + 安装包** 的踩坑、根因、固定做法与验收清单，避免下次再出现  
`cannot import name 'remove' from 'rembg'`、桌面图标一直是 Python 默认标、误用旧 `dist` 打包等一类问题。

**相关：** [architecture-loading.md](architecture-loading.md)（进程引擎 / 自愈）· [progress.md](progress.md)

> **重要：** 当前推理在 **子进程**（`ProcessRembgEngine` + `spawn`）。打包后必须验证子进程能启动；入口已含 `multiprocessing.freeze_support()`（`app/main.py`）。

---

## 1. 一键打包（标准流程）

### 前置条件

| 项 | 要求 |
|----|------|
| Python | 建议 **3.12 x64**（与当前 `requirements.txt` / 已验证环境一致） |
| 依赖 | 先能在开发环境正常跑 `python -m app.main` 并成功抠图 |
| 模型 | 仓库内必须有 `models/u2netp.onnx`（打包默认内置轻量模型） |
| PyInstaller | `>= 6.0`（`build_exe.bat` 会自动安装） |

### 命令

**A. 仅便携目录（onedir）**

```bat
scripts\build_exe.bat
```

等价于：

```bat
python -m pip install -r requirements.txt "pyinstaller>=6.0"
python -m PyInstaller --noconfirm --clean peel.spec
```

**B. 带「选择安装位置」的安装包（推荐给用户）**

```bat
scripts\build_installer.bat
```

- 先跑 PyInstaller，再用 **Inno Setup** 打成 `Setup.exe`
- 向导页可改安装目录（默认 `C:\Program Files\Peel`）
- 可选桌面快捷方式、装完启动
- 仅重打安装包（已有 `dist\Peel\`）：`scripts\build_installer.bat --installer-only`

依赖：**Inno Setup 6**（本机已可用 `winget install --id JRSoftware.InnoSetup -e`）。  
脚本会找 `ISCC.exe`；也可设环境变量 `INNO_SETUP_PATH` 指向它。  
脚本：`packaging\peel_setup.iss`；中文界面语言文件：`packaging\languages\ChineseSimplified.isl`。

### 产物

```
dist\Peel\
  Peel.exe              # 启动入口（窗口程序，无控制台）
  models\u2netp.onnx    # 旁路副本（部分路径会读到）
  _internal\            # 运行时依赖（必须整目录带走）
    models\u2netp.onnx  # 包内只读资源（_MEIPASS）
    rembg\ numpy\ cv2\ onnxruntime\ ...

dist\Peel-Setup-1.0.0.exe   # 安装程序（选路径安装，推荐分发这个）
```

**便携分发**时必须整包复制 `dist\Peel\` 文件夹，禁止只拷贝 `Peel.exe`。  
**普通用户**建议只发 `Peel-Setup-*.exe`。

### 多进程（必测）

| 检查 | 说明 |
|------|------|
| 启动后顶栏由「引擎准备中」变为就绪 | worker 已 hello + warmup |
| 拖一张图能抠完 | remove IPC 正常 |
| 任务管理器可见短暂/常驻 python 子进程（开发）或同目录子进程 | spawn 成功 |
| 在任务管理器结束 worker 后状态栏出现自动恢复 | supervisor 自愈 |

若 exe 下 worker 起不来：检查 `freeze_support`、hiddenimports、是否只拷了 exe。

---

## 2. 架构约定（改打包前先懂这三点）

### 2.1 onedir，不是 onefile

- 使用 **onedir**（`EXE` + `COLLECT`），依赖落在 `_internal\`。
- onefile 解压到临时目录，对 onnx / 大量 DLL 更慢、更难排查，当前不采用。

### 2.2 两条路径：可写根 vs 只读包根

见 `app/runtime_paths.py`：

| 函数 | 冻结后含义 | 用途 |
|------|------------|------|
| `app_root()` | `Peel.exe` 所在目录 | 可写：`models\`、用户配置 |
| `bundle_root()` | `sys._MEIPASS`（即 `_internal`） | 只读：内置权重、收集的库 |

启动时 `ensure_bundled_models()` 把包内 `u2netp.onnx` 复制到 exe 旁 `models\`，供 `U2NET_HOME` / rembg 下载逻辑使用。

### 2.3 打包默认模型

- 开发默认：`isnet-general-use`（见 `models_catalog.DEFAULT_MODEL_ID`）
- **冻结默认**：`u2netp`（`BUNDLED_MODEL_ID`，断网也能先用）

---

## 3. 曾踩过的致命问题

### 3.1 症状（用户可见）

界面中央红色错误类似：

```text
处理失败：cannot import name 'remove' from 'rembg'
(...\dist\Peel\_internal\rembg\__init__.py)
```

开发环境 `from rembg import remove` **完全正常**，只有 exe 失败。

### 3.2 表面原因

`rembg/__init__.py` 里是：

```python
from .bg import remove
from .session_factory import new_session
```

任意一步在冻结环境失败，Python 常表现为 **cannot import name 'remove'**，而不是底层真实异常  
（例如 `ModuleNotFoundError: numpy.core.multiarray`）。

### 3.3 根因：半截包 + 命名空间遮蔽（最重要经验）

PyInstaller 常见模式：

1. **二进制扩展**（`.pyd` / `.dll`）被放到 `_internal\某包\` 磁盘上  
2. **纯 Python 模块**被打进 `PYZ` 压缩包  
3. 运行时若磁盘上已有 **不完整的包目录**（例如 `numpy\core\` 里只有 2 个 `.pyd`，没有 `multiarray.py`），会形成 **namespace / 半截 package**  
4. 它会 **遮蔽 PYZ 里完整的同名模块**，导致 `import numpy.core.multiarray` 失败  
5. 失败链：`numpy` → `cv2` → `pymatting`/`numba` → `rembg.bg` → `from rembg import remove` 炸掉

实测旧包问题示例：

| 路径 | 错误状态 | 正常状态 |
|------|----------|----------|
| `_internal\numpy\core\` | 仅 2 个 `.pyd` | 约 60+ 文件，含 `multiarray.py` |
| `_internal\numba\` | 无 `__init__.py`，空 namespace | 有完整 `__init__.py` 与子模块 |
| `_internal\pymatting\` | 可能缺失 | 有完整树 |

**经验法则：凡是带大量 C 扩展的栈，不要只靠 “hiddenimports 写个包名”，必须 `collect_all("包名")`，让 datas + binaries 成套落地。**

### 3.4 次要根因：rembg 启动时 import 全部会话

上游 `rembg/sessions/__init__.py` 会 **顺序 import 所有模型后端**，包括：

- `sam` → 依赖 **jsonschema**（及 attrs / referencing / rpds…）
- 其它可选后端若缺依赖，也会在 **import rembg 阶段** 直接失败

Peel 默认只用 `u2netp`，但 import 阶段仍会被 SAM 拖死。

**固定做法：** 用项目内覆盖文件，把会话注册改成 try/except 防御式加载：

```
packaging/rembg_sessions/__init__.py
  → 打进包内覆盖 rembg/sessions/__init__.py
```

逻辑在 `peel.spec` 末尾：过滤掉 collect_all 带来的上游 `__init__.py`，再写入我们的版本。

### 3.5 其它相关坑

| 现象 | 说明 |
|------|------|
| 只拷 `Peel.exe` | 没有 `_internal`，必挂 |
| `console=False` | 无黑窗，底层 traceback 看不见；调试可临时改 `console=True` 重打 |
| warn-peel.txt 一堆 missing | 多数是 torch/jax 等 **可选** 依赖，不必全收；但 **numpy/cv2/numba 不完整是致命的** |
| `tbb12.dll` missing（numba tbbpool） | 构建警告常见；默认线程池通常仍可用，暂可忽略 |
| 环境 Python 与打包 Python 不一致 | 务必用 **同一解释器** 装依赖并执行 PyInstaller |
| UPX | 当前 `upx=False`，不要随意打开（易压坏原生库） |

---

## 4. 当前 `peel.spec` 固定清单

### 4.1 必须 `collect_all` 的包

| 包 | 原因 |
|----|------|
| `rembg` | 主引擎 + sessions 源码 |
| `onnxruntime` | 推理 |
| `PIL` | 图像 IO |
| `numpy` | 半截包会毁掉一切 |
| `cv2` | rembg.bg 顶层 import |
| `pymatting` | Alpha Matting / bg 顶层 import |
| `scipy` | `scipy.ndimage` 等 |
| `numba` | pymatting 依赖 |
| `llvmlite` | numba 依赖 |
| `jsonschema` | sessions.sam（即使用防御注册也建议收齐） |
| `jsonschema_specifications` | jsonschema 资源 |
| `referencing` / `rpds` / `attrs` | jsonschema 依赖链 |
| `pooch` | 用 `collect_data_files` 即可（模型下载） |

### 4.2 内置模型

```python
extra_datas.append((str(root / "models" / "u2netp.onnx"), "models"))
```

构建前检查：`models\u2netp.onnx` 必须存在（`build_exe.bat` 已校验）。

### 4.3 rembg sessions 覆盖

```
packaging/rembg_sessions/__init__.py
```

- 每个 session `_register(...)` 包在 try/except  
- 至少保证 `u2netp`（及尽量 `u2net`）可用  
- **升级 rembg 版本后**：对比上游 `sessions/__init__.py` 是否新增 session，必要时同步到覆盖文件  

### 4.4 应用侧兜底（代码）

`app/engines/local_rembg.py`：

- `_import_rembg_remove()` / `_import_rembg_new_session()`  
- 优先 `from rembg.bg import remove`，失败再回退 `from rembg import remove`  
- 用 `_format_rembg_import_error` 给出中文可操作提示  

`app/ui/errors.py`：对 rembg / numpy.core.multiarray / 安装包不完整 等做友好文案映射。

---

## 5. 打包后验收清单（必做）

每次重新打包后，按顺序勾：

### A. 目录完整性

- [ ] 存在 `dist\Peel\Peel.exe`
- [ ] 存在 `dist\Peel\_internal\` 且体积合理（通常数 GB 级依赖很常见）
- [ ] `dist\Peel\_internal\numpy\core\multiarray.py` **存在**（不只是 `.pyd`）
- [ ] `dist\Peel\_internal\numba\__init__.py` **存在**
- [ ] `dist\Peel\_internal\pymatting\` 目录存在
- [ ] `dist\Peel\_internal\rembg\sessions\__init__.py` 开头含 **「Peel packaging override」**
- [ ] `dist\Peel\_internal\models\u2netp.onnx` 存在且大小正常（远大于 1MB）

快速检查（PowerShell）：

```powershell
$b = "dist\Peel\_internal"
@(
  "$b\numpy\core\multiarray.py",
  "$b\numba\__init__.py",
  "$b\pymatting\__init__.py",
  "$b\models\u2netp.onnx",
  "$b\rembg\bg.py"
) | ForEach-Object { "$_ -> $(Test-Path $_)" }
Select-String -Path "$b\rembg\sessions\__init__.py" -Pattern "Peel packaging override" -Quiet
```

### B. 功能验收

- [ ] 双击 `Peel.exe` 能启动主界面  
- [ ] 拖入一张 jpg/png，**能出抠图结果**（不再报 cannot import remove）  
- [ ] 首次运行后，exe 旁出现/更新 `models\u2netp.onnx`  
- [ ] （可选）设置里切换其它模型：需联网下载到 `models\`  

### C. 出问题后如何拿真实堆栈

1. 临时改 `peel.spec`：`console=True`  
2. `python -m PyInstaller --noconfirm --clean peel.spec`  
3. 从终端启动 `dist\Peel\Peel.exe`，复现后看控制台  
4. 修完再改回 `console=False`  

或在 `local_rembg` / rembg 导入处写日志到 `app_root()/rembg_import_error.log`（调试用，勿长期留敏感路径）。

---

## 6. 调试技巧（勿用错误方法）

### 6.1 错误：用 `python -S` + 只加 `_internal` 模拟冻结

这样会：

- **没有** PyInstaller 的 PYZ 导入器  
- 若把 `cv2` 等子目录塞进 `sys.path`，还会把 **`cv2/typing` 遮蔽标准库 `typing`**  
- 结论与真实 exe **不一致**

真实冻结行为只能用 **PyInstaller 打出来的 exe** 验证。

### 6.2 正确：小探针 exe（可选）

需要验证「仅 rembg 是否可 import」时，可临时做一个 console onedir，对下列包 `collect_all`，并 `--add-data models/u2netp.onnx;models`，脚本内：

```python
from rembg import remove, new_session
# + new_session("u2netp") + remove(小图)
```

通过后再打完整 Peel。不要依赖 site-packages 混跑。

### 6.3 构建日志

- `build\peel\warn-peel.txt`：缺失模块列表（区分致命 vs 可选）  
- `build\peel\xref-peel.html`：模块引用图（体积大，按需打开）  

---

## 7. 修改打包时的变更检查表

改依赖或升级库之后，按表过一遍：

| 变更 | 要做什么 |
|------|----------|
| 升级 `rembg` | 看 sessions 列表变化；更新 `packaging/rembg_sessions/__init__.py`；重测 import + 抠图 |
| 升级 `numpy` / `scipy` / `opencv` | 全量 `--clean` 重打；检查 `multiarray.py` 是否仍在包内 |
| 升级 `onnxruntime` | 确认 providers；CPU 至少可用；加速模式单独测 |
| 新增引擎依赖 | 在 `peel.spec` 增加 `collect_all`，不要只写 hiddenimport |
| 改默认模型 | 同步 `runtime_paths.BUNDLED_MODEL_ID`、`models/` 权重、`build_exe.bat` 检查项 |
| 只改 UI/业务代码 | 一般仍建议 `--clean` 后重打，避免脏 Analysis 缓存 |

---

## 8. 分发与用户侧注意

1. **整目录分发** `dist\Peel\`（zip 整个文件夹），或只发 **`Peel-Setup-*.exe`**  
2. 解压路径尽量短、无奇怪权限；避免只读介质当「可写 models 目录」  
3. 杀软可能拦截未知 exe / 大量 DLL：首次运行允许  
4. 「更快处理」依赖本机 DirectML/CUDA 等，失败会回落 CPU（见 F14 设计），与打包完整性无关  
5. 其它大模型首次切换仍需联网下载到 exe 旁 `models\`  
6. **安装包必须用当前源码重打的 `dist\Peel\`**，不要拿很久以前的目录只重跑 Inno（见 §11）

---

## 9. 相关文件索引

| 路径 | 作用 |
|------|------|
| `peel.spec` | PyInstaller 规格：collect_all、模型、sessions 覆盖、**exe icon** |
| `scripts/build_exe.bat` | 一键打包 onedir 入口 |
| `scripts/build_installer.bat` | onedir + Inno 安装包；`--installer-only` 仅重打 Setup |
| `packaging/peel_setup.iss` | Inno Setup：可选安装路径、桌面快捷方式、图标 |
| `packaging/peel.ico` | 应用图标（由产品图转多尺寸 ICO） |
| `packaging/languages/ChineseSimplified.isl` | 安装向导中文 |
| `packaging/rembg_sessions/__init__.py` | 防御式 sessions 注册（覆盖上游） |
| `app/runtime_paths.py` | 冻结路径 / 内置模型复制 |
| `app/engines/local_rembg.py` | rembg 导入兜底与推理；GitHub 镜像下载 |
| `app/ui/errors.py` | 用户可见错误文案 |
| `models/u2netp.onnx` | 打包默认权重源文件 |
| `docs/research-rembg.md` | rembg 调研（产品侧） |
| `docs/design-accel.md` | 加速模式（F14） |

---

## 10. 历史问题速查

| 时间 | 问题 | 处理 |
|------|------|------|
| 2026-08 | 打包 exe 报 `cannot import name 'remove' from 'rembg'` | 根因：numpy/numba 半截包 + rembg 全量 sessions；fix：`collect_all` 全家桶 + sessions 覆盖 + 重打包 |
| 同上 | 只收集 rembg/ort/PIL 不够 | 补 numpy/cv2/pymatting/scipy/numba/llvmlite/jsonschema 链 |
| 同上 | 调试时误判 cv2.typing 遮蔽 typing | 勿把 cv2 目录加入 sys.path 做模拟 |
| 2026-08-06 | 桌面快捷方式一直是 Python 默认图标 | 见 §12：多尺寸 ICO + 独立 `peel.ico` + 清图标缓存 |
| 同上 | 用户要「当前版本」却打了旧 dist | 必须先 `build_exe` / 全量 `build_installer`，禁止只对陈旧 `dist\Peel` 跑 Inno |
| 同上 | `dist\Peel` 拒绝访问、COLLECT 失败 | 先结束所有 `Peel.exe` 再打包 |

---

## 11. 注意事项：务必打「当前版本」

### 11.1 禁止用旧目录冒充新版本

| 错误做法 | 正确做法 |
|----------|----------|
| 只改 UI/代码后执行 `build_installer.bat --installer-only` | 源码有变更时跑 **完整** `scripts\build_installer.bat`（先 PyInstaller 再 Inno） |
| 复制很久以前的 `dist\Peel` 再压安装包 | 以 **今天** 的 `python -m PyInstaller … peel.spec` 产物为准 |
| 开发机还开着 `Peel.exe` 就重打 | 先 `taskkill /F /IM Peel.exe`，否则可能 `PermissionError` 删不掉 `_internal` |

### 11.2 验收「是不是当前版本」

- 看 `dist\Peel\Peel.exe` 的**修改时间**是否晚于最后一次源码提交/本地改动  
- 安装包 `dist\Peel-Setup-*.exe` 的修改时间应 **≥** 上述 exe  
- 若用户反馈「装完还是旧界面」：几乎一定是装了旧 Setup 或没卸旧快捷方式

### 11.3 安装包 vs 便携目录

| 分发物 | 适用 |
|--------|------|
| `Peel-Setup-*.exe` | 普通用户：向导选安装路径、可选桌面图标、卸载项 |
| `dist\Peel\` 整夹 zip | 便携/调试：勿只拷贝单个 exe |

---

## 12. 注意事项：应用图标与桌面快捷方式

产品图（如 `导出\图标.jpg`）**不能**直接给 Windows 当 exe/快捷方式图标，需转成 **多尺寸 `.ico`**。

### 12.1 固定产物与接线

| 项 | 约定 |
|----|------|
| 源文件 | `packaging/peel.ico`（16～256 多尺寸；PNG-in-ICO 亦可） |
| PyInstaller | `peel.spec` → `EXE(..., icon=packaging/peel.ico)` |
| 安装目录 | 额外安装 `{app}\peel.ico`（与 `Peel.exe` 同级） |
| Inno 桌面/开始菜单 | `IconFilename: {app}\peel.ico`（**不要**只写 `IconFilename: Peel.exe` + `IconIndex: 0` 指望总能刷新） |
| Setup 向导图标 | `SetupIconFile=peel.ico` |
| 卸载列表图标 | `UninstallDisplayIcon={app}\peel.ico` |

### 12.2 为何「永远是 Python 默认标」

1. **图标缓存**：装过旧版/旧快捷方式后，桌面仍显示缓存（常见黄蓝 Python 标）  
2. **快捷方式未绑独立 ico**：仅依赖 exe 内嵌资源时，Explorer 有时不更新  
3. **ICO 只有 256 单尺寸**：小尺寸槽位缺失时，部分场景缩放/回落异常（应含 16/32/48/256 等）  
4. **用户未重装新包**：仍在用旧 Setup 或旧桌面 `.lnk`

### 12.3 用户侧操作清单（写进发行说明亦可）

1. 结束所有 `Peel.exe`  
2. 卸载旧 Peel；**删除桌面旧快捷方式**  
3. 运行**最新** `Peel-Setup-*.exe`，勾选「创建桌面快捷方式」  
4. 确认安装目录存在 `Peel.exe` 与 **`peel.ico`**  
5. 若仍是旧图标，**清 Windows 图标缓存**后刷新桌面（管理员 PowerShell）：

```powershell
taskkill /f /im explorer.exe
Remove-Item "$env:LOCALAPPDATA\IconCache.db" -Force -ErrorAction SilentlyContinue
Remove-Item "$env:LOCALAPPDATA\Microsoft\Windows\Explorer\iconcache*" -Force -ErrorAction SilentlyContinue
Start-Process explorer.exe
```

必要时注销或重启一次。

### 12.4 开发侧自检

```text
# 从 exe 抽图标应能看到产品图（非 Python 标）
# 安装目录 {app}\peel.ico 存在
# 右键桌面快捷方式 → 属性 → 更改图标 → 应列出产品图
```

### 12.5 与「选安装路径」安装包的关系

- Inno：`DisableDirPage=no`，用户可选目录  
- 默认任务「桌面图标」建议 `Flags: checkedonce`（默认勾选一次）  
- 大体积 onedir 用 `Compression=lzma2`；排除 `*.part` 半成品模型  

---

## 13. 注意事项：模型下载与镜像（产品话术）

- 模型官方 URL 在 **GitHub Releases**（rembg）；应用内 **镜像优先、直连兜底**  
- **不能保证**所有无加速器用户都「秒下」；第三方镜像可能挂  
- 长期可控方案：自建 **OSS + CDN**；Gitee 仅适合过渡，不宜当大文件主站  
- 详见代码 `app/engines/local_rembg.py` 中 `_mirror_urls`

---

## 11. 最短记忆（贴在显示器上）

1. **永远 `collect_all` 重型原生栈，禁止半截 numpy**  
2. **永远整包分发 `dist\Peel\`，禁止只拷 exe**  
3. **rembg sessions 用我们的防御覆盖**  
4. **打完包：检查 multiarray.py + 真机拖一张图 + 引擎就绪**  
5. **测 spawn：准备中→就绪；杀 worker 应自愈**  
6. **出问题：console=True 看真堆栈，别只看 UI 那一行 cannot import remove**

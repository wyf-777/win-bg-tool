# Peel Rust + TypeScript

这是 `win-bg-tool` 的 Rust + TypeScript 重构版本，桌面层使用 Tauri 2。

## 运行

```powershell
npm install
npm run tauri dev
```

前端单独开发预览：

```powershell
npm run dev
```

## 构建

```powershell
npm run tauri build
```

`src-tauri/target/release/peel.exe` 是不带安装器的可执行文件；完整安装包由 Tauri 的 Windows bundle 生成。

## 目录职责

- `src/`：TypeScript 界面、队列交互、设置页和蒙版编辑画布。
- `src-tauri/src/image_engine.rs`：ONNX Runtime、U²-Net 预处理和透明结果生成。
- `src-tauri/src/main.rs`：Tauri commands、后台串行队列、设置和事件桥接。
- `src-tauri/src/mask.rs`：套索/画笔选择、擦除/恢复/保留和撤销重做数据。
- `src-tauri/src/export.rs`：PNG、WebP、JPEG、BMP、TIFF 导出。
- `src-tauri/src/watch.rs`：热文件夹轮询、清单、递归目录和失败重试。
- `models/u2netp.onnx`：随项目提供的轻量模型，首次启动可离线处理。

用户导入的其他 ONNX 模型放在运行时数据目录的 `models/` 中；设置页的“导入 ONNX 模型”会自动复制并登记模型。

## 验证

```powershell
npm run build
cd src-tauri
cargo fmt --all -- --check
cargo test
cargo check
```

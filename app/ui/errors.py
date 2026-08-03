from __future__ import annotations

import re


def friendly_error(exc: BaseException | str) -> str:
    """Map raw exceptions to short Chinese messages for the UI."""
    raw = str(exc).strip() if not isinstance(exc, BaseException) else f"{type(exc).__name__}: {exc}"
    text = str(exc)
    lower = text.lower()

    rules: list[tuple[str, str]] = [
        (r"filenotfound|找不到图片|no such file", "找不到图片文件，可能已被移动或删除。"),
        (r"permission|access is denied|拒绝访问", "没有权限读写该文件，请换路径或检查权限。"),
        (r"cannot identify image|unidentified image|truncated file", "无法识别为图片，请换一张 jpg/png/webp。"),
        (r"memory|out of memory|oom", "内存不足。请关掉其它程序，或换一张更小的图。"),
        (r"onnxruntime|ort\.|cuda|cudnn", "本机推理组件异常。请使用普通模式重试（设置中可关闭「更快处理」）。"),
        (r"cannot import name ['\"]remove['\"]|rembg|numpy\.core\.multiarray|pymatting|安装包依赖不完整|打包环境缺少", "去背景引擎加载失败。请使用完整打包的 Peel 目录（勿只复制 exe），或重新运行 scripts\\build_exe.bat。"),
        (r"download|urlopen|connection|timed out|network|http", "模型下载或网络失败。首次使用需联网下载模型到 models/ 目录。"),
        (r"无法加载 rembg 模型|new_session", "无法加载本机模型。请确认 models/ 可写，且首次已联网下载模型。"),
        (r"clipboard|剪贴板", "剪贴板里没有可用图片。"),
        (r"disk|no space|not enough space", "磁盘空间不足，无法保存结果。"),
    ]
    for pattern, msg in rules:
        if re.search(pattern, lower) or re.search(pattern, text, re.I):
            # keep a short technical hint for power users
            short = text.strip().replace("\n", " ")
            if len(short) > 120:
                short = short[:117] + "…"
            return f"{msg}\n（详情：{short}）"

    short = text.strip().replace("\n", " ")
    if len(short) > 160:
        short = short[:157] + "…"
    if not short:
        return "处理失败，请换一张图重试。"
    return f"处理失败：{short}"

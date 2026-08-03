# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Peel (win-bg-tool)
# Default package ships U²-Net 轻量 (u2netp.onnx).
#
# Full packaging guide / pitfalls / checklist:
#   docs/packaging.md
#
# Critical packaging note:
# rembg.bg imports numpy / cv2 / pymatting / scipy at module import time.
# Partial on-disk numpy (only *.pyd in numpy/core) shadows PYZ pure modules and
# breaks `from rembg import remove` with:
#   cannot import name 'remove' from 'rembg'
# Fix: collect_all for every heavy native stack so pure + binary files stay together.

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None
root = Path(SPECPATH)


def _collect(name: str):
    try:
        return collect_all(name)
    except Exception:
        return [], [], []


# Full package trees (datas + binaries + hiddenimports)
# Incomplete on-disk packages (only .pyd fragments) shadow PYZ pure modules and
# break imports — always collect_all for the native stacks rembg pulls in.
rembg_datas, rembg_binaries, rembg_hidden = _collect("rembg")
ort_datas, ort_binaries, ort_hidden = _collect("onnxruntime")
pil_datas, pil_binaries, pil_hidden = _collect("PIL")
numpy_datas, numpy_binaries, numpy_hidden = _collect("numpy")
cv2_datas, cv2_binaries, cv2_hidden = _collect("cv2")
pymatting_datas, pymatting_binaries, pymatting_hidden = _collect("pymatting")
scipy_datas, scipy_binaries, scipy_hidden = _collect("scipy")
numba_datas, numba_binaries, numba_hidden = _collect("numba")
llvmlite_datas, llvmlite_binaries, llvmlite_hidden = _collect("llvmlite")
# rembg.sessions.sam imports jsonschema at package import time
jsonschema_datas, jsonschema_binaries, jsonschema_hidden = _collect("jsonschema")
jsonschema_spec_datas, jsonschema_spec_binaries, jsonschema_spec_hidden = _collect(
    "jsonschema_specifications"
)
referencing_datas, referencing_binaries, referencing_hidden = _collect("referencing")
rpds_datas, rpds_binaries, rpds_hidden = _collect("rpds")
attrs_datas, attrs_binaries, attrs_hidden = _collect("attrs")
pooch_datas = collect_data_files("pooch")

# Ship lightweight model into the bundle (also copied next to exe via COLLECT)
u2netp = root / "models" / "u2netp.onnx"
extra_datas = []
if u2netp.is_file():
    extra_datas.append((str(u2netp), "models"))

# Override rembg.sessions so optional backends (SAM/jsonschema) cannot break import
sessions_override = root / "packaging" / "rembg_sessions" / "__init__.py"
if sessions_override.is_file():
    extra_datas.append((str(sessions_override), "rembg/sessions"))

hidden = set(
    rembg_hidden
    + ort_hidden
    + pil_hidden
    + numpy_hidden
    + cv2_hidden
    + pymatting_hidden
    + scipy_hidden
    + numba_hidden
    + llvmlite_hidden
    + jsonschema_hidden
    + jsonschema_spec_hidden
    + referencing_hidden
    + rpds_hidden
    + attrs_hidden
    + [
        "app",
        "app.main",
        "app.runtime_paths",
        "app.engines.local_rembg",
        "app.engines.models_catalog",
        "app.engines.runtime_accel",
        "app.ui.main_window",
        "app.ui.settings_dialog",
        "app.services.folder_watch",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "rembg",
        "rembg.bg",
        "rembg.session_factory",
        "rembg.sessions",
        "rembg.sessions.u2netp",
        "rembg.sessions.u2net",
        "rembg.sessions.base",
        "onnxruntime",
        "pooch",
        "pymatting",
        "pymatting.alpha.estimate_alpha_cf",
        "pymatting.foreground.estimate_foreground_ml",
        "pymatting.util.util",
        "scipy.ndimage",
        "cv2",
        "numpy",
        "numpy.core",
        "numpy.core.multiarray",
        "numpy.core._multiarray_umath",
        "numba",
        "numba.njit",
        "llvmlite",
        "jsonschema",
        "jsonschema_specifications",
        "referencing",
        "rpds",
        "rpds.rpds",
        "attrs",
        "attr",
    ]
)
# Pull rembg session submodules so model switch works offline in the package
try:
    hidden.update(collect_submodules("rembg.sessions"))
except Exception:
    pass
try:
    hidden.update(collect_submodules("pymatting"))
except Exception:
    pass

a = Analysis(
    [str(root / "app" / "main.py")],
    pathex=[str(root)],
    binaries=(
        rembg_binaries
        + ort_binaries
        + pil_binaries
        + numpy_binaries
        + cv2_binaries
        + pymatting_binaries
        + scipy_binaries
        + numba_binaries
        + llvmlite_binaries
        + jsonschema_binaries
        + jsonschema_spec_binaries
        + referencing_binaries
        + rpds_binaries
        + attrs_binaries
    ),
    datas=(
        rembg_datas
        + ort_datas
        + pil_datas
        + numpy_datas
        + cv2_datas
        + pymatting_datas
        + scipy_datas
        + numba_datas
        + llvmlite_datas
        + jsonschema_datas
        + jsonschema_spec_datas
        + referencing_datas
        + rpds_datas
        + attrs_datas
        + pooch_datas
        + extra_datas
    ),
    hiddenimports=list(hidden),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "notebook"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Prefer our defensive sessions __init__ over the copy from collect_all("rembg")
_override_src = str((root / "packaging" / "rembg_sessions" / "__init__.py").resolve()).lower()
_filtered = []
_seen_sessions_init = False
for entry in a.datas:
    # datas entries: (dest_name, src_path, typecode) after Analysis
    dest = str(entry[0]).replace("\\", "/").lower()
    src = str(entry[1]).replace("\\", "/").lower() if len(entry) > 1 else ""
    if dest.endswith("rembg/sessions/__init__.py") or dest == "rembg/sessions/__init__.py":
        if "packaging/rembg_sessions" in src or src.endswith("packaging/rembg_sessions/__init__.py"):
            _filtered.append(entry)
            _seen_sessions_init = True
        # drop upstream rembg sessions __init__
        continue
    _filtered.append(entry)
a.datas = _filtered
if not _seen_sessions_init and sessions_override.is_file():
    a.datas.append(
        (
            "rembg/sessions/__init__.py",
            str(sessions_override.resolve()),
            "DATA",
        )
    )

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Peel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Peel",
)

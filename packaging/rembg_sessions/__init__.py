"""Peel packaging override for rembg.sessions.

Upstream rembg imports every session (including SAM → jsonschema) at package
import time. One missing optional dependency then breaks `from rembg import remove`
entirely. Register each session defensively so Peel still works with u2netp etc.
"""
from __future__ import annotations

from typing import Dict

from .base import BaseSession

sessions: Dict[str, type[BaseSession]] = {}


def _register(import_path: str, attr: str) -> None:
    try:
        module = __import__(import_path, fromlist=[attr])
        cls = getattr(module, attr)
        sessions[cls.name()] = cls
    except Exception:
        # Optional model backend missing in this install / frozen build.
        pass


# Keep order close to upstream; failures are skipped.
_register("rembg.sessions.birefnet_general", "BiRefNetSessionGeneral")
_register("rembg.sessions.birefnet_general_lite", "BiRefNetSessionGeneralLite")
_register("rembg.sessions.birefnet_portrait", "BiRefNetSessionPortrait")
_register("rembg.sessions.birefnet_dis", "BiRefNetSessionDIS")
_register("rembg.sessions.birefnet_hrsod", "BiRefNetSessionHRSOD")
_register("rembg.sessions.birefnet_cod", "BiRefNetSessionCOD")
_register("rembg.sessions.birefnet_massive", "BiRefNetSessionMassive")
_register("rembg.sessions.dis_anime", "DisSession")
_register("rembg.sessions.dis_custom", "DisCustomSession")
_register("rembg.sessions.dis_general_use", "DisSession")
_register("rembg.sessions.sam", "SamSession")
_register("rembg.sessions.silueta", "SiluetaSession")
_register("rembg.sessions.u2net_cloth_seg", "Unet2ClothSession")
_register("rembg.sessions.u2net_custom", "U2netCustomSession")
_register("rembg.sessions.u2net_human_seg", "U2netHumanSegSession")
_register("rembg.sessions.u2net", "U2netSession")
_register("rembg.sessions.u2netp", "U2netpSession")
_register("rembg.sessions.bria_rmbg", "BriaRmBgSession")
_register("rembg.sessions.ben_custom", "BenCustomSession")

# Absolute minimum for Peel packaged default
if "u2netp" not in sessions:
    from .u2netp import U2netpSession

    sessions[U2netpSession.name()] = U2netpSession
if "u2net" not in sessions:
    try:
        from .u2net import U2netSession

        sessions[U2netSession.name()] = U2netSession
    except Exception:
        pass

sessions_names = list(sessions.keys())
sessions_class = list(sessions.values())

"""Smoke-test local rembg engine without UI."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw

from app.engines.local_rembg import LocalRembgEngine


def main() -> int:
    sample = ROOT / "models" / "_smoke_input.png"
    sample.parent.mkdir(parents=True, exist_ok=True)
    # simple synthetic image: orange circle on blue bg
    img = Image.new("RGB", (256, 256), (40, 100, 200))
    draw = ImageDraw.Draw(img)
    draw.ellipse((48, 48, 208, 208), fill=(230, 120, 40))
    img.save(sample)

    engine = LocalRembgEngine()
    print("warmup…", flush=True)
    engine.warmup()
    print("model:", engine.model_name, flush=True)
    print("remove…", flush=True)
    result = engine.remove(sample)
    out = ROOT / "models" / "_smoke_output.png"
    result.image.save(out)
    print("saved", out, "size", result.image.size, "mode", result.image.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

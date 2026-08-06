from pathlib import Path
import re

p = Path(r"D:\tools\Python\Lib\site-packages\rembg\sessions")
files = {
    "isnet-general-use": "dis_general_use.py",
    "u2net": "u2net.py",
    "u2netp": "u2netp.py",
    "silueta": "silueta.py",
    "u2net_human_seg": "u2net_human_seg.py",
    "isnet-anime": "dis_anime.py",
    "u2net_cloth_seg": "u2net_cloth_seg.py",
    "birefnet-general": "birefnet_general.py",
    "birefnet-general-lite": "birefnet_general_lite.py",
    "birefnet-portrait": "birefnet_portrait.py",
    "birefnet-dis": "birefnet_dis.py",
    "birefnet-hrsod": "birefnet_hrsod.py",
    "birefnet-cod": "birefnet_cod.py",
    "birefnet-massive": "birefnet_massive.py",
    "bria-rmbg": "bria_rmbg.py",
}
for mid, fn in files.items():
    text = (p / fn).read_text(encoding="utf-8", errors="replace")
    urls = re.findall(r"https?://[^\s\"'\\]+", text)
    seen = set()
    u2 = []
    for u in urls:
        u = u.rstrip("),\\'\"")
        if u not in seen:
            seen.add(u)
            u2.append(u)
    print("===", mid)
    for u in u2:
        print(" ", u)

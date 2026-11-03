#!/usr/bin/env python3
"""Reduce image and background-video transfer size without changing project layout."""
from __future__ import annotations
from pathlib import Path
from io import BytesIO
import json
import re
import shutil
import subprocess
import tempfile
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO = ROOT / "Portfolio"
INDEX = ROOT / "index.html"
THUMBS = ROOT / "Index" / "thumbs"

def make_thumb(source: Path, target: Path) -> None:
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        image.thumbnail((760, 600), Image.Resampling.LANCZOS)
        out = BytesIO()
        image.save(out, "JPEG", quality=82, optimize=True, progressive=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(out.getvalue())
        print(f"THUMB {target.relative_to(ROOT)} {len(out.getvalue()) / 1024:.0f} KiB")

def optimize_photo(source: Path) -> None:
    before = source.stat().st_size
    if before < 250_000:
        return
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        if max(image.size) > 2200:
            image.thumbnail((2200, 2200), Image.Resampling.LANCZOS)
        out = BytesIO()
        image.save(out, "JPEG", quality=84, optimize=True, progressive=True)
    after = len(out.getvalue())
    if after < before * 0.88:
        source.write_bytes(out.getvalue())
        print(f"IMAGE {source.relative_to(ROOT)} {before/1e6:.2f} MB -> {after/1e6:.2f} MB")

def optimize_hero() -> None:
    original = ROOT / "Index" / "hero.mp4"
    if not original.exists() or not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("SKIP HERO: video or ffmpeg missing")
        return
    meta = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", str(original)
    ]).decode())
    stream = meta["streams"][0]
    width, height = int(stream["width"]), int(stream["height"])
    target_w = min(width, 1600)
    target_w -= target_w % 2
    target_h = max(2, round(height * target_w / width / 2) * 2)
    temp = original.with_name("hero-optimized.mp4")
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(original), "-an", "-vf", f"scale={target_w}:{target_h}",
            "-r", "30", "-c:v", "libx264", "-preset", "fast",
            "-crf", "26", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(temp)]
    try:
        subprocess.run(args, check=True, timeout=540)
        before, after = original.stat().st_size, temp.stat().st_size
        if after < before * 0.90:
            temp.replace(original)
            print(f"HERO {width}x{height} -> {target_w}x{target_h}; {before/1e6:.2f} MB -> {after/1e6:.2f} MB")
        else:
            temp.unlink()
            print(f"HERO unchanged ({before/1e6:.2f} MB; proposed {after/1e6:.2f} MB)")
    except Exception as error:
        print(f"HERO compression skipped due to {error}")
        temp.unlink(missing_ok=True)

def main() -> None:
    index_text = INDEX.read_text(encoding="utf-8")
    names = set(re.findall(r'Index/thumbs/([a-zA-Z0-9-]+\.jpg)', index_text))
    available = {p.name: p for p in PORTFOLIO.glob("*/*.jpg")}
    if len(names) != 15:
        raise RuntimeError(f"Expected 15 homepage thumbnails, got {len(names)}")
    for filename in sorted(names):
        if filename not in available:
            raise RuntimeError("Missing original thumbnail: " + filename)
        make_thumb(available[filename], THUMBS / filename)
    for photo in sorted(PORTFOLIO.glob("*/*.jpg")):
        optimize_photo(photo)
    optimize_hero()

if __name__ == "__main__":
    main()

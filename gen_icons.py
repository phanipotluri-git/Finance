#!/usr/bin/env python3
"""
Run this ONCE locally to generate icon-192.png and icon-512.png.
Requires: pip install Pillow

Usage:
    python scripts/gen_icons.py

Then commit both icon-*.png files to your repo root.
"""
import sys
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Install Pillow first:  pip install Pillow")
    sys.exit(1)

def make_icon(size: int, path: str):
    img  = Image.new("RGBA", (size, size), "#0a0c0f")
    draw = ImageDraw.Draw(img)

    # Background circle
    pad = size * 0.06
    draw.ellipse([pad, pad, size-pad, size-pad], fill="#0f1318", outline="#f5a623", width=max(2, size//60))

    # "R" lettermark in amber — scale with size
    text = "R"
    font_size = int(size * 0.52)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf", font_size)
    except:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    x = (size - tw) / 2 - bbox[0]
    y = (size - th) / 2 - bbox[1] - size*0.03
    draw.text((x, y), text, fill="#f5a623", font=font)

    # Small dot (live indicator aesthetic)
    dot_r = size * 0.07
    dot_x = size * 0.72
    dot_y = size * 0.25
    draw.ellipse([dot_x-dot_r, dot_y-dot_r, dot_x+dot_r, dot_y+dot_r], fill="#00d084")

    img.save(path, "PNG")
    print(f"✓ {path} ({size}×{size})")

if __name__ == "__main__":
    make_icon(192, "icon-192.png")
    make_icon(512, "icon-512.png")
    print("\nCommit both files to your repo root and push.")

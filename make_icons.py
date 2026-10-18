# -*- coding: utf-8 -*-
"""生成 App 图标（192/512），用 bundled Python 的 Pillow。"""
import os

from PIL import Image, ImageDraw, ImageFont

base = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(base, "static")
os.makedirs(static_dir, exist_ok=True)


def make_icon(size, path):
    img = Image.new("RGB", (size, size), (79, 124, 255))  # 蓝底
    d = ImageDraw.Draw(img)
    # 顶部到中部做一点渐变
    for y in range(size // 2):
        t = y / (size // 2)
        r = int(79 + (111 - 79) * t)
        g = int(124 + (92 - 124) * t)
        b = 255
        d.line([(0, y), (size, y)], fill=(r, g, b))
    try:
        font = ImageFont.truetype("arialbd.ttf", int(size * 0.3))
    except Exception:
        font = ImageFont.load_default()
    text = "MP3"
    bbox = d.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    d.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]), text, fill="white", font=font)
    img.save(path)
    print("saved", path)


make_icon(512, os.path.join(static_dir, "icon-512.png"))
make_icon(192, os.path.join(static_dir, "icon-192.png"))

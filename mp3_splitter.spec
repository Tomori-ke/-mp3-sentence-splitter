# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（文件夹模式，启动无需解压）。运行：python -m PyInstaller mp3_splitter.spec --noconfirm"""
import os

from PyInstaller.utils.hooks import collect_all

# 1) 定位 ffmpeg（构建机上来自 imageio-ffmpeg，仅用于把二进制打进 exe）
def find_ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

ffmpeg = find_ffmpeg()
binaries = []
if ffmpeg and os.path.isfile(ffmpeg):
    binaries.append((ffmpeg, "."))

# 2) 网页模板 + PWA 静态资源（manifest / 图标 / service worker）
datas = [("templates", "templates"), ("static", "static")]

# 2.1) 内置 base 模型（只打包 snapshots 里的模型文件，不含 trees/refs 等 HF 元数据）
_model_snapshots = os.path.join(
    os.getcwd(),
    "data", "models", "models--Systran--faster-whisper-base", "snapshots",
)
if os.path.isdir(_model_snapshots):
    datas.append((_model_snapshots, "models/models--Systran--faster-whisper-base/snapshots"))

# 3) 收集第三方库的二进制与数据文件
#    onnxruntime 仅用于 VAD（本软件 vad_filter=False），不打包以减小体积
hiddenimports = []
for pkg in [
    "ctranslate2", "av", "tokenizers", "faster_whisper",
    "huggingface_hub", "tqdm", "hf_xet",
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pandas", "IPython", "jupyter", "PyQt5", "PySide6",
              "notebook", "onnxruntime", "scipy", "PIL", "Pillow", "setuptools"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Mp3SentenceSplitter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # 显示控制台窗口，方便看到状态和错误
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Mp3SentenceSplitter",
)

# -*- coding: utf-8 -*-
"""把当前构建（dist_new/Mp3SentenceSplitter）打包成 zip，排除运行时 data 目录。"""
import os
import zipfile

base = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(base, "dist_new", "Mp3SentenceSplitter")
dst = os.path.join(base, "dist_new", "Mp3SentenceSplitter.zip")

if os.path.exists(dst):
    os.remove(dst)

with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for root, dirs, files in os.walk(src):
        # 跳过运行时产生的 data 目录（上传/输出/日志）
        dirs[:] = [d for d in dirs if d != "data"]
        for f in files:
            p = os.path.join(root, f)
            arc = os.path.relpath(p, os.path.dirname(src))
            z.write(p, arc)

print("zip done:", dst, os.path.getsize(dst))

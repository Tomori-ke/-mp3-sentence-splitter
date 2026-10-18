# -*- coding: utf-8 -*-
"""打包脚本：在项目目录下执行  python build_exe.py  """
import subprocess
import sys

cmd = [sys.executable, "-m", "PyInstaller", "mp3_splitter.spec", "--noconfirm", "--clean"]
print("运行:", " ".join(cmd))
raise SystemExit(subprocess.call(cmd))

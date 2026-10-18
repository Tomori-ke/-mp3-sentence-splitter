# -*- coding: utf-8 -*-
"""
app.py — 本地网页服务
  提供网页界面、上传音频、后台识别切分、下载结果等功能。
"""
from __future__ import annotations

import os
import sys
import shutil
import socket
import threading
import traceback
import uuid
import webbrowser
import zipfile
from datetime import datetime

from flask import Flask, jsonify, render_template, request, send_file, send_from_directory

import segmenter

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1GB

# 线程安全的任务表
JOBS = {}
JOBS_LOCK = threading.Lock()


def get_base_dir() -> str:
    """数据目录：优先放在 exe 自己文件夹里（便携、可写），否则退回用户目录。"""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "data")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


BASE_DIR = get_base_dir()
UPLOAD_ROOT = os.path.join(BASE_DIR, "uploads")
OUTPUT_ROOT = os.path.join(BASE_DIR, "outputs")
for _d in (UPLOAD_ROOT, OUTPUT_ROOT):
    try:
        os.makedirs(_d, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass


def _log(msg: str) -> None:
    try:
        log_dir = BASE_DIR
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "app.log"), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except Exception:
        pass


def _run_job(job_id: str, audio_path: str, language: str, model_name: str) -> None:
    out_dir = os.path.join(OUTPUT_ROOT, job_id)
    os.makedirs(out_dir, exist_ok=True)

    def progress(stage, pct, msg):
        with JOBS_LOCK:
            j = JOBS.get(job_id)
            if j is not None:
                j["stage"] = stage
                j["progress"] = pct
                j["message"] = msg

    try:
        res = segmenter.transcribe_and_split(
            audio_path,
            out_dir,
            language=language,
            model_name=model_name,
            progress=progress,
        )
        with JOBS_LOCK:
            JOBS[job_id]["state"] = "done"
            JOBS[job_id]["result"] = res
            JOBS[job_id]["message"] = "完成"
    except Exception as e:  # noqa: BLE001
        _log(traceback.format_exc())
        with JOBS_LOCK:
            JOBS[job_id]["state"] = "error"
            JOBS[job_id]["message"] = str(e)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/segment", methods=["POST"])
def segment():
    f = request.files.get("file")
    if f is None or f.filename == "":
        return jsonify({"error": "没有收到音频文件"}), 400

    job_id = uuid.uuid4().hex[:12]
    job_dir = os.path.join(UPLOAD_ROOT, job_id)
    os.makedirs(job_dir, exist_ok=True)

    ext = os.path.splitext(f.filename)[1].lower() or ".mp3"
    save_path = os.path.join(job_dir, "input" + ext)
    f.save(save_path)

    language = request.form.get("language", "en")
    model_name = request.form.get("model", "base")

    with JOBS_LOCK:
        JOBS[job_id] = {
            "state": "queued",
            "progress": 0,
            "stage": "init",
            "message": "排队中…",
            "result": None,
        }

    t = threading.Thread(target=_run_job, args=(job_id, save_path, language, model_name), daemon=True)
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    j = JOBS.get(job_id)
    if j is None:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(
        {
            "state": j["state"],
            "progress": j["progress"],
            "stage": j["stage"],
            "message": j["message"],
            "result": j["result"],
        }
    )


@app.route("/audio/<job_id>/<path:filename>")
def audio(job_id, filename):
    out_dir = os.path.join(OUTPUT_ROOT, job_id)
    return send_from_directory(out_dir, filename)


@app.route("/download/<job_id>")
def download(job_id):
    out_dir = os.path.join(OUTPUT_ROOT, job_id)
    if not os.path.isdir(out_dir):
        return jsonify({"error": "没有可下载的结果"}), 404
    mp3s = sorted(fn for fn in os.listdir(out_dir) if fn.lower().endswith(".mp3"))
    if not mp3s:
        return jsonify({"error": "没有可下载的结果"}), 404
    zpath = os.path.join(out_dir, "sentences.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in mp3s:
            z.write(os.path.join(out_dir, fn), fn)
    return send_file(zpath, as_attachment=True, download_name=f"sentences_{job_id}.zip")


@app.route("/open/<job_id>", methods=["POST"])
def open_folder(job_id):
    out_dir = os.path.join(OUTPUT_ROOT, job_id)
    opened = False
    if os.path.isdir(out_dir) and sys.platform == "win32":
        try:
            os.startfile(out_dir)  # type: ignore[attr-defined]
            opened = True
        except Exception as e:  # noqa: BLE001
            _log(f"open folder failed: {e}")
    return jsonify({"ok": True, "path": out_dir, "opened": opened})


@app.route("/shutdown", methods=["POST"])
def shutdown():
    _log("收到退出请求")
    threading.Timer(0.5, lambda: os._exit(0)).start()  # noqa: SLF001
    return jsonify({"ok": True})


def find_ffmpeg():
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.dirname(sys.executable))
        candidates.append(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    else:
        candidates.append(os.path.dirname(os.path.abspath(__file__)))

    for d in candidates:
        try:
            for name in os.listdir(d):
                if name.lower().startswith("ffmpeg") and name.lower().endswith(".exe"):
                    return os.path.join(d, name)
        except OSError:
            pass

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        pass

    return shutil.which("ffmpeg")


FIXED_PORT = 8765


def find_free_port() -> int:
    """优先使用固定端口，方便用户收藏固定网址；被占用时退回随机端口。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", FIXED_PORT))
        return FIXED_PORT
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


def get_lan_ip() -> str:
    """获取本机局域网 IP（用于局域网内其他人访问）。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:  # noqa: BLE001
        return ""


def _msgbox(title: str, text: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def _global_excepthook(exc_type, exc_value, tb) -> None:
    """未捕获异常的兜底：写日志 + 弹窗提示。"""
    try:
        _log("".join(traceback.format_exception(exc_type, exc_value, tb)))
    except Exception:  # noqa: BLE001
        pass
    try:
        _msgbox("发生错误", str(exc_value))
    except Exception:  # noqa: BLE001
        pass
    sys.__excepthook__(exc_type, exc_value, tb)


sys.excepthook = _global_excepthook


def main() -> int:
    print("=" * 56)
    print("  MP3 智能分段工具")
    print("  正在启动，请稍候…")
    print("=" * 56)

    # 减少控制台里 flask 的请求日志噪音
    import logging

    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    ff = find_ffmpeg()
    if not ff:
        _log("未找到 ffmpeg，无法切分音频")
        print("错误：未找到 ffmpeg，无法切分音频。")
        _msgbox("错误", "未找到 ffmpeg，无法切分音频。请重新安装本软件。")
        return 1
    segmenter.set_ffmpeg(ff)
    _log(f"ffmpeg: {ff}")

    host = "0.0.0.0"  # 监听所有网卡，方便局域网内其他设备访问
    port = find_free_port()
    url = f"http://127.0.0.1:{port}"
    _log(f"启动服务: {url}")

    lan_ip = get_lan_ip()

    print()
    print(f"  本机访问: {url}")
    if lan_ip:
        print(f"  局域网访问: http://{lan_ip}:{port}")
    print("  浏览器应已自动打开；如果没有，请手动打开上面的地址。")
    print()
    print("  关闭此窗口即可退出软件。")
    print()

    threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        app.run(host=host, port=port, threaded=True, debug=False, use_reloader=False)
    except Exception as e:  # noqa: BLE001
        _log(traceback.format_exc())
        print(f"启动失败: {e}")
        _msgbox("启动失败", str(e))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""
segmenter.py — 核心功能
  1) 用 faster-whisper 做本地离线语音识别（带词级时间戳）
  2) 把识别出的词按句末标点合并成句子
  3) 用 ffmpeg 把每个句子切成独立的 MP3 文件
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Callable, List, Optional

# 句末标点（英文为主，兼容中文标点）
_SENTENCE_END = ".!?。！？"

# 常见英文缩写，避免把 "Mr." / "Dr." 之类误判成句尾
_ABBREV = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "e.g", "i.e", "u.s", "u.k", "no", "fig", "dept", "approx", "a.m", "p.m",
}

_ffmpeg_path: Optional[str] = None


def set_ffmpeg(path: str) -> None:
    """设置 ffmpeg 可执行文件路径。"""
    global _ffmpeg_path
    _ffmpeg_path = path


def get_ffmpeg() -> Optional[str]:
    return _ffmpeg_path


@dataclass
class Sentence:
    index: int
    text: str
    start: float
    end: float


def _clean_text(text: str) -> str:
    """去掉标点前的多余空格，规范空白。"""
    t = re.sub(r"\s+([,.!?;:。，！？；：])", r"\1", text)
    return re.sub(r"\s+", " ", t).strip()


def _ends_sentence(word: str) -> bool:
    w = (word or "").strip()
    if not w:
        return False
    # 整词都是句末标点，如 "."、"?"、"..."、"!!"
    if all(ch in _SENTENCE_END for ch in w):
        return True
    if w[-1] in _SENTENCE_END:
        core = w.rstrip(_SENTENCE_END).strip().lower()
        if core in _ABBREV:
            return False
        # 单个大写字母 + 句点，通常是缩写首字母（U.S. 里的 S.）
        if len(core) == 1 and core.isalpha():
            return False
        return True
    return False


def _sanitize(text: str, max_len: int = 48) -> str:
    """把句子文字转成安全的文件名片段。"""
    t = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE)
    t = t.strip("_")
    if not t:
        t = "sentence"
    return t[:max_len]


def group_words_to_sentences(
    words: List[tuple],
    pre_pad: float = 0.08,
    post_pad: float = 0.30,
) -> List[Sentence]:
    """
    words: [(text, start, end), ...] 已按时间排序
    按句末标点把词合并成句子，返回句子列表。
    """
    sentences: List[Sentence] = []
    cur: List[tuple] = []

    for text, start, end in words:
        cur.append((text, start, end))
        if _ends_sentence(text):
            if cur:
                text_all = " ".join(w for w, _, _ in cur)
                s = max(0.0, cur[0][1] - pre_pad)
                e = cur[-1][2] + post_pad
                sentences.append(Sentence(0, _clean_text(text_all), s, e))
                cur = []

    # 结尾没有句末标点的尾巴
    if cur:
        text_all = " ".join(w for w, _, _ in cur)
        sentences.append(
            Sentence(0, _clean_text(text_all), max(0.0, cur[0][1] - pre_pad), cur[-1][2] + post_pad)
        )

    for i, s in enumerate(sentences, 1):
        s.index = i
    return sentences


def _word_count(text: str) -> int:
    return len(text.split())


def _merge_text(a: str, b: str) -> str:
    return f"{a} {b}".strip()


def merge_short_sentences(
    sentences: List[Sentence],
    min_words: int = 4,
) -> List[Sentence]:
    """把少于 min_words 个单词的句子就近合并到相邻句子。

    默认要求每段「大于 3 个单词」（即至少 4 个单词）。
    合并方向：看它跟哪边贴得更近（时间间隔更小），就近并入；边界处只能往一侧并。
    """
    if len(sentences) <= 1:
        return sentences

    def is_short(s: Sentence) -> bool:
        return _word_count(s.text) < min_words

    merged = list(sentences)
    for _ in range(len(merged) + 1):
        new_list: List[Sentence] = []
        changed = False
        i = 0
        n = len(merged)
        while i < n:
            s = merged[i]
            if not is_short(s):
                new_list.append(s)
                i += 1
                continue
            prev = new_list[-1] if new_list else None
            nxt = merged[i + 1] if i + 1 < n else None
            if prev is None and nxt is None:
                new_list.append(s)
                i += 1
                continue
            gap_prev = (s.start - prev.end) if prev else float("inf")
            gap_next = (nxt.start - s.end) if nxt else float("inf")
            if prev is not None and (nxt is None or gap_prev <= gap_next):
                # 并入前一句
                prev.text = _merge_text(prev.text, s.text)
                prev.end = max(prev.end, s.end)
                changed = True
                i += 1
            else:
                # 并入后一句
                nxt.text = _merge_text(s.text, nxt.text)
                nxt.start = min(nxt.start, s.start)
                changed = True
                new_list.append(nxt)
                i += 2
        merged = new_list
        if not changed:
            break

    for idx, s in enumerate(merged, 1):
        s.index = idx
    return merged


def get_data_root() -> str:
    """数据根目录（模型、缓存等）。"""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "data")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def get_model_dir() -> str:
    base = os.environ.get("MP3SPLIT_MODEL_DIR")
    if base:
        return base
    if getattr(sys, "frozen", False):
        # 1) 内置模型（_internal/models，随软件打包）
        meipass = getattr(sys, "_MEIPASS", "") or ""
        bundled = os.path.join(meipass, "models")
        if os.path.isdir(bundled):
            return bundled
        # 2) exe 同目录的 models（手动放置，也支持）
        local = os.path.join(os.path.dirname(sys.executable), "models")
        if os.path.isdir(local):
            return local
        # 3) 回退到 exe 旁 data/models（可写，用于后续下载）
        return os.path.join(os.path.dirname(sys.executable), "data", "models")
    return os.path.join(get_data_root(), "models")


def _setup_hf_env() -> None:
    """把 HuggingFace 缓存重定向到可写目录。

    必须在任何 huggingface_hub 导入之前执行（faster-whisper 导入时就会连带导入它）。
    """
    root = get_data_root()
    os.environ.setdefault("HF_HOME", os.path.join(root, "hf_cache"))
    os.environ.setdefault("HF_HUB_CACHE", os.path.join(root, "hf_cache", "hub"))


_setup_hf_env()


# 模型名 -> HuggingFace 仓库（与 faster-whisper 内部一致）
_MODEL_REPOS = {
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
}
_MODEL_FILES = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]


def _find_cached_model(model_name: str) -> Optional[str]:
    """若模型已下载到缓存目录，返回其 snapshot 路径，否则返回 None。"""
    model_dir = get_model_dir()
    if not os.path.isdir(model_dir):
        return None
    prefix = f"models--Systran--faster-whisper-{model_name}"
    for name in os.listdir(model_dir):
        if name.startswith(prefix):
            base = os.path.join(model_dir, name)
            for root, _dirs, files in os.walk(base):
                if "model.bin" in files:
                    return root
    return None


def _set_hf_mirror() -> None:
    """把 HuggingFace 下载端点切换到国内镜像（hf-mirror.com）。"""
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    try:
        import huggingface_hub.constants as c

        c.ENDPOINT = "https://hf-mirror.com"
        c.HUGGINGFACE_CO_URL_HOME = "https://hf-mirror.com/"
        c.HUGGINGFACE_CO_URL_TEMPLATE = "https://hf-mirror.com/{repo_id}/resolve/{revision}/{filename}"
    except Exception:
        pass


def _resolve_model(model_name: str, cb) -> str:
    """返回本地模型路径；不存在则下载（与 faster-whisper 相同的缓存布局）。"""
    cached = _find_cached_model(model_name)
    if cached:
        return cached

    repo = _MODEL_REPOS.get(model_name)
    if not repo:
        # 非标准名称：交给 faster-whisper 处理（当作本地路径或仓库 ID）
        return model_name

    cb("model", 0, "首次运行，正在下载模型（约 145MB），请耐心等待…")
    from huggingface_hub import snapshot_download

    kwargs = dict(repo_id=repo, cache_dir=get_model_dir(), allow_patterns=_MODEL_FILES)
    try:
        return snapshot_download(**kwargs)
    except Exception:
        cb("model", 0, "直连下载失败，正在切换国内镜像重试…")
        _set_hf_mirror()
        return snapshot_download(**kwargs)


def _slice_audio(ffmpeg: str, input_path: str, start_s: float, end_s: float, out_path: str) -> None:
    """用 ffmpeg 切出 [start_s, end_s) 一段并导出为 MP3。"""
    duration = max(0.05, end_s - start_s)
    cmd = [
        ffmpeg, "-y",
        "-ss", f"{start_s:.3f}",
        "-i", input_path,
        "-t", f"{duration:.3f}",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        out_path,
    ]
    with tempfile.TemporaryFile() as errf:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=errf)
        if r.returncode != 0:
            errf.seek(0)
            detail = errf.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"ffmpeg 切分失败: {detail[-400:]}")


def transcribe_and_split(
    audio_path: str,
    out_dir: str,
    language: str = "en",
    model_name: str = "base",
    pre_pad: float = 0.08,
    post_pad: float = 0.30,
    min_sentence_ms: int = 200,
    progress: Optional[Callable[[str, int, str], None]] = None,
) -> dict:
    """
    识别并切分音频。progress(stage, percent, message) 用于回传进度。
    返回 {results, language, duration, count}。
    """
    def cb(stage, pct, msg):
        if progress:
            try:
                progress(stage, pct, msg)
            except Exception:
                pass

    cb("model", 0, "正在加载 Whisper 模型…")
    from faster_whisper import WhisperModel

    model_path = _resolve_model(model_name, cb)
    model = WhisperModel(model_path, device="cpu", compute_type="int8")

    cb("transcribe", 10, "正在识别语音（视音频长度而定，请稍候）…")
    lang = None if language == "auto" else language
    segments, info = model.transcribe(
        audio_path,
        language=lang,
        word_timestamps=True,
        vad_filter=False,
        beam_size=5,
    )

    words: List[tuple] = []
    raw_segs = []
    for seg in segments:
        raw_segs.append(seg)
        ws = getattr(seg, "words", None)
        if ws:
            for w in ws:
                words.append((w.word.strip(), float(w.start), float(w.end)))

    detected_lang = getattr(info, "language", language) or language
    total_s = float(getattr(info, "duration", 0.0) or 0.0)
    cb("transcribe", 85, "识别完成，正在按句子切分音频…")

    sentences = group_words_to_sentences(words, pre_pad, post_pad)

    # 兜底：若全文没有句末标点，则按 whisper 自身的段落切分
    if len(sentences) <= 1 and len(raw_segs) > 1:
        sentences = []
        for seg in raw_segs:
            dur = float(seg.end) - float(seg.start)
            if dur <= 0:
                continue
            sentences.append(
                Sentence(0, _clean_text(seg.text), max(0.0, seg.start - pre_pad), seg.end + post_pad)
            )
        for i, s in enumerate(sentences, 1):
            s.index = i

    # 合并过短的句子（如单独的 "Yes."、"Yeah."），避免分段太碎
    sentences = merge_short_sentences(sentences)

    if total_s <= 0:
        total_s = max((s.end for s in sentences), default=0.0)

    cb("slice", 90, f"共识别出 {len(sentences)} 句，正在生成音频文件…")

    ffmpeg = _ffmpeg_path
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg，无法切分音频")
    os.makedirs(out_dir, exist_ok=True)

    min_s = min_sentence_ms / 1000.0
    results = []
    for s in sentences:
        start_s = max(0.0, s.start)
        end_s = min(total_s, s.end)
        if end_s - start_s < min_s:
            end_s = min(total_s, start_s + min_s)
        filename = f"{s.index:02d}_{_sanitize(s.text)}.mp3"
        _slice_audio(ffmpeg, audio_path, start_s, end_s, os.path.join(out_dir, filename))
        results.append(
            {
                "index": s.index,
                "text": s.text,
                "start": round(s.start, 3),
                "end": round(end_s, 3),
                "filename": filename,
            }
        )

    cb("done", 100, "完成！")
    return {
        "results": results,
        "language": detected_lang,
        "duration": round(total_s, 3),
        "count": len(results),
    }

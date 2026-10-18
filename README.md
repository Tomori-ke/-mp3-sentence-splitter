# MP3 智能分段工具（Mp3SentenceSplitter）

> A desktop tool that automatically splits an English conversation audio file into individual sentences (one MP3 per sentence), powered by offline Whisper.

一个 Windows 桌面工具：上传一段**英文对话音频**，自动识别出每一句话，并按句切分成独立的 MP3 文件。全程**本地离线运行**，无需联网、无需 API Key、完全免费。

例如一段 13 秒、4 句话的对话，会生成 4 个 MP3，每个文件对应一句话。

## 功能特点

- 🔒 **本地离线识别**：使用 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)（Whisper 的优化版），断网也能用
- 🧩 **按句切分**：词级时间戳 + 句末标点分组，自动合并过短的碎片（如单独的 "Yes."）
- 🎧 **网页界面**：上传 → 识别 → 逐句试听 / 打包下载 ZIP
- 📱 **PWA 支持**：手机浏览器可「添加到主屏幕」，像 App 一样使用
- 📦 **内置模型**：预打包 base 模型，解压即用、免下载

## 快速开始

### 方式一：下载现成软件（普通用户，推荐）

1. 到本仓库右侧 **Releases** 页面，下载 `Mp3SentenceSplitter.zip`
2. **解压整个压缩包**（不要只解压 exe）
3. 进入解压出来的 `Mp3SentenceSplitter` 文件夹，双击 `Mp3SentenceSplitter.exe`

> 首次双击若弹出「Windows 已保护你的电脑」→ 点「更多信息」→「仍要运行」。
> Windows 11 若开着「智能应用控制」需先关闭（设置 → Windows 安全中心 → 应用和浏览器控制 → 智能应用控制设置 → 关）。

### 方式二：从源码运行（开发者）

```bash
# 需要 Python 3.10 ~ 3.12
python -m venv .venv
.\.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python app.py                   # 自动打开浏览器
```

首次运行会自动下载模型（base 约 145MB），之后离线可用。

## 打包成 exe

```bash
.\.venv\Scripts\activate
pip install pyinstaller
python -m PyInstaller mp3_splitter.spec --noconfirm
python make_zip.py              # 把 dist_new/Mp3SentenceSplitter 打包成 zip
```

## 项目结构

```
app.py               Flask 后端：网页服务、上传、后台任务、下载
segmenter.py         核心：语音识别、按句合并、ffmpeg 切分
templates/           网页界面
static/              PWA 清单、图标、service worker
mp3_splitter.spec    PyInstaller 打包配置
requirements.txt     依赖清单
```

## 常见问题

**Q：识别语言是中文怎么办？** 界面里把「识别语言」选为「中文」或「自动检测」。

**Q：想更准？** 界面里换 `small` 或 `medium` 模型（体积更大、首次需下载）。

**Q：句子切分太碎 / 太粗？** 调整 `segmenter.py` 里 `merge_short_sentences` 的 `min_words` 参数。

## 许可证

[MIT](LICENSE)

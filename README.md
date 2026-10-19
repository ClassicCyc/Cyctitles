# Cyctitles

[![Tests](https://github.com/ClassicCyc/Cyctitles/actions/workflows/tests.yml/badge.svg)](https://github.com/ClassicCyc/Cyctitles/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/ClassicCyc/Cyctitles)](https://github.com/ClassicCyc/Cyctitles/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-0078D6.svg)](#requirements)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

Real-time **offline** subtitles **and dictation** for OBS Studio (and any Windows app).

Speak into your microphone (or translate what your PC is playing), and the result
appears as a styled subtitle overlay in OBS — or is typed straight into the focused
window. No cloud services, no API keys, no monthly cost: transcription and translation
run entirely on your PC after the models are downloaded once (on first use).

> Made by **ClassicCyc**. Specially for **CraftingVegeto**.

> **Quick links:**
> [Install](#install) ·
> [Requirements](#requirements) ·
> [Quick start](#quick-start-for-the-streamer) ·
> [Models](#models-storage--custom-models) ·
> [Building](#building-the-executable) ·
> [Troubleshooting](#troubleshooting)

## How it works

```
Audio (mic / loopback) → VAD (webrtcvad) → faster-whisper (GPU) → quickmt (CTranslate2) → OBS overlay  /  typing
```

- **Speech recognition:** [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
  (Whisper on CTranslate2). The model is auto-picked from your GPU.
- **Translation:** [quickmt](https://huggingface.co/quickmt) CTranslate2 models, fully
  local. Many language pairs ship in one format (EN↔RU, EN↔ZH, EN↔FR, EN↔DE, EN↔ES,
  EN↔JA, EN↔KO, EN↔IT, EN↔PL, EN↔PT, EN↔TR, EN↔AR, EN↔UK, EN↔CS …).
- **Outputs:**
  - **Overlay** — a local web server on `http://127.0.0.1:8765` that OBS renders as a
    transparent Browser Source (customisable font, opacity, line wrapping).
  - **Dictation** — the recognised (optionally translated) text is typed into whatever
    window is focused.
- Everything runs locally. Models download once on first use (when you press **Start**
  or open **Manage models…**), then it works offline.

## Highlights

- **Two output modes** — **Subtitles → OBS overlay**, or **Dictation → type into the
  focused window** (chat, notepad, browser…). Uncheck *Translate* to type the spoken
  language as-is, or keep it on to type the translation.
- **On-screen caption window** — a small frameless, always-on-top caption strip on your
  own screen (independent of OBS) — handy for video calls and conferences.
- **Text-to-speech** — optionally speak the translated text out loud through the system
  voice (selectable output).
- **Microphone, any output device, or both** — listen to your mic, capture the loopback
  of **any** output device (speakers, monitor, USB interface — no virtual cable needed),
  or **both at the same time** (e.g. your voice *and* the meeting audio).
- **Multiple languages & translation models** — pick a language pair and the model list
  is filtered to matching models (or shows *"Not found"* with everything if no exact
  pair exists). Download pairs you need from **Manage models…** (each shows its
  languages and size).
- **Performance control** — keep **Auto** (GPU preferred) or **Force CPU**, and choose
  a compute type (int8 / int8_float16 / float16).
- **Model manager** — lists every model with size, languages and disk usage; download
  or delete with one click. Missing models are offered for install when you press Start.
- **Choose where models are stored** — point the models folder at any drive
  (e.g. `%LOCALAPPDATA%\Cyctitles\models`) and optionally move what you already have.
- **Bring your own models** — open any on-disk CTranslate2 model folder (Whisper or
  translation) instead of the built-in ones.
- **System tray** — close the window and Cyctitles keeps running in the tray
  (right-click for Start/Stop, Mute, Show, Quit).
- **Live styling** — position (top/bottom), text colour, box colour, opacity, font size,
  max lines, and an optional smaller original line — all apply instantly in OBS.
  **Send test subtitle** previews the look without speaking.
- **Customisable mute hotkey** (default `Ctrl+Shift+S`) and **auto-start** on launch.
- **Status indicator** in the status bar (Idle / Loading / Listening / Muted / Error).
- **Tabbed Settings** — the main window keeps only the essentials; everything else lives
  in **Settings → Settings…** on the **Subtitles**, **Performance**, **Text processing**,
  **Speech** and **Behavior** tabs, applied instantly.
- **Text processing controls** — cap words per caption, split at sentence ends,
  capitalise, de-duplicate repeated phrases, drop too-short captions, and choose the
  dictation method (paste vs. type).
- **Download progress** — model downloads show a live progress bar with MB, percentage,
  speed and time remaining.
- **Built-in guide** — `Help → How to use Cyctitles…` walks through every feature.

## Install

Grab the latest files from the [**Releases**](https://github.com/ClassicCyc/Cyctitles/releases)
page. You normally download **just one file** — pick one of the three ways below.

### Way 1 — Installer (recommended)

1. Download **`Cyctitles-Setup-<version>.exe`**.
2. Run it and click through the wizard (Next → Install).
3. Leave the **“NVIDIA GPU support (CUDA)”** component checked if you have a GeForce/Quadro
   GPU — the wizard downloads the CUDA runtime automatically (~1.3 GB). Uncheck it for a
   smaller CPU-only install on AMD/Intel/other PCs.
4. Launch **Cyctitles** from the Start menu. Models download on first run.

### Way 2 — Installer + offline CUDA

If the CUDA download is blocked (firewall/VPN) or you want a single offline bundle:

1. Download **`Cyctitles-Setup-<version>.exe`** **and** **`cuda.zip`**.
2. Put **`cuda.zip` next to the installer** (same folder).
3. Run the installer, keep the CUDA component checked — it will detect the local
   `cuda.zip` and ask whether to use it (no internet needed).

### Way 3 — Portable (no install)

1. Download **`Cyctitles.exe`** (CPU-only single file) and run it from anywhere.
2. For NVIDIA GPU acceleration, also download **`cuda.zip`** and extract its `cuda`
   folder **next to `Cyctitles.exe`**. Without it, the app runs on CPU automatically.

> The app **never bundles the models** — they download once on first run into
> `%LOCALAPPDATA%\Cyctitles\models` (Whisper ≈ 300 MB–1.5 GB, translation ≈ 300–400 MB).

## Requirements

- Windows 10/11 (x64)
- NVIDIA GPU recommended (CUDA 12). Runs on CPU too, but slower.
- For best latency on RTX 40/50-series: a recent NVIDIA driver.

## Quick start (for the streamer)

1. Launch **Cyctitles** (from the Start menu, or by running `Cyctitles.exe`).
2. Pick your **microphone**, choose the **Spoken** and **Translate to** languages, and
   leave **Whisper: Auto**. The **Models** panel shows whether the needed models are
   already downloaded.
3. Press **Start**. If a model is missing, a dialog appears —
   *"Model is not downloaded. Install it?"* — listing its **size**, **folder** and
   **source** (Hugging Face). Click **Install** to download it once.
4. In OBS: **Sources → + → Browser**, paste the URL shown in the app
   (`http://127.0.0.1:8765`), set **1920×1080**, then **Fit to Screen**.
   `Overlay → How to add to OBS…` repeats these steps.
5. Talk. Subtitles appear. Press **Ctrl+Shift+S** to mute/unmute them.

Run out of space on `C:`? Open **Manage models… → Change folder…** and pick another
drive (e.g. `%LOCALAPPDATA%\Cyctitles\models`); choose **Yes** to move the models you already downloaded.

## Modes

| Mode | Where the text goes | Use for |
|---|---|---|
| **Subtitles → OBS overlay** | The browser source in OBS | Normal streaming |
| **Dictation → type into focused window** | The active text field | Chat, notes, anywhere you type |

In Dictation mode, **Translate before output** decides whether the spoken language is
typed as-is (off) or translated (on).

## Audio source

- **Microphone** — the default; transcribes what you say.
- **System output (loopback)** — transcribes what your PC is playing. Cyctitles captures
  the loopback of **any** output device you pick under **Output device** (speakers,
  monitor, USB interface, …) through the Windows WASAPI loopback API — no virtual audio
  cable required. If the system exposes no output device the option stays disabled.
- **Both (mic + system output)** — captures your microphone **and** the system output
  at the same time into one subtitle stream (e.g. your voice *and* the meeting audio).

## On-screen captions & speech (calls, conferences)

Besides the OBS overlay, Cyctitles can show captions directly on your screen and read
them out loud — useful when you are **not** streaming:

- **On-screen caption window** — a small frameless, always-on-top strip at the bottom of
  your screen. It is click-through (never steals focus) and auto-hides like the OBS
  overlay. Great for calls/conferences.
- **Text-to-speech** — the translated line is spoken through the Windows system voice
  (`System.Speech`). Adjust rate and volume in the config; it stops on mute/stop.

## Long sentences, long conversations

There is no fixed "one sentence" limit: the segmenter cuts a chunk when the speaker
**pauses** (~0.55 s of silence) and forces a cut on a long monologue every **8 s**
(keeping a small overlap so no word is lost). Each chunk is transcribed and translated
independently, so an endless monologue becomes a steady stream of subtitles. In the
overlay, long lines **wrap** and automatically **shrink** to fit **Max lines**.

## Models: storage & custom models

**Storage.** Models live in `%LOCALAPPDATA%\Cyctitles\models` by default. Use
**Manage models… → Models folder → Change folder…** to move them anywhere; if the old
folder already has models you are asked whether to move them (no re-download).

**Your own models.** In **Manage models… → Custom models** you can point at folders you
already have on disk:

- **Whisper** — a CTranslate2 Whisper folder containing `model.bin`.
- **Translation** — a CTranslate2 folder containing `model.bin` and either
  `src.spm.model` + `tgt.spm.model`, or a `joint.spm.model`.

A custom folder takes priority over the built-in model; **Clear** goes back to the
built-in one. An invalid folder is reported when you press **Start**.

## Development setup

Requires [uv](https://docs.astral.sh/uv/) (or plain Python 3.12 + pip).

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
# CUDA runtime libraries (for GPU inference)
uv pip install --python .venv\Scripts\python.exe nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-cuda-runtime-cu12 nvidia-cuda-nvrtc-cu12
```

Run from source:

```powershell
run_dev.bat
# or: .venv\Scripts\python.exe app.py
```

Run tests:

```powershell
.venv\Scripts\python.exe -m pytest tests -q
```

## Building the executable

**Single file with CUDA** (`-OneFile`) — everything bundled (~1.4 GB):

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1 -OneFile
```

**Single file, CPU-only** (`-Lite`) — small (~150 MB), used by the installer:

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1 -Lite
```

**Folder build (onedir)** — faster startup, includes CUDA:

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

Produces `dist\Cyctitles\Cyctitles.exe` (onefile) or `dist\Cyctitles\Cyctitles.exe`
inside the folder (onedir).

Models are **not** bundled — they download on first run into
`%LOCALAPPDATA%\Cyctitles\models`.

### Building the Windows installer (with optional CUDA)

The installer ships a small **CPU-only** build and (by default) downloads an
optional **CUDA pack** so NVIDIA users get GPU acceleration:

```powershell
# 1. CPU-only single-file build (fast, ~150 MB)
powershell -ExecutionPolicy Bypass -File build.ps1 -Lite

# 2. Pack the CUDA runtime (~1.3 GB) for download
powershell -ExecutionPolicy Bypass -File installer\make_cuda_pack.ps1
#    -> upload installer\Output\cuda.zip to a GitHub Release,
#       then set CudaPackUrl in installer\Cyctitles.iss

# 3. Compile the wizard (install Inno Setup first)
ISCC.exe installer\Cyctitles.iss
#    -> installer\Output\Cyctitles-Setup-<version>.exe
```

The installed app looks for CUDA DLLs in a `cuda\` folder next to `Cyctitles.exe`
(or in a bundled `nvidia` package) and automatically falls back to CPU when
they are absent.

## Configuration

Settings live in `%LOCALAPPDATA%\Cyctitles\config.json` and are editable in the app.
Logs go to `%LOCALAPPDATA%\Cyctitles\cyctitles.log`.

| Setting | Default | Notes |
|---|---|---|
| Spoken language | English | or **Auto-detect** |
| Translate to | Russian | any language with a downloaded translation model |
| Translation model | quickmt-en-ru | filtered by the chosen language pair; shows *Not found* if no exact pair |
| Translate before output | on | off → pass the spoken language through (dictation) |
| Input source | Microphone | **Microphone**, **System output (loopback)** or **Both (mic + system output)** |
| Output device | (default) | any speaker/interface whose loopback is captured |
| Output mode | Subtitles → OBS overlay | or **Dictation → type into focused window** |
| On-screen caption window | off | frameless always-on-top caption strip on your own screen (calls) |
| Text-to-speech | off | speak the translated text through the system voice |
| Performance mode | Auto (GPU preferred) | or **Force CPU** |
| Compute type | auto | int8 / int8_float16 / float16 (for GPU) |
| Whisper model | Auto | auto = large-v3-turbo (≥10 GB VRAM), medium (≥6 GB), small, or base on CPU |
| Models folder | `%LOCALAPPDATA%\Cyctitles\models` | change in Manage models… |
| Custom Whisper / translation | (off) | open your own CTranslate2 model folders |
| Background opacity | 75% | |
| Font size | 100% | |
| Max lines | 2 | 1–3; taller text auto-shrinks to fit |
| Position | Bottom | top or bottom of the frame |
| Text / box colour | white / black | pick with the colour buttons |
| Show original | off | shows the spoken line smaller under the translation |
| Hide after | 6 s | |
| Cut long speech after | 8 s | force a cut on a long monologue (Settings → Text processing) |
| End a phrase after silence of | 0.55 s | segment on a pause |
| Max words per caption | No limit | split captions to at most N words |
| Split sentences | off | break long text at sentence ends |
| Capitalize sentences | off | capitalise the first letter of each caption |
| Dedupe repeats | on | collapse repeated words/phrases (hallucination filter) |
| Dictation method | Paste | **Paste** (clipboard + Ctrl+V) or **Type** (synthetic keystrokes) |
| Mute hotkey | Ctrl+Shift+S | editable in Settings → Behavior |
| Keep running in tray | on | closing the window minimises to the tray |
| Start automatically | off | begins listening as soon as the app opens |

## OBS tips

- Put the Browser Source **above** your game/camera in the Sources list.
- The overlay background is transparent; the black box behind the text is drawn by the
  page (adjust opacity in the app).
- Use headphones: if other audio leaks into your microphone, the recogniser may pick it
  up. To translate that audio on purpose, use **System output (loopback)** instead.

## Troubleshooting

- **`cublas64_12.dll is not found`** — install the CUDA pip packages (see Development
  setup). The app registers them automatically at startup.
- **Garbled / repeated text on silence or music** — expected Whisper behaviour; built-in
  filters drop the common hallucinations and the VAD ignores silence.
- **High latency** — switch Whisper to `small`/`base`, or make sure the GPU is actually
  used (see the hardware line in the app after pressing Start).
- **Nothing is typed in Dictation mode** — click the target text field first; some
  full-screen games ignore synthetic input. If typing still fails, switch **Settings →
  Text processing → Dictation method** to **Paste** (clipboard + Ctrl+V).
- **Verify the GPU stack** — run `Cyctitles.exe --selftest`. The result is appended to
  `%LOCALAPPDATA%\Cyctitles\cyctitles.log`; look for the final `selftest: OK` line.

## Credits

Made by **ClassicCyc**. Specially for **CraftingVegeto**.

- Telegram: [t.me/classiccyc](https://t.me/classiccyc)
- YouTube: [youtube.com/@ClassicCyc](https://youtube.com/@ClassicCyc)
- GitHub: [github.com/ClassicCyc/Cyctitles](https://github.com/ClassicCyc/Cyctitles)

Built on open-source work: faster-whisper, CTranslate2, Whisper (OpenAI), quickmt,
webrtcvad, sounddevice (PortAudio), soundcard, PySide6 (Qt), aiohttp, and the Inter
typeface.

## License

[MIT](LICENSE). Bundled third-party components keep their own licenses (Inter is under
the SIL Open Font License — see `overlay/fonts/OFL.txt`).

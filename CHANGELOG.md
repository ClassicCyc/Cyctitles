# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-19

First public release.

### Added

- Real-time **offline** speech recognition with [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
  (Whisper on CTranslate2), GPU accelerated when an NVIDIA GPU is present, CPU otherwise.
- Local **translation** with [quickmt](https://huggingface.co/quickmt) CTranslate2 models
  (EN↔RU, EN↔ZH, EN↔FR, EN↔DE, EN↔ES, EN↔JA, EN↔UK and more), including pivot translation
  through English for unsupported direct pairs.
- **OBS overlay** via a local web server (`http://127.0.0.1:8765`) rendered as a
  transparent Browser Source, with live styling (position, colours, opacity, font size,
  max lines, optional smaller original line) and a test-subtitle preview.
- **Dictation mode** — type recognised (optionally translated) text into the focused
  window, with configurable trailing space, Enter-after-phrase and typing delay.
- **On-screen caption window** — a frameless, always-on-top caption strip for calls and
  conferences.
- **Text-to-speech** of the translated text through the system voice.
- **Audio sources** — microphone, the loopback of **any** output device, or both at once.
- **VAD backends** — `webrtcvad` and a lightweight energy-based detector.
- **Model manager** — download/delete models with a live progress bar, choose the models
  folder, and open custom on-disk CTranslate2 models.
- **Settings** — subtitles, performance (compute type), text processing, speech and
  behaviour tabs, applied instantly. Dark / light / auto theme.
- **System tray** with Start/Stop, Mute, Show and Quit; customisable mute hotkey
  (default `Ctrl+Shift+S`) and auto-start.
- **Localisation** — English, Русский, Українська, Français, Español, Deutsch, 中文, 日本語.
- **Windows installer** with an optional **NVIDIA CUDA** component that downloads (or
  picks up a local `cuda.zip`) and extracts the CUDA runtime next to the executable.

[1.0.0]: https://github.com/ClassicCyc/Cyctitles/releases/tag/v1.0.0

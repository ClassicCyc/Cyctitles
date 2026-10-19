"""Unit tests for Cyctitles core logic (no GPU / no network needed)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cyctitles import inject
from cyctitles.audio import FRAME_SAMPLES
from cyctitles.config import (
    SOURCE_LANGUAGES,
    TARGET_LANGUAGES,
    MODELS_DIR,
    Config,
    OverlayConfig,
    load_config,
    resolved_models_dir,
    save_config,
)
from cyctitles.hotkey import MOD_CONTROL, MOD_SHIFT, parse_hotkey
from cyctitles.models import (
    DEFAULT_TRANSLATION_KEY,
    LANGUAGE_NAMES,
    TRANSLATION_BY_KEY,
    custom_translation_info,
    custom_whisper_info,
    delete_model,
    directory_size,
    find_translation_key,
    human_size,
    is_quickmt_downloaded,
    is_translation_downloaded,
    is_whisper_downloaded,
    move_models_dir,
    quickmt_model_info,
    translation_model_dir,
    translation_model_info,
    whisper_cache_dir,
    whisper_model_info,
)
from cyctitles.transcriber import (
    GpuInfo,
    TranscribeResult,
    Transcriber,
    resolve_device_compute,
    resolve_model,
)
from cyctitles.vad import SpeechSegmenter


# --- hotkey parsing -----------------------------------------------------------
def test_parse_hotkey_ctrl_shift_s():
    mods, vk = parse_hotkey("ctrl+shift+s")
    assert mods == MOD_CONTROL | MOD_SHIFT
    assert vk == ord("S")


def test_parse_hotkey_function_key():
    _mods, vk = parse_hotkey("ctrl+f5")
    assert vk == 0x74  # F5


def test_parse_hotkey_invalid():
    with pytest.raises(ValueError):
        parse_hotkey("ctrl+")


# --- device/model resolution --------------------------------------------------
def test_blackwell_forces_float16():
    gpu = GpuInfo(name="RTX 5090", vram_mb=32768, cc_major=12)
    device, compute = resolve_device_compute("auto", "auto", gpu)
    assert device == "cuda"
    assert compute == "float16"


def test_ampere_uses_int8():
    gpu = GpuInfo(name="RTX 3080", vram_mb=10240, cc_major=8)
    device, compute = resolve_device_compute("auto", "auto", gpu)
    assert (device, compute) == ("cuda", "int8_float16")


def test_no_gpu_falls_back_to_cpu():
    device, compute = resolve_device_compute("auto", "auto", None)
    assert (device, compute) == ("cpu", "int8")


def test_model_auto_by_vram():
    big = GpuInfo("RTX 5090", 32768, 12)
    mid = GpuInfo("RTX 3060", 8192, 8)
    small = GpuInfo("GTX 1650", 4096, 7)
    assert resolve_model("auto", "cuda", big) == "large-v3-turbo"
    assert resolve_model("auto", "cuda", mid) == "medium"
    assert resolve_model("auto", "cuda", small) == "small"
    assert resolve_model("auto", "cpu", None) == "base"


# --- hallucination / noise filters -------------------------------------------
def _result(text: str, logprob: float = -0.2, nsp: float = 0.05) -> TranscribeResult:
    return TranscribeResult(text=text, avg_logprob=logprob, no_speech_prob=nsp)


def test_filter_rejects_empty():
    r = _result("")
    Transcriber._apply_filters(r)
    assert r.rejected


def test_filter_rejects_hallucination_phrase():
    r = _result("Thank you for watching.")
    Transcriber._apply_filters(r)
    assert r.rejected
    assert r.reason == "hallucination-blacklist"


def test_filter_rejects_tiny_noise():
    r = _result(" .. ")
    Transcriber._apply_filters(r)
    assert r.rejected


def test_filter_keeps_real_sentence():
    r = _result("So anyway, let's check out this clip.")
    Transcriber._apply_filters(r)
    assert not r.rejected


def test_filter_rejects_low_confidence_nonspeech():
    r = _result("Some marginal whisper", logprob=-1.6, nsp=0.95)
    Transcriber._apply_filters(r)
    assert r.rejected


# --- VAD state machine (speech detection monkeypatched) -----------------------
def test_segmenter_emits_chunk_after_silence():
    seg = SpeechSegmenter(min_silence_sec=0.3, min_speech_sec=0.2, max_chunk_sec=8.0)
    state = {"speech": True}
    seg._is_speech = lambda frame: state["speech"]  # type: ignore[assignment]

    chunk = None
    for _ in range(20):  # 0.6 s of speech
        chunk = seg.feed(np.zeros(FRAME_SAMPLES, dtype=np.float32))
    assert chunk is None

    state["speech"] = False
    for _ in range(15):  # 0.45 s silence -> triggers emit
        chunk = seg.feed(np.zeros(FRAME_SAMPLES, dtype=np.float32))
        if chunk is not None:
            break
    assert chunk is not None
    assert len(chunk) > FRAME_SAMPLES * 10


def test_segmenter_ignores_pure_silence():
    seg = SpeechSegmenter()
    seg._is_speech = lambda frame: False  # type: ignore[assignment]
    for _ in range(100):
        assert seg.feed(np.zeros(FRAME_SAMPLES, dtype=np.float32)) is None


def test_segmenter_forced_cut_on_long_speech():
    seg = SpeechSegmenter(max_chunk_sec=1.0, min_speech_sec=0.1)
    seg._is_speech = lambda frame: True  # type: ignore[assignment]
    chunk = None
    for _ in range(60):  # 1.8 s of continuous speech
        out = seg.feed(np.zeros(FRAME_SAMPLES, dtype=np.float32))
        if out is not None:
            chunk = out
            break
    assert chunk is not None  # forced cut fired


# --- config round trip --------------------------------------------------------
def test_config_roundtrip(tmp_path: Path):
    path = tmp_path / "config.json"
    cfg = Config()
    cfg.src_lang = "fr"
    cfg.tgt_lang = "ru"
    cfg.device_id = "5"
    cfg.overlay = OverlayConfig(opacity=0.5, show_original=True, auto_hide_sec=9.0)
    save_config(cfg, path)

    loaded = load_config(path)
    assert loaded.src_lang == "fr"
    assert loaded.device_id == "5"
    assert loaded.overlay.opacity == 0.5
    assert loaded.overlay.show_original is True
    assert loaded.overlay.auto_hide_sec == 9.0


def test_config_defaults_when_missing(tmp_path: Path):
    loaded = load_config(tmp_path / "nope.json")
    assert loaded.src_lang == "en"
    assert loaded.tgt_lang == "ru"
    assert loaded.overlay.opacity == 0.75


# --- model registry / download detection --------------------------------------
def test_human_size():
    assert human_size(500) == "500 B"
    assert human_size(75_000_000) == "71.5 MB"
    assert human_size(1_530_000_000) == "1.4 GB"


def test_whisper_cache_dir_layout():
    d = whisper_cache_dir(Path("models"), "large-v3-turbo")
    assert d.name == "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo"


def test_whisper_download_detection(tmp_path: Path):
    assert not is_whisper_downloaded("medium", tmp_path)
    snap = tmp_path / "models--Systran--faster-whisper-medium" / "snapshots" / "abc123"
    snap.mkdir(parents=True)
    assert not is_whisper_downloaded("medium", tmp_path)  # no weights yet
    (snap / "model.bin").write_bytes(b"x")
    assert is_whisper_downloaded("medium", tmp_path)


def test_quickmt_download_detection(tmp_path: Path):
    assert not is_quickmt_downloaded(tmp_path)
    model_dir = tmp_path / "quickmt-en-ru"
    model_dir.mkdir()
    (model_dir / "model.bin").write_bytes(b"x")
    (model_dir / "src.spm.model").write_bytes(b"x")
    (model_dir / "tgt.spm.model").write_bytes(b"x")
    (model_dir / "source_vocabulary.json").write_bytes(b"{}")
    (model_dir / "target_vocabulary.json").write_bytes(b"{}")
    assert is_quickmt_downloaded(tmp_path)


def test_model_info_fields(tmp_path: Path):
    info = whisper_model_info("small", tmp_path)
    assert info.kind == "whisper"
    assert info.repo_id == "Systran/faster-whisper-small"
    assert info.size_text == "461.6 MB"
    assert info.downloaded is False
    assert info.url.startswith("https://huggingface.co/")

    mt = quickmt_model_info(tmp_path)
    assert mt.kind == "translation"
    assert mt.repo_id == "quickmt/quickmt-en-ru"


def test_directory_size_and_delete(tmp_path: Path):
    model_dir = tmp_path / "models--Systran--faster-whisper-base" / "snapshots" / "rev"
    model_dir.mkdir(parents=True)
    (model_dir / "model.bin").write_bytes(b"x" * 1000)
    info = whisper_model_info("base", tmp_path)
    assert info.downloaded is True
    assert directory_size(info.directory) == 1000
    delete_model(info)
    assert not info.directory.exists()
    assert not is_whisper_downloaded("base", tmp_path)


def test_overlay_config_extended_roundtrip(tmp_path: Path):
    path = tmp_path / "config.json"
    cfg = Config()
    cfg.overlay.position = "top"
    cfg.overlay.text_color = "#ffcc00"
    cfg.overlay.background = "#101010"
    cfg.overlay.max_lines = 3
    cfg.auto_start = True
    cfg.minimize_to_tray = False
    save_config(cfg, path)

    loaded = load_config(path)
    assert loaded.overlay.position == "top"
    assert loaded.overlay.text_color == "#ffcc00"
    assert loaded.overlay.background == "#101010"
    assert loaded.overlay.max_lines == 3
    assert loaded.auto_start is True
    assert loaded.minimize_to_tray is False


# --- configurable model storage ----------------------------------------------
def test_resolved_models_dir_default():
    assert resolved_models_dir(Config()) == MODELS_DIR


def test_resolved_models_dir_custom(tmp_path: Path):
    cfg = Config()
    cfg.models_dir = str(tmp_path / "custom")
    assert resolved_models_dir(cfg) == tmp_path / "custom"


def test_storage_config_roundtrip(tmp_path: Path):
    path = tmp_path / "config.json"
    cfg = Config()
    cfg.models_dir = r"E:\Models"
    cfg.whisper_model_path = r"E:\Models\my-whisper"
    cfg.translation_model_path = r"E:\Models\my-mt"
    save_config(cfg, path)

    loaded = load_config(path)
    assert loaded.models_dir == r"E:\Models"
    assert loaded.whisper_model_path == r"E:\Models\my-whisper"
    assert loaded.translation_model_path == r"E:\Models\my-mt"


def test_custom_whisper_info(tmp_path: Path):
    folder = tmp_path / "my-whisper"
    folder.mkdir()
    info = custom_whisper_info(folder)
    assert info.repo_id == "(custom folder)"
    assert info.downloaded is False
    assert info.kind == "whisper"
    (folder / "model.bin").write_bytes(b"x" * 500)
    info = custom_whisper_info(folder)
    assert info.downloaded is True
    assert directory_size(info.directory) == 500


def test_custom_translation_info(tmp_path: Path):
    folder = tmp_path / "my-mt"
    folder.mkdir()
    assert custom_translation_info(folder).downloaded is False
    (folder / "model.bin").write_bytes(b"x")
    (folder / "src.spm.model").write_bytes(b"x")
    assert custom_translation_info(folder).downloaded is False  # tgt missing
    (folder / "tgt.spm.model").write_bytes(b"x")
    assert custom_translation_info(folder).downloaded is True


def test_move_models_dir(tmp_path: Path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    (old / "models--Systran--faster-whisper-base" / "snapshots" / "rev").mkdir(parents=True)
    (old / "models--Systran--faster-whisper-base" / "snapshots" / "rev" / "model.bin").write_bytes(b"x")
    (old / ".locks").mkdir()

    moved = move_models_dir(old, new)
    assert moved == 1
    assert (new / "models--Systran--faster-whisper-base" / "snapshots" / "rev" / "model.bin").is_file()
    assert is_whisper_downloaded("base", new)
    # .locks is intentionally left behind
    assert (old / ".locks").exists()


# --- translation model registry ----------------------------------------------
def test_translation_registry_has_common_pairs():
    for key in ("quickmt-en-ru", "quickmt-ru-en", "quickmt-en-zh", "quickmt-zh-en"):
        assert key in TRANSLATION_BY_KEY
    assert TRANSLATION_BY_KEY[DEFAULT_TRANSLATION_KEY].src == "en"
    assert TRANSLATION_BY_KEY[DEFAULT_TRANSLATION_KEY].tgt == "ru"


def test_find_translation_key():
    assert find_translation_key("en", "zh") == "quickmt-en-zh"
    assert find_translation_key("ru", "en") == "quickmt-ru-en"
    assert find_translation_key("en", "ru") == "quickmt-en-ru"
    assert find_translation_key("zh", "ru") is None
    assert find_translation_key("ru", "zh") is None
    assert find_translation_key("en", "xx") is None


def test_only_supported_pairs_are_listed():
    # quickmt ships only X->en and en->X models (no zh->ru etc.)
    for spec in TRANSLATION_BY_KEY.values():
        assert spec.src == "en" or spec.tgt == "en"
    assert "quickmt-zh-ru" not in TRANSLATION_BY_KEY
    assert "quickmt-ru-zh" not in TRANSLATION_BY_KEY
    for key in ("quickmt-tr-en", "quickmt-ar-en", "quickmt-uk-en", "quickmt-cs-en"):
        assert key in TRANSLATION_BY_KEY


def test_language_names_cover_registry():
    for spec in TRANSLATION_BY_KEY.values():
        assert spec.src in LANGUAGE_NAMES
        assert spec.tgt in LANGUAGE_NAMES


def test_ui_language_lists_use_registry():
    codes = {code for _label, code in TARGET_LANGUAGES}
    assert {"en", "ru", "zh"} <= codes
    src_codes = {code for _label, code in SOURCE_LANGUAGES}
    assert "auto" in src_codes


def test_translation_model_info_fields(tmp_path: Path):
    info = translation_model_info("quickmt-en-zh", tmp_path)
    assert info.kind == "translation"
    assert info.repo_id == "quickmt/quickmt-en-zh"
    assert info.downloaded is False
    assert info.url.startswith("https://huggingface.co/")


def test_translation_download_detection(tmp_path: Path):
    assert not is_translation_downloaded("quickmt-en-ru", tmp_path)
    d = translation_model_dir("quickmt-en-ru", tmp_path)
    d.mkdir(parents=True)
    (d / "model.bin").write_bytes(b"x")
    assert not is_translation_downloaded("quickmt-en-ru", tmp_path)  # spm missing
    (d / "src.spm.model").write_bytes(b"x")
    (d / "tgt.spm.model").write_bytes(b"x")
    # vocab still missing -> CTranslate2 would fail, so not "downloaded" yet
    assert not is_translation_downloaded("quickmt-en-ru", tmp_path)
    (d / "source_vocabulary.json").write_bytes(b"{}")
    (d / "target_vocabulary.json").write_bytes(b"{}")
    assert is_translation_downloaded("quickmt-en-ru", tmp_path)


def test_translation_shared_vocab_counts(tmp_path: Path):
    d = translation_model_dir("quickmt-en-fr", tmp_path)
    d.mkdir(parents=True)
    (d / "model.bin").write_bytes(b"x")
    (d / "joint.spm.model").write_bytes(b"x")
    (d / "shared_vocabulary.json").write_bytes(b"{}")
    assert is_translation_downloaded("quickmt-en-fr", tmp_path)


# --- text injection (dictation) ----------------------------------------------
def test_inject_available_is_bool():
    assert isinstance(inject.available(), bool)


def test_inject_noop_when_unavailable(monkeypatch):
    monkeypatch.setattr(inject, "_IS_WIN", False)
    assert inject.available() is False
    assert inject.type_text("hello") is False
    assert inject.paste_text("hello") is False


# --- performance + new options config ----------------------------------------
def test_device_and_compute_mode_roundtrip(tmp_path: Path):
    path = tmp_path / "config.json"
    cfg = Config()
    cfg.device_mode = "cpu"
    cfg.compute_mode = "int8"
    cfg.audio_source = "both"
    cfg.screen_overlay_enabled = True
    cfg.tts_enabled = True
    save_config(cfg, path)

    loaded = load_config(path)
    assert loaded.device_mode == "cpu"
    assert loaded.compute_mode == "int8"
    assert loaded.audio_source == "both"
    assert loaded.screen_overlay_enabled is True
    assert loaded.tts_enabled is True


def test_tts_module_importable():
    from cyctitles import tts

    assert isinstance(tts.available(), bool)
    assert callable(tts.speak) and callable(tts.stop)


# --- CUDA pack / external CUDA lookup ----------------------------------------
def test_cuda_runtime_available_is_bool():
    from cyctitles import cuda_env

    assert isinstance(cuda_env.cuda_runtime_available(), bool)


def test_setup_cuda_dlls_idempotent():
    from cyctitles import cuda_env

    assert cuda_env.setup_cuda_dlls() == cuda_env.setup_cuda_dlls()


def test_external_cuda_bins_found(monkeypatch, tmp_path: Path):
    from cyctitles import cuda_env

    # Build a fake external cuda/<pkg>/bin layout next to a fake "exe".
    fake_exe_dir = tmp_path / "app"
    cuda_bin = fake_exe_dir / "cuda" / "cublas" / "bin"
    cuda_bin.mkdir(parents=True)
    (cuda_bin / "cublas64_12.dll").write_bytes(b"")
    monkeypatch.setattr(cuda_env.sys, "executable", str(fake_exe_dir / "Cyctitles.exe"))

    bins = list(cuda_env._iter_external_bins())
    assert any(str(cuda_bin) == str(b) for b in bins)


# --- text post-processing -----------------------------------------------------
def test_textproc_normalize_and_dedupe():
    from cyctitles import textproc

    assert textproc.normalize_whitespace("  a   b \n c ") == "a b c"
    assert textproc.dedupe_repeats("the the the cat") == "the cat"


def test_textproc_segments_max_words():
    from cyctitles import textproc

    cfg = Config()
    cfg.max_words_per_caption = 3
    segs = textproc.segments("one two three four five six seven", cfg)
    assert segs == ["one two three", "four five six", "seven"]


def test_textproc_split_sentences_and_capitalize():
    from cyctitles import textproc

    cfg = Config()
    cfg.split_sentences = True
    cfg.capitalize_sentences = True
    segs = textproc.segments("hello world. how are you? fine", cfg)
    assert segs == ["Hello world.", "How are you?", "Fine"]


def test_textproc_process_joins():
    from cyctitles import textproc

    cfg = Config()
    cfg.split_sentences = True
    assert textproc.process("a. b. c.", cfg) == "a. b. c."


def test_text_processing_config_roundtrip(tmp_path: Path):
    path = tmp_path / "config.json"
    cfg = Config()
    cfg.max_words_per_caption = 12
    cfg.split_sentences = True
    cfg.capitalize_sentences = True
    cfg.dedupe_repeats = False
    cfg.min_caption_chars = 3
    cfg.dictation_method = "type"
    cfg.dictation_trailing_space = False
    cfg.dictation_enter_after = True
    cfg.dictation_typing_delay_ms = 15
    save_config(cfg, path)

    loaded = load_config(path)
    assert loaded.max_words_per_caption == 12
    assert loaded.split_sentences is True
    assert loaded.capitalize_sentences is True
    assert loaded.dedupe_repeats is False
    assert loaded.min_caption_chars == 3
    assert loaded.dictation_method == "type"
    assert loaded.dictation_trailing_space is False
    assert loaded.dictation_enter_after is True
    assert loaded.dictation_typing_delay_ms == 15


# --- audio devices ------------------------------------------------------------
def test_list_output_devices_shape():
    from cyctitles import audio

    for dev in audio.list_output_devices():
        assert isinstance(dev.name, str)
        assert dev.key  # a soundcard id


# --- profanity filter ---------------------------------------------------------
def test_censor_masks_whole_words():
    from cyctitles.textproc import censor_text

    out = censor_text("This shit is shitty, shit.", ["shit"])
    assert "****" in out
    assert "shitty" in out  # substring inside another word is left alone
    assert "shit" not in out.replace("shitty", "")


def test_apply_censor_respects_flag():
    from cyctitles.textproc import apply_censor

    cfg = Config()
    cfg.censor_enabled = False
    cfg.censor_words = ["hell"]
    assert apply_censor("go to hell", cfg) == "go to hell"
    cfg.censor_enabled = True
    assert apply_censor("go to hell", cfg) == "go to ****"


# --- translation routing to English pivot ------------------------------------
def test_pivot_path_ru_to_zh_goes_through_english():
    from cyctitles.models import find_translation_path

    path = find_translation_path("ru", "zh")
    assert len(path) >= 2
    assert "ru-en" in path[0]
    assert "en-zh" in path[-1]


# --- overlay config roundtrip -------------------------------------------------
def test_overlay_style_config_roundtrip(tmp_path: Path):
    path = tmp_path / "config.json"
    cfg = Config()
    ov = cfg.overlay
    ov.outline_width = 0.05
    ov.outline_color = "#102030"
    ov.font_weight = 700
    ov.animation = "slide-up"
    ov.animation_duration = 0.4
    ov.preset = "bold"
    save_config(cfg, path)

    loaded = load_config(path)
    lo = loaded.overlay
    assert lo.outline_width == 0.05
    assert lo.outline_color == "#102030"
    assert lo.font_weight == 700
    assert lo.animation == "slide-up"
    assert lo.animation_duration == 0.4
    assert lo.preset == "bold"


# --- i18n ---------------------------------------------------------------------
def test_i18n_english_and_russian():
    from cyctitles import i18n

    try:
        i18n.set_language("en")
        assert i18n.tr("models_title") == "Models"
        i18n.set_language("ru")
        assert i18n.tr("models_title") == "Модели"
        assert "Неизвестный ключ" == i18n.tr("неизвестный_ключ")
    finally:
        i18n.set_language("en")


def test_i18n_all_languages_have_same_keys():
    from cyctitles import i18n

    english = set(i18n._STRINGS["en"])
    for code, strings in i18n._STRINGS.items():
        assert set(strings) == english, f"{code} differs"
    for _label, code in i18n.UI_LANGUAGES:
        assert code in i18n._STRINGS


# --- VAD backends -------------------------------------------------------------
def test_energy_vad_segmenter_emits_speech_chunk():
    from cyctitles.vad import SpeechSegmenter

    seg = SpeechSegmenter(
        backend="energy",
        energy_threshold=0.05,
        min_silence_sec=0.15,
        min_speech_sec=0.15,
        max_chunk_sec=2.0,
    )
    n = seg.frame_ms  # ms
    loud = np.full(16000 * n // 1000, 0.4, dtype=np.float32)
    quiet = np.zeros(16000 * n // 1000, dtype=np.float32)

    for _ in range(10):  # speak long enough to satisfy min_speech
        assert seg.feed(loud) is None
    chunk = None
    for _ in range(12):  # then pause until min_silence fires
        out = seg.feed(quiet)
        if out is not None:
            chunk = out
            break
    assert chunk is not None and len(chunk) > 0


def test_webrtc_vad_default_backend_is_selected():
    from cyctitles.vad import SpeechSegmenter

    seg = SpeechSegmenter()
    assert seg.backend == "webrtcvad"
    assert seg._vad is not None
    assert SpeechSegmenter(backend="weird").backend == "webrtcvad"


def test_level_fraction_bounds():
    from cyctitles.vad import frame_rms, level_fraction

    assert frame_rms(np.zeros(480, dtype=np.float32)) == 0.0
    assert level_fraction(0.0) == 0.0
    assert 0.0 <= level_fraction(0.5) <= 1.0
    assert level_fraction(1.0) >= 0.99


# --- config roundtrip for the new keys ----------------------------------------
def test_audio_config_roundtrip(tmp_path: Path):
    path = tmp_path / "config.json"
    cfg = Config()
    cfg.vad_backend = "energy"
    cfg.vad_energy_threshold = 0.025
    cfg.audio_source = "both"
    save_config(cfg, path)

    loaded = load_config(path)
    assert loaded.vad_backend == "energy"
    assert loaded.vad_energy_threshold == 0.025
    assert loaded.audio_source == "both"



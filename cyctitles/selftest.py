"""Self-test: validates the GPU inference stack in a packaged build.

Run with ``Cyctitles.exe --selftest``; results are written to the log file
(%LOCALAPPDATA%\\Cyctitles\\cyctitles.log).
"""

from __future__ import annotations

import logging


def run_selftest() -> int:
    import numpy as np

    from .config import load_config, resolved_models_dir
    from .cuda_env import setup_cuda_dlls
    from .transcriber import Transcriber, detect_gpu, resolve_device_compute, resolve_model
    from .translator import Translator

    log = logging.getLogger("selftest")
    added = setup_cuda_dlls()
    log.info("selftest: cuda dll dirs registered: %s", added)

    cfg = load_config()
    models_dir = resolved_models_dir(cfg)
    log.info("selftest: models dir: %s", models_dir)

    gpu = detect_gpu()
    log.info("selftest: gpu detected: %s", gpu)

    device, compute = resolve_device_compute("auto", "auto", gpu)
    model = cfg.whisper_model_path or resolve_model(cfg.whisper_model, device, gpu)
    log.info("selftest: whisper model=%s device=%s compute=%s", model, device, compute)

    ok = True

    try:
        transcriber = Transcriber(model, device, compute, models_dir)
        result = transcriber.transcribe(np.zeros(16000, dtype=np.float32), "en")
        log.info("selftest: whisper ran (%s), text=%r", model, result.text)
    except Exception as exc:  # noqa: BLE001
        ok = False
        log.exception("selftest: whisper FAILED: %s", exc)

    try:
        translator = Translator(
            models_dir, device=device, model_dir=cfg.translation_model_path or None
        )
        out = translator.translate(["Hello world, this is a diagnostic test."])[0]
        log.info("selftest: translation ran (%s), text=%r", device, out)
    except Exception as exc:  # noqa: BLE001
        ok = False
        log.exception("selftest: translation FAILED: %s", exc)

    log.info("selftest: %s", "OK" if ok else "FAILED")
    return 0 if ok else 1

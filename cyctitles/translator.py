"""Offline machine translation via CTranslate2.

Models come from the quickmt family (eole → CTranslate2, SentencePiece). Every
model shares the same on-disk layout (``model.bin`` + ``src.spm.model`` +
``tgt.spm.model``, or a ``joint.spm.model``), so one loader handles them all.
"""

from __future__ import annotations

from pathlib import Path

from .models import (
    DEFAULT_TRANSLATION_KEY,
    QUICKMT_IGNORE,
    TRANSLATION_BY_KEY,
    is_translation_downloaded,
    translation_model_dir,
)


class Translator:
    """A quickmt CTranslate2 model + SentencePiece tokenizers."""

    def __init__(
        self,
        models_dir: Path,
        device: str = "auto",
        compute_type: str = "auto",
        beam_size: int = 2,
        model_dir: str | Path | None = None,
        model_key: str = DEFAULT_TRANSLATION_KEY,
    ):
        from .cuda_env import setup_cuda_dlls

        setup_cuda_dlls()
        import ctranslate2

        self.beam_size = beam_size
        self._models_dir = Path(models_dir)
        self._model_key = model_key
        self._custom_dir: Path | None = None

        if model_dir:
            resolved_dir = Path(model_dir)
            if not (resolved_dir / "model.bin").is_file():
                raise FileNotFoundError(
                    f"Custom translation model folder is missing model.bin: {resolved_dir}"
                )
            self._custom_dir = resolved_dir
        else:
            resolved_dir = self._ensure_model(self._models_dir, model_key)

        self.model_dir = resolved_dir

        resolved_device = device
        resolved_compute = compute_type
        if device == "auto":
            resolved_device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        if compute_type == "auto":
            resolved_compute = "float16" if resolved_device == "cuda" else "int8"

        try:
            self._load(resolved_dir, resolved_device, resolved_compute)
        except Exception as exc:  # noqa: BLE001
            # Built-in models self-heal: re-download and retry. Custom folders never
            # touch the network (the user owns those files).
            if self._custom_dir is not None:
                raise
            resolved_dir = self._repair_model(self._models_dir, model_key, resolved_dir, exc)
            self.model_dir = resolved_dir
            self._load(resolved_dir, resolved_device, resolved_compute)

    def _load(self, resolved_dir: Path, device: str, compute_type: str) -> None:
        import ctranslate2
        import sentencepiece as spm

        src_spm = resolved_dir / "src.spm.model"
        tgt_spm = resolved_dir / "tgt.spm.model"
        joint = resolved_dir / "joint.spm.model"
        if not src_spm.is_file():
            src_spm = joint
        if not tgt_spm.is_file():
            tgt_spm = joint

        translator = ctranslate2.Translator(
            str(resolved_dir),
            device=device,
            compute_type=compute_type,
        )
        sp_src = spm.SentencePieceProcessor(model_file=str(src_spm))
        sp_tgt = spm.SentencePieceProcessor(model_file=str(tgt_spm))

        self._translator = translator
        self._sp_src = sp_src
        self._sp_tgt = sp_tgt

    @classmethod
    def _repair_model(
        cls, models_dir: Path, model_key: str, model_dir: Path, exc: Exception
    ) -> Path:
        """Re-fetch a broken/incomplete built-in model and return its directory.

        First a normal (incremental) download fills any missing file; if the model
        still will not load it is re-downloaded from scratch (fixes corruption).
        """
        from huggingface_hub import snapshot_download

        spec = TRANSLATION_BY_KEY.get(model_key)
        if spec is None:
            raise exc

        last: Exception = exc
        for force in (False, True):
            try:
                snapshot_download(
                    repo_id=spec.repo_id,
                    local_dir=str(model_dir),
                    ignore_patterns=QUICKMT_IGNORE,
                    force_download=force,
                )
            except Exception as dl_exc:  # noqa: BLE001
                last = dl_exc
                continue
            try:
                import ctranslate2  # noqa: F401
                import sentencepiece as spm

                probe = spm.SentencePieceProcessor(
                    model_file=str(model_dir / "src.spm.model")
                )
                ctranslate2.Translator(str(model_dir), device="cpu", compute_type="int8")
                del probe
                return model_dir
            except Exception as probe_exc:  # noqa: BLE001
                last = probe_exc
                continue
        raise RuntimeError(f"Could not repair translation model '{model_key}': {last}")

    @classmethod
    def _ensure_model(cls, models_dir: Path, model_key: str = DEFAULT_TRANSLATION_KEY) -> Path:
        from huggingface_hub import snapshot_download

        spec = TRANSLATION_BY_KEY.get(model_key)
        if spec is None:
            raise ValueError(f"Unknown translation model: {model_key}")
        model_dir = translation_model_dir(spec.key, models_dir)
        # Re-download (incrementally) if anything is missing — this also repairs
        # models fetched by older versions that skipped the vocabulary JSON.
        if not is_translation_downloaded(spec.key, models_dir):
            snapshot_download(
                repo_id=spec.repo_id,
                local_dir=str(model_dir),
                ignore_patterns=QUICKMT_IGNORE,
            )
        return model_dir

    def translate(self, texts: list[str]) -> list[str]:
        if not texts:
            return []
        batch = [self._sp_src.encode(t, out_type=str) for t in texts]
        results = self._translator.translate_batch(
            batch,
            beam_size=self.beam_size,
            max_decoding_length=256,
            repetition_penalty=1.0,
        )
        out: list[str] = []
        for result in results:
            tokens = list(result.hypotheses[0])
            # Strip eole decoder start token if it leaks into the output.
            while tokens and tokens[0] in ("</s>", "<s>"):
                tokens = tokens[1:]
            text = self._sp_tgt.decode(tokens)
            out.append(text.strip())
        return out


class ChainTranslator:
    """Applies several quickmt models in sequence (pivot translation).

    Lets pairs without a direct model still work, e.g. ru -> zh becomes
    ru -> en -> zh. Each hop is a normal :class:`Translator`.
    """

    def __init__(self, translators: list[Translator], keys: list[str]) -> None:
        self._translators = translators
        self.keys = list(keys)
        self.beam_size = translators[0].beam_size if translators else 2
        self.model_dir = translators[0].model_dir if translators else Path()

    @property
    def is_direct(self) -> bool:
        return len(self._translators) <= 1

    @property
    def description(self) -> str:
        from .models import path_description

        return path_description(self.keys)

    def translate(self, texts: list[str]) -> list[str]:
        current = list(texts)
        for translator in self._translators:
            current = translator.translate(current)
        return current


def build_translator(
    models_dir: Path,
    keys: list[str],
    device: str = "auto",
    compute_type: str = "auto",
    model_dir: str | Path | None = None,
) -> ChainTranslator:
    """Load every model in ``keys`` and return a translator (direct or pivot).

    ``model_dir`` overrides only the first (or single) model with a custom folder.
    """
    translators: list[Translator] = []
    for i, key in enumerate(keys):
        override = model_dir if (i == 0 and (len(keys) == 1 or model_dir)) else None
        if override and i > 0:
            override = None
        translators.append(
            Translator(
                models_dir,
                device=device,
                compute_type=compute_type,
                model_dir=override,
                model_key=key,
            )
        )
    return ChainTranslator(translators, keys)

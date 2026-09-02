"""Offline speech-to-text behind /api/stt, one engine per language, all on
sherpa-onnx (a prebuilt wheel - no compiler):

  Hindi / Marathi -> AI4Bharat IndicConformer-600M (CTC). One multilingual model
    that emits the correct native script - no language auto-detect, so no
    Hindi/Urdu confusion.
  English         -> Moonshine (tiny, int8) - a small, fast on-device English
    model, so English STT is fully offline too (no browser Web Speech / Google).

Each engine loads lazily on the first request for a language it serves (or an
explicit `warm()`), so a single-language session only pays for what it uses.
"""

from __future__ import annotations

import array
import io
import logging
import wave
from functools import lru_cache
from pathlib import Path
from threading import Lock

from app.config import settings

logger = logging.getLogger(__name__)

# apps/backend/ - relative model dirs in settings resolve against this.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]

# tutor language name (lowercased) -> which engine transcribes it
_ENGINE_FOR = {
    "english": "english",  # sherpa Whisper or Moonshine, auto-detected by files
    "hindi": "indic",
    "marathi": "indic",
}

_lock = Lock()


class SttUnavailable(RuntimeError):
    """Model files or the sherpa-onnx wheel aren't present. Surfaced as 503 so
    the UI can say "run setup" rather than showing a generic error."""


def _abs(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else _BACKEND_ROOT / p


def _one(d: Path, pattern: str) -> Path:
    hits = sorted(d.glob(pattern))
    if not hits:
        raise SttUnavailable("{} missing from {}. Run scripts/setup.ps1.".format(pattern, d))
    return hits[0]


def _import_sherpa():
    try:
        import sherpa_onnx  # noqa: F401

        return sherpa_onnx
    except ImportError as exc:  # pragma: no cover - depends on install state
        raise SttUnavailable(
            "sherpa-onnx isn't installed. Run: pip install -r apps/backend/requirements.txt"
        ) from exc


@lru_cache(maxsize=2)
def _recognizer(engine: str):
    sherpa_onnx = _import_sherpa()

    if engine == "indic":
        d = _abs(settings.stt_indic_dir)
        model, tokens = d / settings.stt_indic_file, d / "tokens.txt"
        if not model.exists() or not tokens.exists():
            raise SttUnavailable(
                "IndicConformer model not found at {}. Run scripts/setup.ps1.".format(d)
            )
        logger.info("Loading IndicConformer STT model from %s", d)
        rec = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
            model=str(model),
            tokens=str(tokens),
            num_threads=settings.stt_num_threads,
        )
        logger.info("IndicConformer STT model ready")
        return rec

    if engine == "english":
        d = _abs(settings.stt_english_dir)
        if not d.is_dir():
            raise SttUnavailable(
                "English STT model not found at {}. Run scripts/setup.ps1.".format(d)
            )
        # Auto-detect which sherpa English model this folder holds by its files:
        # Moonshine has preprocess/encode/decode parts; Whisper has an
        # encoder + decoder pair.
        if sorted(d.glob("preprocess*.onnx")):
            logger.info("Loading Moonshine English STT model from %s", d)
            rec = sherpa_onnx.OfflineRecognizer.from_moonshine(
                preprocessor=str(_one(d, "preprocess*.onnx")),
                encoder=str(_one(d, "encode*.onnx")),
                uncached_decoder=str(_one(d, "uncached_decode*.onnx")),
                cached_decoder=str(_one(d, "cached_decode*.onnx")),
                tokens=str(d / "tokens.txt"),
                num_threads=settings.stt_num_threads,
            )
        elif sorted(d.glob("*encoder*.onnx")):
            logger.info("Loading Whisper English STT model from %s", d)
            rec = sherpa_onnx.OfflineRecognizer.from_whisper(
                encoder=str(_one(d, "*encoder*.onnx")),
                decoder=str(_one(d, "*decoder*.onnx")),
                tokens=str(_one(d, "*tokens.txt")),
                num_threads=settings.stt_num_threads,
                language="en",
                task="transcribe",
            )
        else:
            raise SttUnavailable(
                "Unrecognised English STT model layout in {}.".format(d)
            )
        logger.info("English STT model ready")
        return rec

    raise SttUnavailable("unknown STT engine '{}'".format(engine))


def _engine_for(language: str) -> str:
    engine = _ENGINE_FOR.get((language or "").strip().lower())
    if not engine:
        raise ValueError("no offline STT for language '{}'".format(language))
    return engine


def is_supported_language(language: str) -> bool:
    return (language or "").strip().lower() in _ENGINE_FOR


def available_languages() -> list[str]:
    out = []
    for lang, engine in _ENGINE_FOR.items():
        try:
            _recognizer(engine)
            out.append(lang)
        except Exception:  # noqa: BLE001 - readiness probe, never raise
            pass
    return sorted(out)


def is_ready(language: str) -> bool:
    try:
        _recognizer(_engine_for(language))
        return True
    except (SttUnavailable, ValueError) as exc:
        logger.warning("STT not ready for %s: %s", language, exc)
        return False


def warm(language: str) -> bool:
    """Load a language's engine and run one throwaway decode so the first real
    request pays neither the graph load nor onnxruntime's first-inference cost.
    Returns False (not raises) when the files are missing."""
    try:
        rec = _recognizer(_engine_for(language))
    except (SttUnavailable, ValueError) as exc:
        logger.warning("STT unavailable for %s: %s", language, exc)
        return False
    try:
        with _lock:
            stream = rec.create_stream()
            stream.accept_waveform(16000, [0.0] * 6400)  # ~0.4 s of silence
            rec.decode_stream(stream)
    except Exception as exc:  # pragma: no cover - warm-up is best-effort
        logger.warning("STT warm decode failed for %s (non-fatal): %s", language, exc)
    return True


def transcribe(wav_bytes: bytes, language: str) -> str:
    """Blocking - call via run_in_threadpool. Expects a 16-bit mono PCM WAV."""
    rec = _recognizer(_engine_for(language))

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        if wf.getsampwidth() != 2 or wf.getnchannels() != 1:
            raise ValueError("expected 16-bit mono PCM WAV")
        sample_rate = wf.getframerate()
        pcm = array.array("h")
        pcm.frombytes(wf.readframes(wf.getnframes()))

    if not pcm:
        return ""
    samples = [s / 32768.0 for s in pcm]

    with _lock:
        stream = rec.create_stream()
        stream.accept_waveform(sample_rate, samples)
        rec.decode_stream(stream)
        return (stream.result.text or "").strip()

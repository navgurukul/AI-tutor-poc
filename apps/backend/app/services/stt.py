"""Offline speech-to-text for the Indian languages, using sherpa-onnx +
AI4Bharat's IndicConformer-600M (CTC).

The frontend routes Hindi / Marathi speech input here (`/api/stt`); English is
recognised on-device by the browser and never hits this. One multilingual model
(fp32 `model.onnx` ~470 MB by default; `model.int8.onnx` ~188 MB is available
but ~2x the WER) emits the correct native script — no language auto-detect, so
no Hindi/Urdu confusion.

Everything loads lazily on the first request (or an explicit `warm()`), so an
English-only session pays nothing.
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

# apps/backend/ — settings.stt_model_dir is resolved against this when relative.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]

_TOKENS_FILE = "tokens.txt"

_lock = Lock()


class SttUnavailable(RuntimeError):
    """The model files or the sherpa-onnx wheel aren't present. Surfaced as 503
    so the UI can say "run setup" rather than showing a generic error."""


def _model_dir() -> Path:
    base = Path(settings.stt_model_dir)
    if not base.is_absolute():
        base = _BACKEND_ROOT / base
    return base


@lru_cache(maxsize=1)
def _recognizer():
    d = _model_dir()
    model, tokens = d / settings.stt_model_file, d / _TOKENS_FILE
    if not model.exists() or not tokens.exists():
        raise SttUnavailable(
            "IndicConformer model not found at {} ({}). Run scripts/setup.ps1.".format(
                d, settings.stt_model_file
            )
        )
    try:
        import sherpa_onnx
    except ImportError as exc:  # pragma: no cover - depends on install state
        raise SttUnavailable(
            "sherpa-onnx isn't installed. Run: pip install -r apps/backend/requirements.txt"
        ) from exc

    logger.info("Loading IndicConformer STT model from %s", d)
    rec = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
        model=str(model),
        tokens=str(tokens),
        num_threads=settings.stt_num_threads,
    )
    logger.info("IndicConformer STT model ready")
    return rec


def warm() -> bool:
    """Load the model *and run one throwaway decode* so the first real request
    pays neither the graph load nor onnxruntime's first-inference cost (arena
    allocation, kernel selection, thread-pool spin-up — 2-5x the steady-state
    time). Returns False (not raises) when it can't, so the readiness endpoint
    can report a plain boolean."""
    try:
        rec = _recognizer()
    except SttUnavailable as exc:
        logger.warning("STT unavailable: %s", exc)
        return False
    try:
        with _lock:
            stream = rec.create_stream()
            # ~0.4 s of near-silence at 16 kHz — enough to force a full decode.
            stream.accept_waveform(16000, [0.0] * 6400)
            rec.decode_stream(stream)
    except Exception as exc:  # pragma: no cover - warm-up is best-effort
        logger.warning("STT warm decode failed (non-fatal): %s", exc)
    return True


def transcribe(wav_bytes: bytes) -> str:
    """Blocking — call via run_in_threadpool. Expects a 16-bit mono PCM WAV."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        if wf.getsampwidth() != 2 or wf.getnchannels() != 1:
            raise ValueError("expected 16-bit mono PCM WAV")
        sample_rate = wf.getframerate()
        pcm = array.array("h")
        pcm.frombytes(wf.readframes(wf.getnframes()))

    if not pcm:
        return ""
    samples = [s / 32768.0 for s in pcm]

    rec = _recognizer()
    # OfflineRecognizer is thread-safe for decode, but keep one turn at a time.
    with _lock:
        stream = rec.create_stream()
        stream.accept_waveform(sample_rate, samples)
        rec.decode_stream(stream)
        return (stream.result.text or "").strip()

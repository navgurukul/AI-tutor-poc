"""Offline text-to-speech, using sherpa-onnx + a Piper VITS voice.

Only non-English tutor answers come here (`/api/tts`); English is spoken by the
browser's own `speechSynthesis`. sherpa-onnx is already a dependency (it runs
STT), so this adds no new package — just a voice folder placed by
scripts/setup.ps1: `<voice>.onnx`, `tokens.txt`, and `espeak-ng-data/`.

The model loads lazily on the first request (or an explicit `warm()`).
"""

from __future__ import annotations

import io
import logging
import wave
from array import array
from functools import lru_cache
from pathlib import Path
from threading import Lock

from app.config import settings

logger = logging.getLogger(__name__)

# apps/backend/ — settings.tts_model_dir is resolved against this when relative.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]

_lock = Lock()


class TtsUnavailable(RuntimeError):
    """Voice files or the sherpa-onnx wheel aren't present. Surfaced as 503 so
    the UI can say "run setup" rather than showing a generic error."""


def _voice_dir() -> Path:
    base = Path(settings.tts_model_dir)
    if not base.is_absolute():
        base = _BACKEND_ROOT / base
    return base / settings.tts_voice


@lru_cache(maxsize=1)
def _engine():
    d = _voice_dir()
    onnx = next(iter(sorted(d.glob("*.onnx"))), None)
    tokens = d / "tokens.txt"
    data_dir = d / "espeak-ng-data"
    if onnx is None or not tokens.exists() or not data_dir.is_dir():
        raise TtsUnavailable(
            "Piper voice not found at {}. Run scripts/setup.ps1.".format(d)
        )
    try:
        import sherpa_onnx
    except ImportError as exc:  # pragma: no cover - depends on install state
        raise TtsUnavailable(
            "sherpa-onnx isn't installed. Run: pip install -r apps/backend/requirements.txt"
        ) from exc

    logger.info("Loading Piper TTS voice from %s", d)
    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(onnx),
                tokens=str(tokens),
                data_dir=str(data_dir),
            ),
            num_threads=settings.tts_num_threads,
            provider="cpu",
        ),
        max_num_sentences=1,
    )
    tts = sherpa_onnx.OfflineTts(config)
    logger.info("Piper TTS voice ready (%d Hz)", tts.sample_rate)
    return tts


def warm() -> bool:
    """Load the voice up front (and run one throwaway synthesis) so the first
    real request doesn't pay for it. Returns False rather than raising when the
    files are missing, so the readiness endpoint can report a plain boolean."""
    try:
        tts = _engine()
    except TtsUnavailable as exc:
        logger.warning("TTS unavailable: %s", exc)
        return False
    try:
        with _lock:
            tts.generate("नमस्ते", sid=0, speed=settings.tts_speed)
    except Exception as exc:  # pragma: no cover - warm-up is best-effort
        logger.warning("TTS warm synthesis failed (non-fatal): %s", exc)
    return True


def synthesize(text: str) -> bytes:
    """Blocking — call via run_in_threadpool. Returns a 16-bit mono PCM WAV."""
    text = (text or "").strip()
    if not text:
        return b""

    tts = _engine()
    with _lock:
        audio = tts.generate(text, sid=0, speed=settings.tts_speed)

    samples = audio.samples
    samples = samples.tolist() if hasattr(samples, "tolist") else list(samples)
    rate = int(audio.sample_rate)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        pcm = array("h", (max(-32768, min(32767, int(s * 32767))) for s in samples))
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()

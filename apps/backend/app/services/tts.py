"""Offline text-to-speech behind /api/tts: sherpa-onnx running a Piper VITS
voice, one voice per language.

sherpa-onnx is already a dependency (it runs STT), so this adds no new package —
just voice folders placed by scripts/setup.ps1. Layout under `tts_model_dir`:

    models/tts/
      espeak-ng-data/     shared phonemizer data, ~18 MB, one copy for all voices
      english/            <voice>.onnx + tokens.txt
      hindi/              <voice>.onnx + tokens.txt
      marathi/            <voice>.onnx + tokens.txt

A folder is named after the tutor language (lowercased), so adding a language is
dropping in a folder — no code change here. Voices come from
https://huggingface.co/rhasspy/piper-voices (auditionable at
https://rhasspy.github.io/piper-samples/).

Each voice loads lazily on the first request for its language (or an explicit
`warm()`), so a single-language session only pays for what it uses.
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

# One lock for every voice: synthesis is CPU-bound and sherpa's session isn't
# guaranteed re-entrant, so turns are serialised rather than run in parallel.
_lock = Lock()

# Piper's multi-speaker voices (Marathi's is 9-speaker) take a speaker id.
# 0 is the first speaker in the voice's own speaker_id_map, which is the one the
# Piper samples page plays — i.e. the voice that was auditioned before choosing.
_SPEAKER_ID = 0


class TtsUnavailable(RuntimeError):
    """Voice files or the sherpa-onnx wheel aren't present. Surfaced as 503 so
    the UI can say "run setup" rather than showing a generic error."""


def _root() -> Path:
    base = Path(settings.tts_model_dir)
    return base if base.is_absolute() else _BACKEND_ROOT / base


def _voice_dir(language: str) -> Path:
    return _root() / (language or "").strip().lower()


def _espeak_dir(voice_dir: Path) -> Path | None:
    """Shared phonemizer data, with a per-voice copy taking precedence — a voice
    packaged the way k2-fsa ships theirs carries its own and still works."""
    for candidate in (voice_dir / "espeak-ng-data", _root() / "espeak-ng-data"):
        if candidate.is_dir():
            return candidate
    return None


@lru_cache(maxsize=1)
def _load_engine(language: str):
    """Cached for the one language in use. A session speaks a single language
    (the frontend tears down and re-inits TTS on a language switch), so holding
    more than one voice resident just spends ~60-75 MB per extra language for
    nothing on an 8 GB box. maxsize=1 means a mid-session language switch pays
    one cold voice load (~1-3s, measured once per switch); maxsize=2 is the
    fallback if that proves annoying in practice."""
    d = _voice_dir(language)
    onnx = next(iter(sorted(d.glob("*.onnx"))), None)
    tokens = d / "tokens.txt"
    data_dir = _espeak_dir(d)

    if onnx is None or not tokens.exists() or data_dir is None:
        raise TtsUnavailable(
            "No Piper voice for '{}' at {}. Run scripts/setup.ps1.".format(language, d)
        )

    try:
        import sherpa_onnx
    except ImportError as exc:  # pragma: no cover - depends on install state
        raise TtsUnavailable(
            "sherpa-onnx isn't installed. Run: pip install -r apps/backend/requirements.txt"
        ) from exc

    logger.info("Loading %s Piper TTS voice from %s", language, onnx.name)
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
    logger.info("%s TTS voice ready (%d Hz)", language, tts.sample_rate)
    return tts


def _key(language: str) -> str:
    """The cache key for a voice: the folder name it loads from.

    The folder is looked up lowercased, but the cache was keyed on the raw
    string -- so "Hindi" from the frontend and "hindi" from anywhere else were
    two cache entries for one voice, and with maxsize=1 each evicted the other:
    a full reload (measured 11.5 s under load on 2026-09-11) on a switch that
    was not a switch at all.
    """
    return (language or "").strip().lower()


# The voice whose first synthesis has already been paid. onnxruntime allocates
# its arenas and espeak loads its data on the FIRST generate(), not at load, so
# a voice that is loaded but never spoken still makes the first real sentence
# wait. Reset whenever a (re)load happens.
_warmed_key: str | None = None


def _engine(language: str):
    global _warmed_key
    key = _key(language)
    misses = _load_engine.cache_info().misses
    engine = _load_engine(key)
    if _load_engine.cache_info().misses != misses:
        _warmed_key = None  # freshly loaded: not yet spoken
    return engine


def _has_voice_files(d: Path) -> bool:
    return d.is_dir() and bool(sorted(d.glob("*.onnx"))) and (d / "tokens.txt").exists()


def is_supported_language(language: str) -> bool:
    return _has_voice_files(_voice_dir(language))


def available_languages() -> list[str]:
    """Languages with a voice installed. Checks files rather than loading each
    engine — a readiness probe shouldn't pull 200 MB of models into memory."""
    root = _root()
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.iterdir() if _has_voice_files(d))


def is_ready(language: str) -> bool:
    try:
        _engine(language)
        return True
    except TtsUnavailable as exc:
        logger.warning("TTS not ready for %s: %s", language, exc)
        return False


def _warmup_text(language: str) -> str:
    """A real sentence in the voice's own script, written beside it by
    scripts/package_tts_voices.py. It matters that this isn't a stray character:
    the first synthesis is what makes onnxruntime allocate its arenas and espeak
    load the voice's phoneme rules, and a Latin token exercises neither for a
    Devanagari voice — the first real sentence would then pay for both."""
    path = _voice_dir(language) / "warmup.txt"
    try:
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    except OSError:
        pass
    logger.debug("No warmup.txt for %s; warming on a placeholder.", language)
    return "a"


def warm(language: str) -> bool:
    """Load a language's voice and speak one throwaway sentence, so the first
    real sentence pays neither the graph load nor onnxruntime's first-inference
    cost. Returns False (not raises) when the files are missing."""
    global _warmed_key
    try:
        tts = _engine(language)
    except TtsUnavailable as exc:
        logger.warning("TTS unavailable for %s: %s", language, exc)
        return False
    if _warmed_key == _key(language):
        return True  # already spoken once since it was loaded
    try:
        with _lock:
            tts.generate(_warmup_text(language), sid=_SPEAKER_ID, speed=settings.tts_speed)
        _warmed_key = _key(language)
    except Exception as exc:  # pragma: no cover - warm-up is best-effort
        logger.warning("TTS warm synthesis failed for %s (non-fatal): %s", language, exc)
    return True


def synthesize(text: str, language: str) -> bytes:
    """Blocking — call via run_in_threadpool. Returns a 16-bit mono PCM WAV."""
    text = (text or "").strip()
    if not text:
        return b""

    global _warmed_key
    tts = _engine(language)
    with _lock:
        audio = tts.generate(text, sid=_SPEAKER_ID, speed=settings.tts_speed)
    _warmed_key = _key(language)

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

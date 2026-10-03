#!/usr/bin/env python3
"""Speech half of the golden set: STT accuracy/latency and TTS latency, measured
the way AFE-Learning-App's benchmark does (benchmarks/golden/run.mjs).

    python3 scripts/eval/speech_bench.py --answers apps/backend/logs/golden/<run>-warm

STT  Each golden question is spoken by the backend's own TTS voice (/api/tts),
     resampled to 16 kHz mono 16-bit -- what the browser sends -- and transcribed
     by /api/stt. `after_stop_ms` is that request's round trip: the backend
     decodes the whole clip after the mic closes, so this is what a student waits
     between stopping and seeing the text. AFE feeds a streaming recognizer in
     real time and times its finish(); same moment, different engine shape.
     WER is word edit distance over AFE's normalisation (lowercase, letters,
     digits and apostrophes). Synthesized speech is clean, single-voice audio, so
     WER is optimistic -- the same caveat AFE prints.
TTS  The answer from a golden run (--answers) is split into sentences exactly as
     AFE splits it, and each sentence is synthesized by /api/tts. `first_sentence_ms`
     is the first sentence's synthesis time, `rtf` = synthesis time / audio time.
     Times here include an HTTP round trip on loopback (~1-2 ms); AFE's are
     in-process calls.

Output: apps/backend/logs/golden/<timestamp>-speech/results.json and summary.md.
The models are already resident (the backend warms them at boot); their cold
load times are in the backend's startup log ("STT/TTS warm-up done in ...").
"""

from __future__ import annotations

import argparse
import io
import json
import re
import statistics
import sys
import time
import urllib.request
import wave
from array import array
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "docs" / "groundedness" / "afe-golden.json"
OUT_ROOT = ROOT / "apps" / "backend" / "logs" / "golden"
TARGET_RATE = 16000


def post(url: str, body: bytes, content_type: str) -> Tuple[bytes, float]:
    req = urllib.request.Request(url, data=body, headers={"Content-Type": content_type})
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    return data, (time.perf_counter() - started) * 1000


def tts(base: str, text: str, language: str) -> Tuple[bytes, float]:
    return post(
        "{}/api/tts?language={}".format(base, language),
        json.dumps({"text": text}).encode("utf-8"),
        "application/json",
    )


def wav_info(wav: bytes) -> Tuple[List[float], int]:
    with wave.open(io.BytesIO(wav), "rb") as wf:
        if wf.getsampwidth() != 2:
            raise ValueError("expected 16-bit PCM")
        channels, rate = wf.getnchannels(), wf.getframerate()
        pcm = array("h")
        pcm.frombytes(wf.readframes(wf.getnframes()))
    mono = [pcm[i] / 32768.0 for i in range(0, len(pcm), channels)]
    return mono, rate


def to_16k_wav(wav: bytes) -> Tuple[bytes, float]:
    """Linear resample to 16 kHz mono 16-bit, as AFE's readWav16k does."""
    mono, rate = wav_info(wav)
    seconds = len(mono) / rate
    if rate != TARGET_RATE:
        n = int(len(mono) * TARGET_RATE / rate)
        out = []
        for i in range(n):
            pos = i * rate / TARGET_RATE
            lo = int(pos)
            hi = min(lo + 1, len(mono) - 1)
            out.append(mono[lo] + (mono[hi] - mono[lo]) * (pos - lo))
        mono = out
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(TARGET_RATE)
        wf.writeframes(array("h", (max(-32768, min(32767, int(s * 32767))) for s in mono)).tobytes())
    return buf.getvalue(), seconds


def normalize_words(text: str) -> List[str]:
    """AFE's normalizeWords: lowercase, keep letters/digits/apostrophes."""
    return [w for w in re.split(r"\s+", re.sub(r"[^\w' ]+|_", " ", text.lower())) if w]


def edit_distance(ref: List[str], hyp: List[str]) -> int:
    prev = list(range(len(hyp) + 1))
    for i in range(1, len(ref) + 1):
        diag, prev[0] = prev[0], i
        for j in range(1, len(hyp) + 1):
            tmp = prev[j]
            prev[j] = min(prev[j] + 1, prev[j - 1] + 1, diag + (ref[i - 1] != hyp[j - 1]))
            diag = tmp
    return prev[len(hyp)]


def strip_markdown(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.M)
    text = re.sub(r"[*_`>|~]", "", text)
    text = re.sub(r"^\s*[-+]\s+", "", text, flags=re.M)
    return re.sub(r"\s+", " ", text).strip()


def run_stt(base: str, q: Dict[str, Any], language: str) -> Dict[str, Any]:
    spoken, _ = tts(base, q["question"], language)
    clip, seconds = to_16k_wav(spoken)
    body, ms = post("{}/api/stt?language={}".format(base, language), clip, "audio/wav")
    text = json.loads(body).get("text", "")
    ref, hyp = normalize_words(q["question"]), normalize_words(text)
    return {
        "source": "tts-synthetic",
        "audio_sec": round(seconds, 2),
        "after_stop_ms": round(ms, 1),
        "words": len(ref),
        "wer": round(edit_distance(ref, hyp) / len(ref), 3),
        "transcript": text,
    }


def run_tts(base: str, answer: str, language: str) -> Dict[str, Any]:
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", strip_markdown(answer)) if len(s) >= 3]
    synth_ms = audio_sec = 0.0
    first: Optional[float] = None
    for sentence in sentences:
        wav, ms = tts(base, sentence, language)
        mono, rate = wav_info(wav)
        first = ms if first is None else first
        synth_ms += ms
        audio_sec += len(mono) / rate
    return {
        "sentences": len(sentences),
        "first_sentence_ms": round(first, 1) if first is not None else None,
        "synth_ms": round(synth_ms, 1),
        "audio_sec": round(audio_sec, 2),
        "rtf": round(synth_ms / 1000 / audio_sec, 3) if audio_sec else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--answers", required=True, help="a golden run dir whose answers are spoken (results.json)")
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--language", default="English")
    ap.add_argument("--label", default="speech")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    questions = json.loads(GOLDEN.read_text())["questions"]
    answers = {r["id"]: r["answer"] for r in json.loads((Path(args.answers) / "results.json").read_text())}
    voice_note = ROOT / "apps" / "backend" / "models" / "tts" / args.language.lower() / "VOICE.txt"
    stt_model = "whisper-base.en (sherpa-onnx)"
    voice = voice_note.read_text().split(" ", 1)[0] if voice_note.exists() else args.language.lower()

    rows = []
    print("{:<4} {:>6} {:>9} {:>6}  {:>9} {:>8} {:>6}".format("id", "audio", "after stop", "WER", "1st sent", "synth", "rtf"))
    for q in questions:
        stt = run_stt(base, q, args.language)
        speech = run_tts(base, answers.get(q["id"], ""), args.language) if answers.get(q["id"]) else {}
        rows.append({"id": q["id"], "type": q["type"], "question": q["question"], "stt": stt, "tts": speech})
        print("{:<4} {:>5.1f}s {:>8.0f}ms {:>5.0f}%  {:>7}ms {:>7}ms {:>6}".format(
            q["id"], stt["audio_sec"], stt["after_stop_ms"], stt["wer"] * 100,
            speech.get("first_sentence_ms"), speech.get("synth_ms"), speech.get("rtf")))

    words = sum(r["stt"]["words"] for r in rows)
    summary = {
        "stt_model": stt_model,
        "tts_voice": voice,
        "answers_from": Path(args.answers).name,
        "wer_mean": round(statistics.mean(r["stt"]["wer"] for r in rows), 3),
        "words": words,
        "after_stop_ms_mean": round(statistics.mean(r["stt"]["after_stop_ms"] for r in rows), 1),
        "after_stop_ms_max": round(max(r["stt"]["after_stop_ms"] for r in rows), 1),
        "first_sentence_ms_mean": round(statistics.mean(r["tts"]["first_sentence_ms"] for r in rows if r["tts"]), 1),
        "rtf_mean": round(statistics.mean(r["tts"]["rtf"] for r in rows if r["tts"].get("rtf")), 3),
        "rtf_max": round(max(r["tts"]["rtf"] for r in rows if r["tts"].get("rtf")), 3),
    }
    out = OUT_ROOT / "{}-{}".format(datetime.now().strftime("%Y%m%dT%H%M%S"), args.label)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps({"summary": summary, "results": rows}, indent=2, ensure_ascii=False))
    (out / "summary.md").write_text(
        "# Speech run\n\nSTT `{stt_model}`: mean WER {w:.1f}% over {words} words; after stop mean "
        "{after_stop_ms_mean} ms, max {after_stop_ms_max} ms.\n\nTTS `{tts_voice}`: first sentence mean "
        "{first_sentence_ms_mean} ms; RTF mean {rtf_mean}, max {rtf_max}.\n".format(w=summary["wer_mean"] * 100, **summary)
    )
    print("\n" + json.dumps(summary, indent=2))
    print("Wrote {}".format(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

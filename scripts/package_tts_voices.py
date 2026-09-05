#!/usr/bin/env python3
"""Package Piper voices into the layout sherpa-onnx expects, for backend TTS.

Piper publishes its voices as plain ONNX (huggingface.co/rhasspy/piper-voices,
auditionable at https://rhasspy.github.io/piper-samples/), so this is
repackaging rather than model conversion — no torch, no training. Two things get
added on top of the upstream files:

  tokens.txt   from `phoneme_id_map` in the voice's .onnx.json
  metadata     the keys sherpa-onnx reads out of the ONNX itself; without
               `sample_rate` it refuses the model outright

espeak-ng-data is the phonemizer's dictionary set and is identical for every
voice, so it is fetched once and shared rather than copied per language.

Result, under apps/backend/models/tts/:

    espeak-ng-data/
    english/  model.onnx  tokens.txt
    hindi/    model.onnx  tokens.txt
    marathi/  model.onnx  tokens.txt

Adding a language: add an entry to VOICES and re-run. Folder names are the tutor
language lowercased, which is what app/services/tts.py looks up.

Usage:
    python scripts/package_tts_voices.py [language ...]      (default: all)
"""

from __future__ import annotations

import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

import onnx

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO_ROOT / "apps" / "backend" / "models" / "tts"

PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

# espeak-ng-data isn't published standalone, so it is lifted out of one of
# k2-fsa's own sherpa-onnx Piper bundles.
ESPEAK_SOURCE = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
    "vits-piper-hi_IN-priyamvada-medium.tar.bz2"
)

# language folder -> (path under piper-voices, voice stem, warm-up sentence)
#
# The warm-up sentence is written next to the voice as warmup.txt and spoken
# once into the void at boot. It has to be a real sentence in the language's own
# script: the first synthesis is what makes onnxruntime allocate its arenas and
# espeak load that voice's phoneme rules, and a token like "a" exercises neither
# for a Devanagari voice — the first real sentence would then pay for both.
#
# Indic voices Piper publishes today: hi, mr, te, ml, bn, ne, ur.
# No Piper voice exists for Tamil, Kannada, Gujarati, Punjabi, Odia or Assamese.
VOICES: dict[str, tuple[str, str, str]] = {
    # en_US-amy-low, not -medium: 'low' is a smaller/faster export of the same
    # voice, and English carries the most traffic.
    "english": (
        "en/en_US/amy/low",
        "en_US-amy-low",
        "Let's warm up the voice with a full sentence before the first answer.",
    ),
    "hindi": (
        "hi/hi_IN/priyamvada/medium",
        "hi_IN-priyamvada-medium",
        "पहले उत्तर से पहले आवाज़ को एक पूरे वाक्य से तैयार कर लेते हैं।",
    ),
    # 9-speaker model; the service synthesizes with speaker 0 (mrt_01523), the
    # one the Piper samples page plays.
    "marathi": (
        "mr/mr_IN/google/medium",
        "mr_IN-google-medium",
        "पहिल्या उत्तराआधी संपूर्ण वाक्याने आवाज तयार करून घेऊ.",
    ),
}


def _download(url: str, dest: Path) -> None:
    print(f"    downloading {url.rsplit('/', 1)[-1]} ...", flush=True)
    with urllib.request.urlopen(url) as response, open(dest, "wb") as out:
        shutil.copyfileobj(response, out)


def _fetch_voice_files(stem: str, remote_dir: str, work: Path) -> tuple[Path, Path]:
    """Returns (onnx, config), downloaded from Hugging Face."""
    onnx_path, cfg_path = work / f"{stem}.onnx", work / f"{stem}.json"
    _download(f"{PIPER_BASE}/{remote_dir}/{stem}.onnx", onnx_path)
    _download(f"{PIPER_BASE}/{remote_dir}/{stem}.onnx.json", cfg_path)
    return onnx_path, cfg_path


def _write_tokens(cfg: dict, dest: Path) -> None:
    """`<phoneme> <id>` per line.

    sherpa-onnx's Piper token reader takes exactly one codepoint per token, so
    multi-codepoint entries are skipped — in the Indic voices these are only the
    English diphthongs (aɪ aʊ ɔɪ eɪ oʊ) kept for loanwords. IDs stay correct
    because the file maps them explicitly rather than by position. Marathi has
    five; Hindi has none, which is why upstream never hit this.
    """
    skipped = []
    with open(dest, "w", encoding="utf-8") as f:
        for phoneme, ids in cfg["phoneme_id_map"].items():
            if len(phoneme) > 1:
                skipped.append(phoneme)
                continue
            f.write(f"{phoneme} {ids[0]}\n")
    total = len(cfg["phoneme_id_map"])
    note = f"  (skipped {' '.join(skipped)})" if skipped else ""
    print(f"    tokens.txt: {total - len(skipped)}/{total} phonemes{note}")


def _add_metadata(onnx_path: Path, cfg: dict, language: str) -> None:
    """sherpa-onnx reads these out of the ONNX; it aborts without sample_rate."""
    meta = {
        "model_type": "vits",
        "comment": "piper",
        "language": language,
        "voice": cfg["espeak"]["voice"],
        "has_espeak": 1,
        "n_speakers": cfg.get("num_speakers", 1),
        "sample_rate": cfg["audio"]["sample_rate"],
    }
    model = onnx.load(str(onnx_path))
    existing = {p.key for p in model.metadata_props}
    for key, value in meta.items():
        if key in existing:
            continue
        prop = model.metadata_props.add()
        prop.key, prop.value = key, str(value)
    onnx.save(model, str(onnx_path))
    print(f"    metadata: {meta['sample_rate']} Hz, {meta['n_speakers']} speaker(s)")


def ensure_espeak_data() -> None:
    dest = OUT_ROOT / "espeak-ng-data"
    if dest.is_dir():
        print("espeak-ng-data: already present")
        return
    print("espeak-ng-data: fetching (shared by every voice)")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / "bundle.tar.bz2"
        _download(ESPEAK_SOURCE, archive)
        with tarfile.open(archive, "r:bz2") as tar:
            tar.extractall(tmp_path)
        found = next(tmp_path.rglob("espeak-ng-data"), None)
        if found is None:
            raise SystemExit("espeak-ng-data not found inside the bundle")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(found, dest)
    print(f"    -> {dest}")


def package(language: str) -> None:
    remote_dir, stem, warmup = VOICES[language]
    out_dir = OUT_ROOT / language
    out_dir.mkdir(parents=True, exist_ok=True)

    # Cheap to (re)write, and lets an existing install pick up a changed phrase.
    (out_dir / "warmup.txt").write_text(warmup, encoding="utf-8")

    if (out_dir / "model.onnx").exists() and (out_dir / "tokens.txt").exists():
        print(f"{language}: already packaged")
        return

    print(f"{language}: packaging {stem}")
    with tempfile.TemporaryDirectory() as tmp:
        onnx_path, cfg_path = _fetch_voice_files(stem, remote_dir, Path(tmp))
        cfg = json.load(open(cfg_path, encoding="utf-8"))
        _write_tokens(cfg, out_dir / "tokens.txt")
        _add_metadata(onnx_path, cfg, language)
        shutil.copyfile(onnx_path, out_dir / "model.onnx")
    size = (out_dir / "model.onnx").stat().st_size / 1e6
    print(f"    -> {out_dir}  ({size:.0f} MB)")


def main() -> None:
    wanted = sys.argv[1:] or list(VOICES)
    unknown = [w for w in wanted if w not in VOICES]
    if unknown:
        raise SystemExit(
            f"unknown language(s): {', '.join(unknown)}. Known: {', '.join(VOICES)}"
        )
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    ensure_espeak_data()
    for language in wanted:
        package(language)
    print("\nDone. Voices in", OUT_ROOT)


if __name__ == "__main__":
    main()

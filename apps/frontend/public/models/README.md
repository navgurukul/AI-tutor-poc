# Piper voice models

Browser TTS runs entirely on-device from these files — one `.onnx` plus its
`.json` config per language. They are **not committed** (60–75 MB each); add
them locally before running the tutor screen.

| Language | Files | Notes |
| --- | --- | --- |
| English | `en_US-amy-low.onnx` / `.json` | `-low`, not `-medium`: on single-thread WASM the medium model runs ~200–300 ms per character, so a 100-char sentence took 20–30 s. Low is ~2–3× faster for the same voice. |
| Hindi | `hi_IN-priyamvada-medium.onnx` / `.json` | No `-low` export exists, so it stays on medium. |
| Marathi | `mr_IN-google-medium.onnx` / `.json` | 9-speaker model; the worker sends speaker 0 (`mrt_01523`). No `-low` export. |

## Where they come from

Voices live in <https://huggingface.co/rhasspy/piper-voices> and can be
auditioned first at <https://rhasspy.github.io/piper-samples/>.

Download a voice's two files, renaming the config from `<voice>.onnx.json` to
`<voice>.json` to match the naming used here:

```
curl -L -o mr_IN-google-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/mr/mr_IN/google/medium/mr_IN-google-medium.onnx
curl -L -o mr_IN-google-medium.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/mr/mr_IN/google/medium/mr_IN-google-medium.onnx.json
```

## Adding a language

1. Audition voices on the samples page above.
2. Drop the two files here.
3. Add a `piper` block to that language in `src/config/languages.ts`.

Nothing else changes — no new engine, no backend, no model conversion.

Indic voices currently published by Piper: Hindi, Marathi, Telugu, Malayalam,
Bengali, Nepali, Urdu. Tamil, Kannada, Gujarati, Punjabi, Odia and Assamese have
no Piper voice yet and would need a different source.

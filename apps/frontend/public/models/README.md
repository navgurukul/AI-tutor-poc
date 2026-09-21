Place the Piper voice model here:

- `indian-accent-60.onnx`
- `indian-accent-60.json`

Download from https://huggingface.co/navgurukul-ai/Indian_accent_60 — the repo's
`model.onnx` and `model.json`, renamed:

```bash
curl -L -o indian-accent-60.onnx \
  https://huggingface.co/navgurukul-ai/Indian_accent_60/resolve/main/model.onnx
curl -L -o indian-accent-60.json \
  https://huggingface.co/navgurukul-ai/Indian_accent_60/resolve/main/model.json
```

sha256, verified against the repo's LFS oids:

```
5fa27435a7759c77a9b10c1ef7ce6a0bb14e3f10c1c1b2d2ee9c008a673a6ca7  indian-accent-60.onnx
fc1c99f3a7f2aa00e1986de5ab3203787007aa6e63bef406674d605448f9e1a6  indian-accent-60.json
```

A standard Piper voice — espeak `en-us`, one speaker, 22050 Hz — so it is a
drop-in for the `en_US-amy-medium` voice this replaced (Rhasspy's, from
https://rhasspy.github.io/piper-samples/). The config ships `length_scale: 1.2`
against amy's 1.0, i.e. it speaks about 20% slower; lower it here if that costs
too much on the time-to-audio budget.

**Licence is unspecified upstream** — the HF repo carries no LICENSE file and no
licence tag. Resolve that before any fleet rollout; see `packaging/README.md`.

These files are not committed to the repo — add them locally before running the
tutor screen. The names come from `VITE_VOICE_MODEL_URL` / `VITE_VOICE_CONFIG_URL`
(`apps/frontend/src/config/voice.ts`).

# AI Tutor

A proof-of-concept offline AI tutor for low-spec devices. Speak a question into the
mic and get a spoken answer back, powered by on-device speech-to-text and Piper TTS.

See [apps/frontend/README.md](apps/frontend/README.md) for the full project overview,
architecture, and backend API contract.

## Installation

**Prerequisites:** Node.js 18+, npm, and Google Chrome or Microsoft Edge installed.

From the repo root, on Windows:

```powershell
powershell -File scripts\setup.ps1
```

This installs dependencies for `apps/frontend` and `apps/desktop`, creates
`apps/frontend/.env` (mock API mode on, so no backend is needed to try it), and
downloads the Piper voice model files. Safe to re-run — each step is skipped if
already done.

## Run

```bash
cd apps/desktop
npm start
```

Opens the AI Tutor in a borderless window.

## Rebuild after code changes

```powershell
powershell -File scripts\build.ps1
```

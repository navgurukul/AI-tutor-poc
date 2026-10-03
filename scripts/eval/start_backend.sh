#!/usr/bin/env bash
# Start the backend for a golden-set run with the code's own generation settings.
# Environment variables beat apps/backend/.env, so a developer's .env (model,
# temperature, max tokens, ...) cannot leak into a measurement; everything else is
# whatever the code currently does. Each comparison stage is a code change, and the
# golden runner records the options and prompt actually sent with every turn.
#
#   scripts/eval/start_backend.sh
#   python3 scripts/eval/golden_latency.py --label <stage>     # cold + warm passes
set -euo pipefail
cd "$(dirname "$0")/../../apps/backend"

export OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3.5:2b-q4_K_M}"   # the model AFE benchmarks with
export TEMPERATURE=0.3
export MAX_TOKENS=512
export NUM_CTX=4096
export TURN_DETAIL_LOG=true
export WARM_MODEL_ON_STARTUP=true

echo "==> backend: model=$OLLAMA_MODEL temp=$TEMPERATURE max_tokens=$MAX_TOKENS num_ctx=$NUM_CTX"
exec ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}"

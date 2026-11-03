#!/bin/bash
# Run a Harbor job config against the public Anthropic API with the key in evals/.env:  evals/run.sh evals/configs/cc.yaml
# (append --install-only to check trial setup without model calls). Unsets ANTHROPIC_BASE_URL / CLAUDE_CODE_OAUTH_SCOPES:
# inside Claude Code / the desktop app these point at the host's own proxy; Harbor would forward them into the sandbox
# and keep the "anthropic/" model prefix → 404.
set -euo pipefail
cd "$(dirname "$0")/.."
# host runtimes the configs bind-mount (Claude Code binary; databook for cc-p-t); docker compose expands these vars
export EVALS_DIR="$PWD/evals" EVALS_RT="$PWD/evals/.cache/runtime"
uv run -q python evals/agents/prefetch.py "$1"
exec env -u ANTHROPIC_BASE_URL -u CLAUDE_CODE_OAUTH_SCOPES harbor run -c "$1" --env-file evals/.env "${@:2}"

#!/usr/bin/env bash
# scripts/run-dash.sh — the Headlong dashboard: watch a mind think.
#
# Served over state/, which is where this project keeps its identities, so the
# scan stays small (pointing it at the repo root would walk node_modules).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p state/logs
exec headlong/tools/headlong-web "$(pwd)/state" --port "${HEADLONG_DASH_PORT:-8080}" \
    2>&1 | tee -a state/logs/dash.log

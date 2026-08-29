#!/usr/bin/env bash
# scripts/run-bridge.sh — run the bridge for one or more identities.
#
#   ./scripts/run-bridge.sh ada
#   ./scripts/run-bridge.sh ada bob --experiment discovery
#
# Logs to state/logs/bridge.log. Unbuffered: python buffers stdout when it is
# not a tty, which makes a backgrounded bridge look silent when it is working.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p state/logs
exec env PYTHONPATH=bridge/src python3 -u -m headlong_town.cli "$@" \
    2>&1 | tee -a state/logs/bridge.log

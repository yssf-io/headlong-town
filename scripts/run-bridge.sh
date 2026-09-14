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

# Load .env so the bridge can see OPENROUTER_API_KEY, which it uses only to
# read the key's spend for the town's budget readout. Without this the bridge
# runs fine but that readout stays blank forever, which is a confusing way to
# fail for the one number this project has twice been caught out by.
# Existing environment wins, and `set -a` only exports what the file assigns.
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

exec env PYTHONPATH=bridge/src python3 -u -m headlong_town.cli "$@" \
    2>&1 | tee -a state/logs/bridge.log

#!/usr/bin/env bash
# scripts/restart-mind.sh <identity> — stop a mind cleanly and start it again.
#
# Does the parts that are easy to forget and fail confusingly:
#
#  1. Stops the dispatcher.
#  2. Reaps orphaned shellm runs. The bridge wakes thinkers directly (PLAN §3),
#     and those runs sit outside the dispatcher's process tree, so
#     `thinkers stop --force` cannot see them.
#  3. Clears a stale shellm env. headlong-killall removes the container but
#     leaves the env metadata pointing at it, and shellm then refuses every run
#     with "Env <name> was created without a mount for this run's workdir".
#  4. Starts the thinkers again.
#
# Run the bridge BEFORE this: thinkers inherit the dispatcher's environment, and
# a dispatcher started first pins a stale TOWN_URL for its whole life.
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="${1:?usage: restart-mind.sh <identity>}"
# shellcheck disable=SC1091
source scripts/agent-env.sh
DIR="$TOWN_IDENTITIES/$NAME"
[[ -d "$DIR" ]] || { echo "no identity '$NAME'" >&2; exit 1; }

# `activate` greps info.txt for optional keys, and a grep that finds nothing
# returns 1 -- which under `set -e` aborts this script silently, mid-source.
set +e
# shellcheck disable=SC1090
source "$DIR/activate" >/dev/null 2>&1
set -e

echo "==> stopping thinkers"
thinkers stop --force >/dev/null 2>&1 || true
sleep 2

echo "==> reaping orphaned shellm runs"
pkill -f "shellm" 2>/dev/null || true
sleep 1
printf '    %s still alive\n' "$(pgrep -f shellm | wc -l | tr -d ' ')"

echo "==> clearing stale shellm env"
rm -rf "$DIR/.shellm/envs/$NAME"

echo "==> starting thinkers"
# ONLY the responder runs under the dispatcher. The bridge owns monolith wakes
# outright -- two independent wake sources raced to create the docker env and
# wedged every subsequent run. See PLAN §14.
thinkers start responder 2>&1 | tail -2

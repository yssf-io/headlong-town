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
# NOT `pkill -f shellm`: that matches any process whose command line merely
# CONTAINS the word -- including the shell running this script, or a caller
# that mentioned "shellm-" in an argument. It has killed the caller twice.
# Match the binary path, and never signal ourselves or our ancestors.
_self_tree=" $$ $PPID "
for _pid in $(pgrep -f "bin/shellm" 2>/dev/null); do
    case "$_self_tree" in *" $_pid "*) continue ;; esac
    kill "$_pid" 2>/dev/null || true
done
sleep 1
printf '    %s still alive\n' "$(pgrep -f "bin/shellm" | wc -l | tr -d ' ')"

echo "==> clearing stale shellm env"
rm -rf "$DIR/.shellm/envs/$NAME"

echo "==> starting thinkers"
# Which thinkers run under the dispatcher depends on the experiment's wake mode
# (TOWN_WAKE_MODE, set from [bridge].wake by scripts/experiment).
#
#   bridge      ONLY the responder. The bridge owns monolith wakes outright --
#               two independent wake sources raced to create the docker env and
#               wedged every subsequent run. See PLAN §14.
#   dispatcher  Everything, which is headlong's own design: the dispatcher
#               fires thinkers from trajectory steps and the monolith paces
#               itself via run/<name>.wake_at. The bridge must then NOT wake
#               anything, or the same two-source race returns.
if [[ "${TOWN_WAKE_MODE:-dispatcher}" == "dispatcher" ]]; then
    thinkers start 2>&1 | tail -3
    # Bootstrap the monolith. It subscribes trigger_self:false, and the
    # dispatcher's liveness watchdog covers only trigger_self thinkers
    # ("reactive thinkers are legitimately silent for long stretches"), so a
    # freshly started monolith has no wake_at armed and no wake source. It
    # fires on the first external step -- but a quiet town produces none, and
    # the bridge's embodiment observation can land before this dispatcher even
    # exists. One documented manual trigger starts it; from there its EXIT trap
    # arms the next wake every time, and the dispatcher owns the clock.
    # Backgrounded: `thinkers step` runs the step to completion, which is
    # minutes, and `up` must not block on a mind thinking.
    echo "==> bootstrapping the monolith (dispatcher owns the clock from here)"
    nohup thinkers step monolith >/dev/null 2>&1 &
    disown 2>/dev/null || true
else
    thinkers start responder 2>&1 | tail -2
fi

# scripts/agent-env.sh — source this to work with the town's Headlong agents.
#
#   source scripts/agent-env.sh
#   identity list
#
# Everything is project-local on purpose: no installer, no ~/.local/bin
# symlinks, no ~/.headlong. headlong/ is a pinned submodule and its tools run
# straight from the checkout (`identity` resolves bundled thinkers and skills
# relative to its own path), so the whole agent state is disposable and lives
# under state/.
#
# Note: headlong overloads IDENTITY_DIR -- to `identity` it means the directory
# *containing* identities, but inside a running thinker it means one identity's
# own directory. We pass --dir explicitly rather than exporting it, so the two
# meanings never collide.

_town_root="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"

export HEADLONG_HOME="$_town_root/state/headlong"
export TOWN_IDENTITIES="$_town_root/state/identities"
export PATH="$_town_root/town:$_town_root/headlong/bin:$_town_root/headlong/tools:$PATH"

mkdir -p "$HEADLONG_HOME" "$TOWN_IDENTITIES"

# `identity` and `thinkers` both want the identities dir; alias it in so we
# never forget the flag.
town-identity() { identity --dir "$TOWN_IDENTITIES" "$@"; }

unset _town_root

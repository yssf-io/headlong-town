#!/usr/bin/env python3
"""Expose the `town` CLI to a mind's sandbox, by absolute path.

shellm only mounts binaries passed with --bin, and the thinker lib builds that
list by running `command -v` over a fixed set of names. That resolves against
the PATH of whichever process launched the thinker -- and the dispatcher and the
bridge each build their own -- so a mind's body silently vanished from its
sandbox depending on who woke it. An absolute path cannot vary that way.

Usage: _expose-town-bin.py <identity-thinker-lib> <abs-path-to-town>
"""
import pathlib
import sys

lib = pathlib.Path(sys.argv[1])
town = sys.argv[2]
s = lib.read_text()

if "TOWN_BIN_ABS" in s:
    print("already exposed")
    raise SystemExit(0)

anchor = '''    for cmd in mem traj skills context llm shellm chat glob view put sub; do
        local path
        path=$(command -v "$cmd" 2>/dev/null) || continue
        printf '%s\\n' "--bin" "$path"
    done'''
if anchor not in s:
    print("thinker lib does not have the expected --bin loop", file=sys.stderr)
    raise SystemExit(1)

addition = (
    anchor
    + "\n\n"
    + "    # TOWN_BIN_ABS -- the town CLI by absolute path, not via PATH.\n"
    + "    # See scripts/_expose-town-bin.py for why.\n"
    + '    [[ -x "%s" ]] && printf \'%%s\\n\' "--bin" "%s"\n' % (town, town)
)
lib.write_text(s.replace(anchor, addition, 1))
print("exposed")

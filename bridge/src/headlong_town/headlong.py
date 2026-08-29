"""Talking to one Headlong identity.

Everything goes through headlong's own CLI (`chat`, `traj`) rather than writing
trajectory JSONL directly: step ids, timestamps and blob spilling stay
headlong's business, and the bridge stays a pure client of the format. This is
the same discipline slack/ and telegram/ follow.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class Identity:
    def __init__(self, repo_root: Path, identities_dir: Path, name: str):
        self.name = name
        self.repo_root = repo_root
        self.dir = identities_dir / name
        if not (self.dir / "activate").is_file():
            raise SystemExit(f"no identity {name!r} at {self.dir}")
        self._env = {
            **os.environ,
            "PATH": f"{repo_root/'headlong'/'bin'}:{repo_root/'headlong'/'tools'}:"
                    + os.environ.get("PATH", ""),
            "HEADLONG_HOME": str(repo_root / "state" / "headlong"),
        }

    def _run(self, script: str, stdin: str | None = None) -> subprocess.CompletedProcess:
        # `activate` must be sourced, and sourcing it bare picks an expensive
        # default model -- but that only affects thinkers, not chat/traj.
        wrapped = f'source "{self.dir}/activate" >/dev/null 2>&1 || exit 1\n{script}'
        return subprocess.run(
            ["bash", "-c", wrapped],
            env=self._env,
            input=stdin,
            capture_output=True,
            text=True,
        )

    # -- reading --------------------------------------------------------------

    @property
    def trajectory(self) -> Path:
        info: dict[str, str] = {}
        info_txt = self.dir / "info.txt"
        if info_txt.is_file():
            for line in info_txt.read_text().splitlines():
                key, _, value = line.partition("=")
                if value:
                    info[key.strip()] = value.strip()
        root = self.dir / "trajectories"
        prefix = info.get("root_trajectory", "")[:8]
        if prefix:
            for match in sorted(root.glob(f"{prefix}-*")):
                if (match / "trajectory.jsonl").is_file():
                    return match / "trajectory.jsonl"
        for candidate in sorted(root.iterdir()):
            if (candidate / "trajectory.jsonl").is_file():
                return candidate / "trajectory.jsonl"
        raise SystemExit(f"no trajectory.jsonl under {root}")

    # -- writing --------------------------------------------------------------

    def deliver_message(self, from_name: str, text: str) -> bool:
        """Someone in the town spoke to this mind. Wakes the responder.

        `chat send` reads the body from stdin when given no positional text, so
        the message never goes through argv -- no quoting hazards, no length
        limit, and it stays out of `ps`.
        """
        result = self._run(
            f"chat send --from {shlex.quote(from_name)} --to {shlex.quote(self.name)}",
            stdin=text,
        )
        if result.returncode != 0:
            log.error("chat send failed for %s: %s", from_name, result.stderr.strip()[:300])
            return False
        return True

    def append(self, step: dict[str, Any]) -> bool:
        """Append an arbitrary step (an observation, usually). Wakes the monolith."""
        result = self._run("traj append >/dev/null", stdin=json.dumps(step))
        if result.returncode != 0:
            log.error("traj append failed: %s", result.stderr.strip()[:300])
            return False
        return True

    def observe(self, content: str, **town: Any) -> bool:
        """Record a world event as an observation the mind will wake on."""
        step: dict[str, Any] = {"type": "observation", "content": content, "source": "town"}
        if town:
            step["town"] = town
        return self.append(step)

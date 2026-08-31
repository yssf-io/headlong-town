"""An experiment: what to run, and with what settings.

The repo ships the apparatus and sensible defaults. An *experiment* is the
researcher's own data -- a roster, some personas, a few overrides -- and lives
in a gitignored directory, because a run of this town is a research artifact
rather than part of the software.

So everything here has a working default EXCEPT the two things nobody can
choose on your behalf: which minds live in the town, and which stock AI Town
characters (if any) live alongside them.

    experiments/<name>/
      experiment.toml
      personas/<mind>.md

See experiments.example/ for a documented spec.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ExperimentError(RuntimeError):
    """The spec is missing, malformed, or missing something required."""


@dataclass
class Mind:
    name: str
    persona: Path | None
    model: str


@dataclass
class Experiment:
    name: str
    root: Path
    description: str = ""
    minds: list[Mind] = field(default_factory=list)
    stock_agents: list[str] = field(default_factory=list)

    # --- defaults: tuned, overridable, never required of the researcher -----
    # A wakeup is one function; the cap only catches a model that will not
    # conclude (measured: median 2 iterations, p99 10, max 13).
    max_iterations: int = 20
    # Someone this close is "near you" and worth noticing.
    proximity_range: float = 6.0
    # Don't start a fresh agentic run more often than this from perception.
    monolith_wake_cooldown: float = 30.0
    # How often to remind a stationary mind that it agreed to meet someone.
    meet_nudge_cooldown: float = 45.0
    # How long a quiet mind waits before thinking on its own again.
    spontaneity_interval: float = 90.0
    model: str = "deepseek/deepseek-v4-flash-0731"

    @property
    def mind_names(self) -> list[str]:
        return [m.name for m in self.minds]


def load(path: Path) -> Experiment:
    """Read experiments/<name>/experiment.toml."""
    root = path if path.is_dir() else path.parent
    spec_file = root / "experiment.toml" if path.is_dir() else path
    if not spec_file.is_file():
        raise ExperimentError(
            f"no experiment.toml at {spec_file}. "
            f"Copy experiments.example/ to get started."
        )
    try:
        raw: dict[str, Any] = tomllib.loads(spec_file.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ExperimentError(f"{spec_file}: {exc}") from exc

    name = raw.get("name") or root.name
    exp = Experiment(name=name, root=root, description=raw.get("description", ""))

    bridge = raw.get("bridge") or {}
    for key in (
        "max_iterations", "proximity_range", "monolith_wake_cooldown",
        "meet_nudge_cooldown", "spontaneity_interval", "model",
    ):
        if key in bridge:
            setattr(exp, key, bridge[key])

    world = raw.get("world") or {}
    exp.stock_agents = list(world.get("stock_agents") or [])

    minds = raw.get("minds") or []
    if not minds:
        raise ExperimentError(
            f"{spec_file}: at least one [[minds]] entry is required -- who lives "
            f"in this town is yours to choose, not something to default."
        )
    for entry in minds:
        mind_name = entry.get("name")
        if not mind_name:
            raise ExperimentError(f"{spec_file}: every [[minds]] entry needs a name")
        persona = entry.get("persona")
        persona_path = None
        if persona:
            persona_path = (root / persona).resolve()
            if not persona_path.is_file():
                raise ExperimentError(
                    f"{spec_file}: persona for {mind_name!r} not found at {persona_path}"
                )
        exp.minds.append(
            Mind(name=mind_name, persona=persona_path, model=entry.get("model", exp.model))
        )
    return exp

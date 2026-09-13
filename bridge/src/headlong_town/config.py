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
    # How hard the model thinks before answering. headlong defaults to "high",
    # which suits a general agent; a townsperson mostly looks, decides and acts.
    # This is the lever on all three of: seconds per wakeup (~95% of a run is
    # waiting on the model), tokens burned per call, and spend per day.
    # Who wakes the thinkers.
    #   "dispatcher" — headlong's own flow, and the default. The bridge only
    #                  appends steps; the dispatcher notices them and fires the
    #                  right thinker, and the monolith paces itself by writing
    #                  run/<name>.wake_at with exponential backoff
    #                  (design/monolith_backoff.md) -- 0 while engaged, backing
    #                  off to a cap while nothing happens.
    #   "bridge"      — the bridge appends a step AND runs the thinker itself,
    #                  on a fixed spontaneity timer. This was the default until
    #                  2026-09-04, chosen after headlong's dispatcher silently
    #                  stopped delivering steps (macOS, bash 3.2; root cause
    #                  never found, PLAN §13). It does not reproduce on Linux
    #                  with bash 5.3 -- verified over two full wake cycles --
    #                  but macOS still ships bash 3.2, so this stays as an
    #                  escape hatch rather than being deleted.
    #
    # "bridge" costs the dispatcher's guarantees, and this project had to
    # reimplement all of them badly: busy-thinker refusal, process ownership,
    # and not handing a thinker back its own step (which deadlocked a mind for
    # 13 hours). Prefer "dispatcher" unless it demonstrably fails for you.
    wake: str = "dispatcher"
    # Pin OpenRouter to specific upstream host(s), comma-separated slugs, via
    # Headlong's LLM_OR_ONLY. Empty means "let OpenRouter choose".
    #
    # This matters more than it looks. OpenRouter fans one model id out over
    # many hosts and picks one PER REQUEST -- 28 of them serve
    # deepseek-v4-flash-0731 -- and each host has its own prompt cache. Measured
    # unpinned over 2272 calls: 64% of calls got zero cached input, while the
    # ones that did hit reached 100%. A prefix cached on one host is worthless
    # on the next. Cached input is priced 5-30x below fresh input, so scattering
    # the cache is most of what a long-lived identity pays for.
    #
    # The hosts also differ in quantization (fp4 / fp8 / bf16), so an unpinned
    # run is not one model -- it is a different one per call.
    #
    # An unsatisfiable pin 404s rather than silently rerouting, which is the
    # behaviour you want.
    provider_only: str = ""
    effort: str = "high"
    # Ceiling on ONE response. Reasoning tokens count against it, so a mind that
    # ruminates can spend the whole budget thinking and return nothing at all --
    # observed at 16384, which truncated and then failed empty. Note the ceiling
    # is also charged against your key's remaining credit up front: a limit
    # larger than you can afford makes every call fail outright.
    max_tokens: int = 32768

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
        "effort", "max_tokens", "wake", "provider_only",
    ):
        if key in bridge:
            setattr(exp, key, bridge[key])

    if exp.wake not in ("bridge", "dispatcher"):
        raise ExperimentError(
            f"[bridge] wake must be \"bridge\" or \"dispatcher\" (got {exp.wake!r})"
        )

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

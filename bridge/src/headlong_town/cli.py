"""headlong-town-bridge — run the bridge for one or more minds."""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import secrets
import subprocess
import signal
import sys
import time
import urllib.request
from pathlib import Path

from .agent import Agent
from .commands import COMMANDS
from . import config as expconfig
from . import control
from .convexclient import ConvexClient, ConvexError
from .headlong import Identity
from .world import World

log = logging.getLogger("bridge")

DEFAULT_DESCRIPTION = (
    "A person who lives in this town. You do not know anything about them yet."
)


def _ensure_token(state_dir: Path) -> str:
    """A stable per-identity token, so restarting the bridge does not break a
    `town` CLI already installed in an identity's environment."""
    state_dir.mkdir(parents=True, exist_ok=True)
    token_file = state_dir / "token"
    if token_file.is_file():
        token = token_file.read_text().strip()
        if token:
            return token
    token = secrets.token_urlsafe(24)
    token_file.write_text(token)
    token_file.chmod(0o600)
    return token


def _sandbox_host() -> str:
    """How a mind's Docker sandbox reaches this host.

    `host.docker.internal` is a Docker Desktop convenience and does NOT resolve
    on Linux, where the host is the bridge network's gateway instead. Getting
    this wrong is quiet: the mind simply reports the town unreachable and
    carries on without a body it can act through.

    On Linux the gateway also has to be allowed through the firewall --
    `ufw allow from <docker subnet> to any port <port> proto tcp`.
    """
    if platform.system() != "Linux":
        return "host.docker.internal"
    try:
        out = subprocess.run(
            ["docker", "network", "inspect", "bridge",
             "-f", "{{range .IPAM.Config}}{{.Gateway}}{{end}}"],
            capture_output=True, text=True, timeout=10,
        )
        gateway = out.stdout.strip()
        if gateway:
            return gateway
    except (OSError, subprocess.SubprocessError):
        pass
    return "172.17.0.1"  # Docker's default bridge gateway


def _install_town_env(identity: Identity, token: str, port: int) -> None:
    """Give the mind's shell what `town` needs.

    Written into the identity's own .env, which thinkers/_lib/common.sh loads
    into every thinker (and therefore into generated code) without any change to
    headlong itself.
    """
    env_file = identity.dir / ".env"
    wanted = {
        "TOWN_URL": f"http://{_sandbox_host()}:{port}",
        "TOWN_TOKEN": token,
    }
    existing: dict[str, str] = {}
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            key, _, value = line.partition("=")
            if value:
                existing[key.strip()] = value.strip()
    if all(existing.get(k) == v for k, v in wanted.items()):
        return
    existing.update(wanted)
    env_file.write_text("".join(f"{k}={v}\n" for k, v in sorted(existing.items())))
    env_file.chmod(0o600)


def _openrouter_budget() -> tuple[float | None, float | None]:
    """Ask OpenRouter what this key has spent. Best-effort and quiet.

    The number that most often mattered and was never on screen: this project
    has twice woken up to a town that stopped overnight on an exhausted key,
    with every log reading normal.
    """
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None, None
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp).get("data") or {}
        spent = data.get("usage")
        return (float(spent) if spent is not None else None), (
            float(data["limit"]) if data.get("limit") is not None else None
        )
    except Exception:
        log.debug("budget probe failed", exc_info=True)
        return None, None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="headlong-town-bridge")
    parser.add_argument("identities", nargs="+", help="identity names to embody")
    parser.add_argument("--experiment", default=os.environ.get("TOWN_EXPERIMENT") or None)
    parser.add_argument("--spec", default=None,
                        help="path to an experiment dir; supplies tuning and the roster")
    parser.add_argument("--convex-url", default=os.environ.get("CONVEX_URL", "http://127.0.0.1:3210"))
    parser.add_argument("--root", default=None, help="repo root (default: inferred)")
    parser.add_argument("--interval", type=float, default=1.0, help="poll seconds")
    parser.add_argument("--control-port", type=int, default=int(os.environ.get("TOWN_PORT", "8081")))
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[3]
    identities_dir = root / "state" / "identities"

    convex = ConvexClient(args.convex_url)
    world = World(convex, args.experiment)
    try:
        log.info(
            "world %s (experiment=%s)", world.world_id, args.experiment or "default"
        )
    except (ConvexError, RuntimeError) as exc:
        log.error("%s", exc)
        return 1

    # An experiment supplies tuning (and, via the runner, the roster). Without
    # one the shipped defaults apply, so a bare `run-bridge.sh ada` still works.
    tuning = None
    if args.spec:
        try:
            tuning = expconfig.load(Path(args.spec))
            log.info("experiment %s: %s", tuning.name, tuning.description or "(no description)")
        except expconfig.ExperimentError as exc:
            log.error("%s", exc)
            return 1

    registry = control.Registry()
    agents = []
    for name in args.identities:
        identity = Identity(root, identities_dir, name)
        state_dir = root / "state" / "bridge" / name
        agent = Agent(identity, world, state_dir, tuning=tuning)
        agent.ensure_body(DEFAULT_DESCRIPTION)
        agents.append(agent)

        # One bearer token per identity, and the control plane derives WHICH
        # identity from the token. A mind runs arbitrary bash, so a request that
        # simply named its own identity would let any agent act as any other.
        token = _ensure_token(state_dir)
        registry.register(token, agent)
        _install_town_env(identity, token, args.control_port)
        log.info("embodying %s", name)

    control.serve(registry, COMMANDS, port=args.control_port)

    stopping = False

    def _stop(_signum, _frame):
        nonlocal stopping
        stopping = True
        log.info("stopping")

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    # Well inside IDLE_WORLD_TIMEOUT (5 min) without hammering the mutation.
    heartbeat_every = 30.0
    last_heartbeat = 0.0
    # Budget is per API key, so one probe serves every mind. Slow on purpose:
    # it is an HTTP call to the provider, and the number moves in cents.
    budget_every = 120.0
    # Negative so the first tick probes immediately: time.monotonic() starts
    # near zero, so a 0.0 here leaves the readout blank for the first interval
    # after every restart -- exactly when someone is looking at it.
    last_budget = -budget_every

    while not stopping:
        now = time.monotonic()
        if now - last_heartbeat > heartbeat_every:
            last_heartbeat = now
            try:
                world.heartbeat()
            except ConvexError as exc:
                log.warning("heartbeat: %s", exc)

        if now - last_budget > budget_every:
            last_budget = now
            spent, limit = _openrouter_budget()
            if spent is not None:
                world.report_budget(spent, limit)

        for agent in agents:
            try:
                agent.poll_town()
                agent.poll_mind()
                agent.tick_spontaneity()
                agent.push_health()
            except ConvexError as exc:
                # A backend blip must not kill the bridge; the next tick retries.
                log.warning("convex: %s", exc)
            except Exception:
                log.exception("agent %s failed this tick", agent.identity.name)
        time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    sys.exit(main())

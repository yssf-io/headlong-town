"""headlong-town-bridge — run the bridge for one or more minds."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

from .agent import Agent
from .convexclient import ConvexClient, ConvexError
from .headlong import Identity
from .world import World

log = logging.getLogger("bridge")

DEFAULT_DESCRIPTION = (
    "A person who lives in this town. You do not know anything about them yet."
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="headlong-town-bridge")
    parser.add_argument("identities", nargs="+", help="identity names to embody")
    parser.add_argument("--experiment", default=os.environ.get("TOWN_EXPERIMENT") or None)
    parser.add_argument("--convex-url", default=os.environ.get("CONVEX_URL", "http://127.0.0.1:3210"))
    parser.add_argument("--root", default=None, help="repo root (default: inferred)")
    parser.add_argument("--interval", type=float, default=1.0, help="poll seconds")
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

    agents = []
    for name in args.identities:
        identity = Identity(root, identities_dir, name)
        agent = Agent(identity, world, root / "state" / "bridge" / name)
        agent.ensure_body(DEFAULT_DESCRIPTION)
        agents.append(agent)
        log.info("embodying %s", name)

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

    while not stopping:
        now = time.monotonic()
        if now - last_heartbeat > heartbeat_every:
            last_heartbeat = now
            try:
                world.heartbeat()
            except ConvexError as exc:
                log.warning("heartbeat: %s", exc)

        for agent in agents:
            try:
                agent.poll_town()
                agent.poll_mind()
            except ConvexError as exc:
                # A backend blip must not kill the bridge; the next tick retries.
                log.warning("convex: %s", exc)
            except Exception:
                log.exception("agent %s failed this tick", agent.identity.name)
        time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    sys.exit(main())

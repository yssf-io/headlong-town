"""The control plane the `town` CLI talks to.

A mind acts on the world by running `town ...` in its own shell, which is one
HTTP call to this server, which becomes one engine input. The bridge is the
only thing that knows the identity -> playerId mapping, so the CLI never has to
carry a player id it could tamper with.

Authorisation is a per-identity bearer token, and the identity is derived FROM
the token rather than taken from the request. A Headlong mind runs arbitrary
bash, so a request that names its own identity would let any agent act as any
other -- and agents talking each other into things is a dynamic we want to
observe socially, not one we want available as an API call.
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

log = logging.getLogger(__name__)


class Registry:
    """Identity tokens and the agents they act for."""

    def __init__(self) -> None:
        self._by_token: dict[str, Any] = {}
        self._lock = threading.Lock()

    def register(self, token: str, agent: Any) -> None:
        with self._lock:
            self._by_token[token] = agent

    def agent_for(self, token: str | None) -> Any | None:
        if not token:
            return None
        with self._lock:
            return self._by_token.get(token)


class _Handler(BaseHTTPRequestHandler):
    registry: Registry
    commands: dict[str, Callable[[Any, dict[str, Any]], Any]]

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        log.debug("control: " + fmt, *args)

    def _reply(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        command = self.path.strip("/")
        handler = self.commands.get(command)
        if handler is None:
            self._reply(404, {"ok": False, "error": f"no such command: {command}"})
            return

        token = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        agent = self.registry.agent_for(token)
        if agent is None:
            self._reply(401, {"ok": False, "error": "unknown or missing token"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
            args = json.loads(self.rfile.read(length) or b"{}") if length else {}
        except (ValueError, json.JSONDecodeError) as exc:
            self._reply(400, {"ok": False, "error": f"bad request body: {exc}"})
            return

        try:
            result = handler(agent, args)
        except TownRefusal as exc:
            # A deliberate "no", not a crash: the mind gets told why, in words
            # it can act on.
            self._reply(409, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001
            log.exception("control command %s failed", command)
            self._reply(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            return

        self._reply(200, {"ok": True, **(result if isinstance(result, dict) else {"text": result})})


class TownRefusal(RuntimeError):
    """The world says no, for a reason the mind should hear."""


def serve(
    registry: Registry,
    commands: dict[str, Callable[[Any, dict[str, Any]], Any]],
    host: str = "0.0.0.0",  # noqa: S104 — see the note in serve()
    port: int = 8081,
) -> ThreadingHTTPServer:
    # Bound beyond loopback on purpose: a mind's generated code runs inside a
    # Docker sandbox, where 127.0.0.1 is the *container's* loopback, so a
    # host-loopback server is unreachable to the only caller that matters. Every
    # request needs a per-identity bearer token. Revisit when agents move into
    # microVMs with their own network (PLAN.md §10).
    handler = type("Handler", (_Handler,), {"registry": registry, "commands": commands})
    server = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, name="town-control", daemon=True)
    thread.start()
    log.info("control plane on http://%s:%d", host, port)
    return server

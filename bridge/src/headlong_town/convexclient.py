"""Minimal Convex client over the HTTP API.

Deliberately dependency-free: self-hosted Convex exposes /api/query and
/api/mutation, which is everything the bridge needs. A real subscription
client would be better for perception (PLAN.md §3) but polling is honest for
M1 and removes a dependency we would otherwise have to pin.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class ConvexError(RuntimeError):
    pass


class ConvexClient:
    def __init__(self, url: str, timeout: float = 15.0):
        self.url = url.rstrip("/")
        self.timeout = timeout

    def _call(self, kind: str, path: str, args: dict[str, Any]) -> Any:
        body = json.dumps({"path": path, "args": args, "format": "json"}).encode()
        req = urllib.request.Request(
            f"{self.url}/api/{kind}",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read())
        except urllib.error.URLError as exc:  # network, DNS, refused, timeout
            raise ConvexError(f"{kind} {path}: {exc}") from exc
        # Convex answers 200 with status:error for application errors, so the
        # HTTP status alone never tells you whether the call worked.
        if payload.get("status") != "success":
            raise ConvexError(f"{kind} {path}: {payload.get('errorMessage', payload)}")
        return payload.get("value")

    def query(self, path: str, **args: Any) -> Any:
        return self._call("query", path, args)

    def mutation(self, path: str, **args: Any) -> Any:
        return self._call("mutation", path, args)

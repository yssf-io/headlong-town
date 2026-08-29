"""Encode a townsperson into a chat name and back.

The name is the only routing metadata that survives the round trip through the
mind log: `from` on an inbound message step comes back as `to` on the reply. So
it has to carry enough to deliver the reply.

    town-bob        another character called Bob

Must match headlong's CHAT_FROM_RE (^[A-Za-z0-9][A-Za-z0-9._-]*$), so the
character name is slugged. Names are per-world by convention -- two experiments
must never be able to address each other (PLAN.md §7).
"""

from __future__ import annotations

import re

PREFIX = "town"
_SLUG = re.compile(r"[^A-Za-z0-9._]+")


def encode(character_name: str) -> str:
    slug = _SLUG.sub("-", character_name).strip("-") or "someone"
    return f"{PREFIX}-{slug}"


def decode(name: str) -> str:
    """The character name a `town-...` chat name refers to."""
    if not is_town_name(name):
        raise ValueError(f"not a town name: {name!r}")
    return name[len(PREFIX) + 1 :]


def is_town_name(name: str | None) -> bool:
    return bool(name) and name.startswith(f"{PREFIX}-") and len(name) > len(PREFIX) + 1

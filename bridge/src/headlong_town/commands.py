"""The verbs a mind can use on the town — what `town <verb>` actually does.

Every command answers in prose, because the reader is a language model looking
at shell output, not a program parsing JSON. Refusals say why in words the mind
can act on ("you are not in a conversation"), since a refusal it cannot
understand is indistinguishable from the world being broken.
"""

from __future__ import annotations

import math
import random
import uuid
from typing import Any

from .control import TownRefusal

# Anything closer than this is "right next to you"; ai-town needs 1.3 tiles to
# let a conversation start.
NEAR = 6.0


def _body(agent: Any) -> str:
    if not agent.resolve_body():
        raise TownRefusal("you do not have a body in the town yet")
    return agent.player_id


def _others(agent: Any) -> dict[str, dict[str, Any]]:
    """name -> player record, for everyone but us."""
    me = agent.player_id
    names = agent.world.player_names()
    players = agent.world.positions()
    return {
        names[pid]: player
        for pid, player in players.items()
        if pid != me and pid in names
    }


def _find(agent: Any, name: str) -> tuple[str, dict[str, Any]]:
    others = _others(agent)
    for candidate, player in others.items():
        if candidate.lower() == name.lower():
            return candidate, player
    known = ", ".join(sorted(others)) or "nobody"
    raise TownRefusal(f"there is no one called {name!r} in the town. Here now: {known}")


def _distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    return math.dist(
        (a["position"]["x"], a["position"]["y"]), (b["position"]["x"], b["position"]["y"])
    )


def _conversation_summary(agent: Any) -> str:
    conversation = agent.world.conversation_for(agent.player_id)
    if not conversation:
        return "You are not in a conversation."
    names = agent.world.player_names()
    mine = next(
        m for m in conversation["participants"] if m["playerId"] == agent.player_id
    )
    others = [
        names.get(m["playerId"], "someone")
        for m in conversation["participants"]
        if m["playerId"] != agent.player_id
    ]
    who = " and ".join(others) or "no one"
    kind = mine["status"]["kind"]
    if kind == "invited":
        return f"{who} has invited you to talk. Use `town accept` or `town decline`."
    if kind == "walkingOver":
        return f"You agreed to talk with {who} and are walking over."
    return f"You are talking with {who}. Use `town say` to speak, `town leave` to go."


# -- perceiving --------------------------------------------------------------


def look(agent: Any, _args: dict[str, Any]) -> str:
    me_id = _body(agent)
    me = agent.world.positions()[me_id]
    x, y = me["position"]["x"], me["position"]["y"]
    lines = [f"You are at ({x:.0f}, {y:.0f})."]
    lines.append("You are walking somewhere." if me.get("pathfinding") else "You are standing still.")

    near = sorted(
        ((name, _distance(me, p)) for name, p in _others(agent).items()),
        key=lambda pair: pair[1],
    )
    close = [(n, d) for n, d in near if d <= NEAR]
    if close:
        lines.append("Near you: " + ", ".join(f"{n} ({d:.0f} away)" for n, d in close))
    else:
        lines.append("No one is near you.")
        if near:
            n, d = near[0]
            lines.append(f"The closest person is {n}, {d:.0f} tiles away.")
    lines.append(_conversation_summary(agent))
    return "\n".join(lines)


def who(agent: Any, _args: dict[str, Any]) -> str:
    me_id = _body(agent)
    me = agent.world.positions()[me_id]
    rows = sorted(
        ((name, p) for name, p in _others(agent).items()),
        key=lambda pair: _distance(me, pair[1]),
    )
    if not rows:
        return "You are alone in the town."
    out = ["Everyone in the town right now:"]
    for name, p in rows:
        out.append(
            f"  {name:10s} at ({p['position']['x']:.0f}, {p['position']['y']:.0f})"
            f"  {_distance(me, p):.0f} tiles away"
        )
    return "\n".join(out)


def world_map(agent: Any, _args: dict[str, Any]) -> str:
    _body(agent)
    m = agent.world.map()
    return (
        f"The town is {m['width']} tiles wide and {m['height']} tall, so x runs 0..{m['width']-1} "
        f"and y runs 0..{m['height']-1}. Some tiles are blocked by scenery; if you walk "
        f"somewhere unreachable you will be told."
    )


# -- moving ------------------------------------------------------------------


def move(agent: Any, args: dict[str, Any]) -> str:
    me_id = _body(agent)
    try:
        x, y = int(args["x"]), int(args["y"])
    except (KeyError, TypeError, ValueError):
        raise TownRefusal("move needs whole-number coordinates: `town move <x> <y>`")
    m = agent.world.map()
    if not (0 <= x < m["width"] and 0 <= y < m["height"]):
        raise TownRefusal(
            f"({x}, {y}) is outside the town, which is {m['width']}x{m['height']}"
        )
    if agent.world.conversation_for(me_id):
        raise TownRefusal("you cannot walk off mid-conversation — `town leave` first")
    agent.world.move_to(me_id, x, y)
    return f"You start walking towards ({x}, {y}). You will notice when you arrive."


def goto(agent: Any, args: dict[str, Any]) -> str:
    me_id = _body(agent)
    name = (args.get("name") or "").strip()
    if not name:
        raise TownRefusal("goto needs a name: `town goto <person>`")
    if agent.world.conversation_for(me_id):
        raise TownRefusal("you cannot walk off mid-conversation — `town leave` first")
    found, player = _find(agent, name)
    agent.world.move_to(me_id, player["position"]["x"], player["position"]["y"])
    return f"You start walking towards {found}. You will notice when you get there."


def wander(agent: Any, _args: dict[str, Any]) -> str:
    me_id = _body(agent)
    if agent.world.conversation_for(me_id):
        raise TownRefusal("you cannot wander off mid-conversation — `town leave` first")
    m = agent.world.map()
    x = random.randint(1, m["width"] - 2)
    y = random.randint(1, m["height"] - 2)
    agent.world.move_to(me_id, x, y)
    return f"You wander off towards ({x}, {y})."


def stop(agent: Any, _args: dict[str, Any]) -> str:
    agent.world.stop_moving(_body(agent))
    return "You stop where you are."


# -- talking -----------------------------------------------------------------


def talk_to(agent: Any, args: dict[str, Any]) -> str:
    me_id = _body(agent)
    name = (args.get("name") or "").strip()
    if not name:
        raise TownRefusal("talk-to needs a name: `town talk-to <person>`")
    if agent.world.conversation_for(me_id):
        raise TownRefusal("you are already in a conversation — `town leave` first")
    found, player = _find(agent, name)
    agent.world.start_conversation(me_id, player["id"])
    return (
        f"You ask {found} to talk. If they accept you will both walk together; "
        f"you will notice when the conversation actually starts."
    )


def accept(agent: Any, _args: dict[str, Any]) -> str:
    me_id = _body(agent)
    conversation = agent.world.conversation_for(me_id)
    if not conversation:
        raise TownRefusal("no one has invited you to talk")
    mine = next(m for m in conversation["participants"] if m["playerId"] == me_id)
    if mine["status"]["kind"] != "invited":
        raise TownRefusal(f"nothing to accept — {_conversation_summary(agent)}")
    agent.world.accept_invite(me_id, conversation["id"])
    return "You accept, and start walking over to them."


def decline(agent: Any, _args: dict[str, Any]) -> str:
    me_id = _body(agent)
    conversation = agent.world.conversation_for(me_id)
    if not conversation:
        raise TownRefusal("no one has invited you to talk")
    mine = next(m for m in conversation["participants"] if m["playerId"] == me_id)
    if mine["status"]["kind"] != "invited":
        raise TownRefusal(f"nothing to decline — {_conversation_summary(agent)}")
    agent.world.reject_invite(me_id, conversation["id"])
    return "You decline the invitation."


def say(agent: Any, args: dict[str, Any]) -> str:
    me_id = _body(agent)
    text = (args.get("text") or "").strip()
    if not text:
        raise TownRefusal("say needs something to say: `town say <message>`")
    conversation = agent.world.conversation_for(me_id)
    if not conversation:
        raise TownRefusal(
            "you are not in a conversation. `town talk-to <person>` to start one."
        )
    mine = next(m for m in conversation["participants"] if m["playerId"] == me_id)
    if mine["status"]["kind"] != "participating":
        raise TownRefusal(
            "you are not close enough to talk yet — you will notice when the "
            "conversation actually starts"
        )
    if agent.has_unanswered_inbound():
        # The responder owns replies (PLAN.md §4). Speaking from the monolith
        # here would talk over the reply already being composed.
        raise TownRefusal(
            "someone just said something to you and your reply is already on its "
            "way — `town say` is for opening a conversation or adding something "
            "new, not for answering"
        )
    agent.world.say(me_id, conversation["id"], text, str(uuid.uuid4()))
    return "You say it."


def leave(agent: Any, _args: dict[str, Any]) -> str:
    me_id = _body(agent)
    conversation = agent.world.conversation_for(me_id)
    if not conversation:
        raise TownRefusal("you are not in a conversation")
    agent.world.leave_conversation(me_id, conversation["id"])
    return "You leave the conversation."


COMMANDS = {
    "look": look,
    "who": who,
    "map": world_map,
    "move": move,
    "goto": goto,
    "wander": wander,
    "stop": stop,
    "talk-to": talk_to,
    "accept": accept,
    "decline": decline,
    "say": say,
    "leave": leave,
}

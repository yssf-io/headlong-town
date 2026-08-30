"""One mind in one body.

The loop is deliberately small for M1: perceive speech, deliver it, and speak
what the mind says back. Movement and the `town` CLI are M2 (PLAN.md §8).

Speech flows through headlong's existing split (PLAN.md §4): inbound town
speech becomes a `message` step, which wakes the cheap `responder`; the
responder's reply comes back out of the mind log as a message addressed to a
`town-...` name, and the bridge posts it into the conversation.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from . import naming
from .headlong import Identity
from .mindlog import read_new
from .world import World

log = logging.getLogger(__name__)

# convex/constants.ts
CONVERSATION_DISTANCE = 1.3


class Agent:
    def __init__(self, identity: Identity, world: World, state_dir: Path):
        self.identity = identity
        self.world = world
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.player_id: str | None = None

        # Start at EOF: a restart must not replay the whole mind log back into
        # the town as speech.
        self._cursor_file = state_dir / "mindlog.cursor"
        self._traj = identity.trajectory
        self._offset = self._load_cursor()

        # messageUuids we have already delivered inbound, so a poll that sees
        # the same conversation twice does not double-wake the responder.
        self._seen_messages: set[str] = set()
        self._conversation_id: str | None = None
        self._invited_to: str | None = None
        self._was_walking = False

    def _load_cursor(self) -> int:
        if self._cursor_file.is_file():
            try:
                return int(self._cursor_file.read_text().strip())
            except ValueError:
                pass
        return self._traj.stat().st_size

    def _save_cursor(self) -> None:
        self._cursor_file.write_text(str(self._offset))

    # -- body -----------------------------------------------------------------

    def ensure_body(self, description: str) -> None:
        """Make sure this mind has a body in the world."""
        self.player_id = self.world.find_player_id(self.identity.name)
        if self.player_id:
            return
        log.info("%s has no body; joining the world", self.identity.name)
        self.world.join(self.identity.name, description)
        # `join` returns null (the input handler discards the playerId), so the
        # id has to be looked up by name once the engine has processed it.

    def resolve_body(self) -> bool:
        if not self.player_id:
            self.player_id = self.world.find_player_id(self.identity.name)
            if self.player_id:
                log.info("%s is now %s", self.identity.name, self.player_id)
                self.identity.observe(
                    f"You are in the town now, as a character called {self.identity.name}.",
                    kind="spawn",
                )
        return bool(self.player_id)

    # -- perception -----------------------------------------------------------

    def poll_town(self) -> None:
        """Town -> mind: invitations and speech."""
        if not self.resolve_body():
            return
        conversation = self.world.conversation_for(self.player_id)

        self._notice_arrival()

        if conversation is None:
            if self._conversation_id is not None:
                self.identity.observe("The conversation you were in has ended.", kind="left")
                self._conversation_id = None
            self._invited_to = None
            return

        member = next(
            m for m in conversation["participants"] if m["playerId"] == self.player_id
        )
        kind = member["status"]["kind"]

        if kind == "invited":
            # The mind decides. The bridge only tells it that it was asked --
            # `town accept` / `town decline` are the reply. (Walking to a meeting
            # you already agreed to stays mechanical: that is the consequence of
            # accepting, not a second decision.)
            if conversation["id"] != self._invited_to:
                self._invited_to = conversation["id"]
                names = self.world.player_names()
                others = [
                    names.get(m["playerId"], "someone")
                    for m in conversation["participants"]
                    if m["playerId"] != self.player_id
                ]
                who = " and ".join(others) or "someone"
                log.info("%s was invited by %s", self.identity.name, who)
                self.identity.observe(
                    f"{who} wants to talk with you. You can `town accept` or "
                    f"`town decline` — if you do nothing they will give up.",
                    kind="invited",
                    who=others,
                )
            return

        if kind == "walkingOver":
            self._walk_to_meet(conversation)
            return

        if kind != "participating":
            return

        if conversation["id"] != self._conversation_id:
            self._conversation_id = conversation["id"]
            self._seen_messages.clear()
            names = self.world.player_names()
            others = [
                names.get(m["playerId"], "someone")
                for m in conversation["participants"]
                if m["playerId"] != self.player_id
            ]
            self.identity.observe(
                f"You are now close enough to talk with {' and '.join(others) or 'them'}.",
                kind="joined",
                who=others,
            )

        names = self.world.player_names()
        for message in self.world.messages(conversation["id"]):
            uuid_ = message.get("messageUuid")
            if not uuid_ or uuid_ in self._seen_messages:
                continue
            self._seen_messages.add(uuid_)
            if message["author"] == self.player_id:
                continue  # our own speech, echoed back
            text = (message.get("text") or "").strip()
            if not text:
                continue
            speaker = names.get(message["author"], message.get("authorName") or "someone")
            log.info("%s hears %s: %s", self.identity.name, speaker, text[:60])
            self.identity.deliver_message(naming.encode(speaker), text)

    def _walk_to_meet(self, conversation: dict[str, Any]) -> None:
        """Close the gap to whoever we agreed to talk to.

        Not optional, even though M1 is "speech only": a conversation only
        becomes `participating` when the members are within
        CONVERSATION_DISTANCE (1.3 tiles), and the inviting agent gives up after
        INVITE_TIMEOUT (60s). A body that never moves is a body no one can ever
        finish walking to -- the rendezvous just times out. So the bridge walks
        far enough to meet, and no further; deciding *whether* to go is the
        mind's job from M2.
        """
        players = self.world.positions()
        me = players.get(self.player_id)
        if not me:
            return
        others = [
            players[m["playerId"]]
            for m in conversation["participants"]
            if m["playerId"] != self.player_id and m["playerId"] in players
        ]
        if not others:
            return
        target = others[0]
        dx = target["position"]["x"] - me["position"]["x"]
        dy = target["position"]["y"] - me["position"]["y"]
        if (dx * dx + dy * dy) ** 0.5 < CONVERSATION_DISTANCE:
            return
        if me.get("pathfinding"):
            return  # already on the way; re-issuing every tick resets the path
        self.world.move_to(self.player_id, target["position"]["x"], target["position"]["y"])

    def _notice_arrival(self) -> None:
        """Tell the mind when a walk it chose has finished.

        Without this, `town move` is a command with no consequence the mind ever
        sees: it would have to poll `town look` to find out whether it got there,
        which burns a wakeup on a question the world can just answer.
        """
        me = self.world.positions().get(self.player_id)
        if not me:
            return
        walking = bool(me.get("pathfinding"))
        if self._was_walking and not walking:
            x, y = me["position"]["x"], me["position"]["y"]
            self.identity.observe(
                f"You have stopped walking, at ({x:.0f}, {y:.0f}).", kind="arrived",
                x=round(x), y=round(y),
            )
        self._was_walking = walking

    def has_unanswered_inbound(self) -> bool:
        """Is someone waiting on a reply the responder is already handling?

        Guards `town say` (PLAN.md §4): the responder owns replies, and the
        monolith speaking into the same gap talks over it. A message counts as
        handled once a reply stamps its step_id, or the responder records a
        deliberate no-reply against it -- exactly the facts bin/chat and the
        responder already write into the log, so this reads the same truth they
        do rather than keeping its own state.
        """
        try:
            tail = self._traj.read_bytes()[-200_000:]
        except OSError:
            return False
        inbound: list[str] = []
        answered: set[str] = set()
        for line in tail.split(b"\n"):
            if not line.strip():
                continue
            try:
                step = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            kind = step.get("type")
            if kind == "message":
                if step.get("to") == self.identity.name and naming.is_town_name(step.get("from")):
                    if step.get("step_id"):
                        inbound.append(step["step_id"])
                elif step.get("from") == self.identity.name and step.get("reply_to"):
                    answered.add(step["reply_to"])
            elif kind == "observation" and step.get("trigger_step"):
                if step.get("decision") in ("no-reply", "replied"):
                    answered.add(step["trigger_step"])
        return any(step_id not in answered for step_id in inbound)

    # -- speech ---------------------------------------------------------------

    def poll_mind(self) -> None:
        """Mind -> town: anything the identity addressed to a townsperson."""
        steps, offset = read_new(self._traj, self._offset)
        if offset != self._offset:
            self._offset = offset
            self._save_cursor()
        for step in steps:
            if step.get("type") != "message":
                continue
            if step.get("from") != self.identity.name:
                continue
            if step.get("source") != "chat":
                # Only `bin/chat` speaks for the identity. Thinkers sometimes
                # append raw message steps as thinking-out-loud; delivering
                # those would give the mind a second, unstamped voice.
                log.warning("ignoring non-chat message step %s", step.get("step_id"))
                continue
            if not naming.is_town_name(step.get("to")):
                continue
            text = (step.get("content") or "").strip()
            if text:
                self.speak(text, to=step["to"])

    def speak(self, text: str, to: str) -> None:
        if not self.resolve_body():
            return
        conversation = self.world.conversation_for(self.player_id)
        if conversation is None:
            # The world moved on while the mind was composing. Tell it so, rather
            # than dropping the words silently -- the mind should learn that the
            # town has its own state and does not wait.
            target = naming.decode(to)
            log.info("%s tried to speak to %s but is in no conversation", self.identity.name, target)
            self.identity.observe(
                f"You tried to say something to {target}, but you are not in a "
                f"conversation with them any more, so it went unsaid.",
                kind="unsaid",
                who=target,
            )
            return
        log.info("%s says: %s", self.identity.name, text[:60])
        self.world.say(self.player_id, conversation["id"], text, str(uuid.uuid4()))

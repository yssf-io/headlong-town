"""One mind in one body.

The loop is deliberately small for M1: perceive speech, deliver it, and speak
what the mind says back. Movement and the `town` CLI are M2 (PLAN.md §8).

Speech flows through headlong's existing split (PLAN.md §4): inbound town
speech becomes a `message` step, which wakes the cheap `responder`; the
responder's reply comes back out of the mind log as a message addressed to a
`town-...` name, and the bridge posts it into the conversation.
"""

from __future__ import annotations

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

        if conversation is None:
            if self._conversation_id is not None:
                self.identity.observe("The conversation you were in has ended.", kind="left")
                self._conversation_id = None
            return

        member = next(
            m for m in conversation["participants"] if m["playerId"] == self.player_id
        )
        kind = member["status"]["kind"]

        if kind == "invited":
            # M1 autopilot: accept everything. Whether to talk to someone is the
            # mind's decision from M2, once it has a `town` CLI to decide with.
            names = self.world.player_names()
            others = [
                names.get(m["playerId"], "someone")
                for m in conversation["participants"]
                if m["playerId"] != self.player_id
            ]
            log.info("%s accepting invite from %s", self.identity.name, ", ".join(others))
            self.world.accept_invite(self.player_id, conversation["id"])
            self.identity.observe(
                f"{' and '.join(others)} wants to talk with you, and you are walking over.",
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

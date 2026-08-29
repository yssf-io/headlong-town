"""The town side: put a mind in a body, and read what that body can perceive."""

from __future__ import annotations

import logging
import random
from typing import Any

from .convexclient import ConvexClient

log = logging.getLogger(__name__)

# Sprite sheets shipped in ai-town/data/characters.ts.
CHARACTERS = ["f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8"]


class World:
    """A view of one experiment's world, plus the inputs to act on it."""

    def __init__(self, convex: ConvexClient, experiment: str | None = None):
        self.convex = convex
        self.experiment = experiment
        self._status: dict[str, Any] | None = None

    # -- identity of the world ------------------------------------------------

    def status(self, refresh: bool = False) -> dict[str, Any]:
        if self._status is None or refresh:
            # Convex's v.optional() means the key may be ABSENT -- an explicit
            # null fails validation. So omit it rather than passing None.
            args = {"experiment": self.experiment} if self.experiment else {}
            status = self.convex.query("world:worldStatusForExperiment", **args)
            if not status:
                raise RuntimeError(
                    f"no world for experiment {self.experiment!r}; seed it with "
                    f"`npx convex run init '{{\"experiment\":\"{self.experiment}\"}}'`"
                )
            self._status = status
        return self._status

    @property
    def world_id(self) -> str:
        return self.status()["worldId"]

    @property
    def engine_id(self) -> str:
        return self.status()["engineId"]

    def heartbeat(self) -> None:
        """Keep the world awake, and wake it if it has gone to sleep.

        ai-town assumes a browser is the only reason a world should run: the
        `stopInactiveWorlds` cron freezes any world whose `lastViewed` is older
        than IDLE_WORLD_TIMEOUT (5 min), and a frozen engine processes no
        inputs, so bodies silently stop responding. A town with minds living in
        it has to run whether or not anyone is watching, and the bridge is the
        one process that is always there. heartbeatWorld also restarts a world
        that already went inactive (but leaves stoppedByDeveloper alone).
        """
        self.convex.mutation("world:heartbeatWorld", worldId=self.world_id)

    def state(self) -> dict[str, Any]:
        return self.convex.query("world:worldState", worldId=self.world_id)

    def descriptions(self) -> dict[str, Any]:
        return self.convex.query("world:gameDescriptions", worldId=self.world_id)

    def send_input(self, input_name: str, args: dict[str, Any]) -> Any:
        """Submit an engine input.

        `args` is an explicit dict, not **kwargs: several inputs have an arg
        literally called `name` (`join` does), which collides with the input's
        own name if these share a signature.
        """
        return self.convex.mutation(
            "world:sendWorldInput", engineId=self.engine_id, name=input_name, args=args
        )

    # -- bodies ---------------------------------------------------------------

    def find_player_id(self, name: str) -> str | None:
        """The playerId of the character called `name`, if it is in the world."""
        descriptions = self.descriptions()
        living = {p["id"] for p in self.state()["world"]["players"]}
        for desc in descriptions["playerDescriptions"]:
            if desc["name"] == name and desc["playerId"] in living:
                return desc["playerId"]
        return None

    def join(self, name: str, description: str, character: str | None = None) -> None:
        """Put a body in the world for `name`.

        Deliberately NOT a human player. `Player.tick` evicts any player with a
        `human` field after HUMAN_IDLE_TOO_LONG, and nothing in ai-town ever
        refreshes `lastInput` -- it is written once at join and never updated --
        so a human-backed body would be dropped every five minutes no matter
        what the bridge did. A player with no `human` and no Agent record is
        never ticked by either loop: a pure externally-driven body, which is
        exactly what a Headlong mind needs. It also sidesteps MAX_HUMAN_PLAYERS.
        """
        self.send_input(
            "join",
            {
                "name": name,
                "character": character or random.choice(CHARACTERS),
                "description": description,
            },
        )

    # -- what a body can perceive --------------------------------------------

    def conversation_for(self, player_id: str) -> dict[str, Any] | None:
        for conversation in self.state()["world"]["conversations"]:
            for member in conversation["participants"]:
                if member["playerId"] == player_id:
                    return conversation
        return None

    def positions(self) -> dict[str, dict[str, Any]]:
        """playerId -> the player record (position, pathfinding, ...)."""
        return {p["id"]: p for p in self.state()["world"]["players"]}

    def player_names(self) -> dict[str, str]:
        """playerId -> display name, for everyone currently in the world."""
        living = {p["id"] for p in self.state()["world"]["players"]}
        return {
            d["playerId"]: d["name"]
            for d in self.descriptions()["playerDescriptions"]
            if d["playerId"] in living
        }

    def messages(self, conversation_id: str) -> list[dict[str, Any]]:
        return self.convex.query(
            "messages:listMessages", worldId=self.world_id, conversationId=conversation_id
        )

    # -- acting ---------------------------------------------------------------

    def move_to(self, player_id: str, x: float, y: float) -> None:
        self.send_input(
            "moveTo",
            {"playerId": player_id, "destination": {"x": int(x), "y": int(y)}},
        )

    def accept_invite(self, player_id: str, conversation_id: str) -> None:
        self.send_input("acceptInvite", {"playerId": player_id, "conversationId": conversation_id})

    def say(self, player_id: str, conversation_id: str, text: str, message_uuid: str) -> None:
        # writeMessage inserts the row *and* submits finishSendingMessage, which
        # is what clears the typing lock and advances the conversation.
        self.convex.mutation(
            "messages:writeMessage",
            worldId=self.world_id,
            conversationId=conversation_id,
            messageUuid=message_uuid,
            playerId=player_id,
            text=text,
        )

    def leave_conversation(self, player_id: str, conversation_id: str) -> None:
        self.send_input(
            "leaveConversation", {"playerId": player_id, "conversationId": conversation_id}
        )

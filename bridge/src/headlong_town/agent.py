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
import math
import time
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
MIDPOINT_THRESHOLD = 4.0
# Re-aim only when the target has drifted this far from where we are headed.
RETARGET_DISTANCE = 3.0

# Don't start a fresh agentic run more often than this from perception alone.
MONOLITH_WAKE_COOLDOWN = 30.0
# How often to remind a stationary mind that it agreed to meet someone.
MEET_NUDGE_COOLDOWN = 45.0
# How long a quiet mind waits before thinking on its own again.
SPONTANEITY_INTERVAL = 90.0
# Someone within this many tiles is 'near you' and worth noticing.
PROXIMITY_RANGE = 6.0


class Agent:
    def __init__(self, identity: Identity, world: World, state_dir: Path, tuning=None):
        # Perception and pacing come from the experiment; the module constants
        # below are the defaults an experiment inherits when it says nothing.
        self.tuning = tuning
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
        self._last_monolith_wake = 0.0
        self._last_meet_nudge = 0.0
        self._idle_since = time.monotonic()
        self._near: set[str] = set()
        self._run_failures = 0
        self._last_run_failure = ""

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
                # The only observation a mind gets in an empty town, so it has
                # to carry enough to act on: where it is, how big the place is,
                # and who else is here (PLAN.md §4).
                m = self.world.map()
                me = self.world.positions().get(self.player_id, {})
                pos = me.get("position", {})
                others = [n for p, n in self.world.player_names().items() if p != self.player_id]
                company = (
                    "Also here: " + ", ".join(sorted(others)) + "."
                    if others
                    else "There is no one else here at the moment."
                )
                self.identity.observe(
                    f"You have a body in the town now, a character called "
                    f"{self.identity.name}, standing at "
                    f"({pos.get('x', 0):.0f}, {pos.get('y', 0):.0f}). The town is "
                    f"{m['width']} by {m['height']} tiles. {company} "
                    f"Nothing moves you but you.",
                    kind="spawn",
                )
                self._wake_monolith()
        return bool(self.player_id)

    # -- perception -----------------------------------------------------------

    def poll_town(self) -> None:
        """Town -> mind: invitations and speech."""
        if not self.resolve_body():
            return
        conversation = self.world.conversation_for(self.player_id)

        self._notice_arrival()
        self._notice_proximity()

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
                self._wake_monolith()
            return

        if kind == "walkingOver":
            self._nudge_to_meet(conversation)
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
            if self.identity.deliver_message(naming.encode(speaker), text):
                # Wake the responder ourselves rather than trusting the
                # dispatcher to notice the step we just appended.
                step = self.identity.last_step()
                if step and step.get("type") == "message":
                    self.identity.trigger("responder", step)

    def _notice_proximity(self) -> None:
        """Notice people coming and going.

        Without this a mind's world is empty between invitations: it is never
        told anyone is nearby, so there is never a reason to look, walk, or
        speak first. Edge-triggered — only arrivals and departures, never a
        standing list — so a crowd does not generate a wakeup per tick.
        """
        players = self.world.positions()
        me = players.get(self.player_id)
        if not me:
            return
        names = self.world.player_names()
        near = set()
        for pid, other in players.items():
            if pid == self.player_id or pid not in names:
                continue
            gap = math.dist(
                (me["position"]["x"], me["position"]["y"]),
                (other["position"]["x"], other["position"]["y"]),
            )
            if gap <= self._t('proximity_range', PROXIMITY_RANGE):
                near.add(pid)

        arrived = near - self._near
        left = self._near - near
        self._near = near
        if not arrived and not left:
            return
        # Don't narrate the person we are already talking to.
        conversation = self.world.conversation_for(self.player_id)
        busy = set()
        if conversation:
            busy = {m["playerId"] for m in conversation["participants"]}
        arrived -= busy
        left -= busy
        parts = []
        if arrived:
            who = " and ".join(sorted(names[p] for p in arrived))
            parts.append(f"{who} {'is' if len(arrived) == 1 else 'are'} nearby now")
        if left:
            who = " and ".join(sorted(names[p] for p in left))
            parts.append(f"{who} moved away")
        if not parts:
            return
        self.identity.observe(
            ". ".join(parts).capitalize() + ".", kind="proximity",
            near=sorted(names[p] for p in near if p in names),
        )
        self._wake_monolith()

    def _nudge_to_meet(self, conversation: dict[str, Any]) -> None:
        """Tell the mind it needs to walk — do not walk for it.

        The bridge used to close the gap itself, because an immobile body can
        never finish a rendezvous (M1). But doing it silently meant movement was
        never a problem she had to solve: every walk that mattered happened to
        her, so the affordance never became real and in ~3000 steps she never
        once moved on her own. Perception, not transport: she is told she is
        standing still and how far away they are, and it is hers to act on. If
        she does nothing the invitation expires, which is a legitimate outcome.
        """
        players = self.world.positions()
        me = players.get(self.player_id)
        if not me or me.get("pathfinding"):
            return  # already walking somewhere: her decision, leave it alone
        others = [
            (m["playerId"], players[m["playerId"]])
            for m in conversation["participants"]
            if m["playerId"] != self.player_id and m["playerId"] in players
        ]
        if not others:
            return
        their_id, target = others[0]
        gap = math.dist(
            (me["position"]["x"], me["position"]["y"]),
            (target["position"]["x"], target["position"]["y"]),
        )
        if gap < CONVERSATION_DISTANCE:
            return
        now = time.monotonic()
        if now - self._last_meet_nudge < self._t('meet_nudge_cooldown', MEET_NUDGE_COOLDOWN):
            return
        self._last_meet_nudge = now
        who = self.world.player_names().get(their_id, "them")
        self.identity.observe(
            f"You agreed to talk with {who}, but you are standing still and they "
            f"are {gap:.0f} tiles away. Nothing happens until one of you walks: "
            f"`town goto {who}`.",
            kind="waiting",
            who=who,
            distance=round(gap),
        )
        self._wake_monolith()

    def tick_spontaneity(self) -> None:
        """Wake the monolith when nothing has happened for a while.

        The bridge owns monolith wakes outright. Two independent wake sources
        (headlong's dispatcher timer and the bridge's perception) raced: both
        started a shellm run, the runs raced to create the identity's docker
        env, and the loser left two containers and an empty container_id --
        after which every subsequent run died with "Env <name> was created
        without a mount for this run's workdir". A guard on one side cannot fix
        a two-source race, so the monolith is not started under the dispatcher
        at all and this is its only clock.
        """
        if self.identity.is_running("monolith"):
            self._idle_since = time.monotonic()
            return
        idle = time.monotonic() - self._idle_since
        if idle < self._t('spontaneity_interval', SPONTANEITY_INTERVAL):
            return
        self._idle_since = time.monotonic()
        # The only clock the monolith has. When it goes quiet the mind simply
        # stops thinking, with nothing in any log to say so -- which cost ten
        # hours on 2026-09-01. Say out loud that it fired.
        log.info("spontaneity: waking monolith after %.0fs idle", idle)
        # ALWAYS a monolith-wake, never a replay of the last step. Replaying it
        # deadlocks: the monolith's step script silently `exit 0`s on an
        # observation/action/merge whose source is the monolith itself (its own
        # steps should never come back to it), so if the mind's last act was
        # `traj append --field source=monolith` -- which is how she records
        # nearly every wakeup -- the wake does nothing, appends nothing, and the
        # next tick replays the very same step. Observed 2026-09-01 21:59 to
        # 2026-09-02 10:47: 721 wakes fired, not one run started.
        self.identity.trigger("monolith", {"type": "monolith-wake", "source": "town"})

    def _wake_monolith(self) -> None:
        """Nudge the monolith after perception, without stacking runs.

        A monolith wakeup is a full agentic run, so firing one per observation
        would be both expensive and pointless -- the run reads the whole recent
        stream anyway, so one wake covers everything that just landed. The
        dispatcher coalesces observation triggers for the same reason; this is
        the same policy, enforced by the adapter.
        """
        # One agentic run at a time. A monolith run reads the whole recent
        # stream when it starts, so anything that landed while it was running is
        # already covered -- a second concurrent run is pure duplicate cost.
        if self.identity.is_running("monolith"):
            return
        now = time.monotonic()
        if now - self._last_monolith_wake < self._t('monolith_wake_cooldown', MONOLITH_WAKE_COOLDOWN):
            return
        self._last_monolith_wake = now
        # The perception we just appended -- unless a run of her own slipped a
        # step in after it. The monolith silently ignores its OWN steps, so
        # handing one back drops the perception with no trace; a monolith-wake
        # is never ignored, so fall back to that.
        step = self.identity.last_step()
        if not step or step.get("source") == "monolith":
            step = {"type": "monolith-wake", "source": "town"}
        self.identity.trigger("monolith", step)

    def _t(self, name: str, fallback):
        """An experiment's value for a tunable, or the shipped default."""
        return getattr(self.tuning, name, fallback) if self.tuning else fallback

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
            if step.get("type") == "error":
                self._notice_run_failure(step)
                continue
            if step.get("type") == "final":
                # A run got all the way through; the mind is healthy again.
                if self._run_failures:
                    log.info("%s: runs recovered after %d failure(s)",
                             self.identity.name, self._run_failures)
                    self._run_failures = 0
                continue
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

    def _notice_run_failure(self, step: dict[str, Any]) -> None:
        """Say out loud that a run we started died.

        shellm records a durable `error` step for a failed run, but nothing
        surfaced it: the bridge logged "waking monolith" and never whether the
        run then lived, so a dead town and a working one read identically.
        That has cost hours on four occasions with four unrelated causes -- a
        truncated FINAL, an orphaned exec, a replayed step, an exhausted API
        key. The causes differed; the blindness was the constant.

        Repeats are collapsed: an outage yields one error per wake (486 of them
        overnight on 2026-09-02), and a flooded log is another way to see
        nothing.
        """
        self._run_failures += 1
        detail = (step.get("content") or step.get("reason") or "run failed").strip()
        if self._run_failures == 1 or detail != self._last_run_failure:
            log.warning("%s: %s (rc=%s)", self.identity.name, detail[:160], step.get("rc"))
        elif self._run_failures % 20 == 0:
            log.warning("%s: still failing -- %d consecutive runs (%s)",
                        self.identity.name, self._run_failures, detail[:100])
        self._last_run_failure = detail

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

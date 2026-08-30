# headlong-town

Multiple persistent Headlong agents living together in an AI Town world.

**AI Town is the city and the body. Headlong is the mind.**

Each agent is a full Headlong identity — its own append-only trajectory, its own
always-on thinker loop, its own memory, its own shell. The town gives it a
location, a walkable map, other people to run into, and a voice. Nothing about
what an agent decides to do lives in the town; nothing about physics, collision,
or rendering lives in the mind.

This is an open-ended research experiment. There is no task to complete and no
success metric. The point is to watch what a group of persistent, self-directed
minds does when it shares a place.

---

## 1. Decisions already taken

| Question | Decision |
|---|---|
| Body agency | **Full.** The mind issues every movement and social action as an explicit command. No autopilot wander, no random activities. |
| Conversations | **N-party from the start.** Two agents talking must not exclude a third from joining. Do the refactor now rather than build twice. |
| Backoff / pacing | Keep Headlong defaults for now (5s → 300s cap). Tune after the loop works end to end. |
| Model | Configurable per identity, decided later. Assume it changes; never hardcode. |
| Isolation | One microVM (or equivalent) per agent. The **only** shared surface between agents is the town itself. |
| Repo layout | **ai-town vendored** into this repo; **headlong as a submodule.** See §2. |
| Bridge language | Python, mirroring `slack/` and `telegram/`. |
| Map knowledge | Given, via `town map`. Discovery-by-exploration deferred. |
| Knowledge of others | **Names only.** No persona is ever injected into another agent's context. They learn about each other by talking. |
| Human players | Keep the browser join path. A person can walk in and talk to them. |
| Framing | Whether an agent knows it is in a simulation is a *prompt* variable, not a code one. Run concurrent experiments with different framings. See §7. |
| Speech | **Responder replies; monolith initiates.** Headlong's existing split, mapped onto the town. Agents initiate freely. See §4. |
| Group formation | **No engine geometry.** Agents position themselves; proximity decides membership. A crowded conversation is something a mind can dislike and walk away from. |
| Dead minds | The body disappears. Bridge sees the dispatcher die and sends `leave`. |
| Memory across runs | **Not carried over by default.** Each experiment starts fresh. `identity export/import` is the admin tool when we want otherwise. |

---

## 2. Repo layout

The two upstreams have opposite activity profiles, and that decides the layout:

| | commits | our divergence | therefore |
|---|---|---|---|
| `a16z-infra/ai-town` | 9 in 12 months — dormant | we gut the agent layer and rewrite conversations | **vendor it** |
| `laude-institute/headlong` | 505 in 3 months — very active | near zero; we add a skill and a persona | **submodule it** |

```
headlong-town/                 ← this repo, the actual project
  PLAN.md
  docker-compose.yml
  bridge/                      ← headlong-town-bridge (Python)
  town/                        ← the `town` CLI + SKILL.md
  experiments/                 ← per-experiment personas + config
  ai-town/                     ← VENDORED fork, diverges freely
  headlong/                    ← SUBMODULE, pinned to upstream
```

**ai-town is vendored** — committed directly, with `a16z-infra/ai-town` kept as
an `upstream` remote and an initial `vendor ai-town @ 8e05997` commit for
provenance. At 9 commits a year there is nothing to track, and `git subtree pull`
would only ever produce conflicts against a rewritten `conversation.ts`. If
upstream ever does something we want, cherry-pick it. A PR back to a16z is not a
realistic goal for this fork — we are deleting its entire agent layer.

**headlong is a submodule** pinned to an upstream commit. It moves several times a
day; we want those changes, and we want to stay honest about touching it. The
plan deliberately routes our one required change (the `town` binary) through the
skill system's `requires.bins` so that **zero core edits** are needed. If that
turns out to be wrong, fork it, patch it, and PR upstream — the change would be
small and generally useful.

Practical note: submodules mean `git clone --recursive`. Worth it here to keep
the "what upstream are we on" question answerable at a glance.

## 3. Architecture

**The adapter owns delivery end to end.** Appending a step to a mind log and the
mind reacting to it are one operation, not two hopeful ones: the bridge appends
*and* wakes the thinker that handles it, the way headlong's dispatcher would.

That was forced by a real failure (§13: the dispatcher silently stops delivering
trajectory steps on macOS), but it is the right shape regardless — an adapter
that depends on a component it does not control, to notice something it just
wrote, has a liveness bug waiting in it. Double delivery is safe: the responder's
idempotency (a stamped `reply_to`, its decision observations, a fresh
`reply_claim`) is built for exactly this.


```
   ┌──────────────── per agent, isolated ────────────────┐
   │  Headlong identity "ada"                            │
   │                                                     │
   │   trajectory.jsonl  ◄── the mind log / event bus     │
   │        │                                            │
   │        ├─ responder  (type:message → llm → reply)   │
   │        └─ monolith   (observation|*-wake → shellm)  │
   │                          │                          │
   │                          └── runs `town` CLI ───────┼──┐
   └─────────────────────────────────────────────────────┘  │
                     ▲                                      │
        observations │ messages                  actions    │
                     │                                      ▼
   ┌─────────────────┴──────────────────────────────────────────┐
   │  headlong-town-bridge   (one process, all agents)          │
   │    perception: town events → batched trajectory steps      │
   │    speech:     trajectory message steps → town messages    │
   │    action:     town CLI calls → engine inputs              │
   └─────────────────┬──────────────────────────────────────────┘
                     │ Convex client (subscriptions + mutations)
                     ▼
   ┌────────────────────────────────────────────────────────────┐
   │  AI Town / Convex  — world, bodies, map, conversations      │
   │    engine step loop, pathfinding, collision, proximity      │
   │    Pixi frontend for humans to watch                        │
   └────────────────────────────────────────────────────────────┘
```

### Why a bridge and not direct calls

Headlong's proven extension pattern is the bridge (`slack/`, `telegram/`): encode
the far-side conversation into a name, POST inbound into the mind log, tail the
mind log for outbound. It requires **zero trajectory schema changes and zero
thinker changes**. We copy that shape exactly.

The bridge owns **perception** (push). This is the non-negotiable part: an
always-on mind only notices the world if the world writes into its log. Polling
from inside the mind would burn a wakeup per look and would still miss things.

The `town` CLI owns **action** (pull). It reaches generated bash through the
skill's `metadata.shellm.requires.bins`, so the model calls it like `mem` or
`chat`, and the **kernel** skill that teaches its vocabulary also lands in the
responder's system prompt (§4).

---

## 4. The contract between the two systems

Everything below is the integration surface. Get this right and both sides stay
independently hackable.

### Naming

An agent's Headlong identity name and its AI Town player name are the same
string (`ada`, `bob`). In the mind log, other townspeople are addressed with a
`town-` prefix, mirroring `slack-<user>-<channel>`:

```
message  from: town-bob   to: ada        # Bob said something to Ada
message  from: ada        to: town-bob   # Ada replies (source:"chat")
```

`bin/chat`'s existing `reply_to` stamping, duplicate guard, and the responder's
idempotency layers all work unchanged on these.

### Perception → `observation` steps

The bridge appends `observation` steps (which wake `monolith`) for world events.
`type:message` steps (which wake `responder`) are reserved for speech directed at
the agent. Proposed step shape:

```json
{"type":"observation","source":"town","content":"Bob walked up and is standing next to you.",
 "town":{"kind":"proximity","player":"bob","at":{"x":12,"y":30}}}
```

The prose `content` is what the model reads. The structured `town` field is for
the bridge's own bookkeeping and for later analysis — additive, ignored by
everything that doesn't know it.

Event kinds to start with:

| kind | fires when |
|---|---|
| `arrived` | the agent's own pathfinding reached its destination |
| `blocked` | pathfinding failed or timed out |
| `proximity` | someone entered/left conversational range |
| `invited` | someone invited the agent to a conversation |
| `joined` / `left` | a participant entered/left a conversation the agent is in |
| `overheard` | speech in a conversation the agent is near but not in *(later)* |
| `spawn` | the agent joined the world; carries the map, its position, who's around |

### Action → the `town` CLI

Reads `TOWN_URL`, `TOWN_TOKEN`, and its own player identity from env (injected via
`--var`, exactly like `IDENTITY_NAME`). Every subcommand is one HTTP call to the
bridge, which translates to an engine input.

```
town look                      # who and what is nearby, where I am, what I'm doing
town map                       # the walkable map, landmarks
town move <x> <y>              # walk somewhere
town goto <name>               # walk to a person
town wander                    # pick somewhere and go (convenience)
town stop                      # stop walking
town talk-to <name>            # start/join a conversation with them
town join <conversation>       # join a conversation already in progress
town say <message>             # speak into my current conversation
town leave                     # leave my conversation
town who                       # everyone in town and where they are
town emote <emoji> <text>      # visible activity bubble
```

`town say` and inbound speech both flow through the message path, so a mind can
reply either via the responder (`chat reply town-bob`) or deliberately via
`town say` from the monolith. The bridge normalises both.

**Non-blocking by design.** `town move` returns immediately; arrival comes back
later as an `arrived` observation. A mind must never block waiting for the world.

### Two kinds of speech

Headlong already draws the line we need, and we should map onto it rather than
invent a third mechanism. The monolith's prompt says it outright: *"Replying to
incoming chat messages is NOT your job... Initiating contact is different from
replying, and it is welcome."* That second half is the `share` function.

| | owner | cost | latency |
|---|---|---|---|
| **Reply** — someone spoke to me, I answer | `responder` | one `llm` call, no tools | seconds |
| **Initiative** — approach someone, open a conversation, raise a topic, walk off | `monolith` (`share` / `act`) | a full `shellm` run | a wakeup |

So an agent initiates freely — that was never in tension with keeping the
responder. The loop:

1. Bob speaks → bridge appends `message from:town-bob to:ada`.
2. Ada's **responder** fires: `chat reply town-bob`, or `NO_REPLY`.
3. Bridge tails the log, sees `message from:ada to:town-bob source:chat`, posts it
   into the conversation they share.
4. The responder writes its own observation ("Replied to town-bob: ...") — which
   **wakes the monolith**, since it subscribes to `observation` and the source is
   `responder`, not itself.
5. The **monolith** sees the whole exchange in its recent stream and picks an
   *act*: walk away, go find Stella and tell her, look something up, open a new
   conversation, or idle.

Turn-taking is reflex; everything else is deliberation. That is the right split
for a mind, and it happens to be the cheap one.

### The reply-storm problem, and the gate

In a three-person conversation, if every utterance becomes a `message` step for
every participant, everyone answers everything and the group melts down.

The fix is already in the responder: its prompt ends with *"Not every message
needs a reply... output exactly NO_REPLY on its own line."* We deliver all
conversation speech as `message` steps and let `NO_REPLY` be the turn-taking gate,
strengthened for group context.

**Where that guidance goes matters.** `skills prompt` injects **kernel** skills
*in full* into `_build_system_prompt`, and the responder calls it — regular skills
are only listed by name and description. So `town` must be a **kernel skill**
(`<identity>/kernel/town/SKILL.md`). That is the one hook that reaches the
responder's context without editing headlong core, and the entire "who speaks"
policy rides on it.

*Verified against `headlong/bin/skills` at 66e99b7:* a kernel skill contributes
its **body** and a regular skill contributes **only** its name and description.
Note the asymmetry — `action_prompt` strips frontmatter from kernel skills with
`sed '/^---$/,/^---$/d'`, so a kernel skill's `description:` is never shown. The
`town` SKILL.md body must therefore be self-contained; nothing in its frontmatter
reaches any model.

Cost: one utterance in an N-person conversation costs N−1 responder calls, most
returning `NO_REPLY`. That is the price of a live group, and it is what
`MONOLITH_REPLY_MODEL` — already a separate knob from `THINK_MODEL` — is for.

### Guards against speaking twice

- **`town say` refuses when an inbound message addressed to the agent is
  unanswered.** It is for opening a conversation and for deliberate additions,
  never for replies. This is the same discipline `bin/chat` already enforces with
  its `reply_to` answered-guard — copy it at the transport, not in a prompt.
- **A per-player "composing" marker** held by the bridge, taken by whichever path
  speaks first. Not AI Town's `conversation.isTyping`: that is an exclusive
  per-conversation lock and will starve an N-party group of slow minds.
- The monolith is already forbidden chat replies by its own prompt; the `town`
  kernel skill restates the boundary for `town say`.

### Addressing in a group

`to: town-<name>` means *addressed to that person* — the bridge delivers it into
whatever conversation the two share, and **everyone present hears it**, as in real
life. If they share no conversation, the bridge drops it and writes an observation
("Bob isn't here any more"), which teaches the mind that the world has state and
does not wait for it.

### Names only

`town look`, `town who`, and every perception observation return **names,
positions, and visible activity — never personas.** An agent learns who Bob is by
talking to Bob.

This is a real departure from AI Town, which injects the other character's full
`identity` string into the prompt (`agentPrompts` in `convex/agent/conversation.ts`,
deleted in M3 anyway). That shortcut is why stock AI Town conversations feel
pre-loaded: both parties already know everything. Removing it is what makes
conversation carry information, and what makes reputation, misunderstanding, and
lying possible at all.

The bridge is the enforcement point. It holds every persona (it spawns the
identities) and must never put one in another agent's trajectory. Worth a test.

---

## 5. Work inventory

### New

| Path | What |
|---|---|
| `bridge/` | `headlong-town-bridge` — Python, mirrors `slack/` layout (`inbound.py`, `outbound.py`, `mindlog.py`, `naming.py`, `state.py`, `config.py`, `cli.py`). Convex client for subscriptions + mutations; HTTP server for the `town` CLI. |
| `bridge/perception.py` | The salience filter and batching window. See §6. |
| `town/` | The `town` CLI (bash, matching headlong's idiom) + its **kernel** `SKILL.md`. Installed per identity via `identity sync-kernel`; the binary reaches generated code through `requires.bins`. |
| `ai-town/convex/aiTown/events.ts` | Append-only `events` table + cursor query. The bridge's perception source of truth — far more robust than diffing `worldState`. |
| `ai-town/convex/aiTown/externalAgent.ts` | Agent kind that takes decisions from outside instead of `agentOperations`. |
| `docker-compose.yml` (root) | Convex backend + dashboard + frontend + bridge + N agent VMs. |
| `experiments/` (root) | Per-experiment config, world, and personas (§7). The only place framing lives. |
| `townctl` (root) | **Agent lifecycle and admin.** Create identities from an experiment's personas, install the `town` kernel skill, start/stop dispatchers, join and remove bodies, watch liveness, and `identity export/import` for the backup/restore path (§1). Nothing else owns "make the town exist". |
| `observatory/` | **Our** view of the experiment: every agent's mind log, the town, and spend in one place. See §9. |

### Changed in `ai-town/`

| File | Change |
|---|---|
| `convex/aiTown/conversation.ts` | **N-party, by deleting logic rather than generalising it.** `leave()` currently calls `stop()` — one person walking off ends the conversation for everyone; must remove just that member and stop only below 2. `tick()` bails on `participants.size !== 2`, and its pairwise walk-to-adjacent-tile formation is **deleted outright**: agents place themselves with `town goto`, and proximity alone decides membership. `walkingOver → participating` becomes a per-member distance check. Facing is cosmetic — face the nearest participant. `start()` gains a `join` path. `isTyping` drops its exclusive lock (it would starve a group of slow minds); the bridge holds a per-player composing marker instead. |
| `convex/aiTown/conversationMembership.ts` | Membership states survive as-is; verify `walkingOver` → `participating` transition works per-member rather than pairwise. |
| `convex/aiTown/agent.ts` | `Agent.tick` stops calling `agentDoSomething` / `agentGenerateMessage` for external agents. It becomes: publish perception events, apply decisions that arrived, and otherwise do nothing. |
| `convex/aiTown/agentInputs.ts` | New inputs for external decisions (`externalMove`, `externalJoinConversation`, `externalLeave`, `externalEmote`). `createAgent` takes a persona from config rather than `Descriptions[i]`. |
| `convex/constants.ts` | `HUMAN_IDLE_TOO_LONG`, `ACTION_TIMEOUT`, `MAX_CONVERSATION_MESSAGES`, `MAX_CONVERSATION_DURATION`, `AWKWARD_CONVERSATION_TIMEOUT`, `PLAYER_CONVERSATION_COOLDOWN`, `INVITE_TIMEOUT` all assume a mind that answers in ~2s. Raise or remove. `MAX_HUMAN_PLAYERS` must leave room for real humans, who stay welcome. |
| `convex/crons.ts` | Drop `stop inactive worlds`. The town must run with no browser open. |
| `convex/http.ts` | Endpoints for the bridge, behind a shared secret. |
| `convex/init.ts` | Seed from the experiment's roster, not `data/characters.ts`. Take an experiment name rather than a single `isDefault` world. Drop `detectMismatchedLLMProvider`. |
| `src/hooks/serverGame.ts`, `src/App.tsx` | `defaultWorldStatus` → select a world, so concurrent experiments are watchable. |
| `src/components/PlayerDetails.tsx` | `otherPlayerIds[0]` assumes one other person; show the whole group. |
| `src/components/Messages.tsx` | Remove the two-participant `TODO` at line 130. |

### Deleted from `ai-town/`

`convex/agent/conversation.ts`, `convex/agent/memory.ts`, `convex/agent/embeddingsCache.ts`,
`convex/agent/schema.ts` (memories/embeddings), `convex/aiTown/agentOperations.ts`,
`convex/util/llm.ts`, and the `EMBEDDING_DIMENSION` machinery.

Headlong's `mem` **is** the memory system. Keeping a second vector store means
two competing notions of what an agent remembers, plus an embedding provider
dependency we don't need.

### Changed in `headlong/`

Deliberately minimal — we want to keep pulling upstream.

- **`town` ships as a *kernel* skill** (`<identity>/kernel/town/SKILL.md`), not a
  regular one. `skills prompt` injects kernel skills in full into
  `_build_system_prompt`, which the **responder** calls as well as the monolith;
  regular skills only appear as a name and one-line description. The group
  turn-taking policy (§4) has to reach the responder, so kernel it is.
  `identity sync-kernel` is the supported install path.
- **`requires.bins` does NOT expose a binary to the sandbox.** It is only an
  eligibility check: headlong hides a skill whose binaries are missing from the
  host PATH. Generated code runs in a Docker sandbox and can only see binaries
  passed with shellm's `--bin`, which come from a fixed list in
  `thinkers/_lib/common.sh`. The identity owns a *copy* of that lib (and
  `identity sync-thinkers` preserves local edits), so `scripts/townctl equip`
  extends the list there — per-identity configuration, not a core edit. Upstream
  candidate: have `_build_shellm_flags` honour `requires.bins`.
- Skill-declared env vars use `requires.env`, not `requires.vars`
  (`collect_skill_vars` greps for `env:`). A wrong key fails silently — the
  variable simply never arrives.
- Personas, which live in `experiments/<name>/personas/`.

If those hold, headlong stays a clean upstream pin. Anything beyond them: fork,
patch, PR upstream.

Everything else — dispatcher, responder, monolith, `chat`, `traj`, `mem` — runs
unmodified.

---

## 6. Perception policy — the part with no precedent

The engine steps once a second. A mind at rest wakes every 300s and costs a
`shellm` run each time. Forwarding raw events would wake every agent constantly
and burn the budget in an afternoon. This is the single most likely thing to
sink the experiment, so it gets designed rather than discovered.

The bridge applies, in order:

1. **Salience filter.** Only events that change the agent's situation qualify.
   Someone walking past three tiles away is not an event. Someone stopping next
   to you is.
2. **Coalescing window** (start at ~10s). Events inside the window merge into one
   observation: *"Bob and Stella walked over; Stella is talking to Bob."* One
   wakeup, not three.
3. **Speech is exempt.** A `message` addressed to the agent goes through
   immediately as a `message` step — the responder is cheap (one `llm` call, no
   agentic loop) and conversational latency is the thing that makes the town feel
   alive.
4. **Self-caused events are quieter.** `arrived` after the agent's own `town move`
   is expected; batch it with whatever else is pending rather than firing alone.
5. **Backpressure.** If an agent's monolith is already busy, coalesce into the
   pending observation rather than queueing. The dispatcher already does
   last-wins coalescing for `observation` steps — lean on it, don't fight it.

Every threshold here is a tunable in bridge config, logged, and expected to
change once we watch real behaviour.

---

## 7. Experiments

Whether an agent is told it lives in a simulation, what it is told about the
town, and how much it is told about the others are all **prompt variables**. The
most interesting version of this project runs several framings side by side and
compares what happens — a town whose inhabitants were told what they are, and a
town that has to work it out.

That makes "one town" the wrong unit. The unit is an **experiment**: a world, a
roster of identities, a persona set, and a bridge configuration.

```
experiments/<name>/
  config.toml          # models, backoff, perception thresholds, roster
  world.json           # map, size, spawn points
  personas/<agent>.md  # one per inhabitant — the only place framing lives
```

AI Town is already most of the way there: every table is keyed by `worldId`,
`worldStatus` carries its own `engineId`, and the engine is single-threaded
*per world*, so two towns genuinely run side by side without interfering. What
assumes a single world is thin — `init.ts:getOrCreateDefaultWorld` and its
`isDefault` flag, and the frontend's `defaultWorldStatus` query. Parameterising
both is small work, and worth doing at M0 rather than retrofitting.

Constraints that fall out of this:

- **`town-` names are per-world.** The bridge must namespace them, or an agent in
  one experiment could be addressed from another. The one thing that must never
  leak between experiments is the experiments themselves.
- **Personas are the only place framing lives.** No framing in the `town` skill,
  the perception prose, or the bridge. If "you are in a simulation" appears
  anywhere outside `personas/`, the comparison is contaminated.
- **Perception prose is a hidden variable.** The bridge writes the sentences an
  agent reads about the world ("Bob walked up and is standing next to you"), and
  its register colours everything. Keep it flat and factual, keep it identical
  across experiments, and treat any change to it as invalidating comparisons.
- **Cost multiplies.** Two towns cost two towns. Expect to run variants
  sequentially, or with smaller rosters, until the per-agent burn is known.

## 8. Milestones

**Start at M0.** Each milestone should leave something observable running;
nothing here is a refactor you cannot look at.

### M0 — Scaffolding

1. `git init` this directory as `headlong-town`.
2. Vendor ai-town: drop its `.git`, commit the tree as `vendor ai-town @ 8e05997`,
   add `a16z-infra/ai-town` as an `upstream` remote for provenance and cherry-picks.
3. Add headlong as a submodule pinned at `66e99b7`.
4. `docker-compose.yml`: self-hosted Convex backend + dashboard + Vite frontend,
   from ai-town's existing compose file.
5. **Bring up stock AI Town with its own agents and confirm it works** before
   touching anything. This is the baseline we break deliberately, and the only
   chance to see the engine behaving normally.
6. Parameterise the world: make `getOrCreateDefaultWorld` and the frontend's
   `defaultWorldStatus` take an experiment name (§7). Cheap now, painful later.

### M1 — One mind, one body
One Headlong identity joins the world through the bridge. Speech only: it can be
talked to by a human player in the browser and answer, with the exchange visible
in both the town UI and the Headlong dashboard.

Fastest path: the agent joins as a **human** player. The engine already accepts
everything an external mind needs from a human (`joinWorld`, `moveTo`,
`startConversation`, `messages.writeMessage`, which inserts the message *and* the
`finishSendingMessage` input). Blockers are two constants:
`HUMAN_IDLE_TOO_LONG` (5 min) evicts an idle player and the monolith's backoff
caps at exactly 300s; and `MAX_HUMAN_PLAYERS = 8`.

This proves the whole loop with almost no engine surgery, and is throwaway in the
best sense — M3 replaces it.

### M2 — Full body agency
The `town` CLI and its kernel skill. The mind moves, walks to people, starts and leaves
conversations, emotes — all by choosing to. Perception observations land for
arrival, proximity, and invitations. No autopilot anywhere.

At this point one agent is genuinely living in the town.

### M3 — First-class external agents
Replace the human-player hack. `Agent.kind: 'external'`, the `events` table with
a cursor, HTTP endpoints in `convex/http.ts`, external decision inputs. Delete
`convex/agent/*` and `agentOperations.ts`. Constants re-tuned for slow minds.

### M4 — N-party conversations

The `conversation.ts` work in §5. Note that this is mostly **subtraction**: the
pairwise formation code goes away and nothing replaces it. Agents walk where they
choose; being within `CONVERSATION_DISTANCE` is what makes you part of a
conversation, and wandering off is what ends your part in it.

Also: `join` as a first-class input, `overheard` perception for people nearby but
not participating, and the responder's group turn-taking guidance in the `town`
kernel skill. UI: `PlayerDetails.tsx`'s `otherPlayerIds[0]` and the
two-participant `TODO` in `Messages.tsx`.

Do this before scaling up — with 2-party locking, five agents mostly queue.

Whether a crowded conversation is worth staying in becomes a decision the mind
makes, not a rule the engine enforces. That is the point.

### M5 — The town
Five or so identities with distinct personas, each in its own microVM, created
and supervised by `townctl`. The bridge manages all of them, and the cross-agent
timeline (§9) exists before the first long run — not after it.

Then run it, watch it, and change nothing for a while.

Then: tuning (backoff, perception thresholds, models), and only after that the
speculative layer — places with meaning, objects that can be manipulated,
whatever the agents turn out to want.

---

## 9. Watching it

An experiment we cannot observe is not an experiment. This is a first-class
component, not a nice-to-have, and it is the thing most likely to be skipped
until it is painful.

Three views exist already and none of them is enough alone:

- **The town** — AI Town's Pixi frontend. Where they are, who is with whom. Says
  nothing about why.
- **Each mind** — Headlong's dashboard, which is already multi-identity
  (`/api/identities`) and shows the trajectory, thinker status, dispatch log,
  spend, and a timeline with deep links to individual steps.
- **The conversations** — messages, in either UI.

The problem: headlong's dash discovers identities on **one filesystem root**. The
moment each agent lives in its own microVM (§10), there are N dashboards, one per
VM, and no aggregate. The isolation we want for safety directly costs us the
observability we want for research.

Options, to settle alongside the isolation mechanism:

1. **Aggregating proxy.** `observatory/` fans out to each agent's dash API and
   presents one roster. Keeps isolation intact; we write a little UI.
2. **Read-only trajectory export.** Each VM ships its `trajectory.jsonl` to a
   shared read-only mount; one dash serves them all. Simplest, and a one-way
   channel is a much smaller hole than a shared filesystem.
3. **Bridge as the tap.** The bridge already tails every trajectory — it could
   mirror what it sees into one place, for free.

(3) is nearly free and worth doing regardless of what else we build; it is also
the natural home for the cross-agent view no per-identity dash can give:
**one timeline, all agents, interleaved with town events.** That is the artifact
this experiment actually produces, and it should exist by M5.

What must be captured per run, or the run is not reproducible: personas, model
per identity, perception thresholds, the full mind log, and spend per agent.

## 10. Isolation and deployment

Requirement: **the town is the only shared surface.** Headlong agents run
arbitrary bash with their own API keys. Two agents that can reach each other's
filesystem or network are not really two agents.

Options, to evaluate at M5:

- **Apple `container`** (macOS 26) — each container already gets its own
  lightweight VM. Native on the dev machine, no extra stack. Likely the best
  local option; needs verifying that Headlong's own Docker sandboxing composes
  with it (`shellm` nests: agent code wants a container *inside* the agent VM).
- **Firecracker / Cloud Hypervisor** — the real microVM answer for a Linux host,
  and where this ends up if it runs anywhere but the laptop.
- **Plain Docker, one container per identity** — weakest boundary, but the
  cheapest to stand up and fine for early milestones.

Whichever we pick, per-agent: its own state home, its own trajectory, its own LLM
key (spend-capped, separate), egress limited to the bridge and the LLM provider.

**Prompt injection between agents is in scope, not a bug.** One agent talking
another into doing something is exactly the kind of thing worth observing. The
isolation is there so that it stays *social* rather than becoming filesystem
access.

---

## 11. Cost

A Headlong agent costs roughly $1–2/hour on Sonnet at default pacing. Five agents
running continuously is real money, and the town is more interesting when it runs
for days than when it runs for an hour.

Levers, in order of preference:
1. Perception batching (§6) — fewer wakeups is strictly better than cheaper
   thoughts.
2. Longer backoff caps once we see what the pacing actually looks like in a
   populated town. Note that *other agents are external events*, so a busy town
   keeps everyone's backoff reset — the population itself drives cost superlinearly.
3. Cheaper think model. Keep `THINK_MODEL` / `SHELLM_MODEL` per-identity and
   configurable; the responder already has its own `MONOLITH_REPLY_MODEL` knob,
   so cheap replies with a stronger monolith is available.
4. A world clock that runs faster than wall time, so a day of town life costs
   fewer hours of thinking. Speculative.

Instrument spend per identity from M1 — the dashboard already has a usage API.

---

## 12. Open questions

Most of the earlier list is settled and folded into §1 and §4. What is left:

1. **Perception thresholds.** §6's salience filter and coalescing window are
   guesses. Deliberately so — start with the guesses, watch a populated town,
   tune. Instrument wakeups-per-agent-per-hour from M1 so there is data to tune
   against.
2. **Group turn-taking quality.** `NO_REPLY` as the gate (§4) is sound in
   principle, but whether a group of four converses or deadlocks into mutual
   silence is an empirical question. Fallback if it deadlocks: a small random
   speak-anyway probability, or letting the monolith break silence via `share`.
3. **World clock vs wall clock.** Running the town faster than real time buys
   more town-life per dollar, but Headlong's pacing is wall-clock throughout
   (backoff in seconds, `wake_at` in epoch). Probably impossible without touching
   headlong core, which we said we would not do. Parked, unresolved.
4. **What the bridge does with a mind that is merely slow**, as opposed to dead.
   A monolith resting at a 300s backoff looks identical to a hung one from the
   town's side. Liveness needs a signal better than "has it acted recently" —
   headlong's `run/dispatcher.pid` and the dash's health API are the likely source.
5. **Isolation mechanism.** Apple `container`, Firecracker, or plain Docker (§10).
   Decide at M5, when there is something worth isolating. The open sub-question is
   whether Headlong's own Docker sandboxing nests cleanly inside a microVM —
   `shellm` wants a container *inside* the agent, for the agent's own generated code.
6. **How we watch N isolated agents** (§9). Tied to (5): the stronger the
   isolation, the harder the aggregate view. Settle both together, not separately.

## 13. Known sharp edges

- `Conversation.leave()` calls `stop()` — one person leaving currently ends the
  conversation for everyone. First thing to fix in M4.
- **`lastInput` is written once at join and never updated anywhere**, so *any*
  player with a `human` field is evicted after `HUMAN_IDLE_TOO_LONG` no matter
  what it does — there is no heartbeat to send. This is why the plan's "join as
  a human player" shortcut for M1 was abandoned: a body with **no** `human`
  field and no `Agent` record is ticked by neither loop, never evicted, and not
  subject to `MAX_HUMAN_PLAYERS`. That is the right shape for an
  externally-driven body anyway, so M3's `Agent.kind: 'external'` is now a
  smaller change than planned.
- **A body that never moves cannot finish a rendezvous.** A conversation only
  becomes `participating` when members are within `CONVERSATION_DISTANCE` (1.3
  tiles), and the inviter gives up after `INVITE_TIMEOUT` (60s). So even a
  "speech only" milestone needs minimal walk-to-meet — the bridge does it
  mechanically in M1, and it becomes the mind's decision at M2.
- `ACTION_TIMEOUT` (120s) < monolith backoff cap (300s). Any external operation
  modelled on the existing `inProgressOperation` mechanism will time out at rest.
- **The world freezes when no browser is watching, and a frozen engine
  processes no inputs.** The `stopInactiveWorlds` cron marks any world whose
  `lastViewed` is older than `IDLE_WORLD_TIMEOUT` (5 min) as `inactive` and
  stops its engine. Nothing errors: inputs keep being accepted and queued, they
  simply never get a `returnValue`, so bodies go quiet for no visible reason.
  Hit on 2026-08-29 while debugging a body that would not walk. The bridge now
  calls `heartbeatWorld` every 30s, which both refreshes `lastViewed` and
  restarts an already-inactive world (it leaves `stoppedByDeveloper` alone, so
  the freeze button still works). Removing the cron is still the right move at
  M3 — a town with minds in it should not need a spectator.
- `chat send` refuses `from == to`, and the responder only answers messages where
  `to == $IDENTITY_NAME`. The `town-` prefix keeps us clear of both.
- The bridge must stamp `source:"chat"` on outbound speech; the slack bridge
  drops non-`chat` message steps deliberately, and we want the same discipline
  (thinkers sometimes append raw `message` steps that are thinking-out-loud, not
  speech).
- Headlong's dispatcher coalesces pending `observation` steps last-wins. A burst
  of perception silently collapses — which is what we want, but it means the
  bridge must not rely on every observation being seen.
- Convex's engine is single-threaded per world and loads all state into memory
  each step. Keep the world doc small; perception events belong in their own
  table, never in world state.
- `skills prompt` injects **kernel** skills in full but lists regular skills by
  name only. If `town` is installed as a regular skill, the responder never sees
  the group turn-taking policy and the whole §4 design silently degrades — with no
  error, just agents talking over each other. Assert this in a test.
- The responder has **no tools** — it is `llm` + `chat reply`, nothing else. It can
  never call `town`. Every reply it produces reaches the world only because the
  bridge is tailing the log. If the bridge's outbound path stalls, agents keep
  talking and the town goes quiet, with both sides believing they are fine.
- `identity new` seeds `chat/.chatrc` with `default_send_from`; `chat send` dies
  without a sender name. Per-identity, not per-directory (see headlong's AGENTS.md).
- Headlong's `--bin` list is what generated code can actually execute. A `town`
  binary that exists on the host but is missing from that list is invisible to
  the mind, no matter what the skill declares.
- **headlong's dispatcher silently stops delivering trajectory steps** (macOS,
  bash 3.2). It stays alive, keeps ticking, keeps consuming its FIFO — and never
  logs or dispatches another step. Every dispatcher works when fresh and dies
  within minutes; a brand-new identity that has never touched the town fails the
  same way, so this is inside headlong, not at the ai-town seam. Partial cause
  proven: bash 3.2's `read -t` DISCARDS partial input on timeout, while the loop
  explicitly assumes it is returned ("*bash then returns the partial input*").
  That explains occasional loss but NOT the permanent silence, so the root cause
  is still open. The bridge routes around it by waking thinkers directly (§3).
  Worth reporting upstream with the one-line repro.
- **Start the bridge before the mind.** `_load_env_defaults` fills in only
  variables that are *not already set*, and every thinker inherits the
  dispatcher's environment. A dispatcher started before the bridge wrote
  `TOWN_URL` pins the stale value for the life of the dispatcher, and no amount
  of rewriting `.env` changes it — restarting the dispatcher is the only fix.
  Cost us a debugging cycle on 2026-08-30.
- **A mind's generated code runs in a Docker sandbox, so `127.0.0.1` is the
  container's loopback, not the host.** Anything the mind must reach lives at
  `host.docker.internal`, and a control plane bound to host loopback is
  invisible to the only caller that matters.
- **`LLM_API_URL` means different things in the two systems, and they collide.**
  ai-town treats it as a *base* and appends `/v1/chat/completions`
  (`convex/util/llm.ts`); headlong uses it *verbatim* as the full endpoint
  (`bin/llm:667`). Headlong's thinkers load `./.env` from the working directory,
  so an unprefixed `LLM_API_URL` in this repo's `.env` points every mind at
  `https://openrouter.ai/api` — which returns an HTML page. The failure is
  near-silent: the responder reports "empty model output" and the HTML lands in
  its log. `LLM_MODEL` and `LLM_API_KEY` collide the same way. Hence the repo
  `.env` namespaces them `AITOWN_*`, and `setup-baseline.sh` maps them onto the
  names Convex reads. Observed 2026-08-29.
- **Sourcing an identity's `activate` bare picks the wrong model.** It falls back
  to `${SHELLM_MODEL:-claude-opus-4-7}`, an expensive Anthropic default we have
  no key for, and `THINK_MODEL` being already-set then beats the `.env` loading
  inside the thinkers. Fix durably by writing `think_model=` into the identity's
  `info.txt`, which is also where a per-identity model belongs (§11).
- **Reasoning models silently produce empty messages in AI Town.** Ollama's
  OpenAI-compatible endpoint returns thinking in a separate `reasoning` field,
  but those tokens still count against `max_tokens` — and
  `convex/agent/conversation.ts` hardcodes `max_tokens: 300`. A thinking model
  spends the whole budget reasoning and returns `content: ""`, so agents post
  blank messages with no error anywhere. Worse, blank messages feed back as
  conversation history (`"Stella to Lucky: "` with nothing after), and the model
  copies the pattern — one empty reply poisons the rest of the conversation.
  Observed with `gemma4:e2b` on 2026-08-29. Fixes: use a non-thinking model, or
  send `reasoning_effort: "none"` (verified working), or raise the budget. Moot
  after M3, when this layer is deleted — but the same trap applies to any model
  we point a Headlong identity at, so check for a `reasoning` field before
  trusting a cheap model's output.

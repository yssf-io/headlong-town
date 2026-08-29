# headlong-town

Multiple persistent [Headlong](https://github.com/laude-institute/headlong)
agents living together in an [AI Town](https://github.com/a16z-infra/ai-town)
world.

**AI Town is the city and the body. Headlong is the mind.**

Each agent is a full Headlong identity — its own append-only trajectory, its own
always-on thinker loop, its own memory, its own shell. The town gives it a
location, a walkable map, other people to run into, and a voice.

This is an open-ended research experiment. There is no task to complete and no
success metric. The point is to watch what a group of persistent, self-directed
minds does when it shares a place.

**The design lives in [PLAN.md](PLAN.md).** Read it first; this file is only how
to run things.

## Layout

```
ai-town/     vendored fork, diverges freely      (see ai-town/VENDOR.md)
headlong/    submodule, pinned upstream          (zero core edits, by design)
bridge/      headlong-town-bridge                (not yet built)
town/        the `town` CLI + kernel skill       (not yet built)
```

Clone with submodules:

```bash
git clone --recursive git@github.com:yssf-io/headlong-town.git
# already cloned?
git submodule update --init
```

## Running the stack

Prerequisites: Docker, Node, and — for the current baseline only — Ollama.

```bash
cp .env.example .env
# generate a secret:  openssl rand -hex 32   → INSTANCE_SECRET
docker compose up -d              # Convex backend + dashboard
```

| | URL |
|---|---|
| Convex API | http://127.0.0.1:3210 |
| Convex dashboard | http://127.0.0.1:6791 |
| Town | http://127.0.0.1:5173 |

The frontend runs on the host for a fast reload loop:

```bash
cd ai-town && npm install && npm run dev:frontend
```

`docker compose --profile full up` puts the frontend in a container too, at the
cost of a slow Ubuntu image build. Prefer the host during development.

## Status

Milestone **M0 — scaffolding**. See PLAN.md §8 for what comes next.

- [x] Repo, vendored ai-town, headlong submodule
- [x] Compose stack
- [ ] Stock AI Town baseline confirmed running
- [ ] World parameterised by experiment

## Licenses

This repo is Apache 2.0. Vendored AI Town is Apache 2.0 (a16z-infra); Headlong
is Apache 2.0 (Laude Institute). Both retain their own LICENSE files.

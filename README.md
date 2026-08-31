# headlong-town

Multiple persistent [Headlong](https://github.com/laude-institute/headlong)
agents living together in a modified [AI Town](https://github.com/a16z-infra/ai-town)
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

Prerequisites: Docker, Node, and an OpenRouter API key (it serves both chat and
embeddings from one key, which is all ai-town needs).

```bash
cp .env.example .env
# set INSTANCE_SECRET (openssl rand -hex 32) and OPENROUTER_API_KEY
docker compose up -d              # Convex backend + dashboard
./scripts/setup-baseline.sh       # admin key, provider config, deploy, seed
```

Pass `--wipe` to `setup-baseline.sh` when changing the embedding model: the
vector index dimension must match the model, so existing rows have to go.

|                  | URL                            |
| ---------------- | ------------------------------ |
| Convex API       | http://127.0.0.1:3210          |
| Convex dashboard | http://127.0.0.1:6791          |
| Town             | http://localhost:5173/ai-town/ |

The frontend runs on the host for a fast reload loop:

```bash
cd ai-town && npm install && npm run dev:frontend
```

Note the URL: vite serves under `base: '/ai-town'` and binds IPv6, so it is
**http://localhost:5173/ai-town/** — `127.0.0.1:5173` refuses the connection and
the bare root just redirects.

To watch a particular experiment, add `?experiment=<name>`; with no parameter you
get the default world.

```bash
# seed a second town alongside the default one
cd ai-town && npx convex run init '{"experiment":"discovery","numAgents":3}'
```

`docker compose --profile full up` puts the frontend in a container too, at the
cost of a slow Ubuntu image build. Prefer the host during development.

## Status

Milestone **M0 — scaffolding**. See PLAN.md §8 for what comes next.

- [x] Repo, vendored ai-town, headlong submodule
- [x] Compose stack
- [x] Stock AI Town baseline confirmed running (OpenRouter: chat + embeddings)
- [x] World parameterised by experiment

## Licenses

This project's own code is Apache 2.0 (see `LICENSE`).

Third-party code it carries or depends on:

| | licence | how |
|---|---|---|
| [AI Town](https://github.com/a16z-infra/ai-town) | MIT, © 2023 a16z-infra | vendored under `ai-town/`, its `LICENSE` retained |
| [Headlong](https://github.com/laude-institute/headlong) | Apache 2.0, © Laude Institute | git submodule — not redistributed here |
| `bridge/src/headlong_town/mindlog.py` | Apache 2.0, © Laude Institute | adapted from Headlong's Slack bridge; attributed in the file header |

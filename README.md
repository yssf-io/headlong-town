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

## From a clean clone

You need Docker, Node 20+, and an OpenRouter API key. (`uv` too, if you want the
mind dashboard.)

**1. Clone with submodules** — Headlong is a submodule, and nothing works without it:

```bash
git clone --recursive https://github.com/yssf-io/headlong-town.git
cd headlong-town
```

**2. Configure the host**

```bash
cp .env.example .env
```

Set two things in `.env`:

- `INSTANCE_SECRET` — any secret, e.g. `openssl rand -hex 32`
- `OPENROUTER_API_KEY` — one key covers both chat and embeddings

`BIND_ADDR` defaults to `127.0.0.1`. Leave it unless you want the UIs reachable
from another machine, and read the note in `docker-compose.yml` first — Docker
publishes ports by writing its own firewall rules, which **bypass ufw**.

**3. Start the engine and set it up (once)**

```bash
docker compose up -d          # Convex backend
cd ai-town && npm install && cd ..
./scripts/setup.sh            # admin key, LLM config, deploy functions
```

Re-run `setup.sh` after any `docker compose down` — that invalidates the admin key.

**4. Declare an experiment**

```bash
cp -r experiments.example experiments/myrun
$EDITOR experiments/myrun/experiment.toml
```

Two things have no default, because nobody can choose them for you: the
**minds** that live in the town (each a full Headlong identity, with a persona
in `personas/`) and which **stock AI Town characters** join them. Everything
else is tuned already — see `[bridge]` in the example.

**5. Run it**

```bash
./scripts/experiment up     myrun
./scripts/experiment status myrun
./scripts/experiment down   myrun
```

`up` is idempotent: add a mind to the spec, re-run, and it creates only the new
one — existing minds keep their memories.

**6. Watch**

```bash
cd ai-town && npm run dev:frontend   # the town
./scripts/run-dash.sh                # the minds
```

| | |
|---|---|
| The town | http://localhost:5173/ai-town/ |
| Mind dashboard | http://127.0.0.1:8080 |
| Convex dashboard | `docker compose --profile admin up -d` → http://127.0.0.1:6791 |

The town URL needs the `/ai-town/` path — vite serves under `base: '/ai-town'`.

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

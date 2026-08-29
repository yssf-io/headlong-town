# Vendored from a16z-infra/ai-town

This directory is a **vendored copy**, not a submodule and not a subtree.

    upstream: git@github.com:a16z-infra/ai-town.git
    vendored: 8e05997f2409275669c8344b84a51692e83f3f33  (2026-08-25)
    license:  Apache 2.0 — see LICENSE

## Why vendored

Upstream took 9 commits in the 12 months before we forked; it is effectively
dormant. We, meanwhile, delete its entire agent layer (`convex/agent/`,
`convex/aiTown/agentOperations.ts`) and rewrite `convex/aiTown/conversation.ts`.
There is nothing to track and everything to diverge from, so a subtree or
submodule would buy only merge conflicts.

See `../PLAN.md` §2.

## Taking a change from upstream

Histories are unrelated and paths are prefixed, so `git cherry-pick` will not
work directly. Apply the patch with the prefix instead:

    git clone git@github.com:a16z-infra/ai-town.git /tmp/ai-town-upstream
    git -C /tmp/ai-town-upstream show <sha> | git apply --directory=ai-town

The root repo also carries `ai-town-upstream` as a remote, so `git fetch
ai-town-upstream` works for reading history without a second clone.

"""headlong-town-bridge — Headlong minds, AI Town bodies.

The bridge is the only thing that knows about both systems. It owns:

  perception  town events  -> observation/message steps in a mind's trajectory
  speech      message steps -> messages in the town
  action      `town` CLI    -> engine inputs            (M2)

Modelled on headlong's own slack/ and telegram/ bridges: encode the far-side
conversation into a chat name, append inbound into the mind log, tail the mind
log for outbound. No trajectory schema changes, no thinker changes.
"""

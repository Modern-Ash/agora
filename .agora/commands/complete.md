---
name: "agora-complete"
description: "Validate final gates and complete governed work"
---

# Complete governed work

If it is not obvious from the request, state in one line the terminal transition and role plus the
gate, criteria, artifact, evidence, approval, and validation checks. Do not reconfirm requested
completion when authority is durable, and do not narrate each step; never invent human approval.
Pause and ask one concrete question — context, choice, recommended default — before the terminal
transition when any approval or decision is the human's. End the turn once work is completed or the
gate blocks it.

Start with `agora work inspect --swarm <swarm> --work <work>`; on an older CLI, use targeted
`show` and `readiness` queries. Read additional registers and policies only when the terminal edge
requires detail. Confirm role, validate the gate, and transition with Agora. Run full validation only
for cross-record integrity. On gate failure, report missing items and leave work unchanged. A child
result is evidence, not automatic parent acceptance. Report state, confirmed checks, missing items,
and next action.

Reuse the compact inspection `snapshot_token` before the transition. If completion is launched as a
separate session, use `--execution-profile efficient --max-transcript-bytes 65536`; increase the
profile only when the terminal gate requires substantive review rather than record bookkeeping.

Completion target: `$ARGUMENTS`

---
name: "agora-review"
description: "Review work against its protocol, criteria, artifacts, and evidence"
---

# Review governed work

If it is not obvious from the request, state in one line what you will review and the criteria,
authority, artifact, evidence, gate, and verification checks you will confirm. Use targeted context;
run project-wide validation only for cross-record findings. Pause and ask one concrete question —
context, choice, recommended default — before any decision that is the user's or an authorized
role's. End the turn once findings are recorded; do not add unrelated checks or restate them.

Start with `agora work inspect --swarm <swarm> --work <work>`; use `work inspect --full` or
targeted domain queries only for details required by the review. On an older CLI, fall back to
targeted `show`, `readiness`, and `traceability` queries. Review the change and Agora record together.
Reuse the compact inspection `snapshot_token` until relevant durable material changes. Keep a review
session `balanced` by default; select `complex` only for genuinely ambiguous implementation or
security analysis, and keep its durable transcript at 128 KiB unless final diagnostics need more.
Check role attribution, applicable tool policy,
acceptance criteria, required artifacts, evidence, approvals, and the selected Method Pack edge and
gate. For environment-aware Tool Runs, verify the recorded environment against current role and
project policy. Inspect relevant Tool Pack results, not conversational claims. Persist only material
findings and never satisfy criteria without inspectable support. Review delegated work at its
authoritative `agora://` location. Report findings by severity, confirmed checks, blockers, and next
action; omit raw payloads unless requested.

Review target: `$ARGUMENTS`

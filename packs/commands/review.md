---
name: "agora-review"
description: "Review work against its protocol, criteria, artifacts, and evidence"
---

# Review governed work

In at most two sentences, tell the user what you will review and which criteria, authority, artifact,
evidence, gate, and verification checks you will confirm. Use targeted context; run project-wide
validation only for cross-record findings.

Start with `agora work inspect --swarm <swarm> --work <work>`; use `work inspect --full` or
targeted domain queries only for details required by the review. On an older CLI, fall back to
targeted `show`, `readiness`, and `traceability` queries. Review the change and Agora record together.
Check role attribution, applicable tool policy,
acceptance criteria, required artifacts, evidence, approvals, and the selected Method Pack edge and
gate. For environment-aware Tool Runs, verify the recorded environment against current role and
project policy. Inspect relevant Tool Pack results, not conversational claims. Persist only material
findings and never satisfy criteria without inspectable support. Review delegated work at its
authoritative `agora://` location. Report findings by severity, confirmed checks, blockers, and next
action; omit raw payloads unless requested.

Review target: `$ARGUMENTS`

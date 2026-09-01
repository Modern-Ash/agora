# Compact work inspection

Agora Core now exposes `work_inspection()` and
`agora work inspect --swarm <swarm> --work <work>` as the default decision surface for one
agent iteration.

The projection preserves the information needed to choose a safe next action: lifecycle and
operational state, bounded available transitions and blockers, assignments and approval actors,
criteria and material counts, required and missing artifacts, terminal status, and a deterministic
snapshot token. It excludes histories, full material bodies, provider output, prompts, credentials,
and model reasoning. Every variable-size field is bounded and reports truncation explicitly.

The consistency fingerprint covers only durable inputs that can affect this projection. In a local
comparison against a completed Renovatio work item, the compact read took about 0.28 seconds and
returned about 0.9 KB. Four separate discovery reads took about 0.92 seconds and returned about
10.9 KB of useful output; the full control projection returned about 80 KB. These numbers are a
single local scenario, not a universal performance guarantee, but they demonstrate the intended
reduction in process startup, filesystem reads, and context usage without weakening Core checks.

Portable specify, execute, review, complete, and status skills now prefer the compact read and retain
targeted fallbacks for older Agora CLIs. Objective definition, swarm formation, and handoff skills do
not inspect an already-selected work item and therefore remain unchanged.

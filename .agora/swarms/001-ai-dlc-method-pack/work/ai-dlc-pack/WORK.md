---
schema: "agora/work/v1"
id: "ai-dlc-pack"
swarm: "ai-dlc-method-pack"
title: "ai-dlc Method Pack"
state: "clarified"
revision: 1
operational-status: "active"
status-reason: null
status-by: null
status-at: null
acceptance-criteria: {"ac-pack-valid":"agora validate and agora method accept the ai-dlc pack; all states reachable, terminal has no outgoing edge","ac-roles-conform":"agora self-test passes with ai-dlc in BUNDLED_METHODS for human, ai-agent, swarm holders","ac-lifecycle-test":"tests/test_ai_dlc_lifecycle.py drives initiation to completed plus both rework edges, green","ac-sample-runs":"uv run python samples/ai-dlc/run.py exits 0 and is discovered by the verifier","ac-gates-enforced":"each phase transition is rejected when gate obligations are unmet","ac-docs":"method-packs reference, new guide, README table describe ai-dlc; link and packaging checks pass","ac-verify-all":"uv run python scripts/verify_all.py passes end to end"}
satisfied-criteria: []
criterion-statuses: {"ac-pack-valid":["specified"],"ac-roles-conform":["specified"],"ac-lifecycle-test":["specified"],"ac-sample-runs":["specified"],"ac-gates-enforced":["specified"],"ac-docs":["specified"],"ac-verify-all":["specified"]}
required-artifacts: ["spec","implementation-plan"]
child-work-refs: []
budget-limits: null
---

# ai-dlc Method Pack

## Description

Translate AWS AI-DLC five-phase methodology to a bundled Agora Method Pack, Markdown-only, no kernel changes. Spec: docs/superpowers/specs/2026-09-01-ai-dlc-method-pack-design.md

## Acceptance criteria

- [ ] **ac-pack-valid:** agora validate and agora method accept the ai-dlc pack; all states reachable, terminal has no outgoing edge; stages: specified
- [ ] **ac-roles-conform:** agora self-test passes with ai-dlc in BUNDLED_METHODS for human, ai-agent, swarm holders; stages: specified
- [ ] **ac-lifecycle-test:** tests/test_ai_dlc_lifecycle.py drives initiation to completed plus both rework edges, green; stages: specified
- [ ] **ac-sample-runs:** uv run python samples/ai-dlc/run.py exits 0 and is discovered by the verifier; stages: specified
- [ ] **ac-gates-enforced:** each phase transition is rejected when gate obligations are unmet; stages: specified
- [ ] **ac-docs:** method-packs reference, new guide, README table describe ai-dlc; link and packaging checks pass; stages: specified
- [ ] **ac-verify-all:** uv run python scripts/verify_all.py passes end to end; stages: specified

## Required artifacts

- spec
- implementation-plan

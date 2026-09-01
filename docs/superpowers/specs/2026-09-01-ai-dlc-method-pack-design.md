# ai-dlc Method Pack — design

**Status:** approved for implementation
**Date:** 2026-09-01
**Swarm:** `ai-dlc-method-pack` (spec-driven)

## Problem

AWS published the AI-Driven Development Life Cycle (AI-DLC): a methodology
([blog](https://aws.amazon.com/blogs/devops/ai-driven-development-life-cycle/))
and a harness-neutral implementation
([`awslabs/aidlc-workflows`](https://github.com/awslabs/aidlc-workflows)) that
renders one gated, auditable, AI-first SDLC across seven agent harnesses. It
overlaps heavily with Agora's thesis — process as configuration, approval gates,
evidence in Git, replaceable LLM — but ships as a fixed methodology with a
hard-coded five-phase graph rather than a governance kernel.

Agora has no bundled method that speaks the AI-DLC vocabulary. A team arriving
from the AWS ecosystem has to author a custom Method Pack from scratch to get a
recognizable lifecycle.

## Goal

Ship `ai-dlc` as a **bundled Method Pack** that translates AI-DLC's five phases
into Agora's lifecycle contract, with **zero kernel changes**. The pack is
Markdown-only under `packs/methods/ai-dlc/`, exercised by the role-conformance
harness and by an executable sample, and documented as a first-class workflow
choice alongside `spec-driven`, `scrum`, and `kanban`.

## Non-goals (tracked as separate work items)

- **Learning loop** — human corrections becoming durable, reinjected rules.
- **Adaptive composer** — proposing a gate/depth subset from a diff or scan.
- **Ceremony / depth dial** — `minimal | standard | comprehensive` per swarm.
- **Concurrent gate review** — the "mob elaboration / mob construction" model of
  several role holders validating the same checkpoint at once.

These are noted in `PROTOCOL.md` as practices, not governed mechanisms.

## Mapping AI-DLC to Agora

AI-DLC defines "5 phases, 33 stages" with "an approval gate at every stage". The
33 stages are activities inside a phase, not governed lifecycle states. Modelling
all 33 as `work-states` would be unusable and would not match how Agora gates
work. The pack therefore models **phase boundaries as work-states and gates**,
and documents the intra-phase stages as expected work in `PROTOCOL.md`.

| AI-DLC phase | Agora work-state | Boundary gate |
| --- | --- | --- |
| Initialization | `initiation` | — (entry state) |
| Ideation | `ideation` | `intent-framed` |
| Inception | `inception` | `units-elaborated` |
| Construction | `construction` | `design-approved` |
| Operation | `operation` | `build-verified` |
| (delivery) | `completed` | `completion` |

### `METHOD.md`

```yaml
schema: "agora/method/v1"
id: "ai-dlc"
name: "AI-Driven Development Life Cycle"
version: "1.0.0"
dependencies: []
required-roles: ["product-owner", "architect", "builder", "operator", "quality-reviewer"]
work-states: ["initiation", "ideation", "inception", "construction", "operation", "completed"]
terminal-state: "completed"
wip-limits: {}
criterion-stages: ["elaborated", "designed", "built", "verified", "deployed", "accepted"]
criterion-stage-roles:
  elaborated: ["product-owner", "architect"]
  designed: ["architect"]
  built: ["builder"]
  verified: ["quality-reviewer", "builder"]
  deployed: ["operator"]
  accepted: ["product-owner"]
```

### Transition graph (`transitions/`)

| File | from → to | gate | roles |
| --- | --- | --- | --- |
| `01-initiation-ideation.md` | initiation → ideation | `intent-framed` | product-owner |
| `02-ideation-inception.md` | ideation → inception | `units-elaborated` | product-owner |
| `03-inception-construction.md` | inception → construction | `design-approved` | architect |
| `04-construction-operation.md` | construction → operation | `build-verified` | quality-reviewer |
| `05-operation-completed.md` | operation → completed | `completion` | product-owner |
| `06-construction-inception.md` | construction → inception | — | architect |
| `07-operation-construction.md` | operation → construction | — | quality-reviewer |

Edges 06 and 07 are rework paths — a requirements gap found during construction
returns to inception; failed verification during operation returns to
construction. No bypass flags; the specification does not mutate mid-cycle.

### Roles (`roles/`)

Agora roles are authority buckets, not personas: AI-DLC's 14-agent roster
collapses to five roles, and one human (or one AI) may hold several.

| Role | Responsibility | Key actions | Actor kinds |
| --- | --- | --- | --- |
| `product-owner` | Holds the intent and final acceptance ("humans make critical decisions") | `work.create`, `work.clarify`, `criterion.satisfy`, `approval.add`, `gate.waive`, `handoff.create` | human, ai-agent, swarm |
| `architect` | Inception: requirements, units of work, domain model, architecture | `work.transition`, `work.decompose`, `artifact.add`, `criterion.satisfy` | human, ai-agent, swarm |
| `builder` | Construction: code and tests (mob construction) | `work.transition`, `artifact.add`, `evidence.add`, `criterion.satisfy` | human, ai-agent, swarm, automation |
| `operator` | Operation: infrastructure-as-code and deployment | `work.transition`, `evidence.add`, `criterion.satisfy` | human, ai-agent, swarm, automation |
| `quality-reviewer` | The two AI-DLC quality-gate reviewers, merged | `work.transition`, `review.*`, `approval.add`, `criterion.satisfy` | human, ai-agent, swarm |

`allowed-tool-capabilities`:
- `builder`: `repository.read/write`, `review.read`, `ci.run`.
- `operator`: `ci.read`, `cloud.read`; write/apply capabilities stay opt-in via
  project environment policy.
- `quality-reviewer`: `repository.read`, `review.read/write/decide`.
- `architect`: `repository.read`, `docs.read/write`.
- `product-owner`: `docs.read/write`, `portfolio.read/write`, `issue.*`.

### Gates (`gates/`)

| Gate | Requires |
| --- | --- |
| `intent-framed` | `intent` artifact registered; latest clarification run covers current inputs with no open question (`require-resolved-clarifications: true`) |
| `units-elaborated` | `units-of-work` artifact; all criteria at stage `elaborated`; `product-owner` approval |
| `design-approved` | `architecture` + `domain-model` artifacts; all criteria at stage `designed`; `architect` + `product-owner` approval |
| `build-verified` | all criteria at stage `verified`; ≥1 successful evidence record; `quality-reviewer` approval |
| `completion` | all criteria at stage `accepted`; `deployed` recorded; deployment evidence; `product-owner` approval |

Gate field shapes mirror `packs/methods/spec-driven/gates/*.md`
(`require-all-criteria`, `required-criterion-stage`, `required-artifacts`,
`require-successful-evidence`, `required-approval-roles`,
`require-resolved-clarifications`).

### `PROTOCOL.md`

Documents:
- The AI-DLC operating pattern: *AI plans → AI asks targeted questions → humans
  decide → AI implements*, repeating within every phase.
- The 33 stages as a per-phase checklist of expected activities (non-binding;
  gates evaluate criteria, artifacts, evidence, and approvals only).
- "Bolts" — phase iterations measured in hours/days, not weeks; "Units of Work"
  in place of epics.
- "Mob elaboration / mob construction" described as a review practice carried out
  through `review.*` actions; concurrent multi-holder gate review is not governed
  by this pack version.
- Rework returns work to an earlier state rather than inventing new ones.

### `TOOLS.md`

- `builder` may use repository and CI tools the project permits.
- Merge, release publication, deployment, and infrastructure apply are never
  implied by `builder`; `operator` needs an explicit environment grant.
- Specification and unit-of-work changes require `product-owner` or `architect`.
- Exceptional paths require an explicit transition and gate, not a flag.

## Deliverables

1. `packs/methods/ai-dlc/` — `METHOD.md`, `PROTOCOL.md`, `TOOLS.md`,
   `roles/` (5), `transitions/` (7), `gates/` (5).
2. `samples/ai-dlc/run.py` + `README.md` — installs the pack in an isolated
   Agora home, initializes a project, creates a swarm, and walks
   `initiation → completed` including one rework edge. Part of
   `scripts/verify_all.py` sample discovery.
3. `src/agora/self_test.py` — add `"ai-dlc"` to `BUNDLED_METHODS`.
4. `tests/test_ai_dlc_lifecycle.py` — mirrors `tests/test_spec_driven_lifecycle.py`:
   full happy path plus edges 06 and 07.
5. Docs — `docs/reference/method-packs.md` intro mention; new
   `docs/guides/ai-dlc.md` (phase↔stage mapping, AWS comparison, non-goals);
   `README.md` row in the "Choose a workflow" table.

## Acceptance criteria

- `ac-pack-valid`: `agora validate` and `agora method` accept the `ai-dlc` pack;
  every declared state is reachable and the terminal state has no outgoing edge.
- `ac-roles-conform`: `agora self-test` passes with `ai-dlc` in `BUNDLED_METHODS`
  for human, ai-agent, and swarm role holders.
- `ac-lifecycle-test`: `tests/test_ai_dlc_lifecycle.py` drives
  `initiation → completed` and both rework edges, green.
- `ac-sample-runs`: `uv run python samples/ai-dlc/run.py` exits 0 and is
  discovered by the verifier.
- `ac-gates-enforced`: each phase transition is rejected when its gate
  obligations (artifact, criterion stage, approval, evidence) are unmet.
- `ac-docs`: method-packs reference, the new guide, and the README table
  describe `ai-dlc`; `scripts/verify_all.py` link and packaging checks pass.
- `ac-verify-all`: `uv run python scripts/verify_all.py` passes end to end.

## Verification

`uv run python scripts/verify_all.py` — format, lint, unit + failure-path tests,
doc link and packaging checks, role harness over four packs, sample discovery and
execution, distribution build. TDD: `tests/test_ai_dlc_lifecycle.py` is written
first and fails before the pack exists.

## Risks

- **Gate field coverage** — if `agora/gate/v1` lacks a field the design assumes
  (e.g. multiple distinct approval roles on one gate), fall back to the
  `spec-driven` subset and record the limitation in the guide. Confirmed against
  `packs/methods/spec-driven/gates/*` before implementation.
- **`criterion-stage-roles` with five stages** — larger than any bundled pack;
  the sample must exercise every stage-role entry.
- **Branch policy** — `.agora/` is un-ignored on this branch only so the
  governance trail ships with the PR; `.gitignore` restoration is out of scope
  for this pack and left to the reviewer's discretion.

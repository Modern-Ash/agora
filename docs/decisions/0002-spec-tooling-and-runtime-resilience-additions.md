# ADR 0002: Spec-tooling parity and runtime resilience additions

- Status: Accepted
- Date: 2026-08-20

## Context

Agora's closest neighbors in spec-driven development are GitHub's `spec-kit` and Fission Labs'
OpenSpec. Both are lighter-weight than Agora and both ship a few genuinely useful capabilities Agora
currently lacks: guided clarification before drafting, generated checklists, cross-artifact
consistency analysis, and BDD/Gherkin generation from acceptance criteria. Separately, operating a
real governed swarm (`Modern-Ash/agora-studio`, `studio-artifacts-evidence/artifacts-evidence-mvp`,
2026-08-19) surfaced two runtime gaps that have nothing to do with spec-kit parity: no declared
fallback when a configured integration's provider is unavailable (a Codex quota exhaustion stalled
an `agora run --until-blocked` loop until an operator manually reconfigured the actor), and no
CLI-native aggregate view across swarms and work items without standing up Agora Studio.

This ADR proposes six additions. Each is scoped to preserve [ADR 0001](0001-initial-architecture.md):
local, Markdown-first, Git-native, no hidden database, no LLM SDK embedded in the core, process
defined by Method Packs rather than hard-coded. None of the six introduce a new persistence layer,
a new mutation-authority model, or an implicit trust decision (e.g. silent auto-approval).

## Decision

Adopt all six as scoped below, in the given priority order. Each keeps the existing gate/role/actor
model as the sole authority for what may progress; none of them can transition work state, satisfy
a criterion, or grant an approval on their own.

### 1. `agora work clarify` — guided pre-drafting clarification

**Problem.** `agora work create` requires acceptance criteria up front (`--criterion id:description`,
repeatable). There is no assisted step for surfacing ambiguity before that point, unlike spec-kit's
`/clarify`, which asks up to five targeted questions and encodes the answers back into the spec.

**Design.**
- New CLI command: `agora work clarify --swarm <id> --work <id> --by <actor>` (and a
  `-prepare`/signed-intent counterpart for authenticated actors, matching every other mutating
  command's pattern).
- Delegates to the assigned `spec-owner`-capable actor's configured runtime (same
  `_runtime_command` resolution already used by `agora run`), with a fixed, reviewed prompt asking
  the actor to produce **at most 5** targeted clarification questions plus, if the actor already has
  enough context, proposed answers.
- The output is written as a new durable record, `.agora/swarms/<swarm>/work/<work>/clarifications.md`
  (schema `agora/clarifications/v1`), append-only, with question, answer (nullable), actor, and
  timestamp — the same table-of-Markdown-rows pattern `artifacts.md`/`evidence.md` already use, so
  `lifecycle.py`-style bounded readers can parse it without new infrastructure.
- Does **not** create or satisfy acceptance criteria itself. It is advisory input for whoever
  (human or AI, per role) subsequently runs `agora work criterion-satisfy` — keeping the gate as the
  sole authority, per ADR 0001.
- Non-goal: auto-answering questions from the codebase. If the actor cannot answer, the row's answer
  stays empty and is visible as an open question — mirrors OpenSpec's explicit "unresolved" markers
  rather than spec-kit's implicit auto-resolution.

**Why it fits.** Purely additive Markdown record; no new mutation authority; reuses existing runtime
resolution and reviewed-adapter boundary.

### 2. `agora work checklist` — lightweight, non-binding quality checklists

**Problem.** Acceptance criteria in Agora are binding — satisfying one is a durable, attributed
mutation that gates can require. That is correct for the contract, but it means there is no cheap
way to track "things to double check" that shouldn't count toward `require-all-criteria`. spec-kit's
`/checklist` fills this gap for a "unit tests for English" pass over intent language.

**Design.**
- `agora work checklist add --swarm <id> --work <id> --title <title> --item "text" [--item "text" ...] --by <actor>`.
- Stored as `.agora/swarms/<swarm>/work/<work>/checklists/<slug>.md`, schema `agora/checklist/v1`,
  each item a Markdown task-list line (`- [ ] ...` / `- [x] ...`).
- `agora work checklist check --swarm <id> --work <id> --checklist <slug> --item <n> --by <actor>`
  toggles one item — a durable, attributed mutation, but explicitly outside the
  `acceptance_criteria` / gate-blocking machinery. `_gate_blockers` (workspace.py) is not touched.
- Rendered in Agora Studio's existing Artifacts panel as a fourth, clearly-labeled non-binding
  section, reusing the accessibility and detail-region patterns from
  `studio-artifacts-evidence/artifacts-evidence-mvp` rather than inventing new UI.

**Why it fits.** Deliberately kept outside the gate contract so it cannot be mistaken for, or substitute
for, an acceptance criterion — preserves the meaning of "clarified"/"completed" gates exactly as they
work today.

### 3. `agora work verify-consistency` — cross-artifact consistency check

**Problem.** Nothing today checks that a registered `implementation-plan` artifact doesn't contradict
its `spec`, or that a `verification-report` actually addresses every acceptance criterion. spec-kit's
`/analyze` does a non-destructive pass across `spec.md`/`plan.md`/`tasks.md` for exactly this.

**Design.**
- `agora work verify-consistency --swarm <id> --work <id> --by <actor>`.
- Non-destructive analysis: resolves the work's registered artifact URIs (already validated
  `repo://` paths, same
  boundary `lifecycle.py._spec_uris` and `artifacts.py` use), reads their contents, and asks the
  assigned actor's runtime to report contradictions and coverage gaps against the acceptance
  criteria already on the work item.
- Output is a bounded `consistency-report` artifact plus `consistency-check` evidence using the
  existing artifact and evidence schemas — no new evidence category is needed at the model layer
  beyond the `type` string.
- A project may opt a gate into requiring this evidence type through
  `required-evidence-types: ["consistency-check"]`; it stays advisory by default.

**Why it fits.** Reuses the existing evidence model exactly as designed — "evidence" already means
"a recorded check with a result," and gates already know how to require evidence. No new concepts.

### 4. Per-actor runtime fallback — the highest-priority fix

**Problem.** This is the one that actually blocked a real swarm. `agora actor runtime` sets exactly
one `integration`/`provider`/`model`. When that provider's CLI is unavailable (quota, outage,
missing binary), `agora run` / `agora run --until-blocked` fails the session with no path forward
except a human manually reconfiguring the actor and — separately from this ADR, already fixed in
`agora` `main` — retrying with the recomputed command.

**Design.**
- Extend the actor record schema (`agora/actor/v1`) with an optional, ordered `runtime-fallbacks`
  list, each entry the same `{integration, provider, model}` shape as the primary runtime. Stored as
  durable front matter, exactly like the existing `integration`/`provider`/`model` fields — no new
  file, no new schema version needed beyond an additive field.
- `agora actor runtime --actor <ref> --integration <primary> ... --fallback <integration>:<provider>:<model> [--fallback ... ]`
  (repeatable) to declare the list; `agora actor runtime --clear-fallbacks` to remove it.
- In `_validate_session_preparation` / `resume_session`, if the resolved primary runtime's
  executable is unavailable (`shutil.which` miss, exactly the check `runtime_available` already
  performs) **or** the most recent session for that actor on that runtime failed with a
  provider-reported quota/rate-limit signature, advance to the next fallback entry before raising.
  This is a pure extension of already-existing runtime-availability checking — it does not change
  what counts as a permitted transition, a satisfied criterion, or an approval.
- The resolved runtime actually used is recorded on the session (`SESSION.md`/`SUMMARY.md` already
  carry `integration`/`provider`/`model` — no schema change), so the durable Activity ledger shows
  exactly which runtime executed each session, preserving full auditability of *which* agent acted,
  not just *that* an agent acted.
- Explicitly does **not** silently retry across fallbacks forever — one governed session still means
  one attempt at one resolved runtime; `run --until-blocked`'s existing retry/backoff semantics are
  unchanged, this only changes *which command* a fresh attempt resolves to.

**Why it fits.** No trust boundary changes: falling back to a *different declared, actor-owned*
runtime is not weaker governance than the primary — it is the same actor identity, roles, and
permissions, just a different execution backend, which the model already treats as an orthogonal
concern (`integration`/`provider`/`model` vs. `roles`/`capabilities`).

### 5. `agora work gherkin` — generate BDD features from acceptance criteria

**Problem.** Acceptance criteria are already structured `id: description` pairs. spec-kit's
`/gherkin` step turns similar structured intent into executable Given/When/Then features; Agora has
no equivalent, even though the structured input already exists natively in `WORK.md`.

**Design.**
- `agora work gherkin --swarm <id> --work <id> --by <actor>`, delegating to the assigned actor's
  runtime with the work's `acceptance_criteria` as fixed structured input (not free text) and a
  reviewed prompt to produce one `.feature` file per criterion.
- Registered as the artifact kind `gherkin-feature` through the existing open artifact model. A
  work contract or Method Pack gate opts into making the output mandatory by requiring that kind;
  generation remains optional otherwise.
- Non-goal: executing the generated features. Agora does not become a test runner; the artifact is
  registered for human/CI consumption exactly like `implementation-plan` is today.

**Why it fits.** Zero model changes — `acceptance_criteria` already exists, artifact kinds are
already an open allowlist per Method Pack.

### 6. `agora status --board` — CLI-native aggregate view

**Problem.** `agora status` already returns swarm/work/session counts and an `attention` block
(forming swarms, blocked work, failed sessions). What's missing is a human-scannable, terminal-native
rendering across all swarms and work items without needing Agora Studio — useful for CI logs, SSH
sessions, and anyone who considers a local web server out of scope for a quick check.

**Design.**
- `agora status --board` renders the *same* data `agora status` and `agora work list` already
  return (no new reads, no new boundary) as a fixed-width terminal Kanban: one column per Method
  Pack work-state, one row per work item, swarm id and blocked/attention markers inline. Plain JSON
  (`agora status`, unchanged) remains the machine-readable default; `--board` is a formatting flag,
  not a new data source.
- Explicitly not a TUI (no curses, no interactivity, no new dependency) — a single rendered frame to
  stdout, consistent with every other Agora CLI command being one-shot and scriptable.

**Why it fits.** Presentation-only change over already-public, already-validated data. No new reads,
no new mutation surface.

## Explicitly rejected (stays out of scope)

- **Parallel multi-agent execution within one swarm.** Would require a coordination/message-passing
  layer Agora does not have and should not build — that is what AutoGen/CrewAI/LangGraph are for.
  Agora's value is sequential, gated, attributable progress, not runtime choreography. Also see the
  `README.md` note distinguishing Agora's "swarm" (governance unit) from theirs (runtime unit).
- **A backend/server holding authoritative state.** Violates ADR 0001 directly — state must remain
  local Markdown plus Git history, not a database with its own availability and backup story.
- **Default or automatic approval bypass**, including as a side effect of runtime fallback (item 4)
  or consistency checks (item 3). Every approval gate keeps requiring an explicit `agora approval add`
  from a role holder; nothing proposed here can grant one.

## Consequences

Items 1, 2, 3, and 5 are purely additive Markdown or Gherkin records and reuse of existing schemas
(evidence, artifacts, checklists-as-a-new-but-isolated-record-type) — low risk, no changes to
`_gate_blockers`, transition validation, or the permission model. Item 6 is presentation-only.

Item 4 is the only one that touches the runtime-resolution path
(`_validate_session_preparation`/`resume_session`) that was already modified once this cycle (see
the `resume`-recomputes-runtime and `claude`-permission-mode fixes merged 2026-08-19). Its coverage
therefore includes fallback selection order, executable availability, recognized quota/rate-limit
signals, ordinary failures that must not switch runtime, and Activity Ledger attribution of the
runtime that executed each session.

## Implemented provenance and traceability extension

The accepted implementation also records canonical SHA-256 provenance on clarification rows,
consistency reports, and Gherkin features. `agora work traceability` derives criterion-to-feature,
evidence, and artifact coverage without creating another state store. `agora validate` reports stale
or legacy provenance as non-failing warnings. Gherkin regeneration updates existing criterion files
without duplicating artifact rows; consistency inputs are bounded to 256 KiB and exclude earlier
consistency reports.

## Future work

- Whether checklist items (item 2) should be promotable to acceptance criteria via an explicit
  command, once real usage shows whether that boundary is being worked around informally.
- Whether `gherkin-feature` artifacts (item 5) should get a bounded "does this feature reference an
  undeclared acceptance criterion" consistency check, folding into item 3 rather than staying
  separate.

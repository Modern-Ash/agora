# SDD-first: Spec-Driven Development as Agora's default Method Pack

Status: approved for planning
Date: 2026-08-16

## Problem

Agora ships two bundled Method Packs, Scrum and Kanban, and defaults new
projects to Scrum (`agora configure`, `agora init`, `agora quickstart` all
default `--default-method` to `"scrum"`). Scrum's ceremony (sprints, a
dedicated `scrum-master` role, WIP-limited board) is heavier than most
solo-developer or AI-agent-paired workflows need, and it doesn't match how
agentic coding tools already operate (spec → clarify → plan → tasks →
implement → verify). This is a weaker onboarding path and a weaker sales
pitch than leading with a lifecycle that's both simpler and closer to how
AI-assisted development already happens.

## Goal

Add a third bundled Method Pack, `spec-driven`, implementing a
Spec-Driven Development lifecycle, and make it Agora's default — while
leaving Scrum and Kanban fully supported, fully documented, and at equal
technical footing. Recommended and modern, not exclusive.

This must be additive only: no change to Agora's core validation, gate,
transition, or artifact engine. `spec-driven` is a Markdown contract like
any other Method Pack (same schema `agora/method/v1` and `agora/role/v1`
already used by scrum/kanban) and Agora's LLM/language/OS-agnosticism is
unaffected — the new pack contains no execution logic, only lifecycle
contract data.

## Non-goals

- No new core mechanism (no new gate types, no new artifact kinds beyond
  what `agora artifact add --kind <anything>` already allows freely).
- No change to Scrum or Kanban's states, roles, or transitions.
- No removal of Scrum or Kanban as options — `--default-method scrum` and
  `--default-method kanban` keep working exactly as today.
- No rewrite of `docs/guides/scrum-delivery.md` content — it moves/stays
  intact as a sibling guide, not a demotion.

## Design

### 1. The `spec-driven` Method Pack

New directory `templates/methods/spec-driven/`, structured exactly like
`templates/methods/scrum/`:

```
templates/methods/spec-driven/
  METHOD.md
  roles/spec-owner.md
  roles/developer.md
```

**States** (`work-states` in `METHOD.md`):

```
drafting -> clarified -> planned -> implementing -> verifying -> completed
```

with one rework edge: `verifying -> implementing`.

`terminal-state: completed`.

**Roles:**

- `spec-owner` — required-capabilities: `["specification", "acceptance"]`.
  Allowed actions: `work.create`, `work.criterion-satisfy`,
  `approval.add`. Permitted actor kinds: `human`, `ai-agent`, `swarm`
  (same as Scrum's roles — no special-casing of humans vs AI).
- `developer` — required-capabilities: `["implementation"]`. Allowed
  actions: `work.transition`, `artifact.add`, `evidence.add`. Same
  permitted actor kinds.

**Transitions** (role-gated same as Scrum's `METHOD.md` pattern):

| source | target | roles | gate |
|---|---|---|---|
| drafting | clarified | spec-owner | `spec-clarified` |
| clarified | planned | developer | — |
| planned | implementing | developer | — |
| implementing | verifying | developer | — |
| verifying | implementing | developer | — (rework, no gate) |
| verifying | completed | spec-owner | `completion` |

**Gates:**

- `spec-clarified` (new gate id, defined in this pack only): requires all
  criteria on the work item satisfied and the `spec` artifact kind
  present. This is the SDD "clarify" step expressed with Agora's existing
  gate primitives — `require_all_criteria: true`,
  `require_required_artifacts: true` with `required-artifact: spec`, no
  approval role required (the spec-owner *is* the one moving the
  transition, so a self-serve gate is correct here — consistent with how
  Scrum's non-completion gates work today).
- `completion` (the same built-in gate every Method Pack gets — see
  `_load_gates` default in `methods.py`): requires satisfied criteria,
  required artifacts, successful evidence, and `spec-owner` approval,
  same as Scrum's completion gate today.

**Suggested (documented, not enforced beyond the gate above) artifact
kinds per state** — documented in the new guide, not hardcoded as
`required-artifact` beyond `spec`, so teams aren't forced into artifact
kinds that don't fit their stack:

- `drafting`: `spec`
- `planned`: `plan`, `tasks`
- `implementing`: `source-code`
- `verifying`: `test-report`

No WIP limits (Scrum-specific concept; omitted, same as Kanban already
allows omitting them).

### 2. Default wiring

- `src/agora/model.py`: `BUILTIN_METHODS: tuple[Method, ...] = ("scrum",
  "kanban")` becomes `("spec-driven", "scrum", "kanban")`.
- `src/agora/cli.py`: every `--default-method` argparse default currently
  hardcoded to `"scrum"` (in `configure`, `init`, `quickstart` parsers)
  changes to `"spec-driven"`. Explicit `--default-method scrum|kanban`
  continues to work unchanged; nothing about the flag's validation
  changes.
- No change to `workspace.py` initialize()/configure() fallback logic —
  it already reads whatever default the CLI passes in, and falls back to
  `"scrum"` today only because that's what the CLI defaults were; that
  fallback string updates to `"spec-driven"` too, for the case where
  `~/.agora/config.md` doesn't exist yet (fresh `agora init` with no
  prior `agora configure`).

### 3. Documentation

- `README.md`: Quickstart section's example command and description stay
  structurally the same but no longer need a `--method` override to get
  spec-driven — it's what `agora quickstart` produces by default. A short
  paragraph notes Scrum and Kanban remain available via
  `--default-method`/`--method`, pointing at their guides.
- `docs/getting-started.md`: rewritten to walk through the spec-driven
  lifecycle end to end (drafting → completed) as the primary tutorial,
  mirroring the existing depth and command style of today's Scrum-based
  walkthrough (spec-owner/developer instead of product-owner/scrum-
  master/delivery, spec artifact instead of sprint ceremony). The
  existing Scrum walkthrough content is preserved verbatim as
  `docs/guides/scrum-delivery.md` (already exists — this spec assumes it
  keeps its current Scrum-specific content; no new content merge needed
  there beyond a possible cross-link).
- New `docs/guides/spec-driven-delivery.md`, sibling to
  `docs/guides/scrum-delivery.md`, same depth: role semantics, gate
  behavior, example CLI walkthrough, LLM/agent interaction notes.
- `docs/architecture.md`: the "Templates" section's one-line description
  of `templates/methods` gets `spec-driven` added to the "Scrum and
  Kanban as replaceable presets" sentence.

### 4. Samples

No change required to existing `samples/*` — `samples/custom-lifecycle`
already demonstrates a non-Scrum/Kanban pack, which is the same shape
`spec-driven` takes. A new `samples/spec-driven/` walkthrough is optional
and out of scope for this spec; can be a fast follow.

## Testing

- Extend the existing Method Pack test coverage (wherever
  `templates/methods/scrum` and `templates/methods/kanban` are validated
  in `tests/`) to include `spec-driven`, asserting `load_method_contract`
  succeeds and the pack round-trips through `agora validate`.
- Add/extend a CLI-level test asserting `agora configure` and `agora
  init` with no `--default-method` flag produce `default-method:
  spec-driven` in the written config/project files.
- Add a test exercising the full spec-driven lifecycle end to end (create
  swarm with method=spec-driven, create work, fail the
  `drafting->clarified` transition without a satisfied criterion/spec
  artifact, satisfy it, walk to `completed`), mirroring the existing
  Scrum lifecycle test pattern.
- `agora quickstart` smoke test (manual, already exercised in this
  session for the simple/secure paths) should be re-run once
  `spec-driven` is the default, confirming role-capability auto-mapping
  in `AgoraWorkspace.quickstart` (`_role_capabilities`) still resolves
  correctly against the new pack's two roles.

## Risks / open questions

- **Gate id collision**: `spec-clarified` must not collide with any
  reserved gate id. Current bundled gates are `completion` (default) and
  Scrum/Kanban-specific ones — grep confirms no existing `spec-clarified`
  id, so this is clear, but the implementer should re-check before
  naming it.
- **Existing users who already ran `agora configure`** keep whatever
  `default-method` is already persisted in their `~/.agora/config.md` or
  project `.agora/project.md` — this change only affects the *default*
  argparse value used when no prior config and no explicit flag exist.
  No migration is needed and none is proposed.

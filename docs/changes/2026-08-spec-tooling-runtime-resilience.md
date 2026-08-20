# Spec tooling and runtime resilience

Implemented on 2026-08-20 from
[ADR 0002](../decisions/0002-spec-tooling-and-runtime-resilience-additions.md).

## Delivered behavior

- `agora work clarify` appends at most five runtime-generated questions and optional answers to a
  durable `clarifications.md` record.
- `agora work checklist add|check|show|list` manages attributed, non-binding Markdown task lists.
- `agora work verify-consistency` compares bounded registered repository artifacts with the work
  contract, then registers a `consistency-report` artifact and `consistency-check` evidence.
- `agora work gherkin` generates one registered `gherkin-feature` per acceptance criterion and
  updates existing criterion files in place on regeneration.
- `agora work traceability` derives criterion, stage, feature, evidence, artifact, and provenance
  coverage without another state store.
- `agora actor runtime --fallback integration:provider:model` records ordered runtime alternatives;
  fresh sessions skip missing executables and runtimes whose latest matching failure has a recognized
  quota or rate-limit signature.
- `agora status --board` renders one fixed-width aggregate frame per swarm using the states from its
  active Method Pack.

Authenticated actors have signed prepare/apply variants for every new mutation. Generic integrations
can execute the model-assisted commands through an explicit `--runner`; the reviewed prompt path is
provided in `AGORA_ADVISORY_PROMPT` and the runner returns bounded structured JSON.

## Governance boundary

All specification outputs are advisory by default. They never satisfy a criterion, grant approval,
or transition work. A project makes `consistency-report`, `gherkin-feature`, or
`consistency-check` binding only through the existing work and Method Pack gate configuration.
Clarifications and checklists remain outside gate evaluation.

## Provenance and compatibility

Clarification rows, consistency reports, and Gherkin features record canonical SHA-256 input
provenance. `agora validate` emits non-failing `*.stale` or `*.provenance-missing` warnings, while
legacy generated records without hashes remain readable. Consistency inputs are capped at 256 KiB
and exclude previous consistency reports.

The implementation is additive: existing projects, actor records without fallbacks, and generated
records without provenance remain compatible.

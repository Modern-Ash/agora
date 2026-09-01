# ai-dlc Method Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a bundled `ai-dlc` Method Pack that renders AWS's AI-Driven Development Life Cycle (five phases) as an Agora lifecycle contract, with no kernel changes.

**Architecture:** The pack is Markdown-only under `packs/methods/ai-dlc/`, following the same directory contract as `packs/methods/spec-driven/`. Phase boundaries become `work-states` and gated `transitions/`; the 33 AI-DLC sub-stages are documented as non-binding per-phase checklists in `PROTOCOL.md`. It is registered with the role-conformance harness (`BUNDLED_METHODS`) and covered by a lifecycle test and an executable sample.

**Tech Stack:** Python 3.11+, `uv`, pytest. Agora domain API in `src/agora/` (`agora.workspace.AgoraWorkspace`, `agora.model.*`, `agora.methods.load_method_contract`).

**Spec:** `docs/superpowers/specs/2026-09-01-ai-dlc-method-pack-design.md`

## Global Constraints

- Method Pack directory contract: `METHOD.md` + `roles/<id>.md` per required role are **required**; `transitions/`, `gates/`, `PROTOCOL.md`, `TOOLS.md` recommended. Source: `docs/reference/method-packs.md`.
- `METHOD.md` front matter must be JSON-compatible YAML with `schema: "agora/method/v1"`.
- `id` must match `[a-z][a-z0-9-]*`. `version` is numeric `MAJOR.MINOR.PATCH`.
- Every declared `work-state` must be reachable from the first state; `terminal-state` has no outgoing transition.
- Gate `required-approval-roles` must all appear in `required-roles` (kernel validation raises otherwise).
- Gate `required-criterion-stage` must be one of `criterion-stages`.
- Artifact kinds and evidence types must be slugs (`[a-z][a-z0-9-]*`).
- Transition `roles` array must be non-empty; each listed role must grant `work.transition`.
- Keep Agora's language / model / provider / process independence. Conventional Commits.
- No new runtime dependencies. No LLM SDK.
- `.agora/` is un-ignored on branch `feat/ai-dlc-method-pack` / `agora/ai-dlc-method-pack` so the governance trail ships with the PR; do not re-add the ignore rule.

---

### Task 1: Method Pack contract (`packs/methods/ai-dlc/`)

Create the complete pack. This is one reviewable deliverable: a reviewer accepts or rejects the lifecycle contract as a whole. TDD via `agora.methods.load_method_contract`.

**Files:**
- Create: `packs/methods/ai-dlc/METHOD.md`
- Create: `packs/methods/ai-dlc/PROTOCOL.md`
- Create: `packs/methods/ai-dlc/TOOLS.md`
- Create: `packs/methods/ai-dlc/roles/product-owner.md`
- Create: `packs/methods/ai-dlc/roles/architect.md`
- Create: `packs/methods/ai-dlc/roles/builder.md`
- Create: `packs/methods/ai-dlc/roles/operator.md`
- Create: `packs/methods/ai-dlc/roles/quality-reviewer.md`
- Create: `packs/methods/ai-dlc/transitions/01-initiation-ideation.md`
- Create: `packs/methods/ai-dlc/transitions/02-ideation-inception.md`
- Create: `packs/methods/ai-dlc/transitions/03-inception-construction.md`
- Create: `packs/methods/ai-dlc/transitions/04-construction-operation.md`
- Create: `packs/methods/ai-dlc/transitions/05-operation-completed.md`
- Create: `packs/methods/ai-dlc/transitions/06-construction-inception.md`
- Create: `packs/methods/ai-dlc/transitions/07-operation-construction.md`
- Create: `packs/methods/ai-dlc/gates/intent-framed.md`
- Create: `packs/methods/ai-dlc/gates/units-elaborated.md`
- Create: `packs/methods/ai-dlc/gates/design-approved.md`
- Create: `packs/methods/ai-dlc/gates/build-verified.md`
- Create: `packs/methods/ai-dlc/gates/completion.md`
- Test: `tests/test_methods.py` (add one test function)

**Interfaces:**
- Consumes: `agora.filesystem.packs_root`, `agora.methods.load_method_contract` (existing).
- Produces: a Method Pack with `contract.id == "ai-dlc"`, `contract.required_roles == ["product-owner", "architect", "builder", "operator", "quality-reviewer"]`, `contract.work_states == ["initiation", "ideation", "inception", "construction", "operation", "completed"]`, `contract.terminal_state == "completed"`, `contract.criterion_stages == ["elaborated", "designed", "built", "verified", "deployed", "accepted"]`. Gate ids: `intent-framed`, `units-elaborated`, `design-approved`, `build-verified`, `completion`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_methods.py`:

```python
def test_loads_the_ai_dlc_pack_phase_lifecycle() -> None:
    contract = load_method_contract(packs_root() / "methods" / "ai-dlc")

    assert contract.id == "ai-dlc"
    assert contract.required_roles == [
        "product-owner",
        "architect",
        "builder",
        "operator",
        "quality-reviewer",
    ]
    assert contract.work_states == [
        "initiation",
        "ideation",
        "inception",
        "construction",
        "operation",
        "completed",
    ]
    assert contract.terminal_state == "completed"
    assert contract.wip_limits == {}
    assert contract.criterion_stages == [
        "elaborated",
        "designed",
        "built",
        "verified",
        "deployed",
        "accepted",
    ]
    assert contract.criterion_stage_roles["designed"] == ["architect"]
    assert contract.criterion_stage_roles["deployed"] == ["operator"]
    assert contract.criterion_stage_roles["accepted"] == ["product-owner"]

    ideation = next(
        r for r in contract.transitions
        if r.source == "initiation" and r.target == "ideation"
    )
    assert ideation.roles == ["product-owner"]
    assert ideation.gate == "intent-framed"
    assert contract.gates["intent-framed"].required_artifacts == ["intent"]
    assert contract.gates["intent-framed"].require_resolved_clarifications is True

    design = next(
        r for r in contract.transitions
        if r.source == "inception" and r.target == "construction"
    )
    assert design.gate == "design-approved"
    assert contract.gates["design-approved"].required_artifacts == [
        "architecture",
        "domain-model",
    ]
    assert contract.gates["design-approved"].required_approval_roles == [
        "architect",
        "product-owner",
    ]
    assert contract.gates["design-approved"].required_criterion_stage == "designed"

    build = next(
        r for r in contract.transitions
        if r.source == "construction" and r.target == "operation"
    )
    assert build.gate == "build-verified"
    assert contract.gates["build-verified"].require_successful_evidence is True
    assert contract.gates["build-verified"].required_approval_roles == ["quality-reviewer"]

    completion = next(r for r in contract.transitions if r.target == "completed")
    assert completion.roles == ["product-owner"]
    assert completion.gate == "completion"
    assert contract.gates["completion"].required_criterion_stage == "accepted"
    assert contract.gates["completion"].require_successful_evidence is True
    assert contract.gates["completion"].required_approval_roles == ["product-owner"]

    # rework edges (backward, no gate)
    assert any(
        r.source == "construction" and r.target == "inception" and r.gate is None
        for r in contract.transitions
    )
    assert any(
        r.source == "operation" and r.target == "construction" and r.gate is None
        for r in contract.transitions
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_methods.py::test_loads_the_ai_dlc_pack_phase_lifecycle -v`
Expected: FAIL — `load_method_contract` raises because `packs/methods/ai-dlc` does not exist.

- [ ] **Step 3: Create `packs/methods/ai-dlc/METHOD.md`**

```markdown
---
schema: "agora/method/v1"
id: "ai-dlc"
name: "AI-Driven Development Life Cycle"
version: "1.0.0"
dependencies: []
required-roles: ["product-owner", "architect", "builder", "operator", "quality-reviewer"]
work-states: ["initiation", "ideation", "inception", "construction", "operation", "completed"]
criterion-stages: ["elaborated", "designed", "built", "verified", "deployed", "accepted"]
criterion-stage-roles: {"elaborated":["product-owner","architect"],"designed":["architect"],"built":["builder"],"verified":["quality-reviewer","builder"],"deployed":["operator"],"accepted":["product-owner"]}
terminal-state: "completed"
wip-limits: {}
---

# AI-Driven Development Life Cycle Method Pack

This pack renders AWS's AI-Driven Development Life Cycle (AI-DLC) as an Agora
lifecycle. AI-DLC treats the model as a teammate that plans work, asks targeted
questions, and implements decisions, while humans hold every judgement call. Its
five phases — Initiation, Ideation, Inception, Construction, Operation — become
five governed work states plus a terminal delivery state, each phase boundary
protected by an approval gate.

AI-DLC's "33 stages" are activities inside a phase, not lifecycle states. They are
listed as a non-binding checklist in `PROTOCOL.md`; gates evaluate acceptance
criteria, registered artifacts, evidence, and approvals only.

The pack fits a single human paired with a single AI agent — one actor may hold
several roles — as readily as a larger delivery swarm.

## Phase gates

- **intent-framed** (initiation to ideation): an `intent` artifact is registered
  and the latest clarification run leaves no open question.
- **units-elaborated** (ideation to inception): a `units-of-work` artifact is
  registered, every criterion has reached `elaborated`, and the Product Owner has
  approved.
- **design-approved** (inception to construction): `architecture` and
  `domain-model` artifacts are registered, every criterion has reached
  `designed`, and the Architect and Product Owner have approved.
- **build-verified** (construction to operation): every criterion has reached
  `verified`, at least one successful evidence record exists, and the Quality
  Reviewer has approved.
- **completion** (operation to completed): every criterion has reached
  `accepted`, deployment evidence exists, and the Product Owner has approved.

## Rework

A requirements gap found during construction returns the work to `inception`. A
failed verification during operation returns it to `construction`. Rework reuses
an earlier state rather than inventing a new one; the specification does not
change mid-cycle without a new draft.
```

- [ ] **Step 4: Create the five role files**

`packs/methods/ai-dlc/roles/product-owner.md`:

```markdown
---
schema: "agora/role/v1"
id: "product-owner"
required-capabilities: ["specification", "acceptance"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["actor.key.recover", "actor.key.revoke", "actor.key.rotate", "actor.runtime.update", "swarm.assign", "work.create", "work.decompose", "work.cancel", "work.clarify", "work.verify-consistency", "work.gherkin", "delegation.accept", "delegation.reject", "delegation.cancel", "criterion.satisfy", "work.transition", "artifact.add", "evidence.add", "checklist.add", "checklist.check", "usage.add", "budget.amend", "approval.add", "approval.delegate", "approval.delegation.revoke", "gate.waive", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "repository.governance.read", "review.read", "review.write", "review.decide", "issue.read", "issue.write", "issue.transition", "docs.read", "docs.write", "release.read", "security.read", "portfolio.read", "portfolio.write"]
allowed-environments: ["*"]
---

# Product Owner

Frames the business intent, elaborates units of work with the team, and holds
final acceptance. In AI-DLC terms this is the human who "makes the critical
decisions". An AI or swarm may hold the role only when project policy does not
reserve final acceptance for a human.
```

`packs/methods/ai-dlc/roles/architect.md`:

```markdown
---
schema: "agora/role/v1"
id: "architect"
required-capabilities: ["specification"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["swarm.assign", "work.decompose", "work.clarify", "work.verify-consistency", "work.gherkin", "criterion.satisfy", "work.transition", "artifact.add", "evidence.add", "checklist.add", "checklist.check", "approval.add", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "repository.governance.read", "docs.read", "docs.write", "review.read"]
allowed-environments: ["*"]
---

# Architect

Owns the Inception phase: turns framed intent into requirements, units of work, a
domain model, and an architecture proposal. Advances the work into Construction
and pulls it back to Inception when a requirements gap surfaces.
```

`packs/methods/ai-dlc/roles/builder.md`:

```markdown
---
schema: "agora/role/v1"
id: "builder"
required-capabilities: ["implementation"]
allowed-actor-kinds: ["human", "ai-agent", "swarm", "automation"]
allowed-actions: ["work.decompose", "criterion.satisfy", "work.transition", "artifact.add", "evidence.add", "checklist.add", "checklist.check", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "repository.write", "review.read", "ci.read", "ci.run"]
allowed-environments: ["*"]
---

# Builder

Owns the Construction phase: proposes code and tests through mob construction and
records the evidence that each acceptance criterion is built and verified. Merge,
release, and deployment authority are never implied by this role.
```

`packs/methods/ai-dlc/roles/operator.md`:

```markdown
---
schema: "agora/role/v1"
id: "operator"
required-capabilities: ["implementation"]
allowed-actor-kinds: ["human", "ai-agent", "swarm", "automation"]
allowed-actions: ["criterion.satisfy", "work.transition", "artifact.add", "evidence.add", "checklist.add", "checklist.check", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "ci.read", "ci.run", "cloud.read", "release.read"]
allowed-environments: ["*"]
---

# Operator

Owns the Operation phase: manages infrastructure-as-code and deployment, records
deployment evidence, and returns the work to Construction when verification
fails. Write and apply capabilities remain opt-in through project environment
policy.
```

`packs/methods/ai-dlc/roles/quality-reviewer.md`:

```markdown
---
schema: "agora/role/v1"
id: "quality-reviewer"
required-capabilities: ["acceptance"]
allowed-actor-kinds: ["human", "ai-agent", "swarm"]
allowed-actions: ["criterion.satisfy", "work.transition", "artifact.add", "evidence.add", "checklist.add", "checklist.check", "approval.add", "handoff.create"]
allowed-tool-capabilities: ["repository.read", "repository.governance.read", "review.read", "review.write", "review.decide", "security.read"]
allowed-environments: ["*"]
---

# Quality Reviewer

Consolidates AI-DLC's two quality-gate reviewers. Confirms that construction
output meets its acceptance criteria and approves the `build-verified` gate;
sends failed work back to Construction.
```

- [ ] **Step 5: Create the seven transition files**

`transitions/01-initiation-ideation.md`:

```markdown
---
schema: "agora/transition/v1"
from: "initiation"
to: "ideation"
roles: ["product-owner"]
gate: "intent-framed"
---

# Frame the intent

Move into Ideation once the business intent is captured as an `intent` artifact
and the clarification run leaves no open question.
```

`transitions/02-ideation-inception.md`:

```markdown
---
schema: "agora/transition/v1"
from: "ideation"
to: "inception"
roles: ["product-owner"]
gate: "units-elaborated"
---

# Elaborate the units of work

Enter Inception once the team has elaborated the units of work and the Product
Owner has approved.
```

`transitions/03-inception-construction.md`:

```markdown
---
schema: "agora/transition/v1"
from: "inception"
to: "construction"
roles: ["architect"]
gate: "design-approved"
---

# Approve the design

Begin Construction once the architecture and domain model are registered and
approved by the Architect and the Product Owner.
```

`transitions/04-construction-operation.md`:

```markdown
---
schema: "agora/transition/v1"
from: "construction"
to: "operation"
roles: ["quality-reviewer"]
gate: "build-verified"
---

# Verify the build

Move into Operation once every criterion is verified, successful evidence
exists, and the Quality Reviewer has approved.
```

`transitions/05-operation-completed.md`:

```markdown
---
schema: "agora/transition/v1"
from: "operation"
to: "completed"
roles: ["product-owner"]
gate: "completion"
---

# Accept the delivered increment

Complete the work once it is deployed, accepted, and evidenced.
```

`transitions/06-construction-inception.md`:

```markdown
---
schema: "agora/transition/v1"
from: "construction"
to: "inception"
roles: ["architect"]
---

# Return for re-elaboration

Send work back to Inception when Construction uncovers a requirements gap.
```

`transitions/07-operation-construction.md`:

```markdown
---
schema: "agora/transition/v1"
from: "operation"
to: "construction"
roles: ["quality-reviewer"]
---

# Return for rework

Send work back to Construction when Operation verification fails.
```

- [ ] **Step 6: Create the five gate files**

`gates/intent-framed.md`:

```markdown
---
schema: "agora/gate/v1"
id: "intent-framed"
require-all-criteria: false
require-required-artifacts: true
required-artifacts: ["intent"]
require-successful-evidence: false
required-approval-roles: []
require-resolved-clarifications: true
---

# Intent gate

Ideation cannot begin until the business intent is registered as an `intent`
artifact and the latest clarification run covers current inputs with no open
question.
```

`gates/units-elaborated.md`:

```markdown
---
schema: "agora/gate/v1"
id: "units-elaborated"
require-all-criteria: true
required-criterion-stage: "elaborated"
require-required-artifacts: true
required-artifacts: ["units-of-work"]
require-successful-evidence: false
required-approval-roles: ["product-owner"]
require-resolved-clarifications: false
---

# Elaboration gate

Inception cannot begin until every acceptance criterion has reached `elaborated`,
a `units-of-work` artifact is registered, and the Product Owner has approved.
```

`gates/design-approved.md`:

```markdown
---
schema: "agora/gate/v1"
id: "design-approved"
require-all-criteria: true
required-criterion-stage: "designed"
require-required-artifacts: true
required-artifacts: ["architecture", "domain-model"]
require-successful-evidence: false
required-approval-roles: ["architect", "product-owner"]
require-resolved-clarifications: false
---

# Design gate

Construction cannot begin until every criterion has reached `designed`, the
`architecture` and `domain-model` artifacts are registered, and both the
Architect and the Product Owner have approved.
```

`gates/build-verified.md`:

```markdown
---
schema: "agora/gate/v1"
id: "build-verified"
require-all-criteria: true
required-criterion-stage: "verified"
require-required-artifacts: false
require-successful-evidence: true
required-approval-roles: ["quality-reviewer"]
require-resolved-clarifications: false
---

# Build gate

Operation cannot begin until every criterion has reached `verified`, at least one
successful evidence record exists, and the Quality Reviewer has approved.
```

`gates/completion.md`:

```markdown
---
schema: "agora/gate/v1"
id: "completion"
require-all-criteria: true
required-criterion-stage: "accepted"
require-required-artifacts: true
require-successful-evidence: true
required-approval-roles: ["product-owner"]
require-resolved-clarifications: false
---

# Completion gate

The increment is complete only when every criterion has reached `accepted`,
deployment evidence exists, and the Product Owner has approved.
```

- [ ] **Step 7: Create `PROTOCOL.md`**

```markdown
# AI-DLC protocol

## Operating pattern

Every phase repeats the AI-DLC loop: the AI drafts a plan from the current
intent, asks the team targeted questions, the humans decide, and the AI
implements the decision. The Product Owner holds every judgement that changes
scope or acceptance.

## Phases and their stages

The gates below are binding. The bulleted stages are the expected activities
inside each phase — a checklist for the team, never evaluated by a gate.

- **Initiation** — capture the business intent; agree the working scope; record
  constraints and assumptions as the `intent` artifact.
- **Ideation** — mob elaboration: expand intent into requirements, stories, and
  units of work; resolve open questions; register `units-of-work`.
- **Inception** — propose the domain model and architecture; map each unit of
  work to acceptance criteria; register `architecture` and `domain-model`.
- **Construction** — mob construction: propose code and tests per unit of work;
  record evidence that each criterion is built and then verified.
- **Operation** — infrastructure-as-code and deployment; record deployment
  evidence; confirm acceptance in the running environment.

## Vocabulary

- A **bolt** is one pass through a phase, measured in hours or days rather than
  weeks.
- A **unit of work** replaces the epic: the smallest slice of intent that can be
  elaborated, built, and accepted on its own.

## Mob review

"Mob elaboration" and "mob construction" are practices the team runs through
`review` actions and shared sessions. This pack version does not govern
concurrent multi-holder gate approval; each gate records the approvals its
policy names.

## Rework

Failed verification returns work to `construction`; a requirements gap returns it
to `inception`. The specification does not change mid-cycle without a new draft.
```

- [ ] **Step 8: Create `TOOLS.md`**

```markdown
# AI-DLC tool restrictions

- The Builder may use repository and CI tools the project permits.
- The Operator needs an explicit project environment grant before any deploy,
  release, or infrastructure apply. None of these is implied by the Builder role.
- Intent and unit-of-work changes require the Product Owner or the Architect.
- Exceptional workflow paths require an explicit transition and gate, not a flag.
- Merge, release publication, and deployment permissions are never implied by the
  Builder role.
```

- [ ] **Step 9: Run the test to verify it passes**

Run: `uv run pytest tests/test_methods.py::test_loads_the_ai_dlc_pack_phase_lifecycle -v`
Expected: PASS.

- [ ] **Step 10: Validate the contract graph directly**

Run:
```bash
uv run python -c "from agora.filesystem import packs_root; from agora.methods import load_method_contract; c = load_method_contract(packs_root()/'methods'/'ai-dlc'); print('states', c.work_states); print('terminal', c.terminal_state); print('transitions', [(t.source,t.target,t.gate) for t in c.transitions])"
```
Expected: prints the six states, `completed` terminal, seven transitions with the five gated forward edges and two ungated backward edges. No exception.

- [ ] **Step 11: Commit**

```bash
git add packs/methods/ai-dlc tests/test_methods.py
git commit -m "feat(methods): add the ai-dlc Method Pack

Renders AWS AI-DLC's five phases as an Agora lifecycle: phase-boundary
work states, five approval gates, two rework edges, five roles. Markdown
only, no kernel change.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Register with the role-conformance harness

**Files:**
- Modify: `src/agora/self_test.py:23` (`BUNDLED_METHODS`)
- Test: `tests/test_self_test.py` (existing — confirm coverage; add assertion if the file asserts a method count)

**Interfaces:**
- Consumes: `agora.self_test.run_role_self_test` (existing).
- Produces: `run_role_self_test()` result whose `methods` count includes `ai-dlc` and whose `cases` cover `ai-dlc` for `human`, `ai-agent`, `swarm`.

- [ ] **Step 1: Write the failing test**

Check `tests/test_self_test.py` first: `grep -n "BUNDLED\|methods\|spec-driven\|ai-dlc" tests/test_self_test.py`. Add this test (adjust import to match the file's existing style):

```python
def test_role_self_test_covers_the_ai_dlc_pack() -> None:
    from agora.self_test import run_role_self_test

    report = run_role_self_test()
    ai_dlc_cases = [case for case in report["cases"] if case["method"] == "ai-dlc"]
    assert {case["actor_kind"] for case in ai_dlc_cases} == {"human", "ai-agent", "swarm"}
    for case in ai_dlc_cases:
        assert case["terminal_state"] == "completed"
        assert case["disallowed_assignments_rejected"] == len(case["roles"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_self_test.py::test_role_self_test_covers_the_ai_dlc_pack -v`
Expected: FAIL — no `ai-dlc` cases in the report.

- [ ] **Step 3: Add `ai-dlc` to `BUNDLED_METHODS`**

In `src/agora/self_test.py`, line 23:

```python
BUNDLED_METHODS = ("spec-driven", "scrum", "kanban", "ai-dlc")
```

- [ ] **Step 4: Run the harness test**

Run: `uv run pytest tests/test_self_test.py::test_role_self_test_covers_the_ai_dlc_pack -v`
Expected: PASS.

If it fails inside `_run_case` for `ai-dlc`, read the assertion. Likely causes and fixes:
- *"cannot reach `<stage>` before: ..."* — `_run_case` calls `satisfy_criterion(work_actor, "verified")` with no stage, which satisfies every stage in order; this should be fine. If a stage-role rejects the single candidate actor, confirm every entry in `criterion-stage-roles` names a role in `required-roles` (it does per Task 1).
- *gate missing approval* — `_run_case` adds approvals for every role in every gate's `required-approval-roles`; confirm those roles are in `required-roles`.
- *unreachable state* — run Step 10 of Task 1 again.

- [ ] **Step 5: Run the full self-test entrypoint**

Run: `uv run agora self-test`
Expected: exit 0; JSON reports `"methods": 4` and `scope: bundled-role-conformance`.

- [ ] **Step 6: Commit**

```bash
git add src/agora/self_test.py tests/test_self_test.py
git commit -m "test(self-test): cover the ai-dlc pack in role conformance

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Lifecycle test — full walk plus both rework edges

**Files:**
- Create: `tests/test_ai_dlc_lifecycle.py`

**Interfaces:**
- Consumes: `agora.workspace.AgoraWorkspace`; `agora.model` inputs `ConfigureInput`, `InitInput`, `AddActorInput`, `CreateSwarmInput`, `AssignActorInput`, `CreateWorkInput`, `WorkActorInput`, `AddArtifactInput`, `AddEvidenceInput`, `AddApprovalInput`, `TransitionWorkInput` (all already used by `tests/test_spec_driven_lifecycle.py` — copy its import list and helper shape).
- Produces: nothing consumed downstream; this is a leaf test.

- [ ] **Step 1: Write the test file**

Model the fixture on `tests/test_spec_driven_lifecycle.py` (`_workspace`, `_form_swarm`, `_clarify`). Key differences: `default_method="ai-dlc"`, five distinct actors, and per-stage `satisfy_criterion` calls made by the role allowed for that stage.

```python
import json
import subprocess
from pathlib import Path

import pytest

from agora.model import (
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddEvidenceInput,
    AssignActorInput,
    ConfigureInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    TransitionWorkInput,
    WorkActorInput,
)
from agora.workspace import AgoraWorkspace


def _workspace(tmp_path: Path, monkeypatch) -> AgoraWorkspace:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    spec = tmp_path / "docs" / "intent.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# Intent\n", encoding="utf-8")

    def run(command, cwd, environment):
        return subprocess.CompletedProcess(command, 0, json.dumps({"questions": []}), "")

    workspace = AgoraWorkspace(cwd=tmp_path, tool_runner=run)
    workspace.configure(
        ConfigureInput(
            integration="generic",
            provider="configured-by-integration",
            model="configured-by-integration",
            default_method="ai-dlc",
        )
    )
    workspace.initialize(InitInput())
    return workspace


_ROLES = {
    "product-owner": ("po", "human", ["specification", "acceptance"]),
    "architect": ("arch", "ai-agent", ["specification"]),
    "builder": ("build", "ai-agent", ["implementation"]),
    "operator": ("ops", "ai-agent", ["implementation"]),
    "quality-reviewer": ("qa", "human", ["acceptance"]),
}


def _form_swarm(workspace: AgoraWorkspace) -> None:
    for role_id, (actor_id, kind, caps) in _ROLES.items():
        workspace.add_actor(
            AddActorInput(id=actor_id, name=actor_id, kind=kind, capabilities=caps, scope="project")
        )
    workspace.create_swarm(CreateSwarmInput(id="delivery", objective="Deliver via AI-DLC"))
    for role_id, (actor_id, _kind, _caps) in _ROLES.items():
        workspace.assign_actor(
            AssignActorInput(swarm_id="delivery", role_id=role_id, actor_id=actor_id)
        )


def _work_actor(actor_id: str) -> WorkActorInput:
    return WorkActorInput(swarm_id="delivery", work_id="feature", actor_id=actor_id)


def _artifact(workspace, actor_id, kind):
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="feature",
            actor_id=actor_id,
            kind=kind,
            uri=f"repo://docs/{kind}.md",
        )
    )


def _transition(workspace, actor_id, target):
    return workspace.transition_work(
        TransitionWorkInput(
            swarm_id="delivery", work_id="feature", actor_id=actor_id, target_state=target
        )
    )


def _seed_work(workspace: AgoraWorkspace) -> None:
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="feature",
            title="Ship a feature via AI-DLC",
            actor_id="po",
            description="Exercise every phase gate.",
            acceptance_criteria=[("value", "The feature delivers its stated value")],
            required_artifacts=["intent"],
        )
    )


def _drive_to_operation(workspace: AgoraWorkspace) -> None:
    # initiation -> ideation
    _artifact(workspace, "po", "intent")
    workspace.clarify_work(_work_actor("po"), runner="/bin/true")
    _transition(workspace, "po", "ideation")

    # ideation -> inception
    workspace.satisfy_criterion(_work_actor("po"), "value", stage="elaborated")
    _artifact(workspace, "po", "units-of-work")
    workspace.add_approval(
        AddApprovalInput(
            swarm_id="delivery", work_id="feature", actor_id="po",
            role_id="product-owner", note="units elaborated",
        )
    )
    _transition(workspace, "po", "inception")

    # inception -> construction
    workspace.satisfy_criterion(_work_actor("arch"), "value", stage="designed")
    _artifact(workspace, "arch", "architecture")
    _artifact(workspace, "arch", "domain-model")
    for actor_id, role_id in (("arch", "architect"), ("po", "product-owner")):
        workspace.add_approval(
            AddApprovalInput(
                swarm_id="delivery", work_id="feature", actor_id=actor_id,
                role_id=role_id, note="design approved",
            )
        )
    _transition(workspace, "arch", "construction")

    # construction -> operation
    workspace.satisfy_criterion(_work_actor("build"), "value", stage="built")
    workspace.satisfy_criterion(_work_actor("qa"), "value", stage="verified")
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery", work_id="feature", actor_id="build",
            type="test-suite", result="success", artifact_refs=["repo://docs/intent.md"],
        )
    )
    workspace.add_approval(
        AddApprovalInput(
            swarm_id="delivery", work_id="feature", actor_id="qa",
            role_id="quality-reviewer", note="build verified",
        )
    )
    _transition(workspace, "qa", "operation")


def test_ai_dlc_happy_path_reaches_completed(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    _form_swarm(workspace)
    _seed_work(workspace)
    _drive_to_operation(workspace)

    workspace.satisfy_criterion(_work_actor("ops"), "value", stage="deployed")
    workspace.satisfy_criterion(_work_actor("po"), "value", stage="accepted")
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery", work_id="feature", actor_id="ops",
            type="deployment", result="success", artifact_refs=["repo://docs/intent.md"],
        )
    )
    workspace.add_approval(
        AddApprovalInput(
            swarm_id="delivery", work_id="feature", actor_id="po",
            role_id="product-owner", note="accepted",
        )
    )
    completed = _transition(workspace, "po", "completed")
    assert completed.state == "completed"


def test_ai_dlc_rework_operation_back_to_construction(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    _form_swarm(workspace)
    _seed_work(workspace)
    _drive_to_operation(workspace)

    reworked = _transition(workspace, "qa", "construction")
    assert reworked.state == "construction"
    # forward again with no new gate obligations outstanding
    forward = _transition(workspace, "qa", "operation")
    assert forward.state == "operation"


def test_ai_dlc_rework_construction_back_to_inception(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    _form_swarm(workspace)
    _seed_work(workspace)
    # drive only to construction
    _artifact(workspace, "po", "intent")
    workspace.clarify_work(_work_actor("po"), runner="/bin/true")
    _transition(workspace, "po", "ideation")
    workspace.satisfy_criterion(_work_actor("po"), "value", stage="elaborated")
    _artifact(workspace, "po", "units-of-work")
    workspace.add_approval(
        AddApprovalInput(
            swarm_id="delivery", work_id="feature", actor_id="po",
            role_id="product-owner", note="units",
        )
    )
    _transition(workspace, "po", "inception")
    workspace.satisfy_criterion(_work_actor("arch"), "value", stage="designed")
    _artifact(workspace, "arch", "architecture")
    _artifact(workspace, "arch", "domain-model")
    for actor_id, role_id in (("arch", "architect"), ("po", "product-owner")):
        workspace.add_approval(
            AddApprovalInput(
                swarm_id="delivery", work_id="feature", actor_id=actor_id,
                role_id=role_id, note="design",
            )
        )
    _transition(workspace, "arch", "construction")

    reworked = _transition(workspace, "arch", "inception")
    assert reworked.state == "inception"


def test_ai_dlc_build_gate_blocks_without_verified_evidence(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    _form_swarm(workspace)
    _seed_work(workspace)
    _drive_to_operation.__wrapped__ if False else None  # noqa: B018
    # reach construction, then attempt the build gate with nothing recorded
    _artifact(workspace, "po", "intent")
    workspace.clarify_work(_work_actor("po"), runner="/bin/true")
    _transition(workspace, "po", "ideation")
    workspace.satisfy_criterion(_work_actor("po"), "value", stage="elaborated")
    _artifact(workspace, "po", "units-of-work")
    workspace.add_approval(
        AddApprovalInput(
            swarm_id="delivery", work_id="feature", actor_id="po",
            role_id="product-owner", note="u",
        )
    )
    _transition(workspace, "po", "inception")
    workspace.satisfy_criterion(_work_actor("arch"), "value", stage="designed")
    _artifact(workspace, "arch", "architecture")
    _artifact(workspace, "arch", "domain-model")
    for actor_id, role_id in (("arch", "architect"), ("po", "product-owner")):
        workspace.add_approval(
            AddApprovalInput(
                swarm_id="delivery", work_id="feature", actor_id=actor_id,
                role_id=role_id, note="d",
            )
        )
    _transition(workspace, "arch", "construction")

    with pytest.raises(ValueError):
        _transition(workspace, "qa", "operation")
```

Note: delete the stray `_drive_to_operation.__wrapped__ ...` line — it is a copy-paste guard reminder; the fourth test intentionally inlines the path to construction. Keep the four tests; the fourth proves `ac-gates-enforced`.

- [ ] **Step 2: Run the tests to verify the happy path first fails, then passes**

Run: `uv run pytest tests/test_ai_dlc_lifecycle.py -v`
Expected before Task 1 is merged: collection/first-call failure. After Task 1: all four pass. If a `satisfy_criterion` stage call raises "role not allowed", check the actor's assigned role matches `criterion-stage-roles` for that stage in `METHOD.md`.

- [ ] **Step 3: Adjust and re-run until green**

Common fixes:
- Evidence `type` must be a slug — `test-suite`, `deployment` are fine.
- If `clarify_work` needs the spec input registered first, register the `intent` artifact before calling it (already ordered that way).
- If the happy path's `completed` transition reports a missing approval, confirm `completion.md` lists only `product-owner`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_ai_dlc_lifecycle.py
git commit -m "test(ai-dlc): drive the full lifecycle and both rework edges

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Executable sample

**Files:**
- Create: `samples/ai-dlc/run.py`
- Create: `samples/ai-dlc/README.md`

**Interfaces:**
- Consumes: `agora.workspace.AgoraWorkspace`; `agora.model` `ConfigureInput`, `InitInput`, `AddActorInput`, `CreateSwarmInput`, `AssignActorInput`, `CreateWorkInput`, `WorkActorInput`, `AddArtifactInput`, `AddEvidenceInput`, `AddApprovalInput`, `TransitionWorkInput`.
- Produces: a `samples/ai-dlc/run.py` with a `main()` and `if __name__ == "__main__": main()`, discovered by `scripts/verify_all.py` via `samples/*/run.py`.

- [ ] **Step 1: Write `samples/ai-dlc/run.py`**

The pack is bundled, so no `install_method` — `InitInput` with `default_method="ai-dlc"`. Walk `initiation -> ... -> operation`, take the `operation -> construction` rework edge once, then forward to `completed`. Print each phase. Mirror the structure of `samples/custom-lifecycle/run.py` for the setup boilerplate and `tests/test_ai_dlc_lifecycle.py` for the lifecycle calls.

```python
import os
import tempfile
from pathlib import Path

from agora.model import (
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddEvidenceInput,
    AssignActorInput,
    ConfigureInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    TransitionWorkInput,
    WorkActorInput,
)
from agora.workspace import AgoraWorkspace

ROLES = {
    "product-owner": ("po", "human", ["specification", "acceptance"]),
    "architect": ("arch", "ai-agent", ["specification"]),
    "builder": ("build", "ai-agent", ["implementation"]),
    "operator": ("ops", "ai-agent", ["implementation"]),
    "quality-reviewer": ("qa", "human", ["acceptance"]),
}


def main() -> None:
    project = Path(tempfile.mkdtemp(prefix="agora-ai-dlc-project-"))
    os.environ["AGORA_HOME"] = tempfile.mkdtemp(prefix="agora-ai-dlc-home-")
    agora = AgoraWorkspace(cwd=project)
    agora.configure(
        ConfigureInput(
            integration="generic",
            provider="any-provider",
            model="any-model",
            default_method="ai-dlc",
        )
    )
    agora.initialize(InitInput())

    for role_id, (actor_id, kind, caps) in ROLES.items():
        agora.add_actor(
            AddActorInput(id=actor_id, name=actor_id, kind=kind, capabilities=caps, scope="project")
        )
    agora.create_swarm(CreateSwarmInput(id="delivery", objective="Deliver via AI-DLC", create_branch=False))
    for role_id, (actor_id, _k, _c) in ROLES.items():
        agora.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role_id, actor_id=actor_id))

    wa = lambda actor: WorkActorInput(swarm_id="delivery", work_id="feature", actor_id=actor)
    artifact = lambda actor, kind: agora.add_artifact(
        AddArtifactInput(swarm_id="delivery", work_id="feature", actor_id=actor, kind=kind, uri=f"repo://{kind}.md")
    )
    approve = lambda actor, role: agora.add_approval(
        AddApprovalInput(swarm_id="delivery", work_id="feature", actor_id=actor, role_id=role, note="ok")
    )
    move = lambda actor, target: agora.transition_work(
        TransitionWorkInput(swarm_id="delivery", work_id="feature", actor_id=actor, target_state=target)
    )

    agora.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="feature",
            title="Ship a feature via AI-DLC",
            actor_id="po",
            acceptance_criteria=[("value", "The feature delivers its value")],
            required_artifacts=["intent"],
        )
    )

    artifact("po", "intent")
    agora.clarify_work(wa("po"), runner="/bin/true")
    print("initiation -> ideation:", move("po", "ideation").state)

    agora.satisfy_criterion(wa("po"), "value", stage="elaborated")
    artifact("po", "units-of-work")
    approve("po", "product-owner")
    print("ideation -> inception:", move("po", "inception").state)

    agora.satisfy_criterion(wa("arch"), "value", stage="designed")
    artifact("arch", "architecture")
    artifact("arch", "domain-model")
    approve("arch", "architect")
    approve("po", "product-owner")
    print("inception -> construction:", move("arch", "construction").state)

    agora.satisfy_criterion(wa("build"), "value", stage="built")
    agora.satisfy_criterion(wa("qa"), "value", stage="verified")
    agora.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery", work_id="feature", actor_id="build",
            type="test-suite", result="success", artifact_refs=["repo://intent.md"],
        )
    )
    approve("qa", "quality-reviewer")
    print("construction -> operation:", move("qa", "operation").state)

    print("operation -> construction (rework):", move("qa", "construction").state)
    print("construction -> operation (forward again):", move("qa", "operation").state)

    agora.satisfy_criterion(wa("ops"), "value", stage="deployed")
    agora.satisfy_criterion(wa("po"), "value", stage="accepted")
    agora.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery", work_id="feature", actor_id="ops",
            type="deployment", result="success", artifact_refs=["repo://intent.md"],
        )
    )
    approve("po", "product-owner")
    final = move("po", "completed")
    print("operation -> completed:", final.state)
    assert final.state == "completed"


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the sample**

Run: `uv run python samples/ai-dlc/run.py`
Expected: prints each transition ending `operation -> completed: completed`; exit 0.

- [ ] **Step 3: Write `samples/ai-dlc/README.md`**

```markdown
# AI-DLC lifecycle sample

`ai-dlc` is a bundled Method Pack that renders AWS's AI-Driven Development Life
Cycle as an Agora lifecycle: five phase-boundary states, five approval gates, and
two rework edges.

Run the sample from the repository root:

```bash
uv run python samples/ai-dlc/run.py
```

The script initializes an isolated project with `ai-dlc` as the default method,
forms a five-role delivery swarm, and walks one work item from `initiation` to
`completed`, including one `operation -> construction` rework loop. Every gate is
satisfied with real artifacts, evidence, and approvals.

See the [AI-DLC guide](../../docs/guides/ai-dlc.md) and the
[Method Pack reference](../../docs/reference/method-packs.md).
```

- [ ] **Step 4: Run via the verifier's sample discovery**

Run: `uv run python scripts/verify_all.py --skip-samples` is NOT what we want here; instead run just the sample discovery path:
```bash
uv run python -c "from pathlib import Path; print(sorted(str(p) for p in Path('samples').glob('*/run.py')))"
```
Expected: the list includes `samples/ai-dlc/run.py`.

- [ ] **Step 5: Commit**

```bash
git add samples/ai-dlc
git commit -m "docs(samples): executable ai-dlc lifecycle walkthrough

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Documentation

**Files:**
- Modify: `docs/reference/method-packs.md` (intro paragraph naming the bundled packs)
- Create: `docs/guides/ai-dlc.md`
- Modify: `README.md` ("Choose a workflow" table)
- Modify: `docs/README.md` if it has a guide index listing (check with `grep -n "guides/" docs/README.md`)

**Interfaces:** none (documentation only).

- [ ] **Step 1: Update `docs/reference/method-packs.md`**

Find the opening sentence: `... `spec-driven`, `scrum`, and `kanban` are bundled examples ...`. Change to:

```markdown
A Method Pack is a versioned Markdown contract for a work lifecycle. The Agora core does not reserve
method identifiers: `spec-driven`, `scrum`, `kanban`, and `ai-dlc` are bundled examples, while user and
project scopes may install any valid pack.
```

- [ ] **Step 2: Write `docs/guides/ai-dlc.md`**

```markdown
# AI-DLC method

The `ai-dlc` Method Pack renders AWS's
[AI-Driven Development Life Cycle](https://aws.amazon.com/blogs/devops/ai-driven-development-life-cycle/)
as an Agora lifecycle. It is a bundled example, selectable like `spec-driven`,
`scrum`, or `kanban`:

```bash
agora configure --default-method ai-dlc
# or per swarm
agora quickstart --method ai-dlc --objective "Ship the first increment"
```

## Phase-to-state mapping

AI-DLC defines five phases and, in the `awslabs/aidlc-workflows` implementation,
33 stages with "an approval gate at every stage". Agora models the **phase
boundaries** as work states and gates; the 33 stages are documented as a
non-binding per-phase checklist in the pack's `PROTOCOL.md`, because Agora gates
evaluate acceptance criteria, artifacts, evidence, and approvals — not stage
completion.

| AI-DLC phase | `ai-dlc` work state | Boundary gate | Gate obligations |
| --- | --- | --- | --- |
| Initialization | `initiation` | — | entry state |
| Ideation | `ideation` | `intent-framed` | `intent` artifact; clarifications resolved |
| Inception | `inception` | `units-elaborated` | `units-of-work`; all criteria `elaborated`; Product Owner approval |
| Construction | `construction` | `design-approved` | `architecture` + `domain-model`; all criteria `designed`; Architect + Product Owner approval |
| Operation | `operation` | `build-verified` | all criteria `verified`; successful evidence; Quality Reviewer approval |
| Delivery | `completed` | `completion` | all criteria `accepted`; deployment evidence; Product Owner approval |

Rework edges: `construction -> inception` (requirements gap) and
`operation -> construction` (failed verification).

## Roles

AI-DLC's 14-agent roster collapses to five Agora roles — authority buckets, not
personas. One human or one AI may hold several.

| Role | Owns | AI-DLC counterpart |
| --- | --- | --- |
| `product-owner` | Intent, unit-of-work elaboration, final acceptance | the human who "makes the critical decisions" |
| `architect` | Requirements, domain model, architecture (Inception) | analysis and architecture experts |
| `builder` | Code and tests (Construction) | development experts |
| `operator` | Infrastructure-as-code and deployment (Operation) | operations experts |
| `quality-reviewer` | Gate review of construction output | the two quality-gate reviewers |

## Differences from `awslabs/aidlc-workflows`

Agora governs *who may do what and the durable record of what they did*. It is a
kernel; `ai-dlc` is one pack on it. The AWS implementation additionally ships
features this pack version does not model:

- **Learning loop** — human corrections becoming durable, reinjected rules.
- **Adaptive composer** — proposing a tailored gate/stage subset from a task
  description or repo scan.
- **Scope and depth dials** — `minimal | standard | comprehensive` ceremony per
  workflow.
- **Concurrent "mob" gate review** — several role holders validating one
  checkpoint at once. Here, mob elaboration and mob construction are practices
  run through `review` actions; each gate records the approvals its policy names.

Conversely, Agora adds signed actor identity, recursively composed swarms,
governed external tool invocation, and issue-tracker reconciliation, none of
which AI-DLC provides.

## Verify

```bash
uv run python samples/ai-dlc/run.py
uv run agora self-test
```
```

- [ ] **Step 3: Update the README "Choose a workflow" table**

In `README.md`, add a row after `kanban`:

```markdown
| `ai-dlc` | Teams adopting AWS's AI-Driven Development Life Cycle | Phase gates for initiation, ideation, inception, construction, and operation, with rework edges |
```

Also add, in the same section's prose or the table intro, a link: `See the [AI-DLC guide](docs/guides/ai-dlc.md).`

- [ ] **Step 4: Update `docs/README.md` guide index if present**

Run `grep -n "operational-loop\|llm-environments\|guides/" docs/README.md`. If there is an alphabetical or grouped guide list, add `- [AI-DLC method](guides/ai-dlc.md)` in the matching spot.

- [ ] **Step 5: Run the docs checks**

Run: `uv run python scripts/verify_all.py --skip-samples` — or the doc-link check directly if the script exposes it (`grep -n "link\|def.*doc" scripts/verify_all.py`).
Expected: link validation and packaging checks pass; no broken relative links from the new guide.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/reference/method-packs.md docs/guides/ai-dlc.md docs/README.md
git commit -m "docs(ai-dlc): guide, workflow table row, method-pack reference

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Full verification and governance close-out

**Files:**
- Modify: any file surfaced by `scripts/verify_all.py` failures (format/lint only — no behavior changes here).

- [ ] **Step 1: Format and lint**

Run: `uv run python scripts/verify_all.py` (full).
If it stops at formatting/lint, run the formatter it names (`uv run ruff format .` / `uv run ruff check --fix .`), review the diff, re-run.

- [ ] **Step 2: Full suite green**

Expected: `verify_all.py` passes end to end — format, lint, unit + failure-path tests, doc link + packaging checks, role harness over **four** packs, sample discovery + execution (including `samples/ai-dlc/run.py`), distribution build.

- [ ] **Step 3: Commit any formatting fallout**

```bash
git add -A
git commit -m "style: formatter fallout for ai-dlc pack

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Record evidence on the governed work item**

```bash
uv run agora evidence add --swarm ai-dlc-method-pack --work ai-dlc-pack \
  --by project:agent --type verify-all --result success \
  --artifact "repo://scripts/verify_all.py"
```
(Adjust flags to `agora evidence add --help`.)

- [ ] **Step 5: Mark implementation criteria and advance the governed lifecycle**

The `ai-dlc-pack` work item is governed by **spec-driven**. Register the plan artifact, mark criteria `planned` then `implemented`/`verified`, and walk `clarified -> planned -> implementing -> verifying -> completed` per `agora work readiness` output. Each transition is its own reviewed step:

```bash
uv run agora artifact add --swarm ai-dlc-method-pack --work ai-dlc-pack \
  --kind implementation-plan --by project:owner \
  --uri docs/superpowers/plans/2026-09-01-ai-dlc-method-pack.md
uv run agora work readiness --swarm ai-dlc-method-pack --work ai-dlc-pack
# then criterion-satisfy per stage + work transition, following readiness
```

- [ ] **Step 6: Open the PR**

```bash
git push -u origin agora/ai-dlc-method-pack
gh pr create --title "feat(methods): ai-dlc Method Pack" --body "$(cat <<'EOF'
Renders AWS's AI-Driven Development Life Cycle as a bundled Agora Method Pack —
Markdown only, no kernel changes.

- `packs/methods/ai-dlc/`: five phase-boundary states, five approval gates, two
  rework edges, five roles.
- Role-conformance harness coverage (`BUNDLED_METHODS`).
- `tests/test_ai_dlc_lifecycle.py`: full walk + both rework edges + a gate-block case.
- `samples/ai-dlc/run.py`: executable walkthrough (verifier-discovered).
- `docs/guides/ai-dlc.md`: phase-to-state mapping, role mapping, differences from
  `awslabs/aidlc-workflows` (learning loop, composer, scope/depth dials, concurrent
  mob review remain future work).

Spec: `docs/superpowers/specs/2026-09-01-ai-dlc-method-pack-design.md`
Plan: `docs/superpowers/plans/2026-09-01-ai-dlc-method-pack.md`

The `.agora/` governance trail for this work ships in the branch; the reviewer
decides whether to keep tracking it or restore the ignore rule on merge.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- `ac-pack-valid` → Task 1 (Steps 9–10) + Task 6 Step 2 (`verify_all` Markdown-contract validation).
- `ac-roles-conform` → Task 2.
- `ac-lifecycle-test` → Task 3 (happy path + tests for edges 06 and 07).
- `ac-sample-runs` → Task 4.
- `ac-gates-enforced` → Task 3 Step 1, fourth test (`test_ai_dlc_build_gate_blocks_without_verified_evidence`).
- `ac-docs` → Task 5.
- `ac-verify-all` → Task 6.
- Non-goals (learning loop, composer, dials, mob review) → documented in `PROTOCOL.md` (Task 1 Step 7) and `docs/guides/ai-dlc.md` (Task 5 Step 2). Not implemented, by design.

**Placeholder scan:** the `_drive_to_operation.__wrapped__` line in Task 3 Step 1 is explicitly called out for deletion with the reason (copy-paste guard). No other TODO/TBD. All code blocks are complete.

**Type consistency:** actor ids (`po`, `arch`, `build`, `ops`, `qa`), role ids (`product-owner`, `architect`, `builder`, `operator`, `quality-reviewer`), work id (`feature`), criterion id (`value`), and stage names (`elaborated`, `designed`, `built`, `verified`, `deployed`, `accepted`) are used identically across Tasks 3 and 4. Gate ids and artifact kinds (`intent`, `units-of-work`, `architecture`, `domain-model`) match between Task 1 `METHOD.md`/gates and the Task 1 test assertions.

**Risk carried from spec:** if the kernel rejects two entries in `design-approved`'s `required-approval-roles`, fall back to `["product-owner"]` and note the limitation in `docs/guides/ai-dlc.md`. Task 1 Step 9 surfaces this immediately.

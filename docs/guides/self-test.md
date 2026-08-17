# Role conformance test harness

Agora includes a zero-configuration test harness for checking an installed distribution before a
person or team adopts it:

```bash
agora self-test
```

The command needs no initialized project, provider account, LLM, key, repository, or network
connection. It creates isolated temporary workspaces, exercises the bundled lifecycle contracts,
prints a human terminal report or captured JSON, and removes the workspaces when complete.

## Fastest confidence check

Run the harness immediately after installation, before choosing a provider or creating a project:

```mermaid
flowchart LR
    A[Install Agora] --> B[Run agora self-test]
    B --> C{Exit status}
    C -->|0| D[Installation conforms]
    C -->|non-zero| E[Stop and diagnose]
    D --> F[Quickstart a real project]
    F --> G[Run agora validate]
```

For an isolated command-line installation:

```bash
pipx install agora-framework
agora self-test
```

For development from a checkout:

```bash
uv sync --extra dev
uv run agora self-test
```

Success returns exit status `0` and a report whose top-level `ok` value is `true`. Any exception or
contract violation makes the command fail, so it can be used directly as a CI step.

## Coverage at a glance

The harness evaluates the Cartesian product of all bundled Method Packs and all role-holder forms
supported by the conformance suite:

```mermaid
flowchart TB
    subgraph Methods[Bundled Method Packs]
        SD[Spec-Driven]
        SC[Scrum]
        KB[Kanban]
    end

    subgraph Forms[Role-holder forms]
        H[Human]
        AI[AI agent]
        SW[Swarm]
    end

    SD --> MX[3 methods x 3 forms]
    SC --> MX
    KB --> MX
    H --> MX
    AI --> MX
    SW --> MX
    MX --> N[9 complete lifecycle cases]
    N --> V[24 valid role assignments]
    N --> R[24 forbidden assignments rejected]
```

The role counts are derived from the installed Method Pack manifests, not duplicated in a test-only
role catalog:

| Method Pack | Required roles | Cases | Valid assignments | Forbidden assignments rejected |
| --- | --- | ---: | ---: | ---: |
| Spec-Driven | `spec-owner`, `developer` | 3 | 6 | 6 |
| Scrum | `product-owner`, `scrum-master`, `developer` | 3 | 9 | 9 |
| Kanban | `service-request-manager`, `flow-manager`, `delivery` | 3 | 9 | 9 |
| **Total** | **8 role definitions per actor-form pass** | **9** | **24** | **24** |

Each actor receives the union of `required-capabilities` declared by the roles in the active Method
Pack. This proves that actor-kind policy is enforced independently of capability compatibility.

## What one case does

Every method and actor-form pair follows the same deterministic sequence:

```mermaid
sequenceDiagram
    participant H as Test harness
    participant FS as Temporary filesystem
    participant A as Agora workspace
    participant M as Method Pack

    H->>FS: Create isolated project and AGORA_HOME
    H->>A: Initialize with generic integration
    A->>M: Load roles, capabilities, states, transitions, and gates
    H->>A: Register capability-compatible service actor
    loop Every required role
        H->>A: Try assigning service actor
        A-->>H: Reject actor kind
        H->>A: Assign human, AI agent, or swarm candidate
    end
    H->>A: Create governed work
    H->>A: Satisfy acceptance criterion
    H->>FS: Materialize a real local spec artifact
    H->>A: Register required repo artifact
    H->>A: Record successful evidence
    H->>A: Add every approval required by gates
    loop Until terminal state
        H->>M: Select a declared forward transition
        H->>A: Apply transition through workspace rules
    end
    H->>A: Validate the complete terminal workspace
    A-->>H: Valid
    H->>FS: Remove temporary state
```

This is not a mocked parser test. The harness calls the same `AgoraWorkspace` operations used by the
CLI for actor registration, swarm formation, work mutation, gate evaluation, and validation.

## How actor forms are exercised

The role contract stays constant while only the role holder changes:

```mermaid
flowchart TD
    R[Required Method Pack role]
    R --> K{Candidate kind}
    K -->|human| H[Project human actor]
    K -->|ai-agent| A[Project AI actor]
    K -->|swarm| S[Ready child swarm represented as an actor]
    K -->|service| X[Expected rejection]
    H --> C[Same capabilities and lifecycle gates]
    A --> C
    S --> C
    X --> P[Actor-kind policy confirmed]
```

For the `swarm` form, the harness first creates a child swarm, assigns a helper human to every child
role, and verifies that the child is ready. It then registers an actor representing that child swarm
and assigns the representative to the parent delivery roles. Recursive readiness is therefore part
of the exercised path.

The `service` candidate deliberately has every required capability. Its rejection demonstrates that
capabilities alone cannot bypass the `allowed-actor-kinds` declared by a role.

## Lifecycle paths

Each case follows only declared transitions that move forward in the Method Pack state order. Rework
edges are valid production behavior, but the deterministic installation check takes the successful
path:

```mermaid
flowchart LR
    subgraph SpecDriven[Spec-Driven]
        SD1[drafting] --> SD2[clarified] --> SD3[planned] --> SD4[implementing] --> SD5[verifying] --> SD6[completed]
    end

    subgraph Scrum[Scrum]
        SC1[specified] --> SC2[planned] --> SC3[implementing] --> SC4[reviewing] --> SC5[verifying] --> SC6[completed]
    end

    subgraph Kanban[Kanban]
        K1[requested] --> K2[ready] --> K3[in-progress] --> K4[review] --> K5[done]
    end
```

Before these transitions, every case creates the minimum complete body of governed work:

```mermaid
flowchart LR
    W[Work item] --> C[Acceptance criterion satisfied]
    C --> A[Required spec artifact registered]
    A --> E[Successful evidence recorded]
    E --> P[Required approvals recorded]
    P --> T[Terminal gate may pass]
```

## Isolation and persistence

The harness tests filesystem persistence without modifying the user's real Agora home or current
project:

```mermaid
flowchart TD
    C[Current directory] -. read no project state .-> H[agora self-test]
    UH[User AGORA_HOME] -. saved and restored .-> H
    H --> TH[Temporary AGORA_HOME]
    H --> P1[Temporary spec-driven projects]
    H --> P2[Temporary Scrum projects]
    H --> P3[Temporary Kanban projects]
    TH --> D{Command finishes}
    P1 --> D
    P2 --> D
    P3 --> D
    D -->|success or failure| X[Temporary directory cleanup]
    X --> R[Original AGORA_HOME restored]
```

The temporary records are real Markdown protocol state while the test runs. They are intentionally
not retained because this command answers whether the installed framework conforms; it does not
create audit evidence for a real project.

## Reading the report

A successful report has this shape:

```json
{
  "ok": true,
  "scope": "bundled-role-conformance",
  "methods": 3,
  "actor_kinds": ["human", "ai-agent", "swarm"],
  "cases": [
    {
      "method": "scrum",
      "actor_kind": "ai-agent",
      "roles": ["product-owner", "scrum-master", "developer"],
      "terminal_state": "completed",
      "disallowed_assignments_rejected": 3
    }
  ],
  "role_assignments_verified": 24,
  "disallowed_assignments_rejected": 24
}
```

The real `cases` array contains all nine cases. Read the fields as follows:

| Field | Meaning |
| --- | --- |
| `ok` | Every case reached a valid terminal workspace |
| `scope` | The fixed assurance scope of this command |
| `methods` | Number of bundled Method Packs exercised |
| `actor_kinds` | Role-holder forms used in every Method Pack |
| `cases` | Per-method and per-form result, roles, terminal state, and rejection count |
| `role_assignments_verified` | Total permitted assignments exercised |
| `disallowed_assignments_rejected` | Total capability-compatible service assignments blocked |

For scripts and CI, trust the process exit status first and archive the JSON as diagnostic output.
The report is an observation of the run, not a durable authorization artifact.

## Where it fits in adoption

The self-test is the first layer in a progressive assurance model. Later layers add project state and
real runtimes only when the team needs them:

```mermaid
flowchart TB
    L1[Layer 1: agora self-test<br/>Installed distribution and bundled roles]
    L2[Layer 2: agora validate<br/>One team's materialized project]
    L3[Layer 3: agora run --until-blocked<br/>Configured non-human runtime]
    L4[Layer 4: Human review and acceptance<br/>Judgment, usefulness, and business outcome]
    L1 --> L2 --> L3 --> L4
```

| Question | Command or activity |
| --- | --- |
| Did Agora install correctly and can every bundled role use human, AI, and swarm holders? | `agora self-test` |
| Is this project's materialized Markdown internally valid? | `agora validate` |
| Can the configured external agent runtime advance real work within its authority? | `agora run --until-blocked` |
| Is the produced work correct, useful, and acceptable? | Project tests plus accountable human review |
| Does the Agora source repository pass its complete contributor contract? | `uv run python scripts/verify_all.py` |

## Add it to CI

Keep the CI gate independent of provider credentials and project initialization:

```mermaid
flowchart LR
    P[Install approved Agora version] --> S[agora self-test]
    S --> J{Result}
    J -->|pass| V[Validate project fixtures or continue build]
    J -->|fail| B[Block adoption or upgrade]
```

A provider-neutral job needs only Python and the approved Agora package:

```bash
python -m pip install "agora-framework==X.Y.Z"
agora self-test
```

Pin `X.Y.Z` to the version reviewed by the team. No LLM or ecosystem secrets should be added to this
job. Agora's own complete verification runner includes the same harness as a mandatory step:

```bash
uv run python scripts/verify_all.py --quiet
```

## Diagnose a failure

```mermaid
flowchart TD
    F[agora self-test failed] --> Q{Was the command found?}
    Q -->|no| I[Check isolated install and PATH]
    Q -->|yes| V[Record Python and Agora package versions]
    V --> R[Re-run once without suppressing output]
    R --> D{Working from source?}
    D -->|yes| T[Run pytest tests/test_self_test.py -vv]
    D -->|no| U[Reinstall the approved package version]
    T --> C[Run complete verification before changing contracts]
    U --> O[Report version, platform, Python, and failure output]
```

From a source checkout, use the focused tests for fast diagnosis:

```bash
uv run pytest tests/test_self_test.py -vv
```

Then run the complete repository contract before submitting a change:

```bash
uv run python scripts/verify_all.py
```

## Assurance boundary

The harness proves deterministic framework conformance for the installed bundled Method Packs. It
does not contact or evaluate an LLM, score human judgment, inspect product code, authenticate to an
external tool, or execute a custom Method Pack.

```mermaid
flowchart LR
    subgraph Proven[Proven by self-test]
        A[Bundled contracts load]
        B[Actor-kind rules hold]
        C[Required roles can be assigned]
        D[Work gates and transitions execute]
        E[Terminal Markdown validates]
    end

    subgraph Separate[Requires separate evidence]
        F[LLM output quality]
        G[Human decision quality]
        H[Product tests]
        I[Provider credentials and APIs]
        J[Custom Method Pack behavior]
    end
```

For a custom Method Pack, initialize a representative fixture, exercise its own success and failure
paths, and finish with `agora validate`. For a configured non-human runtime, use
`agora run --until-blocked`; use `agora inbox` for corresponding human authority and validation
steps. This preserves a small adoption path while keeping installation confidence, project
conformance, runtime behavior, and work quality as explicit layers.

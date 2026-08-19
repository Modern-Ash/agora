# Core hardening and observable Jira integration

Status: implemented and covered by repository verification.

This increment closes two concrete gaps: compound work creation could expose partial Markdown state
after a later write failure, and the Jira sample prepared commands without showing the external
process interaction or captured provider output.

## Implemented behavior

### Rollback-protected work creation

Creating work produces a contract distributed across several files:

```text
.agora/swarms/<swarm>/work/<work>/
├── WORK.md
├── artifacts.md
├── evidence.md
├── approvals.md
└── interactions.md
```

It also appends scoped events and the project Activity Ledger. These writes now join one filesystem
transaction. Agora stages their final text, snapshots existing destinations, and applies atomic
single-file replacements. If a later write fails, it restores applied files and removes files and
empty directories created by the failed mutation.

The transaction is nested: event and activity helpers called during work creation contribute to the
same commit. They do not publish an independent partial result. The project mutation lock remains
the concurrency boundary around validation and commit.

This does not claim crash-safe database semantics. A host or process failure during commit still
requires `git status --short` and `agora validate`. Other compound lifecycle mutations will adopt
the shared boundary incrementally after their failure paths are characterized.

### Typed Tool Result inspection

The read command:

```bash
agora tool result --run <tool-run-id>
```

returns the persisted Tool Run plus its optional result. It verifies the `RESULT.md` schema and
binds these fields back to `RUN.md`:

| Field | Required consistency |
| --- | --- |
| `run` | Exact Tool Run id |
| `status` | Same terminal `completed` or `failed` status |
| `exit-code` | Same recorded exit code |
| `result-kind` | Same declared operation result kind |

It then returns bounded `stdout`, `stderr`, and the durable result path. A prepared run has no
`RESULT.md` and returns `result: null`. `agora validate` reports malformed or mismatched terminal
results as `tool-result.invalid`.

The core does not interpret provider output as a universal domain object. A Jira item, GitHub Pull
Request, pipeline, deployment, or cloud plan remains adapter output associated with its declared
result kind.

## What changed in the Jira exercise

The previous sample invoked the Jira adapter with `launch=False`. That proved command preparation
and role authority, but it did not execute ACLI, produce `RESULT.md`, or expose provider output. ACLI
was also absent from the development environment.

The updated sample places a deterministic ACLI-compatible Python executable on a temporary `PATH`
and runs the normal adapter with `launch=True`. Agora therefore exercises its real direct-process
path rather than calling an in-memory Jira fake.

The scenario performs:

1. Developer search with `issue.read`.
2. Product Owner creation with `issue.write`.
3. Developer view with `issue.read`.
4. Product Owner comment with `issue.write`.
5. Product Owner transition with `issue.transition`.
6. Developer final read showing the materialized status and comment.
7. Developer comment attempt rejected before launch because `issue.write` is absent.

The successful commands each persist separate `RUN.md` and `RESULT.md` files. The rejected command
does not create a Tool Run. The simulator never contacts Jira Cloud, stores no credentials, and is
not installed outside the temporary sample directory.

Run and inspect it:

```bash
uv run python samples/jira-cli/run.py
agora --project <printed-project-path> \
  tool result --run verify-created-jira-work
```

## Live Jira Cloud boundary

A live run requires a compatible Atlassian CLI already installed and authenticated outside Agora.
The operator must confirm the selected Jira site and provider permissions, install the reviewed
`jira` adapter, prepare the intended command, and explicitly launch it. Agora does not install ACLI,
select an account, request credentials, or silently fall back to MCP.

Use `agora tool adapter list --check` for the local compatibility probe. Provider authentication and
network failures become bounded Tool Results; they never grant missing Agora role authority.

## Compatibility

This increment adds a read-only CLI command and strengthens work-creation failure behavior. It does
not change existing Tool Pack operation schemas, provider commands, lifecycle state machines, or
stored credentials. Existing `RUN.md` and conforming `RESULT.md` documents remain readable. No
project migration is required.

The scaffold protocol now points users to the typed result command. Existing initialized projects
remain valid if their local `PROTOCOL.md` does not contain that explanatory sentence.

## Verification coverage

Automated tests cover:

- successful, failed, and prepared Tool Result inspection;
- rejection and validation of a result bound to another run;
- rollback after an injected work-creation write failure;
- absence of partial work directories and Activity Ledger entries after rollback;
- CLI JSON rendering of captured output;
- the complete executable Jira scenario;
- formatting, linting, documentation links, all bundled samples, role conformance, and distribution
  builds through `scripts/verify_all.py`.

See the [core improvement roadmap](../roadmap.md) for the next recommended increments.

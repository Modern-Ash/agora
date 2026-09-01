# Portable Tool execution boundaries

Agora launches Tool Pack commands as structured argument arrays without a shell. Each Tool Pack can
also bound the direct process by elapsed time and captured output:

```markdown
---
schema: "agora/tool/v1"
id: "issue-tracker"
name: "Team issue tracker"
version: "1.0.0"
dependencies: []
category: "issue-tracker"
executable: "tracker"
timeout-seconds: 120
max-output-bytes: 262144
---
```

`timeout-seconds` defaults to 300 and accepts values from 1 through 3600. `max-output-bytes`
defaults to 1,048,576 and accepts values from 1 through 10,485,760. Defaults preserve compatibility
with existing Tool Packs that do not declare either attribute.

## Durable policy

Preparation copies both limits into `.agora/tool-runs/<run-id>/RUN.md`. A later launch reloads the
installed Tool Pack and rejects the run if its execution policy changed. For authenticated actors,
the canonical Ed25519 authorization payload includes both values, so a signature cannot be reused
with a longer timeout or larger output allowance.

The built-in runner redirects standard output and error into temporary files instead of accumulating
unbounded data in memory. It polls the direct child process and:

- terminates it with Agora exit code `124` when the timeout expires;
- terminates or rejects its result with Agora exit code `125` when combined captured output exceeds
  the declared byte limit;
- persists only bounded child output plus a short Agora diagnostic in `RESULT.md`;
- records the failed run and its events before returning a CLI error.

An embedding that injects its own Python `tool_runner` remains responsible for active process
termination. Agora still bounds the returned output and converts an oversized result to exit code
`125` before persistence.

## Security boundary

These controls are portable execution limits, not an operating-system sandbox. The child retains the
caller's filesystem, network, syscall, credential, and operating-system permissions. Agora only
terminates the direct process; a provider that detaches descendants may outlive it.

Run untrusted or high-impact tools inside a separately governed container, restricted CI runner,
virtual machine, workload identity, or platform sandbox. That environment should enforce the
filesystem, network, process-tree, CPU, memory, and secret boundaries appropriate to the operation.
Agora remains responsible for the Markdown contract, role authorization, exact command, signed
launch evidence, bounded captured result, and durable audit trail.

See the [Tool Pack reference](../reference/tool-packs.md) for the complete manifest and invocation
contract, and run the [execution boundaries sample](../../samples/execution-boundaries/README.md) for
a deterministic demonstration.

## Autonomous session transcripts

Session `max-output-bytes` remains the hard process-output boundary (4 MiB by default). Agora
separately bounds the durable `RESULT.md` transcript to 128 KiB by default. Set
`--max-transcript-bytes` between 65,536 and 262,144 bytes. The result keeps the concise
standard-output outcome and most recent provider diagnostics, marks omitted material explicitly,
and records the original stream sizes. Long diffs, source listings, and successful build logs should
live in normal artifacts; the transcript should contain their final status and durable references.

`--execution-profile efficient|balanced|complex` is provider-neutral. Codex maps it to low, medium,
or high reasoning effort and runs ephemerally without color output; Claude maps it to the equivalent
effort and disables native session persistence. The default is `balanced`. Use `efficient` for
inspection and record maintenance and reserve `complex` for substantive implementation or review.
Explicit runners receive the selected value as `AGORA_EXECUTION_PROFILE`.

`CONTEXT.md` is scoped to the selected work item. It excludes the project Activity Ledger and full
event histories, embeds the compact inspection token, and directs the runtime to targeted reads.
Retries name their source session and include its `SUMMARY.md`, never its full `RESULT.md`, as the
orientation record.

When the Codex runtime emits its authoritative final `tokens used` counter, Agora records an
append-only work usage entry backed by the session summary. Agora does not estimate missing telemetry
and does not add provider SDKs; integrations without a supported authoritative counter continue to
submit usage explicitly.

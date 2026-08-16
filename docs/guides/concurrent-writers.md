# Concurrent writers

Agora serializes each mutating operation with an operating-system file lock. This prevents two local
CLIs, IDE integrations, agent processes, or Python API clients from reading the same state and then
overwriting each other's decisions.

## Protected operations

The lock covers the complete operation, including validation reads, Markdown writes, event appends,
Git branch creation, upgrade transactions, and launched session or tool completion records. It is
not limited to the final atomic file replacement.

Project mutations lock the canonical project path. User configuration, user actors, and user-scoped
pack installation lock the canonical Agora home path. Initialization locks both Agora home and its
target project in deterministic path order. Nested operations reuse the lock; accepting a delegation
can therefore create child work without deadlocking itself.

Read-only commands such as `status`, `list`, `show`, `doctor`, `validate`, and event queries do not
take the writer lock. Atomic Markdown replacement gives them either the preceding or following file,
never a partially written file. A read spanning several records can observe a mutation in progress;
run it again after the writer finishes when a fully stable multi-record view is required.

## Contention behavior

Agora fails immediately by default when another process owns the resource:

```text
Workspace is locked for transition_work (pid=..., host=..., since=...).
```

Set a bounded wait in seconds for automation that should queue behind a writer:

```bash
AGORA_LOCK_TIMEOUT=10 agora work transition \
  --swarm delivery --work implementation --to review --by developer
```

The value must be a non-negative number. A timeout still exits nonzero and identifies the operation,
process, host, and acquisition time recorded by the current owner.

## Inspect the lock

```bash
agora lock status
agora --project /path/to/project lock status
agora lock status --scope user
```

The response reports `active`, runtime metadata, and the lock file path. Lock files live under
`${AGORA_LOCK_HOME}` when configured, otherwise under the operating system temporary directory in
`agora-locks/<project-hash>/workspace.md`. They are runtime coordination records and are never added
to `.agora` or Git.

The Markdown file remains after release as diagnostic metadata. The `active` field comes from the
operating-system lock, not file existence. Do not delete a lock file to release it. Normal exits,
exceptions, and process termination release the operating-system lock automatically.

## Coordinate separate hosts

Local locking remains the default. A project can additionally require a reviewed external lease
CLI for every project mutation:

```bash
agora coordination configure \
  --mode external-lease \
  --resource-id repository:payments \
  --executable team-leasectl \
  --argument=--format \
  --argument=json \
  --version-argument=--version \
  --minimum-runtime-version 1.2.0 \
  --lease-seconds 300
agora coordination show
```

Agora persists the provider-neutral policy in `.agora/coordination.md`. The stable `resource-id`
must identify the same governed project from every clone and runner. It must not be a local path.
Credentials and tokens are forbidden in fixed arguments and remain in the executable's environment,
workload identity, or credential store. Agora runs the structured version command before acquisition
and rejects a missing, unverifiable, or older runtime.

For each outermost project mutation, Agora acquires local locks first and then invokes the external
CLI without a shell. Acquisition receives the resource, a `host:pid:nonce` owner, operation, and TTL.
It must return one bounded JSON object:

```json
{"lease-id":"lease-42","fencing-token":"fence-7"}
```

Agora renews the lease at one third of its TTL and releases it with the exact lease id and fencing
token. Commands have bounded runtime and captured output. Failed acquisition prevents mutation; a
renewal or release failure is reported as indeterminate and requires Git reconciliation plus
`agora validate`.

The adapter must provide atomic exclusive acquisition, owner-checked renewal and release, expiry for
dead clients, and monotonically ordered fencing tokens. Agora does not implement the remote service
or store its credentials. The service coordinates writers; Markdown and Git remain authoritative.

Return to local-only mode through a reviewed change:

```bash
agora coordination configure --mode local --force
```

Reconfiguration uses the active policy. Emergency recovery from an unavailable service must be a
manual, reviewed Git change to `.agora/coordination.md`, followed by validation and reconciliation
across hosts. See the
[distributed coordination sample](../../samples/distributed-coordination/README.md).

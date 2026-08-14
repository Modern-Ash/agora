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

## Scope boundary

This mechanism coordinates processes that see the same lock directory on one host. It does not
claim distributed mutual exclusion across unrelated machines, containers, CI runners, or network
filesystems with unreliable advisory locking. A future distributed lease adapter must preserve the
same resource identity and owner metadata without making a remote service the source of project
truth.

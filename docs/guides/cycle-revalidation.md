# Cycle revalidation and issue trackers

Agora Core treats an external issue tracker as a source of normalized facts, not as the owner of
the lifecycle. GitHub and Jira adapters implement the same read-only port; Core owns bindings,
idempotency, revision creation, authorization, and durable Markdown records.

## See engine steps in chat and CI

Use `--trace compact` for stable, line-oriented progress on `stderr` while JSON results remain on
`stdout`:

```bash
agora --trace compact run --swarm delivery --until-blocked
agora --trace detailed sync github --repo owner/maitre
AGORA_TRACE=jsonl agora status
```

A compact chat relay looks like this:

```text
AGORA 01 ... command.start        Agora accepted the command | command=run
AGORA 02 ... run.select          Selected the next governed action | step=1/20 actor=developer role=delivery state=implementing
AGORA 03 OK  run.session         Governed session reached a terminal result | step=1/20 session=run-001 transition=implementing->verifying
AGORA 04 !!  run.stop            Governed run loop stopped | step=1/20
AGORA 05 OK  command.finish       Agora completed the command | command=run
```

The modes are `off`, `compact`, `detailed`, and `jsonl`. Sessions launched by Agora set
`AGORA_TRACE=compact` unless the caller already selected another mode, so Codex and Claude can relay
the engine phases even though their subprocess streams are not terminals. Trace events contain
bounded summaries and durable IDs; provider output, prompts, credentials, and chain-of-thought are
excluded.

## Bind work to an external issue

Bindings are provider-neutral and explicit:

```bash
agora tracker bind --id maitre-42 \
  --swarm delivery --work bug-42 \
  --tracker github --project owner/maitre --issue 42 \
  --reopen-by owner

agora tracker bind --id jira-maitre-42 \
  --swarm delivery --work bug-42 \
  --tracker jira --project MAITRE --issue MAITRE-42 \
  --reopen-by owner
```

The reopen actor must hold a Method role authorized for the transition into the terminal state. A
given provider/project/issue identity can only be bound once. Actors configured with mandatory
Ed25519 authentication currently fail closed because `work.reopen` does not yet expose a signed
prepare/apply variant; use an authorized unsigned automation actor until that contract exists.

## Synchronize through reviewed adapters

Use the convenient provider commands or the equivalent neutral command:

```bash
agora sync github --repo owner/maitre
agora sync jira --project MAITRE --closed-state Done --closed-state Resolved

agora tracker sync --tracker github --project owner/maitre
```

The GitHub adapter uses `gh`; the Jira adapter uses Atlassian `acli`. Before reading issues, each
adapter enforces the executable and minimum version declared by its bundled reviewed Tool Pack.
Authentication remains in the native CLI. Core receives the same normalized snapshot fields from
both providers and stores no tokens. GitHub preserves the author's native `login`; Jira preserves
the reporter's native `accountId`. Display names remain informational and no cross-provider alias is
inferred.

Repeated synchronization of the same payload is idempotent. A `closed` to `open` transition on a
bound issue reopens terminal work, creates a new revision, and changes its operational status to
`revalidation`. Synchronizing an already-open issue does not manufacture another revision.

## Reopen work manually

```bash
agora work reopen --swarm delivery --work bug-42 --by owner \
  --reason "Production validation reproduced the bug" \
  --source manual --source-id incident-2026-08-30
```

Agora closes the previous revision with a SHA-256 snapshot of its work, artifact, evidence, and
approval registers. The new revision returns to the Method Pack state immediately before its
terminal state, clears only the current projections, and preserves all immutable historical files.
The swarm becomes running while that revision remains open.

## Record structured evidence

```bash
agora evidence add --swarm delivery --work bug-42 --by developer \
  --id production-recheck --phase production-revalidation \
  --type playwright --result success --artifact repo://reports/playwright.txt \
  --tested-commit 0123456789abcdef0123456789abcdef01234567 \
  --command-arg npm --command-arg run --command-arg test:e2e \
  --exit-code 0 --tests-total 18 --tests-passed 18 --tests-failed 0 \
  --environment production --dedupe-key ci:run:1042
```

The artifact must already be registered and exist. Agora stores one immutable
`evidence/<id>/EVIDENCE.md` record with the revision, command vector, counts, environment, tested
commit, artifact digests, actor, and timestamp; `evidence.md` remains the current-revision
projection. Reusing a dedupe key with a different payload fails.

The durable reconciliation and revision records live at:

```text
.agora/issue-trackers/bindings/<binding>/BINDING.md
.agora/issue-trackers/snapshots/<binding>/SNAPSHOT.md
.agora/issue-trackers/events/<event>/EVENT.md
.agora/swarms/<swarm>/work/<work>/revisions/<revision>/REVISION.md
```

`agora validate` checks revision continuity and snapshot hashes, evidence identities and counts,
empty successful artifacts, changed artifact contents, tracker ownership, and orphaned tracker
events. Projects on an older supported protocol can preview and apply the ordered migration to
`0.4.0` with `agora upgrade` and `agora upgrade --apply`; the `0.3.0 -> 0.4.0` edge materializes the
revision ledger without changing Method Pack permissions.

## Current boundary

This phase synchronizes issue state, labels, milestone, author identity, and comment count. PR,
checks, deployment attestations, executable verification, automatic comments, and safe issue close
remain separate subsequent contracts. No adapter is granted write authority by issue synchronization.
The signed `evidence.add` prepare/apply contract currently carries the established type, result, and
artifact subset; extending it to bind every new structured metadata field is also future work.

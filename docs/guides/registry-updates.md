# Registry updates

Agora separates update detection from mutation. `registry update` previews an authenticated release
by default and changes the installed snapshot only when `--apply` is explicit.

Updates are available only for registries originally installed from a versioned remote `INDEX.md`.
Local directory snapshots have no release source to check.

If the installed `SOURCE.md` requires transparency, first verify and record the proof for the target
release. Both preview and application revalidate it, and the applied `UPDATE.md` preserves the
forward-only policy:

```bash
agora registry verify-transparency --source ./PROOF-2.0.0.md --scope project --record
agora registry update --id team-catalog --scope project
agora registry update --id team-catalog --scope project --apply
```

`--require-transparency` can raise the policy while selecting a later release. It becomes durable
only when that update is applied and cannot be lowered afterward.

## Check for an update

```bash
agora registry update --id team-catalog
```

When both project and user scopes contain the id, project scope wins. Select one explicitly when
needed:

```bash
agora registry update --id team-catalog --scope user
```

The preview reads the persisted index URL from `SOURCE.md`, selects the highest semantic release,
and verifies its signature policy. It does not download the archive. The captured JSON result reports current
and target versions, checksum, signature status, scope, and whether an update is available.

Select a particular release instead of latest:

```bash
agora registry update --id team-catalog --version 2.1.0
```

Agora rejects downgrades. It also rejects an index that publishes a different checksum for the
currently installed version, because release versions are immutable identities.

## Apply an update

```bash
agora registry update --id team-catalog --apply
```

Application repeats index authentication, downloads the selected archive, verifies its SHA-256,
checks the registry id and version, validates every pack, prepares provenance and history, and swaps
the complete staged directory with rollback protection.

If the installed release required a signature threshold, every update must satisfy at least that
same number of distinct trusted public-key fingerprints. This policy cannot be downgraded through
CLI flags. `--signature-threshold` may raise it for the selected update and all later releases. Add
rotated keys to the trust store before applying a release signed by their new ids.

HTTP remains disabled unless the original development registry is explicitly accessed with:

```bash
agora registry update --id local-catalog --allow-insecure-http
```

## Durable history

Each successful version change creates:

```text
.agora/registries/team-catalog/updates/<update-id>/UPDATE.md
```

The record contains the registry id, previous and target versions and checksums, final index URL,
verified signer ids, required threshold, and application timestamp. Existing update records are
copied into staging before replacement, so subsequent updates preserve the full chain. `agora
validate` checks the schemas, identities, forward-only version movement, checksums, and registry
ownership of every record.
It also requires adjacent version and checksum continuity and requires the last update to match the
current `SOURCE.md` provenance.

## Pack installation remains explicit

Updating a registry updates its catalog snapshot. It does not silently modify Method Packs or Tool
Packs already copied into user or project pack scope. Review the new catalog, then opt into a pack
refresh separately:

```bash
agora pack search --registry team-catalog
agora pack install --kind method --id release-flow \
  --registry team-catalog --scope project --force
```

This preserves the distinction between distribution metadata and the lifecycle or tool contract
currently governing work.

## No-update result

When the selected release matches the installed version and checksum, the result contains:

```json
{
  "update_available": false,
  "applied": false
}
```

`--apply` remains a no-op in that state and does not create a history record.

## Aggregate audits and notifications

Check every remotely installed registry in one scope without applying anything:

```bash
agora registry audit --scope project
```

The command reuses each registry's persisted source and signature policy. It fails on an
authentication, immutability, transport, or availability error instead of turning that failure into
a successful notification. Local directory registries are omitted because they have no release
index.

Persist the authenticated result as Markdown when a human, agent, CI job, or scheduler needs a
durable notification:

```bash
agora registry audit --scope project --record
```

Reports live under:

```text
.agora/notifications/registry-updates/<audit-id>/AUDIT.md
```

Each entry records the registry, scope, installed and available versions, update flag, and signature
status. `agora validate` checks the report schema, id, version direction, and flags. Recording a
report does not update a registry or any installed pack.

Agora does not run a resident poller. Use the environment's ordinary scheduler and invoke the CLI
non-interactively, keeping credentials in the provider's external credential mechanism. A CI job
can inspect the JSON output or commit a reviewed `AUDIT.md`; applying an update remains a separate
explicit command.

## Current boundary

Agora provides aggregate, recordable update notifications but does not run a background service or
apply registry or installed-pack updates on a schedule. Scheduling and message delivery remain
external integrations. Mutation remains preview-first and explicit.

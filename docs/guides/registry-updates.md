# Registry updates

Agora separates update detection from mutation. `registry update` previews an authenticated release
by default and changes the installed snapshot only when `--apply` is explicit.

Updates are available only for registries originally installed from a versioned remote `INDEX.md`.
Local directory snapshots have no release source to check.

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
and verifies its signature policy. It does not download the archive. The JSON result reports current
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

If the installed release was signature-verified, every update must also verify a signature. This
policy cannot be downgraded through CLI flags. Add a rotated key to the trust store before applying a
release signed by its new `key-id`.

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
signature status, and application timestamp. Existing update records are copied into staging before
replacement, so subsequent updates preserve the full chain. `agora validate` checks the schemas,
identities, forward-only version movement, checksums, and registry ownership of every record.
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

## Current boundary

Agora does not poll in the background, send update notifications, resolve pack dependencies, or
apply updates on a schedule. Checks are explicit CLI operations suitable for a human, agent, CI job,
or future ecosystem adapter.

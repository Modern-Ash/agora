# Installed pack provenance and updates

Agora records where each catalog-installed Method or Tool Pack came from. Updates are explicit,
preview-first operations over that durable evidence; changing a registry snapshot never changes a
pack already copied into user or project scope.

## Provenance record

Catalog installation writes `SOURCE.md` beside `METHOD.md` or `TOOL.md`:

```markdown
---
schema: "agora/pack-source/v1"
kind: "tool"
id: "delivery-tool"
version: "1.4.0"
registry: "dependency-catalog"
registry-scope: "project"
registry-version: null
registry-source: null
sha256: "..."
installed-at: "2026-08-14T12:00:00Z"
---
```

The checksum covers the complete published pack tree except installer-owned metadata. It detects
local amendments without preventing them. `agora validate` reports a modified catalog installation
as `pack-source.modified` with warning severity. Until the amendment is reviewed and locked, the
unchanged composition lock also produces `pack-lock.drift`; malformed or mismatched provenance is an
error.

Direct `agora method install` and `agora tool install` sources do not receive catalog provenance and
cannot use `agora pack update`. A registry is also forbidden from publishing its own `SOURCE.md` or
`updates` directory, so only the local installer can assert provenance.

## Preview an update

First update or replace the registry snapshot through its normal authenticated path. Then inspect the
pack plan:

```bash
agora registry update --id dependency-catalog --apply
agora pack update --kind method --id delivery-flow
```

By default Agora searches the registry recorded in `SOURCE.md`. Use `--registry` only to move the
pack intentionally to another visible source. When both user and project registries share that id,
the original registry scope is preferred.

The JSON result reports the current and target versions, whether local content differs from its
source, and every Method or Tool Pack in dependency-first update order. Preview performs no writes.

Agora rejects downgrades and a catalog that changes pack content without changing the pack version.
An identical version and checksum is a no-op unless the installed copy has local amendments, in
which case the update represents an explicit restoration of published content.

## Apply an update

```bash
agora pack update --kind method --id delivery-flow --apply
```

Agora resolves the prospective dependency graph before mutation. Dependencies are ordered before
their consumer, every pack is staged and validated as a clean snapshot, and the complete plan is
swapped with rollback protection. The new `SOURCE.md` records each selected registry, version,
checksum, and installation time.

Every affected pack also receives `updates/<update-id>/UPDATE.md`. The record connects its previous
actual checksum to the new published checksum. All packs in one dependency plan share the update id,
and their histories are preserved across clean snapshot replacement. See
[Pack composition locks and update history](pack-locks.md).

Local amendments or a dependency without catalog provenance stop application. After reviewing the
preview and Git diff expectations, permit their replacement explicitly:

```bash
agora pack update --kind method --id delivery-flow --apply --force
```

`--force` never bypasses version constraints, missing dependencies, cycles, or reverse-dependent
compatibility. It only authorizes replacing locally divergent content after the final composition
has passed validation.

After a successful swap Agora regenerates the target scope's `PACKS.lock.md`. A failed multi-pack
swap restores every previous pack and leaves the existing lock untouched.

Use `--scope user` or `--scope project` when the same pack is installed in both locations. Without a
scope, an initialized project takes precedence over the user installation.

## Aggregate pack audits

After updating a registry snapshot, inspect every catalog-installed pack in one scope:

```bash
agora pack audit --scope project
```

Directly installed packs have no catalog provenance and are omitted. Each JSON entry reports its
kind, id, registry, installed and target versions, update availability, and whether the installed
tree has local modifications. The audit calls the same dependency-aware preview used by
`agora pack update`; it does not write a pack, history record, or composition lock.

Persist a durable notification for a human, agent, CI job, or external scheduler:

```bash
agora pack audit --scope project --record
```

Reports live under:

```text
.agora/notifications/pack-updates/<audit-id>/AUDIT.md
```

`agora validate` checks report identities, version direction, update flags, and duplicate entries.
A catalog error, incompatible dependency graph, or mutable published version fails the audit rather
than producing a successful notification.

The complete scheduled detection sequence may be automated without granting mutation authority:

```bash
agora registry audit --scope project --record
agora pack audit --scope project --record
```

Registry application and each pack application remain separate, explicit commands. Agora does not
interpret a recorded audit as approval and never turns a notification into an automatic update.

Run the end-to-end example:

```bash
uv run python samples/pack-dependencies/run.py
```

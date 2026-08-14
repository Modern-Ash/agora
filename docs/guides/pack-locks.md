# Pack composition locks and update history

Agora persists both the current installed pack composition and the transitions that produced newer
catalog copies. These records are Markdown with structured front matter, suitable for review and Git
without introducing a package-manager database.

## Composition lock

Each configured user scope and initialized project contains `PACKS.lock.md`:

```markdown
---
schema: "agora/pack-lock/v1"
scope: "project"
generated-at: "2026-08-14T12:00:00Z"
packs: [{"kind":"method","id":"scrum","version":"1.0.0","sha256":"...","registry":null,"source-sha256":null}]
---
```

Entries are sorted by kind and id. Every entry records the installed version and actual tree
checksum. Catalog-installed packs also include their registry and published source checksum. When
the two checksums differ, the lock intentionally captures a reviewed local amendment while
`SOURCE.md` continues to describe the published source.

Agora regenerates the appropriate lock after configuration, project initialization, direct pack
installation, catalog installation, applied pack updates, and applied pack removals. Preview
commands never change it.

Manual filesystem edits cause `agora validate` to report `pack-lock.drift` until the new composition
is reviewed and locked explicitly:

```bash
agora pack lock --scope project
git diff -- .agora/PACKS.lock.md
agora validate
```

Use `--scope user` for `~/.agora/PACKS.lock.md`. A missing project lock is a compatibility warning;
an invalid lock or a lock that disagrees with the filesystem is an error. Refresh does not change a
pack, resolve dependencies, or claim catalog provenance. It inventories the state already present.

## Per-pack update history

Every applied catalog update writes an installer-owned record inside each affected pack:

```text
.agora/tools/delivery-tool/
  TOOL.md
  SOURCE.md
  updates/
    update-20260814t120000000000z/
      UPDATE.md
```

`UPDATE.md` uses `agora/pack-update/v1` and records:

- pack kind and id;
- previous and target versions;
- previous actual tree checksum and target published checksum;
- selected registry and registry scope;
- application timestamp.

An update that introduces a previously absent dependency uses `null` for its previous version and
checksum. Reinstalling an existing catalog pack with `--force` also creates history rather than
silently replacing its source evidence.

Histories are preserved when a clean catalog snapshot replaces pack files. Adjacent records must be
continuous by version and checksum, and the latest record must match current `SOURCE.md`. Agora
validates the chain during staging, ordinary pack reads, and `agora validate`.

The same update id is used for every pack in one dependency-aware plan. This lets reviewers connect
the Method and Tool transitions even though each pack owns its own record. The entire plan is staged
and swapped with rollback protection before `PACKS.lock.md` is regenerated.

## Review workflow

```bash
agora registry update --id team-catalog --apply
agora pack update --kind method --id delivery-flow
agora pack update --kind method --id delivery-flow --apply
git diff -- .agora/methods .agora/tools .agora/PACKS.lock.md
agora validate
```

Commit the updated pack snapshots, `SOURCE.md`, `updates/*/UPDATE.md`, and `PACKS.lock.md` together so
another environment can reconstruct both the current composition and its provenance transitions.
Applied removals commit their `pack-removals/*/REMOVAL.md` record with the changed lock instead of
retaining deleted pack-owned update histories in current state.

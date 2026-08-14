# Pack registries

An Agora registry is a local, Markdown-first catalog of validated Method Packs and Tool Packs. It is
a versionable directory snapshot, not a package server or remote source of truth.

## Registry layout

```text
team-registry/
  REGISTRY.md
  methods/
    release-flow/
      METHOD.md
      PROTOCOL.md
      TOOLS.md
      roles/
      transitions/
      gates/
  tools/
    issue-tracker/
      TOOL.md
      operations/
```

`REGISTRY.md` contains:

```markdown
---
schema: "agora/registry/v1"
id: "team-catalog"
name: "Team Catalog"
---

# Team Catalog

Reviewed lifecycle and developer-tool packs maintained by the team.
```

The id is an Agora lowercase slug. A registry must contain at least one valid pack. Pack directory
names must match their manifest ids. Agora validates every method graph, role, gate, transition, tool
operation, placeholder, capability, and input rule before copying the registry.

## Install a registry snapshot

Install for reuse across projects:

```bash
agora registry install --source ./team-registry --scope user
```

Install into one initialized project and commit the snapshot:

```bash
agora registry install --source ./team-registry --scope project
git add .agora/registries/team-catalog
```

User registries live under `~/.agora/registries`; project registries live under
`.agora/registries`. `--force` refreshes matching files but does not delete files removed from a newer
source snapshot. Review the diff and remove intentionally retired entries explicitly.

## Discover packs

```bash
agora registry list
agora pack search
agora pack search --kind method --query release
agora pack search --kind tool --registry team-catalog
```

Agora always exposes the synthetic `agora-bundled` registry containing the installed distribution's
Scrum, Kanban, and repository packs. Search results report the registry and scope, source path, and
whether a pack with that kind and id is already installed in user or project scope.

When the same pack id exists in multiple sources, resolution order is:

```text
project registry > user registry > bundled registry
```

Search returns every matching source so the collision remains visible. Use `--registry` during
installation when provenance must be explicit.

## Install a discovered pack

```bash
agora pack install --kind method --id release-flow \
  --registry team-catalog --scope project

agora pack install --kind tool --id issue-tracker \
  --registry team-catalog --scope user
```

Registry scope identifies where the catalog snapshot came from. Installation scope independently
identifies where the selected pack is copied. Catalog installation delegates to the ordinary
`method install` or `tool install` path, so it preserves the same validation, overwrite protection,
and local customization behavior.

## Validation and trust

`agora validate` audits every project registry and all packs inside it. User registries are validated
when installed, listed, searched, or selected. Registry installation never executes pack commands;
Tool Pack executables run only through a separately authorized `agora tool invoke --launch`.

Treat a registry source like code: review it before installation. The registry contains no
credentials and must not put credentials in Tool Pack inputs.

## Current boundary

This release accepts local filesystem sources. A remote index, signed releases, version constraints,
checksums, dependency resolution, and network download are not implemented yet. Those features can
later resolve to the same immutable registry snapshot contract without changing installed project
state or making a hosted catalog authoritative.

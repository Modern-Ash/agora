# Pack dependencies and compatibility

Agora packs may declare other Method or Tool Packs that must be present in the same installation
scope. Dependencies are Markdown manifest data: they select no programming language, LLM provider,
development process, or external package manager.

## Manifest contract

Add `version` and `dependencies` to `METHOD.md` or `TOOL.md`:

```markdown
---
schema: "agora/method/v1"
id: "delivery-flow"
name: "Delivery Flow"
version: "2.0.0"
dependencies: [{"kind":"tool","id":"delivery-tool","version":">=1.0.0,<2.0.0"}]
required-roles: ["owner", "maker"]
work-states: ["ready", "active", "done"]
terminal-state: "done"
---
```

Every dependency has exactly three attributes:

| Attribute | Contract |
| --- | --- |
| `kind` | `method` or `tool` |
| `id` | Lowercase Agora pack id |
| `version` | `*`, an exact version, or comma-separated comparisons |

Pack versions use numeric `MAJOR.MINOR.PATCH`. Supported comparisons are `=`, `==`, `>`, `>=`, `<`,
and `<=`. Whitespace, prerelease labels, build metadata, caret ranges, and tilde ranges are not part
of the v1 contract. For example, `>=1.2.0,<2.0.0` accepts `1.2.0` through the latest `1.x` release.

A legacy manifest without `version` remains loadable as `0.0.0`; missing `dependencies` means an
empty list. Authors should always publish both attributes so consumers can declare useful ranges.

## Catalog resolution

```bash
agora pack search --registry dependency-catalog
agora pack install --kind method --id delivery-flow \
  --registry dependency-catalog --scope project
```

Search output includes each pack's version and direct dependencies. Installation resolves the whole
graph before copying any pack. An already installed compatible dependency is reused. Otherwise,
Agora selects the first compatible catalog candidate using normal precedence:

```text
project registry > user registry > bundled registry
```

Dependencies are installed before their consumer. The requested `--registry` fixes the requested
pack's provenance; dependencies may come from another visible registry when that is the highest
precedence compatible source.

Agora rejects missing dependencies, incompatible ranges, conflicting selected versions, duplicate
dependency declarations, and direct or transitive cycles. Resolution failure occurs before a pack
is copied.

## Scope and replacement

Dependencies must exist in the same target scope as the requested pack. A project installation uses
`.agora/methods` and `.agora/tools`; a user installation uses `~/.agora/methods` and
`~/.agora/tools`. This keeps a checked-in project independent from later changes to the user's home.

Direct `agora method install` and `agora tool install` commands do not search catalogs. Their
dependencies must already be installed in the target scope. Catalog installation is the path that
performs recursive discovery.

If an installed dependency has an incompatible version, catalog installation stops unless
`--force` permits replacement. Even with `--force`, Agora computes the final composition first and
rejects a replacement that would break another installed pack.

Registry updates do not refresh installed packs. After updating a registry, explicitly install a
new pack version with `agora pack update` so dependency resolution and the project Git diff remain
reviewable. See [Installed pack provenance and updates](pack-updates.md).

## Validation

`agora validate` loads every project Method and Tool Pack as one composition. Missing dependencies,
incompatible installed versions, and cycles produce `pack.dependency-invalid`. This also detects
manual filesystem edits that bypassed the installation commands.

Run the executable example:

```bash
uv run python samples/pack-dependencies/run.py
```

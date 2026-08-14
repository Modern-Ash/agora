# Safe pack removal

Agora removes installed Method and Tool Packs as a governed composition change. Removal is
preview-first, dependency-aware, and persisted in Markdown. It does not infer intent from a chat
session or silently edit other packs.

## Preview one pack

```bash
agora pack remove --kind method --id delivery-flow
```

The JSON plan names the resolved scope and each pack that would be removed. Without `--scope`, an
initialized project's installation takes precedence over the user installation, matching pack
update behavior. Use `--scope user` or `--scope project` to select explicitly.

Preview does not delete directories, write history, or refresh the composition lock.

Agora rejects the plan when another installed pack depends on the requested pack. Remove the
consumer first, or install a replacement composition that no longer declares the dependency.
Dependency checks remain scope-local.

## Durable references

Composition validity is not the only safety boundary. Project removal is blocked when a selected
pack remains referenced by:

- the project's default method;
- an existing swarm's method;
- a durable tool-run record.

User removal is blocked when the selected Method Pack is the configured user default. Change the
reference deliberately before retrying removal. Agora does not erase historical state to make a
removal pass.

## Prune unused dependencies

The default plan removes only the requested pack. Add the explicit pruning option to inspect the
dependencies that would become unused by the remaining pack graph:

```bash
agora pack remove \
  --kind method \
  --id delivery-flow \
  --with-unused-dependencies
```

Pruning is limited to the requested pack's installed transitive dependency closure. A dependency is
included only when all of its installed consumers are already in the removal plan. Shared
dependencies remain installed.

Agora does not maintain a hidden package-manager database that labels packs as top-level or
transitive installations. The explicit flag therefore means: remove graph-unused dependencies from
this closure after reviewing the preview. Packs unrelated to the closure are never collected.

## Apply and audit

Apply the reviewed plan with the same options:

```bash
agora pack remove \
  --kind method \
  --id delivery-flow \
  --with-unused-dependencies \
  --apply
```

Agora moves every selected pack into temporary staging, builds the next composition lock, and
writes one scope-level record:

```text
.agora/pack-removals/
  removal-20260814t120000000000z/
    REMOVAL.md
```

`REMOVAL.md` uses `agora/pack-removal/v1`. It records the requested identity, removal timestamp, and
each removed pack's kind, id, version, actual SHA-256, optional source registry, and reason:
`requested` or `unused-dependency`.

The pack trees remain recoverable in staging until the removal record and new `PACKS.lock.md` are
published. Any failure restores the prior trees and lock and removes the partial audit record.

Review and commit the composition subtraction together:

```bash
git diff -- .agora/methods .agora/tools .agora/pack-removals .agora/PACKS.lock.md
agora validate
git add .agora
git commit -m "chore(packs): remove delivery flow"
```

Run the executable example:

```bash
uv run python samples/pack-removal/run.py
```

# Pack dependency sample

This sample builds a local registry whose `delivery-flow` Method Pack requires a compatible
`delivery-tool` Tool Pack. Installing only the method from the catalog resolves and installs the
tool first. The sample then publishes a newer local catalog snapshot, previews a dependency-aware
update, applies both pack versions, and validates the complete project composition.

Run it from the repository root:

```bash
uv run python samples/pack-dependencies/run.py
```

The registry, Agora home, and initialized project remain in the printed temporary directory for
inspection. See [Pack dependencies](../../docs/guides/pack-dependencies.md) for manifest syntax and
resolution rules, and [Pack updates](../../docs/guides/pack-updates.md) for provenance and explicit
upgrade behavior.

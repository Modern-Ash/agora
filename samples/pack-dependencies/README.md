# Pack dependency sample

This sample builds a local registry whose `delivery-flow` Method Pack requires a compatible
`delivery-tool` Tool Pack. Installing only the method from the catalog resolves and installs the
tool first, then validates the complete project composition.

Run it from the repository root:

```bash
uv run python samples/pack-dependencies/run.py
```

The registry, Agora home, and initialized project remain in the printed temporary directory for
inspection. See [Pack dependencies](../../docs/guides/pack-dependencies.md) for manifest syntax,
resolution precedence, replacement rules, and legacy behavior.

# Pack removal sample

This sample creates a local catalog with a Method Pack and one Tool Pack dependency, installs the
composition, previews removal with unused-dependency pruning, and applies the same plan. It prints
the durable removal record, resulting composition lock, and validation count.

Run it from the repository root:

```bash
uv run python samples/pack-removal/run.py
```

The registry, Agora home, and initialized project remain in the printed temporary directory for
inspection. See [Safe pack removal](../../docs/guides/pack-removal.md) for blockers, pruning
semantics, transaction behavior, and the `agora/pack-removal/v1` record.

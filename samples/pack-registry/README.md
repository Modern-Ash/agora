# Pack registry sample

This sample builds a local Markdown registry containing the custom `release-flow` Method Pack,
installs the registry at user scope, discovers the pack, installs it into a project, and selects it
for a new swarm. The final project passes complete validation.

Run it from the repository root:

```bash
uv run python samples/pack-registry/run.py
```

The registry snapshot, Agora home, and project remain in the system temporary directory for
inspection.

See [Pack registries](../../docs/guides/pack-registries.md) for the contract, precedence, trust, and
remote-distribution boundaries.

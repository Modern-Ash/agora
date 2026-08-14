# Governed observability sample

This sample uses a deterministic Python provider behind the bundled `observectl` contract. It
checks service health, creates an incident, grants guarded resolution authority, rejects resolution
without Product Owner approval, and resolves after recovery evidence is reviewed.

Run it from the repository root:

```bash
uv run python samples/observability/run.py
```

See the [observability integration guide](../../docs/guides/observability-integrations.md).

# Concurrent writers sample

This sample holds a project write lock, demonstrates that a competing Agora mutation fails without
creating a partial actor record, releases the lock, and repeats the mutation successfully. It also
prints active and released runtime metadata.

Run it from the repository root:

```bash
uv run python samples/concurrent-writes/run.py
```

The generated project and lock home remain in the system temporary directory for inspection.

See [Concurrent writers](../../docs/guides/concurrent-writers.md) for timeout, scope, and distributed
coordination boundaries.

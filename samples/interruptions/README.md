# Interruption and cancellation sample

This sample creates two linked Scrum swarms and demonstrates durable work blocking and resumption,
delegation blocking before and after acceptance, parent cancellation, and child rejection.

Run it from the repository root:

```bash
uv run python samples/interruptions/run.py
```

The generated project remains in the system temporary directory. Inspect its `WORK.md`,
`DELEGATION.md`, nested `status-changes/*/STATUS.md` files, and events to see the complete portable
history.

See [Interruptions and cancellation](../../docs/guides/interruptions-and-cancellation.md) for the
CLI commands and authority rules.

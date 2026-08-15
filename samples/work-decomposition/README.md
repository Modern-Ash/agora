# Work decomposition sample

This sample creates a Scrum work item, materializes two governed children inside the same swarm,
proves that the parent cannot close while either child is open, and then closes the hierarchy with
durable cancellation reasons.

Run it from the repository root:

```bash
uv run python samples/work-decomposition/run.py
```

The generated project remains in the system temporary directory. Inspect the parent and child
`WORK.md` files and their `events.md` and `status-changes` histories.

See [Work decomposition](../../docs/guides/work-decomposition.md) for CLI and signed-action usage.

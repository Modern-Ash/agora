# Governed handoff sample

This sample keeps one Scrum Developer responsibility and work item continuous while execution moves
from a human to an AI agent and then to a composite swarm. Every receiver must satisfy the same role
contract, and each transfer creates an immutable handoff record plus swarm and work events.

Run it from the repository root:

```bash
uv run python samples/handoffs/run.py
```

The generated project remains in the system temporary directory. Inspect
`.agora/swarms/delivery/handoffs`, `SWARM.md`, and the work events to see current responsibility and
historical attribution together.

See the [handoff guide](../../docs/guides/handoffs.md) for authorization and CLI usage.

# Delegated work sample

This sample creates a parent Scrum swarm and a linked specialist swarm, signs work creation,
proposal, governance interruption, acceptance, criteria, evidence, and collection externally,
completes the work under the child's own lifecycle, and collects the result into the parent work
item.

Run it from the repository root:

```bash
uv run python samples/delegated-work/run.py
```

The project is left in the system temporary directory. Inspect `.agora/delegations`, both swarm
work directories, and the parent `artifacts.md` and `evidence.md` files to follow the complete
protocol.

See [Delegated work](../../docs/guides/delegated-work.md) for the lifecycle and CLI reference.

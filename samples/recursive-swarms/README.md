# Recursive swarm sample

This sample links a real child swarm to a project actor, assigns that composite actor to a parent
swarm, and demonstrates enforcement of the configured delegation depth. The child must be ready,
the graph must remain acyclic, and every level keeps its own objective, roles, events, and work.

Run it from the repository root:

```bash
uv run python samples/recursive-swarms/run.py
```

The project is left in the system temporary directory. Inspect the linked actor and each `SWARM.md`
to follow the parent-to-child delegation.

See [Recursive swarms](../../docs/guides/recursive-swarms.md) for configuration and safety rules.

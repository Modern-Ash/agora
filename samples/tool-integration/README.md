# Governed tool integration sample

This sample initializes a temporary Git repository, forms a Scrum swarm, and invokes the bundled
`repository/status` operation as the Developer actor. Agora executes Git without a shell and stores
the invocation and captured result under `.agora/tool-runs/repository-status`.

Run it from the repository root:

```bash
uv run python samples/tool-integration/run.py
```

The same Tool Pack contract can wrap vendor CLIs for issue tracking, CI/CD, documentation, cloud,
observability, and communication. Authentication remains in each CLI environment; Agora persists
only the declared authentication reference, command metadata, actor attribution, and result.

See the [Tool Pack reference](../../docs/reference/tool-packs.md) to author and install an integration.

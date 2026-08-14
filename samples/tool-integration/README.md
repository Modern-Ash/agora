# Governed tool integration sample

This sample initializes a temporary Git repository, forms a Scrum swarm, and invokes the bundled
`repository/status` and `repository/commit` operations as the Developer actor. The commit uses a
validated Conventional Commits 1.0.0 message. Agora executes Git without a shell and stores each
invocation and captured result under `.agora/tool-runs`.
The sample first rejects a non-conforming message and proves that no run record is created, then
executes a valid commit from the staged README.

Run it from the repository root:

```bash
uv run python samples/tool-integration/run.py
```

The same Tool Pack contract can wrap vendor CLIs for issue tracking, CI/CD, documentation, cloud,
observability, and communication. Authentication remains in each CLI environment; Agora persists
only the declared authentication reference, command metadata, actor attribution, and result.

See the [Tool Pack reference](../../docs/reference/tool-packs.md) to author and install an integration.

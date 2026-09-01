# AI-DLC lifecycle sample

`ai-dlc` is a bundled Method Pack that renders AWS's AI-Driven Development Life
Cycle as an Agora lifecycle: five phase-boundary states, five approval gates, and
two rework edges.

Run the sample from the repository root:

```bash
uv run python samples/ai-dlc/run.py
```

The script initializes an isolated project with `ai-dlc` as the default method,
forms a five-role delivery swarm, and walks one work item from `initiation` to
`completed`, including one `operation -> construction` rework loop. Every gate is
satisfied with real artifacts, evidence, and approvals.

See the [AI-DLC guide](../../docs/guides/ai-dlc.md) and the
[Method Pack reference](../../docs/reference/method-packs.md).

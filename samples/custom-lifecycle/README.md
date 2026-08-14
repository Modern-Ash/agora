# Custom lifecycle sample

`release-flow` is a Method Pack defined entirely in Markdown. Its roles and work states do not
derive from Scrum or Kanban, and it does not assume a programming language, runtime, LLM, or model
provider.

Run the sample from the repository root:

```bash
uv run python samples/custom-lifecycle/run.py
```

The script installs the pack in an isolated Agora home, selects it as the user default, initializes
a project, and creates a swarm governed by the custom lifecycle.

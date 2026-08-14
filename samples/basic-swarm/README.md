# Basic swarm sample

This sample creates an isolated Git repository and Agora home, installs the Codex integration,
registers human, AI-agent, and nested-swarm actors, forms a Scrum swarm, prepares a governed Codex
session, exercises a rework edge, demonstrates a rejected completion gate, and completes the work
with artifacts, evidence, and Product Owner approval.

From the repository root:

```bash
uv run python samples/basic-swarm/run.py
```

The generated project is left in the system temporary directory so its Markdown protocol and Git
branch can be inspected after the run.

See [Scrum delivery with humans and AI](../../docs/guides/scrum-delivery.md) for the role model,
commands, LLM prompts, gate behavior, and mapping between Scrum concepts and Agora files.

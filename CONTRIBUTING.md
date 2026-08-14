# Contributing to Agora

Agora is experimental. Prefer small changes that remain inspectable after installation.

```bash
uv sync --extra dev
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run python scripts/check_docs.py
uv build
uv run python samples/basic-swarm/run.py
uv run python samples/llm-environments/run.py
uv run python samples/custom-lifecycle/run.py
uv run python samples/tool-integration/run.py
uv run python samples/handoffs/run.py
uv run python samples/recursive-swarms/run.py
uv run python samples/delegated-work/run.py
```

## Rules

- Preserve programming-language, runtime, provider, model, development-process, agent, IDE, and
  cloud independence.
- Implement Agora automation in Python; do not introduce JavaScript or TypeScript tooling.
- Do not add an LLM SDK to the core CLI.
- Keep operational state in Markdown and Git, not a parallel database or JSON snapshot.
- Keep adapter-specific output outside Method Packs and domain rules.
- Keep Tool Pack commands structured and provider credentials outside durable inputs.
- Keep Method Pack identifiers open; bundled packs are examples, not core enums.
- Add tests for capabilities, role actions, transitions, WIP, gates, approvals, handoffs, recursive
  swarms, delegated work, sessions, tool runs, and filesystem behavior.
- Update templates and documentation whenever the installed protocol changes.
- Never persist raw credentials; store only external authentication references.
- Treat humans, AI agents, services, automations, and swarms as compatible actor forms governed by
  role contracts.

Generated distributions, virtual environments, local `.agora`, and installed agent commands are not
committed to this repository.

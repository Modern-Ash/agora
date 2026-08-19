# Contributing to Agora

Agora is experimental. Prefer small changes that remain inspectable after installation.

The complete verification command is:

```bash
uv run python scripts/verify_all.py
```

Run individual checks while iterating:

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
uv run python samples/operational-query/run.py
uv run python samples/operational-loop/run.py
uv run python samples/interruptions/run.py
uv run python samples/project-upgrade/run.py
uv run python samples/concurrent-writes/run.py
uv run python samples/pack-registry/run.py
uv run python samples/remote-registry/run.py
uv run python samples/github-end-to-end/run.py
uv run python samples/jira-cli/run.py
```

## Rules

- Preserve programming-language, runtime, provider, model, development-process, agent, IDE, and
  cloud independence.
- Implement Agora automation in Python; do not introduce JavaScript or TypeScript tooling.
- Do not add an LLM SDK to the core CLI.
- Keep operational state in Markdown and Git, not a parallel database or JSON snapshot.
- Keep adapter-specific output outside Method Packs and domain rules.
- Prefer reviewed native CLI adapters when a provider CLI already exists; keep MCP optional and
  explicit rather than an automatic fallback.
- Declare and validate a partial adapter when the native CLI implements only a safe subset of a
  provider-neutral contract.
- Keep Tool Pack commands structured and provider credentials outside durable inputs.
- Keep Method Pack identifiers open; bundled packs are examples, not core enums.
- Add tests for capabilities, role actions, transitions, WIP, gates, approvals, handoffs,
  interruptions, recursive swarms, delegated work, sessions, tool runs, queries, validation, and
  filesystem behavior.
- For compound Markdown mutations, document the complete write set and add injected failure tests
  that prove rollback does not leave domain records, event streams, or activity out of sync.
- Keep Tool Result inspection provider-neutral: validate Agora metadata while returning bounded
  provider output without inventing a universal provider schema.
- Update templates and documentation whenever the installed protocol changes.
- Keep explanatory material under `docs/`, operational protocol sources under `packs/`, and
  plugin-owned run output under its existing plugin directory.
- Use Mermaid when a decision tree, lifecycle, sequence, scope hierarchy, or ownership boundary is
  easier to understand visually. Keep adjacent prose and commands authoritative, and prefer a table
  when relationships are static rather than sequential.
- Keep `scripts/verify_all.py` aligned with every executable sample and distribution check.
- Never persist raw credentials; store only external authentication references.
- Never persist registry private signing keys; trust records contain public keys only.
- Treat humans, AI agents, services, automations, and swarms as compatible actor forms governed by
  role contracts.
- Use Conventional Commits 1.0.0 for every commit. Use `feat` for features, `fix` for fixes, and `!`
  or a `BREAKING CHANGE:` footer for breaking changes.

## Commit messages

```text
<type>[optional scope][!]: <description>

[optional body]

[optional footer(s)]
```

Examples:

```text
feat(governance): validate repository commit messages
fix(upgrade): preserve customized tool operations
docs: explain local writer locks
feat(protocol)!: require explicit release evidence
```

Agora projects materialize this rule in `.agora/STANDARDS.md`. When exercising Agora itself, prefer
the governed `repository/commit` Tool Pack operation so the input is validated before Git runs.

Generated distributions, virtual environments, local `.agora`, and installed agent commands are not
committed to this repository.

Use the [core improvement roadmap](docs/roadmap.md) to understand the current extraction and
hardening priorities. Completed behavior is authoritative only when its implementation, tests, and
user-facing documentation land together.

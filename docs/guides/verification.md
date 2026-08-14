# Complete verification

Agora has two complementary verification scopes. `agora validate` audits one initialized workspace.
The repository runner audits the framework implementation, every bundled Markdown contract, every
agent environment, all executable swarm scenarios, and the built distribution.

## Validate an initialized workspace

Run validation from the project or target it from any IDE, CLI, CI worker, or cloud environment:

```bash
agora validate
agora --project /path/to/project validate
```

The report is JSON. `ok` is false and the process exits with status `1` when an error is present.
The `checked` object reports how many records of each kind were successfully parsed, including
`commands` and `adapters`.

Portable commands under `.agora/commands` must have:

- A filename that is a lowercase command id.
- A front matter `name` equal to `agora-<command-id>`.
- A non-empty `description`.
- Non-empty instructions with no unresolved template values.

For Codex and Claude, every portable command must have a matching environment adapter:

```text
Codex:  .agents/skills/agora-<command-id>/SKILL.md
Claude: .claude/commands/agora.<command-id>.md
Generic: .agora/commands/<command-id>.md
```

Codex and Claude adapter content must match the portable command exactly. A missing or malformed
adapter is an error. An adapter without a portable command is reported as a warning. This keeps
environment packaging separate without allowing the governing instructions to diverge silently.

`agora doctor` performs the faster availability check and reports the installed adapter count, for
example `codex: 8/8 commands available`.

## Verify the complete repository

Install development dependencies, then run the Python verification entry point:

```bash
uv sync --extra dev
uv run python scripts/verify_all.py
```

The runner continues through independent failures and returns status `1` if any step fails. It runs:

1. Python formatting verification.
2. Python linting.
3. The complete test suite.
4. Local Markdown link validation.
5. Every `samples/*/run.py` scenario.
6. Source and wheel distribution builds.

The sample matrix covers human and AI actors, recursive swarms, delegation, handoffs, interruptions,
signed remote registry distribution, custom methods, tools, operational queries, and Codex, Claude,
and generic adapters. It prepares contexts but does not launch an LLM or make provider API requests.

Use quiet output in CI:

```bash
uv run python scripts/verify_all.py --quiet
```

For a faster local loop, omit scenarios or packaging:

```bash
uv run python scripts/verify_all.py --skip-samples --skip-build
```

These flags narrow developer verification only. They do not alter Agora project policy or persisted
state.

## CI example

```bash
uv sync --extra dev
uv run python scripts/verify_all.py --quiet
uv run agora --project ./fixture-project validate
```

The first command proves the framework distribution and bundled scenarios. The second proves the
specific persisted workspace used by the team. Neither command repairs invalid Markdown; changes
remain explicit and reviewable through the filesystem and Git.

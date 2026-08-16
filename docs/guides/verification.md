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
5. The bundled human, AI-agent, and swarm role conformance self-test.
6. Every `samples/*/run.py` scenario.
7. Source and wheel distribution builds.

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

## GitHub Actions CI

The repository includes `.github/workflows/ci.yml`. Pull requests and pushes to `main` run:

1. The test suite against Python 3.11, 3.12, and 3.13 using the locked dependency graph.
2. Complete verification on Python 3.13, including formatting, lint, documentation, every sample,
   and both distributions.

The workflow grants only `contents: read`, disables persisted checkout credentials, cancels stale
runs for the same branch, and pins third-party actions to immutable commit SHAs. A manual
`workflow_dispatch` trigger is also available. Local development continues to use the same Python
entry point as CI, so the hosted workflow does not define a second verification contract.

## Tagged releases

Pushing a `vMAJOR.MINOR.PATCH` tag starts `.github/workflows/release.yml`. The workflow runs complete
verification, requires the tag to match `project.version` in `pyproject.toml`, rebuilds the wheel and
source distribution, and generates `SHA256SUMS` through `scripts/prepare_release.py`. GitHub CLI then
creates a release from the existing tag with generated notes and uploads those three artifacts.

The release job receives `contents: write` only because GitHub release creation requires it. It
uploads the already verified distributions as a short-lived workflow artifact. A separate `pypi`
environment job receives only `id-token: write`, downloads those exact files, and publishes through
PyPI Trusted Publishing. Checkout credentials remain disabled and every action is pinned to an
immutable SHA. The PyPI project must authorize this repository, workflow, and `pypi` environment as
its trusted publisher before the first tag is released.

After publication, a separate unprivileged Python 3.11 job installs the exact tagged version from
the public PyPI index. It allows bounded retries for index propagation, then runs `agora quickstart`
and `agora validate` in a temporary project and confirms the installed distribution version. This
consumer smoke test has no publishing identity or repository write permission.

## Other CI systems

```bash
uv sync --extra dev
uv run python scripts/verify_all.py --quiet
uv run agora --project ./fixture-project validate
```

The first command proves the framework distribution and bundled scenarios. The second proves the
specific persisted workspace used by the team. Neither command repairs invalid Markdown; changes
remain explicit and reviewable through the filesystem and Git.

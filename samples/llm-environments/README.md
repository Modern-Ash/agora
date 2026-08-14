# LLM environment sample

This sample materializes three independent Agora projects:

| Project | Integration | Provider label | Model label | Adapter output |
| --- | --- | --- | --- | --- |
| Codex | `codex` | `openai` | `configured-by-codex` | `.agents/skills/agora-*` |
| Claude | `claude` | `anthropic` | `configured-by-claude` | `.claude/commands/agora.*.md` |
| Local | `generic` | `local-runtime` | `team-approved-coder` | `.agora/commands/*.md` |

Run it from the repository root:

```bash
uv run python samples/llm-environments/run.py
```

The labels are configuration examples, not hard-coded provider integrations. The sample does not
make network requests, invoke models, read credentials, or require provider SDKs. It leaves each
temporary project on disk so its Markdown configuration and installed adapter can be inspected.

See [the LLM environments guide](../../docs/guides/llm-environments.md) for responsibilities,
security guidance, and example agent prompts.

After materialization, actors may inherit these project defaults or override integration, provider,
and model. `agora start` resolves those values into a durable session before an external runtime is
optionally launched.

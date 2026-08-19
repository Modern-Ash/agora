# GitLab Issues CLI adapter sample

This sample installs Agora's reviewed `gitlab-issues` adapter, prepares bounded native issue search
and close commands, and rejects a dynamic `delete` subcommand before any Tool Run is written. It
also proves that issue creation is absent because native `glab issue create` cannot represent the
neutral required `type` input exactly.

Run it without credentials or an installed provider CLI:

```bash
uv run python samples/gitlab-issues-cli/run.py
```

The sample prepares commands but does not launch them. Live execution requires GitLab CLI 1.109.0
or newer and an externally authenticated profile or environment. Add `--launch` only after
`agora tool adapter list --check` reports compatible adapter runtimes.

Use a full issue URL to target a project other than the repository selected by `glab`. The adapter
implements `search`, `view`, `comment`, and `transition`; use a reviewed team wrapper when governed
issue creation with a stable work-item type is required.

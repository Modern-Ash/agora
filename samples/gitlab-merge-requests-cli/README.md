# GitLab Merge Requests CLI adapter sample

This sample installs Agora's reviewed `gitlab-merge-requests` adapter, prepares native merge-request
creation and head-pipeline inspection commands, and proves that unsupported merge authority is not
exposed as a weakened translation.

Run it without credentials or an installed provider CLI:

```bash
uv run python samples/gitlab-merge-requests-cli/run.py
```

The sample prepares commands but does not launch them. Live execution requires GitLab CLI 1.109.0
or newer and an externally authenticated profile or environment. Add `--launch` only after
`agora tool adapter list --check` reports compatible adapter runtimes.

The adapter implements `view`, `create`, `comment`, and `checks`. It deliberately omits list,
approval, request-changes, and merge operations where native `glab` commands cannot preserve every
required neutral input or need conditional command translation. Use a reviewed team wrapper for
those operations.

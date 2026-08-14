# GitHub Issues CLI adapter sample

This sample installs the reviewed GitHub Issues adapter and prepares native search and transition
commands through the developer's existing `gh` profile. It does not contact GitHub.

The Product Owner can close or reopen an issue through `issue.transition`. An `input-values` rule
rejects every other dynamic issue subcommand before Agora creates a Tool Run.

Run it from the repository root:

```bash
uv run python samples/github-issues-cli/run.py
```

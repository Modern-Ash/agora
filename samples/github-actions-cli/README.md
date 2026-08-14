# GitHub Actions CLI adapter sample

This sample discovers and installs Agora's reviewed GitHub Actions adapter. The adapter calls the
developer's existing `gh` executable directly and relies on its normal repository selection and
authentication.

The sample prepares list and trigger commands without contacting GitHub, so it runs even when `gh`
is not installed. It also proves that installing the adapter does not grant the Developer the
separate `ci.cancel` capability.

Run it from the repository root:

```bash
uv run python samples/github-actions-cli/run.py
```

Add `--launch` to an equivalent `agora tool invoke` command only after reviewing the generated
`RUN.md` and confirming `gh auth status` in the execution environment.

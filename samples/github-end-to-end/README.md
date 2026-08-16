# Governed GitHub delivery sample

This sample prepares a complete GitHub delivery path without contacting GitHub:

```text
Issue -> branch -> Pull Request -> checks -> approval -> merge -> close Issue -> release
```

It also prepares repository-governance, redacted security, and Projects snapshots. Every command is
stored as a normal Agora Tool Run under `.agora/tool-runs`.

```bash
uv run python samples/github-end-to-end/run.py
```

The sample proves merge is rejected before the project explicitly grants `review.merge`. It then
amends the local Product Owner role with `review.merge` and `release.publish`, refreshes
`PACKS.lock.md`, and prepares the remaining commands. No bundled role receives either capability.

For live use, replace `example/agora`, item numbers, tag, and artifact path with reviewed values.
Launch reads with `agora tool sync`; prepare writes first with `agora tool invoke`, inspect `RUN.md`,
and use signed `agora tool launch` when actor authentication is required.

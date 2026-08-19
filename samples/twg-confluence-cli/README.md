# Atlassian TWG Confluence CLI adapter sample

This sample installs Agora's reviewed `twg-confluence` adapter and prepares provider-native page
view and draft-update commands. It also proves that an update without Confluence's opaque snapshot
token is rejected and that the unsupported search translation is absent.

Run it without credentials or an installed provider CLI:

```bash
uv run python samples/twg-confluence-cli/run.py
```

The sample prepares Tool Runs but does not launch them. Live execution requires Atlassian Teamwork
Graph CLI 1.2.5 or newer, an externally authenticated profile, and appropriate Confluence OAuth
permissions. Add `--launch` to the equivalent `agora tool invoke` command only after
`agora tool adapter list --check` reports compatible adapter runtimes.

The adapter accepts HTML for page create and update operations. Obtain `snapshot-token` from a full
`view` result immediately before updating. Publishing and archival remain distinct opt-in
capabilities; no bundled role receives either by default.

# Governed knowledge-base sample

This sample replaces the bundled `docsctl` executable with a deterministic Python provider. A Scrum
Master searches documentation and a Developer creates a draft. The project then grants
`docs.publish`, requires Product Owner approval, proves publication is rejected without approval,
and publishes after the approval is recorded. Archival remains unauthorized.

Every launched command and result is persisted under `.agora/tool-runs`; credentials remain outside
Agora and remote document state never replaces local lifecycle state.

Run it from the repository root:

```bash
uv run python samples/knowledge-base/run.py
```

The same interface can be implemented by a reviewed wrapper over Confluence, Notion, or an internal
documentation platform. See the
[knowledge-base integration guide](../../docs/guides/knowledge-base-integrations.md).

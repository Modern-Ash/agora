# Governed work-management sample

This sample replaces the bundled `workctl` executable with a deterministic Python provider, then
uses the unchanged `work-management` Tool Pack contract to search, create, and transition external
work items. Every launched command and result is persisted under `.agora/tool-runs`.

The Scrum Master receives read access, the Product Owner receives write and transition access, and
the Developer receives read access. The sample proves that a Developer transition is rejected
before a tool-run record is created.

Run it from the repository root:

```bash
uv run python samples/work-management/run.py
```

The same stable operation interface can be implemented by a reviewed wrapper over Jira, Linear, or
an internal work-management service. See the
[work-management integration guide](../../docs/guides/work-management-integrations.md).

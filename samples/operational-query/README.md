# Operational query sample

This sample creates a small Scrum workspace, prepares one session, queries its operational summary
and events, and runs a complete integrity validation without maintaining a separate database.

Run it from the repository root:

```bash
uv run python samples/operational-query/run.py
```

The project remains in the system temporary directory so the reported Markdown paths can be
inspected directly.

See [Operations and validation](../../docs/guides/operations-and-validation.md) for the complete CLI
reference and CI behavior.

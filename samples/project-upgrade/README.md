# Project upgrade sample

This sample creates a Codex project, simulates its `0.1.0` protocol state, removes the standards,
governed commit operation, command, and adapter introduced in `0.2.0`, and adds a local constitution
amendment. It previews and applies the migration, proves that the amendment remains unchanged, and
validates the resulting workspace.

Run it from the repository root:

```bash
uv run python samples/project-upgrade/run.py
```

The project remains in the system temporary directory so its `.agora/upgrades` manifest and backup
tree can be inspected directly.

See [Project upgrades](../../docs/guides/project-upgrades.md) for the operational procedure and
recovery rules.

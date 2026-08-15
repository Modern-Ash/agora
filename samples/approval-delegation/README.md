# Approval Delegation sample

This sample delegates one Scrum Product Owner approval to an unassigned but role-compatible human,
consumes it once, and separately revokes another unused delegation. It leaves both decisions as
inspectable Markdown without transferring the Product Owner role.

Run it from the repository root:

```bash
uv run python samples/approval-delegation/run.py
```

See [Approval Delegation](../../docs/guides/approval-delegation.md) for CLI, signed-action, and
Method Pack customization details.


# Environment permissions sample

This sample creates a project-defined `production` policy and prepares a cloud plan only after the
linked work has Product Owner approval and successful evidence. The provider target remains a Tool
Pack input while the stable governance environment is recorded separately on the Tool Run.

Run it from the repository root:

```bash
uv run python samples/environment-permissions/run.py
```

Inspect the generated `.agora/environments/production.md` and
`.agora/tool-runs/production-plan/RUN.md` paths printed by the script. No cloud command is launched.

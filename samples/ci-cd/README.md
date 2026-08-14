# Governed CI/CD sample

This sample replaces the bundled `cictl` executable with a deterministic Python provider. A Scrum
Developer lists and triggers verification runs, but cannot cancel them. The project then grants
`deployment.create`, adds a Product Owner approval requirement to the operation, proves deployment
is rejected without approval, and executes it after approval is recorded.

Every launched command and result is persisted under `.agora/tool-runs`; the Method Pack role and
Tool Pack operation remain the authority boundary.

Run it from the repository root:

```bash
uv run python samples/ci-cd/run.py
```

The same stable operation interface can be implemented by a reviewed wrapper over GitHub Actions,
GitLab CI/CD, Jenkins, or an internal delivery platform. See the
[CI/CD integration guide](../../docs/guides/ci-cd-integrations.md).

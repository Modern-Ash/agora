# CLI runtime compatibility sample

This sample discovers every bundled CLI adapter and explicitly runs its local version probe. It
does not initialize a project, read credentials, authenticate, or contact a provider.

Run it from the repository root:

```bash
uv run python samples/cli-runtime-compatibility/run.py
```

Each line distinguishes a compatible runtime from a missing, old, or unverified one. Results depend
on the executables currently on `PATH`; missing tools are expected and do not make the sample fail.

Use the equivalent CLI commands in normal work:

```bash
agora tool adapter list --check
agora tool adapter list --compatible
```

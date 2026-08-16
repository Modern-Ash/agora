# Operational loop sample

This sample proves that a provider-neutral external runner can read `AGORA_CONTEXT`, mutate governed
work while its session is running, preserve the session result, prepare a GitHub Pull Request command
without contacting GitHub, stop at the human inbox, and complete the lifecycle.

Run it from the repository checkout:

```bash
uv run python samples/operational-loop/run.py
```

`agent_runner.py` stands in for an installed Codex, Claude, local-model, CI, or internal runner CLI.
It uses the same exported environment contract and invokes Agora through its Python API. Production
runners can invoke the equivalent `agora` commands and need no provider SDK in the kernel.
The session `RESULT.md` also demonstrates the same bounded output contract used by native Codex,
Claude, and generic runners.

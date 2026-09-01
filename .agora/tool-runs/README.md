# Tool runs

Each directory contains a durable invocation and, when launched, the captured result of a Tool Pack
operation. Tool runs store credential references only; raw credentials belong to the environment.

`RUN.md` records the assigned actor, swarm, optional work and environment, capability, risk, durable
inputs, structured command, execution bounds, status, and optional signed authorization. A launched
run adds `RESULT.md` with bounded standard output and error, terminal status, exit code, and declared
result kind.

Use the CLI to inspect records without parsing Markdown manually:

```bash
agora tool runs
agora tool runs --status failed
agora tool result --run <tool-run-id>
```

A prepared run returns `result: null`. For a completed or failed run, Agora verifies that the result
belongs to the same run and matches its terminal status, exit code, and result kind before returning
the captured output. Provider output can contain sensitive data even when bounded; adapters must
redact it before it becomes durable.

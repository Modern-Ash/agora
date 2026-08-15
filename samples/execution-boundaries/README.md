# Tool execution boundaries sample

This sample installs a Python-backed Tool Pack with a one-second timeout and a 512-byte captured
output limit. One operation completes, one is terminated after exceeding the timeout, and one fails
after producing too much output. Every outcome remains available as a bounded `RUN.md`, `RESULT.md`,
and event history.

Run it from the repository root:

```bash
uv run python samples/execution-boundaries/run.py
```

These portable process limits are not an operating-system sandbox. Use a container, restricted
runner, or equivalent isolation layer when a tool also needs filesystem, network, syscall, resource,
or descendant-process isolation.

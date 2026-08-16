# Distributed coordination sample

This sample configures an external lease CLI for one stable project resource. Agora acquires the
lease after its local operating-system lock, creates an actor, and releases both locks. The sample
provider persists temporary state only to demonstrate the `acquire`, `renew`, and `release` command
contract; production teams must use a reviewed service adapter with atomic leases and fencing.

Run it from the repository root:

```bash
uv run python samples/distributed-coordination/run.py
```

The adapter receives structured arguments without a shell. Its credentials, if any, must come from
its own environment, workload identity, or credential store rather than Agora configuration.

# Delegated work sample

This sample creates a parent Scrum swarm and a linked specialist swarm, signs work creation,
proposal, governance interruption, acceptance, criteria, evidence, and collection externally,
completes the work under the child's own lifecycle, and collects the result into the parent work
item. The signed proposal also assigns provider-neutral `effort` and `tokens` budgets that the
accepted child work inherits and promotes the required child result as a typed parent artifact
reference during collection. The specialist also records externally measured `effort` and `tokens`
usage against that inherited budget before completion.

Run it from the repository root:

```bash
uv run python samples/delegated-work/run.py
```

The project is left in the system temporary directory. Inspect `.agora/delegations`, both swarm
work directories, the child `usage` ledger, and the parent `artifacts.md` and `evidence.md` files to
follow the complete protocol.

See [Delegated work](../../docs/guides/delegated-work.md) for the lifecycle and CLI reference and
[Delegation budgets](../../docs/guides/delegation-budgets.md) for propagation rules.
Artifact reference semantics are described in
[Delegated artifact promotion](../../docs/guides/delegated-artifacts.md).

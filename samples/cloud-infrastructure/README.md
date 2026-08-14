# Governed cloud-infrastructure sample

This sample replaces the bundled `cloudctl` executable with a deterministic Python provider. A
Scrum Master inspects a resource and a Developer produces a non-mutating plan. The project then
grants `cloud.deploy`, requires Product Owner approval, rejects apply without approval, and applies
the reviewed plan after approval. Destruction remains unauthorized.

Every launched command and result is persisted under `.agora/tool-runs`; credentials remain outside
Agora and remote infrastructure never replaces local lifecycle state.

Run it from the repository root:

```bash
uv run python samples/cloud-infrastructure/run.py
```

The same interface can be implemented by a reviewed wrapper over AWS, Azure, Google Cloud,
Terraform, OpenTofu, Pulumi, or an internal platform. See the
[cloud integration guide](../../docs/guides/cloud-integrations.md).

# AWS and Google Cloud inventory adapter sample

This sample installs the reviewed AWS and Google Cloud inventory adapters. Both implement only
`list-resources` and `inspect-resource` from the provider-neutral cloud contract.

The sample prepares native commands without contacting either cloud. It proves that a partial
adapter cannot expose `plan`, `apply-plan`, or `destroy-resource` under its declared contract.

Run it from the repository root:

```bash
uv run python samples/cloud-inventory-cli/run.py
```

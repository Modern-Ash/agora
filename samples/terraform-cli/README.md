# Terraform CLI adapter sample

This sample installs Agora's reviewed Terraform adapter and prepares native `terraform state list`
and saved-plan commands. It uses the configured Terraform backend and provider environment without
copying credentials into Agora.

The sample does not contact a backend or change infrastructure. It also proves that installing the
adapter does not grant the separate `cloud.deploy` capability.

Run it from the repository root:

```bash
uv run python samples/terraform-cli/run.py
```

For a real invocation, treat the saved plan as a sensitive external artifact, record its digest in
the governed work, require the appropriate review, and add `--launch` only in the approved workload
environment.

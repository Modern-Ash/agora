# Signed remote registry sample

This sample creates a versioned registry archive, signs its canonical release payload with a runtime
Ed25519 key, publishes a local `INDEX.md`, and installs it through the same distribution path used by
HTTPS registries. It then installs the discovered Method Pack and validates the project.

Run it from the repository root:

```bash
uv run python samples/remote-registry/run.py
```

The sample writes only to a temporary directory. It does not call an LLM or a network service, and it
does not persist the generated private key in the repository.

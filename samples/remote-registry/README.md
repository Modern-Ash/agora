# Signed remote registry sample

This sample creates a versioned registry archive, signs its canonical release payload with two
runtime Ed25519 keys, imports both public keys into a project trust store, and requires a 2-of-2
threshold while installing through the same distribution path used by HTTPS registries. It then
installs the discovered Method Pack, previews a newer threshold-signed release, applies it with
durable update history, and validates the project.

Run it from the repository root:

```bash
uv run python samples/remote-registry/run.py
```

The sample writes only to a temporary directory. It does not call an LLM or a network service, and it
does not persist the generated private key in the repository.

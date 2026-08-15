# Organization trust sample

This sample simulates an external organization publisher, pins only its Ed25519 public root in an
Agora project, previews a signed trust bundle, and applies it. The resulting registry release key
and exact bundle history are ordinary Markdown files.

Run it from the repository root:

```bash
uv run python samples/organization-trust/run.py
```

The sample creates private keys only in its temporary publisher area. A real organization must keep
the root private key in its external signing system and distribute the PEM fingerprint through an
independent trusted channel.

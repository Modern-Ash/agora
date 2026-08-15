# Actor authentication sample

This sample registers an AI actor with an Ed25519 public key and requires signed authorization
before that actor may apply a lifecycle mutation or launch a prepared Tool Run. The temporary private key is used only by the
sample's external signer and is never stored in `.agora`.

The flow signs and applies a work transition and Product Owner approval, then signs and launches both
a repository Tool Run and an agent session. Lifecycle authorization binds the requested mutation to a digest of the current
work policy files. Session authorization
also binds the exact runtime command and SHA-256 of its materialized `CONTEXT.md`. The resulting
records retain public verification evidence so `agora validate` can recheck them later. The sample
then rotates the actor to a second public key and revokes that key while proving the completed work
remains valid.

Run it from the repository root:

```bash
uv run python samples/actor-authentication/run.py
```

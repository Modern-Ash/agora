# Actor authentication sample

This sample registers actors with Ed25519 public keys and requires signed authorization before they
may apply covered lifecycle mutations or launch a prepared Tool Run. Temporary private keys are used
only by the sample's external signers and are never stored in `.agora`.

The flow signs and applies work creation, block/resume interruptions, a transition, Product Owner
approval, and a developer handoff, then signs and launches both a repository Tool Run and an agent
session. Lifecycle authorization binds the requested mutation to a digest of the current work
policy files. Session authorization
also binds the exact runtime command and SHA-256 of its materialized `CONTEXT.md`. The resulting
records retain public verification evidence so `agora validate` can recheck them later. The sample
then rotates the actor to a second public key and revokes that key while proving the completed work
remains valid.

Run it from the repository root:

```bash
uv run python samples/actor-authentication/run.py
```

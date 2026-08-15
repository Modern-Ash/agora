# Actor authentication

Agora actor ids provide attribution, but an id alone does not prove control of an identity. A human,
AI agent, service, automation, or swarm actor may therefore declare an Ed25519 public key and require
signed authorization before applying supported lifecycle actions or launching governed Tool Runs.

Private keys remain in the actor's existing keychain, hardware device, secret manager, agent host,
or workload identity boundary. Agora reads only a public PEM file during registration.

## Register an authenticated actor

Generate or obtain an Ed25519 key outside Agora. This OpenSSL example is suitable for local testing:

```bash
openssl genpkey -algorithm Ed25519 -out developer-private.pem
openssl pkey -in developer-private.pem -pubout -out developer-public.pem
```

Register the public identity:

```bash
agora actor add \
  --id developer \
  --name "Authenticated Developer" \
  --kind ai-agent \
  --capability implementation \
  --public-key developer-public.pem \
  --require-authentication
```

The actor Markdown stores the Ed25519 public bytes and their SHA-256 fingerprint. It never stores a
private key, passphrase, token, or provider credential. Existing actors without authentication
metadata remain valid.

## Prepare and sign a Tool Run

Authenticated launches use an explicit two-phase flow:

```bash
agora tool invoke \
  --id signed-status \
  --tool repository \
  --operation status \
  --actor developer \
  --swarm delivery

agora tool authorization \
  --run signed-status \
  --output /tmp/signed-status.authorization.json

openssl pkeyutl \
  -sign \
  -inkey developer-private.pem \
  -rawin \
  -in /tmp/signed-status.authorization.json \
  -out /tmp/signed-status.sig

agora tool launch \
  --run signed-status \
  --signature /tmp/signed-status.sig
```

The canonical authorization binds the run id, actor, swarm, optional work, tool, operation,
capability, risk, inputs, exact command, execution timeout, output limit, and creation timestamp. A
signature from another run is rejected, as is a command or execution policy changed after
preparation.

## Durable verification

After successful verification, `RUN.md` records:

- `authentication-verified`
- the signing public key and its fingerprint
- the canonical payload SHA-256
- the Ed25519 signature

These values are public verification evidence, not credentials. `agora validate` reconstructs the
canonical payload and verifies its digest, key fingerprint, and signature. Historical runs remain
verifiable even if the actor later rotates its active key.

## Sign a lifecycle transition

An authenticated actor must prepare `work.transition` as a durable action, export its canonical
authorization, sign it externally, and apply it:

```bash
agora work transition-prepare --id begin-work \
  --swarm delivery --work payment-retry --to implementing --by developer
agora action authorization --action begin-work --output /tmp/begin-work.json
openssl pkeyutl -sign -inkey developer-private.pem -rawin \
  -in /tmp/begin-work.json -out /tmp/begin-work.sig
agora action apply --action begin-work --signature /tmp/begin-work.sig
```

The signature binds the transition to a digest of the current work, artifacts, evidence, and
approvals. Agora also rechecks Method Pack permissions, WIP, gates, and current key state immediately
before mutation. See [Signed lifecycle actions](signed-lifecycle-actions.md) for the complete model.

## Sign an agent session

An authenticated actor uses the same two-phase boundary before launching Codex, Claude, or another
runner:

```bash
agora start \
  --id signed-agent-session \
  --actor developer \
  --swarm delivery \
  --runner "company-agent run"

agora session authorization \
  --session signed-agent-session \
  --output /tmp/signed-agent-session.authorization.json

openssl pkeyutl \
  -sign \
  -inkey developer-private.pem \
  -rawin \
  -in /tmp/signed-agent-session.authorization.json \
  -out /tmp/signed-agent-session.sig

agora session launch \
  --session signed-agent-session \
  --signature /tmp/signed-agent-session.sig
```

The authorization binds actor, swarm, work, roles, integration, provider, model, exact launch
command, creation time, and the SHA-256 digest of the materialized `CONTEXT.md`. Runtime changes,
assignment changes, context edits, signature replay, and revoked keys are rejected before the runner
starts. Completed `SESSION.md` files retain the same public signature evidence as Tool Runs.

## Rotate a key

Rotation accepts a new public PEM file and a durable reason:

```bash
agora actor key rotate \
  --actor developer \
  --public-key developer-next-public.pem \
  --reason "Scheduled quarterly rotation"
```

Agora marks the prior key `rotated`, links it to the replacement fingerprint, updates the actor's
active public identity, and appends an event. A prepared run signed by the prior key is rejected after
rotation; the current key may authorize it by signing its unchanged canonical payload. Reusing any
historical fingerprint is rejected.

## Revoke and recover

Revoke a key when its signer or private material may no longer be trusted:

```bash
agora actor key revoke \
  --actor developer \
  --reason "Credential exposure under investigation"
```

Revocation blocks new Tool Run preparation, authorization export, and launch for that actor. It does
not invalidate completed runs because each completed run contains its own public verification
evidence. Recovery is an explicit rotation to a new public key; the revoked record then links to its
replacement without changing its revoked status.

Inspect the complete public history with:

```bash
agora actor key list --actor developer
```

Records live under `.agora/actors/<actor>/keys/<fingerprint>.md` for project actors or the equivalent
path under `~/.agora`. `agora validate` checks ownership, fingerprints, active-key cardinality,
current actor state, and replacement references.

## Current boundary

This authentication policy protects work transitions, approvals, Tool Run launch, and agent-session
launch. It does not yet sign handoffs, session preparation, interruption, or delegation changes, and it does
not authenticate the operating-system account running Agora. External CLIs still perform their own
provider authentication. Rotation and revocation are local administrative mutations recorded in
Markdown and Git; they are not themselves authorized by a second actor or remote identity authority.

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

The signature binds the transition to a digest of the current work and its companion policy files,
including artifacts, evidence, approvals, clarifications, and checklists. Agora also rechecks Method
Pack permissions, WIP, gates, and current key state immediately before mutation. See
[Signed lifecycle actions](signed-lifecycle-actions.md) for the complete model.

## Sign an agent session

An authenticated actor first authorizes materializing the durable session context:

```bash
agora session prepare \
  --id prepare-signed-agent-session \
  --session signed-agent-session \
  --actor developer \
  --swarm delivery \
  --runner "company-agent run"

agora action authorization \
  --action prepare-signed-agent-session \
  --output /tmp/prepare-signed-agent-session.json

openssl pkeyutl -sign -inkey developer-private.pem -rawin \
  -in /tmp/prepare-signed-agent-session.json \
  -out /tmp/prepare-signed-agent-session.sig

agora action apply \
  --action prepare-signed-agent-session \
  --signature /tmp/prepare-signed-agent-session.sig
```

The preparation action precondition is the SHA-256 of the prospective `CONTEXT.md`. Agora renders it
again immediately before apply, so changes to assignments, Method Pack files, work, delegations, or
project protocol invalidate the intent before any session files are written.

The actor then separately authorizes executing the materialized session:

```bash

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

The launch authorization binds actor, swarm, work, roles, integration, provider, model, exact launch
command, creation time, and the SHA-256 digest of the materialized `CONTEXT.md`. Runtime changes,
assignment changes, context edits, signature replay, and revoked keys are rejected before the runner
starts. `SESSION.md` links to its applied preparation action and retains the launch signature evidence.

## Rotate a key

An authenticated actor with a healthy active key prepares rotation through an assigned role that
grants `actor.key.rotate`:

```bash
agora actor key rotate-prepare \
  --id rotate-developer-key \
  --actor developer \
  --swarm delivery \
  --public-key developer-next-public.pem \
  --reason "Scheduled quarterly rotation"
agora action authorization --action rotate-developer-key \
  --output /tmp/rotate-developer-key.json
# Sign the exact exported bytes with the current private key.
agora action apply --action rotate-developer-key \
  --signature /tmp/rotate-developer-key.sig
```

The action contains the canonical replacement public key, its fingerprint, the current fingerprint,
and reason. Its precondition covers the actor, swarm, and complete public key history. Agora verifies
the action with the current key before marking that key `rotated`, linking it to the replacement,
updating the actor identity, and appending an event. A prepared run signed by the prior key is
rejected after rotation; the new key may authorize it by signing its unchanged canonical payload.
Reusing any historical fingerprint is rejected.

## Revoke and recover

Revocation and recovery are authorized by a different authenticated actor. Both actors must be
assigned to the same swarm, the authorizer's role must grant the corresponding action, and their
public-key fingerprints must differ. The bundled Scrum Product Owner and Scrum Master roles, plus
the Kanban Service Request Manager and Flow Manager roles, carry this authority.

Prepare revocation when a signer or its private material may no longer be trusted:

```bash
agora actor key revoke-prepare --id revoke-developer-key \
  --actor developer --swarm delivery --by security-governor \
  --reason "Credential exposure under investigation"
agora action authorization --action revoke-developer-key \
  --output /tmp/revoke-developer-key.json
# The governance actor signs these bytes with its own private key.
agora action apply --action revoke-developer-key \
  --signature /tmp/revoke-developer-key.sig
```

Revocation blocks new Tool Run preparation, lifecycle authorization export, and session launch for
that actor. It does not invalidate completed operations because each contains its own public
verification evidence. Recover through the same independent authorizer:

```bash
agora actor key recover-prepare --id recover-developer-key \
  --actor developer --swarm delivery --by security-governor \
  --public-key developer-recovery-public.pem \
  --reason "Replace the compromised credential"
agora action authorization --action recover-developer-key \
  --output /tmp/recover-developer-key.json
agora action apply --action recover-developer-key \
  --signature /tmp/recover-developer-key.sig
```

The revoked record keeps its revocation reason and links to the recovery fingerprint. The recovery
reason remains in the signed `ACTION.md`. A revoked key never signs its successor, and an authorizer
cannot target itself or install its own key as the recovered identity.

Inspect the complete public history with:

```bash
agora actor key list --actor developer
```

Records live under `.agora/actors/<actor>/keys/<fingerprint>.md` for project actors or the equivalent
path under `~/.agora`. `agora validate` checks ownership, fingerprints, active-key cardinality,
current actor state, and replacement references.

## Current boundary

This authentication policy protects planned rotation, independent revocation and recovery, actor
runtime updates, vacant-role assignment, work creation and decomposition, criteria, artifacts,
evidence, transitions, interruptions, approvals, handoffs, the complete delegation lifecycle, Tool
Run launch, and agent-session preparation and launch. It does not authenticate the operating-system account running Agora.
External CLIs and any higher-order organizational identity authority remain independent.

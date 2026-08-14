# Registry trust stores

Agora persists trusted Ed25519 registry release keys as Markdown. A trust store removes the need to
pass `--public-key` during every signed installation and makes key approval, rotation, revocation, and
review part of the same filesystem and Git model as the rest of Agora.

Private signing keys never belong in Agora. The trust store contains only public material.

## Scopes and precedence

Trust keys live in:

```text
~/.agora/trust/keys/<key-id>.md
<project>/.agora/trust/keys/<key-id>.md
```

Project trust precedes user trust when the same key id exists in both scopes. A key is eligible only
when both its `id` and authorized `registry` match the signed release. Project-scoped keys and
revocations should be reviewed and committed with `.agora`.

## Add a trusted key

Import an Ed25519 public key in PEM format for personal reuse:

```bash
agora trust add \
  --id team-release-2026 \
  --registry team-catalog \
  --public-key ./team-release-2026.pem \
  --scope user
```

Trust it only for the current project:

```bash
agora trust add \
  --id team-release-2026 \
  --registry team-catalog \
  --public-key ./team-release-2026.pem \
  --scope project
git add .agora/trust/keys/team-release-2026.md
```

Agora stores the raw 32-byte public key as base64 and a SHA-256 fingerprint. Reusing an existing key
id in the same scope is rejected. Rotation must create a new id so history cannot be overwritten.

## Install with the trust store

When `INDEX.md` declares `key-id: "team-release-2026"`, no key path is needed:

```bash
agora registry install \
  --source https://catalog.example.com/agora/INDEX.md \
  --version 2.0.0 \
  --require-signature \
  --scope project
```

Agora selects the effective key by scope, verifies that it authorizes the index registry id, and
then verifies the release signature. `--public-key` remains available for explicit bootstrap or
one-off verification, but it does not bypass a matching revocation in the trust store.

## Inspect trust

```bash
agora trust list
agora trust list --registry team-catalog
```

The output includes scope, fingerprint, status, creation time, and any revocation metadata. Public
keys are not credentials, but fingerprints are the concise values to compare through an independent
trusted channel.

## Rotate and revoke

Add the replacement before revoking the old identity:

```bash
agora trust add \
  --id team-release-2027 \
  --registry team-catalog \
  --public-key ./team-release-2027.pem \
  --scope project

agora trust revoke \
  --id team-release-2026 \
  --scope project \
  --reason "Scheduled annual rotation" \
  --replaced-by team-release-2027
```

The replacement must already be active in the same scope and authorize the same registry. Revocation
is irreversible through the CLI. A revoked key retains its public bytes and fingerprint for audit,
and any release still naming that key id is rejected.

For a compromise, revoke the key immediately without waiting for a replacement:

```bash
agora trust revoke \
  --id team-release-2026 \
  --scope project \
  --reason "Signing key compromise"
```

## Markdown contract

Each key is independently reviewable:

```markdown
---
schema: "agora/registry-trust-key/v1"
id: "team-release-2026"
registry: "team-catalog"
algorithm: "ed25519"
public-key: "<base64 raw public key>"
fingerprint: "<64 lowercase hex characters>"
status: "revoked"
created-at: "2026-01-10T12:00:00Z"
revoked-at: "2027-01-10T12:00:00Z"
revoked-reason: "Scheduled annual rotation"
replaced-by: "team-release-2027"
---

# Registry trust key team-release-2026
```

`agora validate` recomputes the fingerprint, verifies key length and algorithm, checks file identity,
and confirms that every declared replacement is active for the same registry.

## Current boundary

Trust stores are local or project-versioned. Agora does not yet fetch organization trust policy,
certificate chains, revocation feeds, transparency logs, or threshold signatures. Human review and
Git remain the distribution mechanism for project trust changes.

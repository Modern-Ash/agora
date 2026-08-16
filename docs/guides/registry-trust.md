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

## Organization trust feeds

An organization can publish a signed sequence of registry key and revocation declarations. Pin
the organization's Ed25519 root public key through an independently trusted channel:

```bash
agora trust organization add \
  --id example-org \
  --public-key ./example-org-trust-root.pem \
  --scope project
```

The private root key remains in the organization's signing system. Agora persists only the public
root, its fingerprint, the applied sequence, and the checksum of the last bundle under:

```text
<project>/.agora/trust/organizations/example-org/ROOT.md
<project>/.agora/trust/organizations/example-org/history/00000000000000000001.md
```

Preview the next bundle before changing trust:

```bash
agora trust organization sync \
  --id example-org \
  --source https://trust.example.com/agora/BUNDLE.md \
  --scope project
```

Apply the reviewed result explicitly:

```bash
agora trust organization sync \
  --id example-org \
  --source https://trust.example.com/agora/BUNDLE.md \
  --scope project \
  --apply
```

After the first applied sync, the source is remembered and `--source` may be omitted. HTTPS is
required for remote feeds; HTTP requires the explicit development-only
`--allow-insecure-http` switch. Downloads are time- and size-bounded.

Each bundle uses `agora/organization-trust-bundle/v1` and contains an organization id, a strictly
consecutive sequence, generation time, previous-bundle SHA-256, key declarations, and an
Ed25519 signature over the canonical statement. Applying a bundle transactionally materializes its
keys in the ordinary scoped trust store and archives the exact signed document. Omitted local keys
remain unchanged, so removal from a feed cannot erase trust history. Agora rejects:

- invalid signatures, skipped sequences, rollbacks, and broken previous-checksum links;
- duplicate key ids, changed public material under an existing id, or rewritten revocation facts;
- any attempt to reactivate a key already persisted as revoked;
- replacements that are missing, inactive, or authorized for another registry.

The runnable [organization trust sample](../../samples/organization-trust/README.md) shows the exact
bundle fields and canonical signature payload. Publishing and private-key custody deliberately stay
outside the Agora CLI; teams can use their existing signing service, HSM workflow, or reviewed
release automation.

`agora validate` re-verifies every project bundle signature and its complete checksum chain against
the pinned root. The history is therefore a locally auditable transparency trail, while Git can
provide review and replication for project scope.

## Rotate an organization root

The external organization publisher creates an
`agora/organization-trust-root-rotation/v1` Markdown declaration. It binds the outgoing and incoming
public keys to the exact applied `bundle-sequence`, `bundle-sha256`, and previous rotation checksum.
Both roots sign the same canonical
`agora/organization-trust-root-rotation-signature/v1` payload, proving authorization by the current
root and possession of the replacement private key.

Preview the declaration without changing trust:

```bash
agora trust organization rotate \
  --id example-org \
  --source ./ROOT-ROTATION.md \
  --scope project
```

Apply it only after review:

```bash
agora trust organization rotate \
  --id example-org \
  --source ./ROOT-ROTATION.md \
  --scope project \
  --apply
```

Agora rejects invalid signatures, skipped rotations, a changed current root, a stale feed position,
or a broken previous-rotation checksum. Application transactionally replaces only the active public
root and archives the exact signed declaration under:

```text
<project>/.agora/trust/organizations/example-org/rotations/00000000000000000001.md
```

The bundle sequence continues across rotation. Validation reconstructs every root epoch from the
dual-signed chain, verifies old bundles with their historical root, verifies later bundles with the
replacement, requires the first transition to match the immutable initial public anchor retained in
`ROOT.md`, and requires the final transition to equal its active root. Private keys and signing
remain outside Agora.

## Current boundary

Agora supports one active Ed25519 organization root, dual-signed sequential root rotation, and
sequential snapshot feeds. Registry releases support distinct-key signature thresholds, but
organization feed bundles do not yet use a threshold root policy. Third-party transparency-log
inclusion proofs and automatic background synchronization are not implemented. Feed and rotation
application remain explicit reviewed operations.

# Remote registry releases

Agora can install a versioned registry release from a remote Markdown index. The index selects an
immutable archive; Agora verifies the archive before it copies any pack into user or project state.
The installed snapshot remains the source used during work, so a remote service is never required to
operate an initialized project.

## Release layout

Publish these files through HTTPS:

```text
releases/
  INDEX.md
  team-catalog-1.0.0.tar.gz
```

The archive contains one registry root with a versioned `REGISTRY.md`:

```markdown
---
schema: "agora/registry/v1"
id: "team-catalog"
name: "Team Catalog"
version: "1.0.0"
---

# Team Catalog
```

The index uses JSON-compatible YAML values in Markdown front matter:

```markdown
---
schema: "agora/registry-index/v1"
id: "team-catalog"
name: "Team Catalog"
releases: [{"version":"1.0.0","archive":"team-catalog-1.0.0.tar.gz","sha256":"<64 lowercase hex characters>","signature":"<base64 Ed25519 signature>","key-id":"team-release"}]
---

# Team Catalog releases
```

Release versions use `MAJOR.MINOR.PATCH`. Relative archive URLs resolve against the final index URL.
Without `--version`, Agora installs the highest numeric version in the index.

## Canonical signature payload

The Ed25519 signature covers these exact UTF-8 bytes, including the final newline:

```text
agora/registry-release/v1
registry=team-catalog
version=1.0.0
archive=team-catalog-1.0.0.tar.gz
sha256=<archive sha256>
```

The archive value is the literal value declared in `INDEX.md`, before relative URL resolution. Store
the private signing key outside the registry and publishing repository. Distribute the public key
through an independently trusted channel.

## Threshold signatures

A release may carry a `signatures` array instead of the legacy `signature` and `key-id` pair:

```json
{"version":"1.0.0","archive":"team-catalog-1.0.0.tar.gz","sha256":"<sha256>","signatures":[{"key-id":"release-a","signature":"<base64>"},{"key-id":"release-b","signature":"<base64>"}]}
```

Every signer signs the same canonical payload above. Signer ids must be unique, and distinct ids
backed by the same public-key fingerprint count only once. Require a quorum of independently trusted
and active release keys with:

```bash
agora registry install \
  --source https://catalog.example.com/agora/INDEX.md \
  --signature-threshold 2 \
  --scope project
```

An explicit PEM can satisfy at most one signature. Threshold verification therefore uses persisted
user or project trust keys for values above one. A signature made by a persistently revoked key
blocks the release even when other signatures would otherwise satisfy the threshold.

## Transparency inclusion proofs

Agora can independently verify that the canonical release payload is included in an RFC 6962-style
Merkle tree and that the resulting checkpoint was signed by a trusted transparency log key. First
pin the log's Ed25519 checkpoint key, then verify a proof supplied as a local Markdown artifact:

```bash
agora trust transparency add \
  --id public-log-2026 \
  --log public-log \
  --public-key ./public-log-2026.pem \
  --scope project
agora registry verify-transparency \
  --source ./PROOF.md \
  --scope project \
  --record
```

`--record` persists the canonical proof at
`.agora/transparency/<log>/<registry>/<version>/PROOF.md`. `agora validate` repeats both checkpoint
signature and inclusion verification. A later key revocation blocks new proof acceptance but does
not erase the cryptographic audit of evidence recorded before rotation or revocation.

The proof uses schema `agora/transparency-inclusion-proof/v1` and declares `log`, `key-id`,
`registry`, `version`, `archive`, `sha256`, `tree-size`, `leaf-index`, `root-sha256`,
`inclusion-path`, `checkpoint-signature`, and `integrated-at`. Each inclusion-path value is a
lowercase SHA-256 hex digest. The leaf is:

```text
SHA256(0x00 || <canonical registry release signature payload>)
```

Each internal node is `SHA256(0x01 || left || right)`. The Ed25519 checkpoint signature covers these
exact UTF-8 bytes, including the final newline:

```text
agora/transparency-checkpoint/v1
log=public-log
tree-size=<tree size>
root-sha256=<Merkle root>
integrated-at=<integration timestamp>
```

Proof files are bounded, contain an exact versioned attribute set, and are verified only against the
separate transparency authority namespace. They cannot satisfy a registry release signature.

After recording the proof, make it a mutation precondition with:

```bash
agora registry install \
  --source https://catalog.example.com/agora/INDEX.md \
  --version 1.0.0 \
  --require-transparency \
  --scope project
```

The gate selects the recorded proof by the exact registry and semantic version, then verifies its
literal release archive, SHA-256, active log authority, Merkle path, and checkpoint again. Agora
persists `transparency-required`, the portable proof reference, and the literal release archive in
`SOURCE.md`. Once enabled, every later update inherits the requirement and records it in `UPDATE.md`;
the policy cannot be lowered. Record the target release proof before previewing or applying that
update. Agora never discovers or downloads a proof implicitly.

## Install a release

Checksum verification is always mandatory:

```bash
agora registry install \
  --source https://catalog.example.com/agora/INDEX.md \
  --version 1.0.0 \
  --scope user
```

Require a trusted signature for production use:

```bash
agora registry install \
  --source https://catalog.example.com/agora/INDEX.md \
  --version 1.0.0 \
  --public-key ./team-release.pem \
  --require-signature \
  --scope project
```

For repeated use, import the public key into a user or project trust store and omit `--public-key`
from subsequent installations. See [Registry trust stores](registry-trust.md). A matching revoked key
cannot be bypassed by supplying the PEM explicitly.

Plain HTTP is rejected. `--allow-insecure-http` exists only for an explicitly trusted local
development server. Redirects are checked again, so HTTPS cannot silently downgrade to HTTP.
An HTTP or HTTPS index may reference only HTTP or HTTPS archives; it cannot cause Agora to read a
local `file://` source.

## Persisted provenance

Agora generates `SOURCE.md` inside a remotely installed registry. It records:

- the final index and archive locations;
- the selected version and archive SHA-256;
- the verified Ed25519 signer ids and required signature threshold;
- the forward-only transparency requirement and exact recorded proof reference, when enabled;
- the installation timestamp.

`agora registry list` exposes the version, source, checksum, and signature status. `agora validate`
validates `SOURCE.md`, its relationship to `REGISTRY.md`, and every contained pack. A project-scoped
registry and its provenance can be committed with the rest of `.agora`.

## Archive safety

Agora accepts `.zip`, `.tar.gz`, and `.tgz`. Before installation it enforces download, file-count,
path-length, individual-size, and expanded-size limits. Absolute paths, parent traversal, duplicate
paths, links, devices, pipes, and other non-file archive entries are rejected. Extraction happens in
a new temporary directory, followed by normal registry and pack validation.

The checksum authenticates bytes only against the index. Signatures authenticate the release
against public keys selected by the user or organization. An unsigned release may be installed when
signature enforcement is not enabled, and its provenance explicitly reports that it was not
verified.

When signature verification is requested, Agora verifies the signed index payload before following
the archive URL. It then verifies the downloaded archive checksum before extraction.

## Replacement behavior

`--force` stages and validates the complete new snapshot, moves the previous installation to a local
backup, replaces it, and removes the backup after success. A failed replacement restores the prior
directory. Removed files do not leak from an older release into a newer verified snapshot.

## Current boundary

Agora manages local and project trust keys, rotations, revocations, and signed sequential
organization trust feeds. Organization roots rotate through dual-signed, feed-bound declarations.
Agora enforces distinct-key signature thresholds for registry releases and explicitly verifies and
records third-party transparency-log inclusion proofs. A recorded proof may be required for
`registry install` and every later update. Proof discovery remains external and explicit. The index
is a distribution convenience; installed filesystem state remains the governed operational record.

Use [Registry updates](registry-updates.md) to check and apply later releases without replacing packs
that were already installed from the catalog.

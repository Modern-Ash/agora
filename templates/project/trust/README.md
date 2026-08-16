# Registry trust

Project-scoped Ed25519 public keys are stored as Markdown under `keys/`. Agora uses them to verify
signed registry releases. Commit reviewed keys and revocations with the project; never store private
signing keys here.

Pinned organization roots and their signed, sequential revocation-feed history live under
`organizations/`. Preview feeds with `agora trust organization sync` and apply them only after
review with `--apply`. Agora will not accept a skipped sequence or reactivate a revoked key.

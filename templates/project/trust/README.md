# Registry trust

Project-scoped Ed25519 public keys are stored as Markdown under `keys/`. Agora uses them to verify
signed registry releases. Commit reviewed keys and revocations with the project; never store private
signing keys here.

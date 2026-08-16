# Project registries

Installed registry snapshots live in subdirectories containing `REGISTRY.md`, `methods/`, and/or
`tools/`. Use `agora registry install` rather than copying a partial catalog by hand.

Use `agora registry audit --scope project` for an authenticated aggregate update check. Add
`--record` to persist a reviewable notification under `../notifications/registry-updates/`; audits
never apply registry or installed-pack updates.

For production catalogs, `--signature-threshold N` requires N distinct active trusted public-key
fingerprints. Agora persists that minimum and will not allow later updates to lower it.

After updating a registry snapshot, use `agora pack audit --scope project` to inspect every managed
pack. Its optional report lives under `../notifications/pack-updates/` and never authorizes
application.

Apply only an explicitly reviewed and unchanged report with `agora pack apply-audit --id <audit>`.
Agora binds the transaction to the audit checksum, current pack trees, and dependency plans.

Organization trust roots rotate only through a declaration signed by both roots and bound to the
current feed position. Preview it with `agora trust organization rotate` before passing `--apply`.

Transparency checkpoint keys belong under `../trust/transparency/`, separate from registry release
keys. Manage them with `agora trust transparency` so rotation and revocation remain auditable.
Verify a local proof with `agora registry verify-transparency --source <PROOF.md> --record`; Agora
stores verified project evidence under `../transparency/<log>/<registry>/<version>/PROOF.md`.
Add `--require-transparency` to a remote registry installation to persist a forward-only proof
requirement. Record each target release proof before checking or applying a later update.

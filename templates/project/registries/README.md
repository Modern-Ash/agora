# Project registries

Installed registry snapshots live in subdirectories containing `REGISTRY.md`, `methods/`, and/or
`tools/`. Use `agora registry install` rather than copying a partial catalog by hand.

Use `agora registry audit --scope project` for an authenticated aggregate update check. Add
`--record` to persist a reviewable notification under `../notifications/registry-updates/`; audits
never apply registry or installed-pack updates.

After updating a registry snapshot, use `agora pack audit --scope project` to inspect every managed
pack. Its optional report lives under `../notifications/pack-updates/` and never authorizes
application.

Apply only an explicitly reviewed and unchanged report with `agora pack apply-audit --id <audit>`.
Agora binds the transaction to the audit checksum, current pack trees, and dependency plans.

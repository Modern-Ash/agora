# Project registries

Installed registry snapshots live in subdirectories containing `REGISTRY.md`, `methods/`, and/or
`tools/`. Use `agora registry install` rather than copying a partial catalog by hand.

Use `agora registry audit --scope project` for an authenticated aggregate update check. Add
`--record` to persist a reviewable notification under `../notifications/registry-updates/`; audits
never apply registry or installed-pack updates.

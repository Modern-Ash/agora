# Swarm directory numbering and patch work

Implemented 2026-08-24.

## Delivered behavior

- New swarms get a directory prefixed with a sequential number (`001-`, `002-`, ...) under
  `.agora/swarms/`, so the directory sorts in creation order at a glance — e.g.
  `.agora/swarms/001-delivery/`. The logical swarm id stays unprefixed; `--swarm delivery` keeps
  working unchanged. Swarm directories created before this change are left unnumbered and continue
  to resolve normally.
- `create_patch_work` (workspace/Python API) links a lightweight fix work item to a parent whose
  swarm has already reached its Method Pack terminal status, without creating a new swarm, role
  assignment, or branch. It reuses the completed swarm's roles, assignments, and branch as-is.

## Notes

- `create_patch_work` does not require the parent work item to be mutable — only readable — since
  reusing a terminal parent is the point of the operation. The acting role needs `work.patch` in its
  Method Pack's `allowed-actions`; the bundled `developer` role for `spec-driven` grants it.
- Creating a patch work item self-heals the swarm's derived status back to `running`, since status
  is always derived from current work item states rather than stored directly.
- There is no `agora work patch` CLI subcommand yet — `create_patch_work` is API-only as of this
  writing, unlike `agora work decompose`.

## Where to read more

- [Reference: documentation and artifact locations](../reference/artifact-locations.md) — numbered
  swarm directories.
- [Guide: work decomposition](../guides/work-decomposition.md) — "Patch work on a completed swarm"
  section.

# Project upgrades

Agora versions the project protocol in `.agora/project.md`. Installing a newer CLI never changes an
existing workspace: migration is a separate, explicit, reviewable operation.

## Preview an upgrade

Run the command from the project or target the project from any supported environment:

```bash
agora upgrade
agora --project /path/to/project upgrade
```

The captured JSON result reports `from_version`, `to_version`, every proposed `create` or `update`, and
customization warnings. Preview mode does not create directories, backups, events, or manifests.
Commit or stash unrelated work before applying so the resulting diff remains easy to review.

## Apply the plan

```bash
agora upgrade --apply
agora validate
git diff -- .agora .agents .claude
```

Agora applies only an ordered migration supported by the installed CLI. The legacy `0.1.0` path to
the current protocol:

- updates the project protocol version;
- materializes operational status fields on legacy work records;
- materializes interruption fields on legacy delegation records;
- installs the Conventional Commits standards contract when it is absent;
- adds the governed commit operation to the bundled Git repository pack when it is absent;
- installs the portable `status` command when it is absent; and
- installs its selected Codex or Claude adapter when it is absent.

The `0.2.0` to `0.3.0` migration updates the protocol version while preserving installed pack
composition, Method Pack roles, and portable commands. It reports the new operational-loop and
usage-accounting capabilities for explicit role-policy adoption, plus code-review for explicit pack
installation. Install the reviewed neutral pack separately:

```bash
agora pack install --kind tool --id code-review --scope project
```

Then amend project roles deliberately or install a newer reviewed Method Pack. An upgrade never
grants new external authority silently.

Existing files at standard, operation, command, or adapter destinations are preserved. Project
policy, constitution, Method Packs, customized Tool Pack files, actors, sessions, and work history
are never refreshed from distribution templates. Agora does not silently grant newly available role
permissions to an existing Method Pack.

Use a stable id when automation needs a predictable audit path:

```bash
agora upgrade --apply --id upgrade-release-2026
```

The id must be a lowercase Agora slug and must not already exist.

## Audit records and backups

An applied migration creates:

```text
.agora/upgrades/<upgrade-id>/
  UPGRADE.md
  backup/
    .agora/project.md
    ... every other file updated in place
```

`UPGRADE.md` records the source and target versions, application time, change descriptions, changed
files, created files, and backup root. `agora validate` checks the manifest, forward version edge,
relative paths, and the presence of backups for every updated file.

If any write fails during application, Agora restores updated files from those backups, deletes only
files created by that attempt, and removes the incomplete upgrade directory. It returns a nonzero
exit status with a rollback error.

## Manual recovery

After a successfully applied migration, prefer Git to revert the complete reviewed change. When Git
is unavailable, use the manifest to distinguish updated and newly created files, restore updated
files from `backup/`, and remove only paths listed in `created-files`. Keep the upgrade record until
the recovery itself has been reviewed.

Never use `agora init --force` as recovery. Initialization refreshes a much broader template set and
can replace project customization.

## Compatibility failures

Agora refuses an invalid version, a project created by a newer CLI, and any older version without a
registered ordered migration. Upgrade the CLI when the project is newer. For an unsupported older
project, install an intermediate Agora release that provides the missing migration edge, apply it,
then continue forward one supported edge at a time.

Running `agora upgrade --apply` on a current project is a no-op. It does not create a redundant
upgrade record.

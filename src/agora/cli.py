import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, TextIO

from agora.model import (
    ACTOR_KINDS,
    INTEGRATIONS,
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddEvidenceInput,
    AddRegistryTrustKeyInput,
    ApplyLifecycleActionInput,
    AssignActorInput,
    ChangeDelegationStatusInput,
    ChangeWorkStatusInput,
    ConfigureInput,
    CreateDelegationInput,
    CreateSwarmInput,
    CreateWorkInput,
    DecomposeWorkInput,
    DelegateApprovalInput,
    DelegationActorInput,
    HandoffActorInput,
    InitInput,
    InstallCatalogPackInput,
    InstallMethodInput,
    InstallRegistryInput,
    InstallToolAdapterInput,
    InstallToolInput,
    InvokeToolInput,
    LaunchSessionInput,
    LaunchToolRunInput,
    PrepareActorAssignmentInput,
    PrepareActorKeyRecoveryInput,
    PrepareActorKeyRevocationInput,
    PrepareActorKeyRotationInput,
    PrepareActorRuntimeInput,
    PrepareApprovalDelegationInput,
    PrepareApprovalInput,
    PrepareArtifactInput,
    PrepareCreateDelegationInput,
    PrepareCreateWorkInput,
    PrepareCriterionInput,
    PrepareDecomposeWorkInput,
    PrepareDelegationActionInput,
    PrepareEvidenceInput,
    PrepareGateWaiverInput,
    PrepareLifecycleAuthorizationInput,
    PrepareSessionAuthorizationInput,
    PrepareSessionInput,
    PrepareToolAuthorizationInput,
    PrepareWorkTransitionInput,
    RefreshPackLockInput,
    RemovePackInput,
    RevokeActorKeyInput,
    RevokeApprovalDelegationInput,
    RevokeRegistryTrustKeyInput,
    RotateActorKeyInput,
    SetActorRuntimeInput,
    StartSessionInput,
    TransitionWorkInput,
    UpdateCatalogPackInput,
    UpdateRegistryInput,
    UpgradeInput,
    ValidationReport,
    WaiveGateInput,
    WorkActorInput,
)
from agora.workspace import AgoraWorkspace


def main(
    argv: list[str] | None = None,
    *,
    cwd: Path | str | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    output = stdout or sys.stdout
    error_output = stderr or sys.stderr
    project, arguments = _extract_project(arguments)
    parser = _build_parser()
    try:
        namespace = parser.parse_args(arguments)
        workspace = AgoraWorkspace(cwd=project or cwd)
        result = _dispatch(workspace, namespace)
        if result is not None:
            _print_json(output, result)
        if isinstance(result, ValidationReport) and not result.ok:
            return 1
        return 0
    except (FileExistsError, FileNotFoundError, PermissionError, RuntimeError, ValueError) as error:
        print(str(error), file=error_output)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agora",
        description="Customize governed work cycles for human and agentic teams",
        epilog=(
            "Global option: --project PATH targets an initialized project from any environment. "
            "Precedence: Agora defaults < ~/.agora < project .agora < swarm."
        ),
    )
    parser.add_argument("--project", help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", required=True)

    configure = commands.add_parser("configure", help="Persist user-level defaults")
    configure.add_argument("--integration", choices=INTEGRATIONS, default="generic")
    configure.add_argument("--provider", default="configured-by-integration")
    configure.add_argument("--model", default="configured-by-integration")
    configure.add_argument(
        "--default-method",
        default="scrum",
        metavar="METHOD_ID",
        help="Installed Method Pack to use by default (default: scrum)",
    )
    configure.add_argument("--max-delegation-depth", type=int, default=3)
    configure.add_argument("--force", action="store_true")

    initialize = commands.add_parser("init", help="Initialize an Agora project")
    initialize.add_argument("--path")
    initialize.add_argument("--integration", choices=INTEGRATIONS)
    initialize.add_argument("--provider")
    initialize.add_argument("--model")
    initialize.add_argument("--default-method", metavar="METHOD_ID")
    initialize.add_argument("--max-delegation-depth", type=int)
    initialize.add_argument("--force", action="store_true")

    commands.add_parser("doctor", help="Check environment prerequisites")
    commands.add_parser("status", help="Summarize operational project state")
    commands.add_parser("validate", help="Validate every Agora record and reference")
    lock = commands.add_parser("lock", help="Inspect local writer coordination").add_subparsers(
        dest="lock_command", required=True
    )
    lock_status = lock.add_parser("status", help="Show a project or user write lock")
    lock_status.add_argument("--scope", choices=("project", "user"), default="project")
    upgrade = commands.add_parser("upgrade", help="Plan or apply a safe project migration")
    upgrade.add_argument("--apply", action="store_true", help="Apply the displayed migration")
    upgrade.add_argument("--id", help="Stable id for the durable upgrade record")

    registry = commands.add_parser(
        "registry", help="Manage local and remote Markdown pack registries"
    ).add_subparsers(dest="registry_command", required=True)
    registry_install = registry.add_parser("install", help="Install a registry snapshot")
    registry_install.add_argument("--source", required=True)
    registry_install.add_argument("--scope", choices=("user", "project"), default="user")
    registry_install.add_argument("--version", help="Remote release version (default: latest)")
    registry_install.add_argument("--public-key", help="Trusted Ed25519 public key in PEM format")
    registry_install.add_argument(
        "--require-signature",
        action="store_true",
        help="Reject a remote release unless its Ed25519 signature verifies",
    )
    registry_install.add_argument(
        "--allow-insecure-http",
        action="store_true",
        help="Permit HTTP for an explicitly trusted development registry",
    )
    registry_install.add_argument("--force", action="store_true")
    registry_update = registry.add_parser(
        "update", help="Check or apply a verified registry release update"
    )
    registry_update.add_argument("--id", required=True)
    registry_update.add_argument("--scope", choices=("user", "project"))
    registry_update.add_argument("--version", help="Target release version (default: latest)")
    registry_update.add_argument("--public-key", help="Explicit trusted Ed25519 public key")
    registry_update.add_argument("--require-signature", action="store_true")
    registry_update.add_argument("--allow-insecure-http", action="store_true")
    registry_update.add_argument("--apply", action="store_true")
    registry.add_parser("list", help="List bundled and installed registries")

    trust = commands.add_parser(
        "trust", help="Manage trusted registry release keys"
    ).add_subparsers(dest="trust_command", required=True)
    trust_add = trust.add_parser("add", help="Trust an Ed25519 registry release key")
    trust_add.add_argument("--id", required=True)
    trust_add.add_argument("--registry", required=True)
    trust_add.add_argument("--public-key", required=True)
    trust_add.add_argument("--scope", choices=("user", "project"), default="user")
    trust_list = trust.add_parser("list", help="List active and revoked registry keys")
    trust_list.add_argument("--registry")
    trust_revoke = trust.add_parser("revoke", help="Revoke a trusted registry release key")
    trust_revoke.add_argument("--id", required=True)
    trust_revoke.add_argument("--scope", choices=("user", "project"), default="user")
    trust_revoke.add_argument("--reason", required=True)
    trust_revoke.add_argument("--replaced-by")

    pack = commands.add_parser("pack", help="Manage installed and catalog packs").add_subparsers(
        dest="pack_command", required=True
    )
    pack_search = pack.add_parser("search", help="Search registered Method and Tool Packs")
    pack_search.add_argument("--kind", choices=("method", "tool"))
    pack_search.add_argument("--query")
    pack_search.add_argument("--registry")
    pack_install = pack.add_parser("install", help="Install a pack selected from the catalog")
    pack_install.add_argument("--kind", choices=("method", "tool"), required=True)
    pack_install.add_argument("--id", required=True)
    pack_install.add_argument("--registry")
    pack_install.add_argument("--scope", choices=("user", "project"), default="project")
    pack_install.add_argument("--force", action="store_true")
    pack_update = pack.add_parser("update", help="Check or apply a catalog pack update")
    pack_update.add_argument("--kind", choices=("method", "tool"), required=True)
    pack_update.add_argument("--id", required=True)
    pack_update.add_argument("--registry")
    pack_update.add_argument("--scope", choices=("user", "project"))
    pack_update.add_argument("--apply", action="store_true")
    pack_update.add_argument("--force", action="store_true")
    pack_lock = pack.add_parser("lock", help="Refresh the installed pack composition lock")
    pack_lock.add_argument("--scope", choices=("user", "project"), default="project")
    pack_remove = pack.add_parser("remove", help="Preview or apply a safe pack removal")
    pack_remove.add_argument("--kind", choices=("method", "tool"), required=True)
    pack_remove.add_argument("--id", required=True)
    pack_remove.add_argument("--scope", choices=("user", "project"))
    pack_remove.add_argument(
        "--with-unused-dependencies",
        action="store_true",
        help="Also remove dependencies unused by the remaining pack composition",
    )
    pack_remove.add_argument("--apply", action="store_true")

    start = commands.add_parser("start", help="Prepare or launch a governed actor session")
    start.add_argument("--id")
    start.add_argument("--actor", required=True)
    start.add_argument("--swarm", required=True)
    start.add_argument("--work")
    start.add_argument("--runner", help="External command that executes the prepared session")
    start.add_argument("--launch", action="store_true")
    start.add_argument("--force", action="store_true")

    method = commands.add_parser("method", help="Manage lifecycle Method Packs").add_subparsers(
        dest="method_command", required=True
    )
    method_install = method.add_parser("install", help="Install a Method Pack from a directory")
    method_install.add_argument("--source", required=True)
    method_install.add_argument("--scope", choices=("user", "project"), default="project")
    method_install.add_argument("--force", action="store_true")
    method.add_parser("list", help="List installed project Method Packs")

    tool = commands.add_parser("tool", help="Manage governed external tools").add_subparsers(
        dest="tool_command", required=True
    )
    tool_install = tool.add_parser("install", help="Install a Tool Pack from a directory")
    tool_install.add_argument("--source", required=True)
    tool_install.add_argument("--scope", choices=("user", "project"), default="project")
    tool_install.add_argument("--force", action="store_true")

    tool_show = tool.add_parser("show", help="Show an installed project Tool Pack")
    tool_show.add_argument("--tool", required=True)

    tool.add_parser("list", help="List installed project Tool Packs")

    tool_adapter = tool.add_parser(
        "adapter", help="Discover and install reviewed ecosystem adapters"
    ).add_subparsers(dest="tool_adapter_command", required=True)
    adapter_list = tool_adapter.add_parser("list", help="List bundled Tool adapters")
    adapter_list.add_argument(
        "--available", action="store_true", help="Only show adapters whose CLI is on PATH"
    )
    adapter_list.add_argument(
        "--check", action="store_true", help="Probe CLI versions and report compatibility"
    )
    adapter_list.add_argument(
        "--compatible",
        action="store_true",
        help="Only show adapters with a compatible CLI version",
    )
    adapter_install = tool_adapter.add_parser("install", help="Install a bundled Tool adapter")
    adapter_install.add_argument("--id", required=True)
    adapter_install.add_argument("--scope", choices=("user", "project"), default="project")
    adapter_install.add_argument("--force", action="store_true")

    tool_runs = tool.add_parser("runs", help="List governed tool runs")
    tool_runs.add_argument("--status")

    tool_authorization = tool.add_parser(
        "authorization", help="Export the canonical payload for a prepared Tool Run"
    )
    tool_authorization.add_argument("--run", required=True)
    tool_authorization.add_argument("--output", required=True)
    tool_authorization.add_argument("--force", action="store_true")

    tool_launch = tool.add_parser("launch", help="Launch a prepared Tool Run")
    tool_launch.add_argument("--run", required=True)
    tool_launch.add_argument("--signature", help="Raw Ed25519 signature file")

    tool_invoke = tool.add_parser("invoke", help="Prepare or launch a governed tool operation")
    tool_invoke.add_argument("--id")
    tool_invoke.add_argument("--tool", required=True)
    tool_invoke.add_argument("--operation", required=True)
    tool_invoke.add_argument("--actor", required=True)
    tool_invoke.add_argument("--swarm", required=True)
    tool_invoke.add_argument("--work")
    tool_invoke.add_argument("--input", action="append", default=[])
    tool_invoke.add_argument("--launch", action="store_true")
    tool_invoke.add_argument("--force", action="store_true")

    delegation = commands.add_parser(
        "delegation", help="Manage parent-to-child swarm work"
    ).add_subparsers(dest="delegation_command", required=True)
    delegation_create = delegation.add_parser("create", help="Propose work to a linked child swarm")
    delegation_create.add_argument("--id")
    delegation_create.add_argument("--swarm", required=True)
    delegation_create.add_argument("--work", required=True)
    delegation_create.add_argument("--to-actor", required=True)
    delegation_create.add_argument("--child-work", required=True)
    delegation_create.add_argument("--title", required=True)
    delegation_create.add_argument("--by", required=True)
    delegation_create.add_argument("--description", default="")
    delegation_create.add_argument("--criterion", action="append", default=[])
    delegation_create.add_argument("--required-artifact", action="append", default=[])
    delegation_create.add_argument("--result-kind", default="delegated-result")
    delegation_create.add_argument(
        "--budget", action="append", default=[], help="Delegated budget dimension=limit"
    )
    delegation_create.add_argument(
        "--promote-artifact",
        action="append",
        default=[],
        help="Promote a child artifact as source-kind=parent-kind on collection",
    )

    delegation_create_prepare = delegation.add_parser(
        "create-prepare", help="Prepare a signed delegation proposal intent"
    )
    delegation_create_prepare.add_argument("--action-id", required=True)
    delegation_create_prepare.add_argument("--id", required=True)
    delegation_create_prepare.add_argument("--swarm", required=True)
    delegation_create_prepare.add_argument("--work", required=True)
    delegation_create_prepare.add_argument("--to-actor", required=True)
    delegation_create_prepare.add_argument("--child-work", required=True)
    delegation_create_prepare.add_argument("--title", required=True)
    delegation_create_prepare.add_argument("--by", required=True)
    delegation_create_prepare.add_argument("--description", default="")
    delegation_create_prepare.add_argument("--criterion", action="append", default=[])
    delegation_create_prepare.add_argument("--required-artifact", action="append", default=[])
    delegation_create_prepare.add_argument("--result-kind", default="delegated-result")
    delegation_create_prepare.add_argument(
        "--budget", action="append", default=[], help="Delegated budget dimension=limit"
    )
    delegation_create_prepare.add_argument(
        "--promote-artifact",
        action="append",
        default=[],
        help="Promote a child artifact as source-kind=parent-kind on collection",
    )

    delegation_accept = delegation.add_parser(
        "accept", help="Accept a proposal and create child work"
    )
    delegation_accept.add_argument("--delegation", required=True)
    delegation_accept.add_argument("--by", required=True)
    delegation_accept_prepare = delegation.add_parser(
        "accept-prepare", help="Prepare a signed delegation acceptance intent"
    )
    delegation_accept_prepare.add_argument("--id", required=True)
    delegation_accept_prepare.add_argument("--delegation", required=True)
    delegation_accept_prepare.add_argument("--by", required=True)

    delegation_collect = delegation.add_parser(
        "collect", help="Collect a completed child result into parent work"
    )
    delegation_collect.add_argument("--delegation", required=True)
    delegation_collect.add_argument("--by", required=True)
    delegation_collect_prepare = delegation.add_parser(
        "collect-prepare", help="Prepare a signed delegation collection intent"
    )
    delegation_collect_prepare.add_argument("--id", required=True)
    delegation_collect_prepare.add_argument("--delegation", required=True)
    delegation_collect_prepare.add_argument("--by", required=True)

    delegation_show = delegation.add_parser("show", help="Show a delegation")
    delegation_show.add_argument("--delegation", required=True)

    delegation_list = delegation.add_parser("list", help="List delegations")
    delegation_list.add_argument(
        "--status",
        choices=(
            "proposed",
            "accepted",
            "blocked",
            "collected",
            "rejected",
            "cancelled",
        ),
    )

    for command, help_text in (
        ("block", "Temporarily block a delegation"),
        ("resume", "Resume a blocked delegation"),
        ("reject", "Reject a proposed delegation as the child swarm"),
        ("cancel", "Cancel a delegation as the parent swarm"),
    ):
        change = delegation.add_parser(command, help=help_text)
        change.add_argument("--delegation", required=True)
        change.add_argument("--by", required=True)
        change.add_argument("--reason", required=True)
        change.add_argument("--id")
        prepared_change = delegation.add_parser(
            f"{command}-prepare", help=f"Prepare a durable delegation {command} intent"
        )
        prepared_change.add_argument("--delegation", required=True)
        prepared_change.add_argument("--by", required=True)
        prepared_change.add_argument("--reason", required=True)
        prepared_change.add_argument("--id", required=True)

    delegation_changes = delegation.add_parser(
        "status-changes", help="List a delegation's durable status history"
    )
    delegation_changes.add_argument("--delegation", required=True)

    actor = commands.add_parser("actor", help="Manage actors").add_subparsers(
        dest="actor_command", required=True
    )
    actor_add = actor.add_parser("add", help="Register an actor")
    actor_add.add_argument("--id", required=True)
    actor_add.add_argument("--name", required=True)
    actor_add.add_argument("--kind", choices=ACTOR_KINDS, required=True)
    actor_add.add_argument("--capability", action="append", default=[])
    actor_add.add_argument("--scope", choices=("user", "project"), default="project")
    actor_add.add_argument("--description")
    actor_add.add_argument("--integration", choices=INTEGRATIONS)
    actor_add.add_argument("--provider")
    actor_add.add_argument("--model")
    actor_add.add_argument("--public-key", help="Ed25519 public key in PEM format")
    actor_add.add_argument(
        "--require-authentication",
        action="store_true",
        help="Require signed authorization before this actor launches a Tool Run",
    )
    actor_add.add_argument(
        "--represented-swarm",
        help="Project swarm represented by an actor whose kind is swarm",
    )
    actor_add.add_argument("--force", action="store_true")

    actor_runtime = actor.add_parser("runtime", help="Set or clear an actor runtime override")
    actor_runtime.add_argument("--actor", required=True)
    actor_runtime.add_argument("--integration", choices=INTEGRATIONS)
    actor_runtime.add_argument("--provider")
    actor_runtime.add_argument("--model")
    actor_runtime.add_argument("--clear", action="store_true")

    actor_runtime_prepare = actor.add_parser(
        "runtime-prepare", help="Prepare a signed actor runtime change"
    )
    actor_runtime_prepare.add_argument("--id", required=True, help="Lifecycle Action id")
    actor_runtime_prepare.add_argument("--actor", required=True)
    actor_runtime_prepare.add_argument("--swarm", required=True)
    actor_runtime_prepare.add_argument("--integration", choices=INTEGRATIONS)
    actor_runtime_prepare.add_argument("--provider")
    actor_runtime_prepare.add_argument("--model")
    actor_runtime_prepare.add_argument("--clear", action="store_true")

    actor_key = actor.add_parser(
        "key", help="Rotate, revoke, or inspect actor authentication keys"
    ).add_subparsers(dest="actor_key_command", required=True)
    actor_key_rotate = actor_key.add_parser("rotate", help="Rotate an actor public key")
    actor_key_rotate.add_argument("--actor", required=True)
    actor_key_rotate.add_argument("--public-key", required=True)
    actor_key_rotate.add_argument("--reason", required=True)
    actor_key_rotate_prepare = actor_key.add_parser(
        "rotate-prepare", help="Prepare a signed actor public-key rotation"
    )
    actor_key_rotate_prepare.add_argument("--id", required=True, help="Lifecycle Action id")
    actor_key_rotate_prepare.add_argument("--actor", required=True)
    actor_key_rotate_prepare.add_argument("--swarm", required=True)
    actor_key_rotate_prepare.add_argument("--public-key", required=True)
    actor_key_rotate_prepare.add_argument("--reason", required=True)
    actor_key_revoke = actor_key.add_parser("revoke", help="Revoke an actor public key")
    actor_key_revoke.add_argument("--actor", required=True)
    actor_key_revoke.add_argument("--reason", required=True)
    actor_key_revoke_prepare = actor_key.add_parser(
        "revoke-prepare", help="Prepare governance-authorized actor key revocation"
    )
    actor_key_revoke_prepare.add_argument("--id", required=True, help="Lifecycle Action id")
    actor_key_revoke_prepare.add_argument("--actor", required=True, help="Target actor")
    actor_key_revoke_prepare.add_argument("--swarm", required=True)
    actor_key_revoke_prepare.add_argument("--by", required=True, help="Governance authorizer")
    actor_key_revoke_prepare.add_argument("--reason", required=True)
    actor_key_recover_prepare = actor_key.add_parser(
        "recover-prepare", help="Prepare governance-authorized actor key recovery"
    )
    actor_key_recover_prepare.add_argument("--id", required=True, help="Lifecycle Action id")
    actor_key_recover_prepare.add_argument("--actor", required=True, help="Target actor")
    actor_key_recover_prepare.add_argument("--swarm", required=True)
    actor_key_recover_prepare.add_argument("--by", required=True, help="Governance authorizer")
    actor_key_recover_prepare.add_argument("--public-key", required=True)
    actor_key_recover_prepare.add_argument("--reason", required=True)
    actor_key_list = actor_key.add_parser("list", help="List an actor's public key history")
    actor_key_list.add_argument("--actor", required=True)

    actor_list = actor.add_parser("list", help="List effective actors")
    actor_list.add_argument("--scope", choices=("all", "user", "project"), default="all")

    swarm = commands.add_parser("swarm", help="Manage swarms").add_subparsers(
        dest="swarm_command", required=True
    )
    swarm_create = swarm.add_parser("create", help="Create a governed swarm")
    swarm_create.add_argument("--id", required=True)
    swarm_create.add_argument("--objective", required=True)
    swarm_create.add_argument("--method", metavar="METHOD_ID")
    swarm_create.add_argument("--branch")
    swarm_create.add_argument("--no-branch", action="store_true")

    swarm_assign = swarm.add_parser("assign", help="Assign an actor to a role")
    swarm_assign.add_argument("--swarm", required=True)
    swarm_assign.add_argument("--role", required=True)
    swarm_assign.add_argument("--actor", required=True)

    swarm_assign_prepare = swarm.add_parser(
        "assign-prepare", help="Prepare a governance-authorized role assignment"
    )
    swarm_assign_prepare.add_argument("--id", required=True, help="Lifecycle Action id")
    swarm_assign_prepare.add_argument("--swarm", required=True)
    swarm_assign_prepare.add_argument("--role", required=True)
    swarm_assign_prepare.add_argument("--actor", required=True, help="Target actor")
    swarm_assign_prepare.add_argument("--by", required=True, help="Governance authorizer")

    swarm_handoff = swarm.add_parser("handoff", help="Transfer a role between compatible actors")
    swarm_handoff.add_argument("--id")
    swarm_handoff.add_argument("--swarm", required=True)
    swarm_handoff.add_argument("--role", required=True)
    swarm_handoff.add_argument("--from", dest="from_actor", required=True)
    swarm_handoff.add_argument("--to", dest="to_actor", required=True)
    swarm_handoff.add_argument("--by", required=True)
    swarm_handoff.add_argument("--reason", required=True)
    swarm_handoff.add_argument("--work")

    swarm_handoff_prepare = swarm.add_parser(
        "handoff-prepare", help="Prepare a durable role handoff intent"
    )
    swarm_handoff_prepare.add_argument("--id", required=True)
    swarm_handoff_prepare.add_argument("--swarm", required=True)
    swarm_handoff_prepare.add_argument("--role", required=True)
    swarm_handoff_prepare.add_argument("--from", dest="from_actor", required=True)
    swarm_handoff_prepare.add_argument("--to", dest="to_actor", required=True)
    swarm_handoff_prepare.add_argument("--by", required=True)
    swarm_handoff_prepare.add_argument("--reason", required=True)
    swarm_handoff_prepare.add_argument("--work")

    swarm_show = swarm.add_parser("show", help="Show a swarm")
    swarm_show.add_argument("--swarm", required=True)

    swarm_list = swarm.add_parser("list", help="List swarms")
    swarm_list.add_argument("--status")

    swarm_handoffs = swarm.add_parser("handoffs", help="List a swarm's handoffs")
    swarm_handoffs.add_argument("--swarm", required=True)

    work = commands.add_parser("work", help="Manage governed work").add_subparsers(
        dest="work_command", required=True
    )
    work_create = work.add_parser("create", help="Create a work item")
    work_create.add_argument("--swarm", required=True)
    work_create.add_argument("--id", required=True)
    work_create.add_argument("--title", required=True)
    work_create.add_argument("--by", required=True)
    work_create.add_argument("--description", default="")
    work_create.add_argument("--criterion", action="append", default=[])
    work_create.add_argument("--required-artifact", action="append", default=[])
    work_create_prepare = work.add_parser(
        "create-prepare", help="Prepare a signed work creation intent"
    )
    work_create_prepare.add_argument("--action-id", required=True)
    work_create_prepare.add_argument("--swarm", required=True)
    work_create_prepare.add_argument("--id", required=True)
    work_create_prepare.add_argument("--title", required=True)
    work_create_prepare.add_argument("--by", required=True)
    work_create_prepare.add_argument("--description", default="")
    work_create_prepare.add_argument("--criterion", action="append", default=[])
    work_create_prepare.add_argument("--required-artifact", action="append", default=[])

    work_decompose = work.add_parser(
        "decompose", help="Create a governed child work item under a parent"
    )
    work_decompose.add_argument("--swarm", required=True)
    work_decompose.add_argument("--work", required=True, help="Parent work id")
    work_decompose.add_argument("--child", required=True, help="Child work id")
    work_decompose.add_argument("--title", required=True)
    work_decompose.add_argument("--by", required=True)
    work_decompose.add_argument("--description", default="")
    work_decompose.add_argument("--criterion", action="append", default=[])
    work_decompose.add_argument("--required-artifact", action="append", default=[])
    work_decompose_prepare = work.add_parser(
        "decompose-prepare", help="Prepare a signed work decomposition intent"
    )
    work_decompose_prepare.add_argument("--action-id", required=True)
    work_decompose_prepare.add_argument("--swarm", required=True)
    work_decompose_prepare.add_argument("--work", required=True, help="Parent work id")
    work_decompose_prepare.add_argument("--child", required=True, help="Child work id")
    work_decompose_prepare.add_argument("--title", required=True)
    work_decompose_prepare.add_argument("--by", required=True)
    work_decompose_prepare.add_argument("--description", default="")
    work_decompose_prepare.add_argument("--criterion", action="append", default=[])
    work_decompose_prepare.add_argument("--required-artifact", action="append", default=[])

    criterion = work.add_parser("criterion-satisfy", help="Satisfy an acceptance criterion")
    criterion.add_argument("--swarm", required=True)
    criterion.add_argument("--work", required=True)
    criterion.add_argument("--criterion", required=True)
    criterion.add_argument("--by", required=True)
    criterion_prepare = work.add_parser(
        "criterion-satisfy-prepare", help="Prepare a signed criterion satisfaction intent"
    )
    criterion_prepare.add_argument("--id", required=True)
    criterion_prepare.add_argument("--swarm", required=True)
    criterion_prepare.add_argument("--work", required=True)
    criterion_prepare.add_argument("--criterion", required=True)
    criterion_prepare.add_argument("--by", required=True)

    transition = work.add_parser("transition", help="Move work across an allowed method edge")
    transition.add_argument("--swarm", required=True)
    transition.add_argument("--work", required=True)
    transition.add_argument("--to", required=True)
    transition.add_argument("--by", required=True)

    transition_prepare = work.add_parser(
        "transition-prepare", help="Prepare a durable work transition intent"
    )
    transition_prepare.add_argument("--id", required=True)
    transition_prepare.add_argument("--swarm", required=True)
    transition_prepare.add_argument("--work", required=True)
    transition_prepare.add_argument("--to", required=True)
    transition_prepare.add_argument("--by", required=True)

    work_show = work.add_parser("show", help="Show a work item")
    work_show.add_argument("--swarm", required=True)
    work_show.add_argument("--work", required=True)

    work_list = work.add_parser("list", help="List work items")
    work_list.add_argument("--swarm")
    work_list.add_argument("--state")
    work_list.add_argument("--operational-status", choices=("active", "blocked", "cancelled"))

    gate = commands.add_parser("gate", help="Manage explicit gate exceptions").add_subparsers(
        dest="gate_command", required=True
    )
    for command, help_text in (
        ("waive", "Waive exact outstanding gate obligations"),
        ("waive-prepare", "Prepare a signed Gate Waiver intent"),
    ):
        waiver = gate.add_parser(command, help=help_text)
        if command == "waive-prepare":
            waiver.add_argument("--action-id", required=True)
        waiver.add_argument("--id", required=True, help="Gate Waiver id")
        waiver.add_argument("--swarm", required=True)
        waiver.add_argument("--work", required=True)
        waiver.add_argument("--gate", required=True)
        waiver.add_argument("--by", required=True)
        waiver.add_argument("--criterion", action="append", default=[])
        waiver.add_argument("--artifact", action="append", default=[])
        waiver.add_argument("--successful-evidence", action="store_true")
        waiver.add_argument("--approval", action="append", default=[])
        waiver.add_argument("--reason", required=True)
        waiver.add_argument("--evidence", action="append", required=True)
    gate_list = gate.add_parser("list", help="List Gate Waivers for a work item")
    gate_list.add_argument("--swarm", required=True)
    gate_list.add_argument("--work", required=True)
    gate_list.add_argument("--gate")

    for command, help_text in (
        ("block", "Temporarily block a work item"),
        ("resume", "Resume a blocked work item"),
        ("cancel", "Cancel a work item"),
    ):
        change = work.add_parser(command, help=help_text)
        change.add_argument("--swarm", required=True)
        change.add_argument("--work", required=True)
        change.add_argument("--by", required=True)
        change.add_argument("--reason", required=True)
        change.add_argument("--id")
        prepared_change = work.add_parser(
            f"{command}-prepare", help=f"Prepare a durable {command} intent"
        )
        prepared_change.add_argument("--swarm", required=True)
        prepared_change.add_argument("--work", required=True)
        prepared_change.add_argument("--by", required=True)
        prepared_change.add_argument("--reason", required=True)
        prepared_change.add_argument("--id", required=True)

    work_changes = work.add_parser(
        "status-changes", help="List a work item's durable status history"
    )
    work_changes.add_argument("--swarm", required=True)
    work_changes.add_argument("--work", required=True)

    session = commands.add_parser("session", help="Inspect governed sessions").add_subparsers(
        dest="session_command", required=True
    )
    session_list = session.add_parser("list", help="List sessions")
    session_list.add_argument("--status")
    session_prepare = session.add_parser("prepare", help="Prepare a signed session context intent")
    session_prepare.add_argument("--id", required=True, help="Lifecycle Action id")
    session_prepare.add_argument("--session", required=True)
    session_prepare.add_argument("--actor", required=True)
    session_prepare.add_argument("--swarm", required=True)
    session_prepare.add_argument("--work")
    session_prepare.add_argument("--runner")
    session_authorization = session.add_parser(
        "authorization", help="Export the canonical payload for a prepared session"
    )
    session_authorization.add_argument("--session", required=True)
    session_authorization.add_argument("--output", required=True)
    session_authorization.add_argument("--force", action="store_true")
    session_launch = session.add_parser("launch", help="Launch a prepared session")
    session_launch.add_argument("--session", required=True)
    session_launch.add_argument("--signature", help="Raw Ed25519 signature file")

    action = commands.add_parser(
        "action", help="Authorize and apply durable lifecycle mutations"
    ).add_subparsers(dest="action_command", required=True)
    action_authorization = action.add_parser(
        "authorization", help="Export a prepared action's canonical payload"
    )
    action_authorization.add_argument("--action", required=True)
    action_authorization.add_argument("--output", required=True)
    action_authorization.add_argument("--force", action="store_true")
    action_apply = action.add_parser("apply", help="Apply a prepared lifecycle action")
    action_apply.add_argument("--action", required=True)
    action_apply.add_argument("--signature", help="Raw Ed25519 signature file")
    action_list = action.add_parser("list", help="List durable lifecycle actions")
    action_list.add_argument("--status", choices=("prepared", "applied"))

    event = commands.add_parser("event", help="Inspect durable events").add_subparsers(
        dest="event_command", required=True
    )
    event_list = event.add_parser("list", help="List recent events")
    event_list.add_argument("--swarm")
    event_list.add_argument("--work")
    event_list.add_argument("--type")
    event_list.add_argument("--limit", type=int, default=50)

    artifact = commands.add_parser("artifact", help="Manage artifacts").add_subparsers(
        dest="artifact_command", required=True
    )
    artifact_add = artifact.add_parser("add", help="Register an artifact")
    artifact_add.add_argument("--swarm", required=True)
    artifact_add.add_argument("--work", required=True)
    artifact_add.add_argument("--kind", required=True)
    artifact_add.add_argument("--uri", required=True)
    artifact_add.add_argument("--by", required=True)
    artifact_prepare = artifact.add_parser("prepare", help="Prepare a signed artifact intent")
    artifact_prepare.add_argument("--id", required=True)
    artifact_prepare.add_argument("--swarm", required=True)
    artifact_prepare.add_argument("--work", required=True)
    artifact_prepare.add_argument("--kind", required=True)
    artifact_prepare.add_argument("--uri", required=True)
    artifact_prepare.add_argument("--by", required=True)

    evidence = commands.add_parser("evidence", help="Manage evidence").add_subparsers(
        dest="evidence_command", required=True
    )
    evidence_add = evidence.add_parser("add", help="Register evidence")
    evidence_add.add_argument("--swarm", required=True)
    evidence_add.add_argument("--work", required=True)
    evidence_add.add_argument("--type", required=True)
    evidence_add.add_argument("--result", choices=("success", "failure"), required=True)
    evidence_add.add_argument("--by", required=True)
    evidence_add.add_argument("--artifact", action="append", default=[])
    evidence_prepare = evidence.add_parser("prepare", help="Prepare a signed evidence intent")
    evidence_prepare.add_argument("--id", required=True)
    evidence_prepare.add_argument("--swarm", required=True)
    evidence_prepare.add_argument("--work", required=True)
    evidence_prepare.add_argument("--type", required=True)
    evidence_prepare.add_argument("--result", choices=("success", "failure"), required=True)
    evidence_prepare.add_argument("--by", required=True)
    evidence_prepare.add_argument("--artifact", action="append", default=[])

    approval = commands.add_parser(
        "approval", help="Manage explicit work approvals"
    ).add_subparsers(dest="approval_command", required=True)
    approval_add = approval.add_parser("add", help="Approve work as an assigned role")
    approval_add.add_argument("--swarm", required=True)
    approval_add.add_argument("--work", required=True)
    approval_add.add_argument("--role", required=True)
    approval_add.add_argument("--by", required=True)
    approval_add.add_argument("--note", default="")
    approval_add.add_argument("--delegation")
    approval_prepare = approval.add_parser("prepare", help="Prepare a durable approval intent")
    approval_prepare.add_argument("--id", required=True)
    approval_prepare.add_argument("--swarm", required=True)
    approval_prepare.add_argument("--work", required=True)
    approval_prepare.add_argument("--role", required=True)
    approval_prepare.add_argument("--by", required=True)
    approval_prepare.add_argument("--note", default="")
    approval_prepare.add_argument("--delegation")
    for command, help_text in (
        ("delegate", "Delegate one work-scoped role approval"),
        ("delegate-prepare", "Prepare a signed approval delegation"),
    ):
        delegation = approval.add_parser(command, help=help_text)
        if command == "delegate-prepare":
            delegation.add_argument("--action-id", required=True)
        delegation.add_argument("--id", required=True, help="Approval Delegation id")
        delegation.add_argument("--swarm", required=True)
        delegation.add_argument("--work", required=True)
        delegation.add_argument("--role", required=True)
        delegation.add_argument("--to", required=True, help="Delegated approver")
        delegation.add_argument("--by", required=True, help="Current role holder")
        delegation.add_argument("--reason", required=True)
    for command, help_text in (
        ("delegation-revoke", "Revoke an unused Approval Delegation"),
        ("delegation-revoke-prepare", "Prepare a signed delegation revocation"),
    ):
        revocation = approval.add_parser(command, help=help_text)
        if command == "delegation-revoke-prepare":
            revocation.add_argument("--action-id", required=True)
        revocation.add_argument("--delegation", required=True)
        revocation.add_argument("--swarm", required=True)
        revocation.add_argument("--work", required=True)
        revocation.add_argument("--by", required=True)
        revocation.add_argument("--reason", required=True)
    delegation_list = approval.add_parser(
        "delegations", help="List work-scoped Approval Delegations"
    )
    delegation_list.add_argument("--swarm", required=True)
    delegation_list.add_argument("--work", required=True)
    delegation_list.add_argument("--status", choices=("active", "used", "revoked"))
    return parser


def _dispatch(workspace: AgoraWorkspace, args: argparse.Namespace) -> Any:
    if args.command == "configure":
        return workspace.configure(
            ConfigureInput(
                integration=args.integration,
                provider=args.provider,
                model=args.model,
                default_method=args.default_method,
                max_delegation_depth=args.max_delegation_depth,
                force=args.force,
            )
        )
    if args.command == "init":
        return workspace.initialize(
            InitInput(
                target=args.path,
                integration=args.integration,
                provider=args.provider,
                model=args.model,
                default_method=args.default_method,
                max_delegation_depth=args.max_delegation_depth,
                force=args.force,
            )
        )
    if args.command == "doctor":
        checks = workspace.doctor()
        return {"ok": all(item.ok or item.name == "git" for item in checks), "checks": checks}
    if args.command == "status":
        return workspace.status()
    if args.command == "validate":
        return workspace.validate()
    if args.command == "lock" and args.lock_command == "status":
        return workspace.lock_status(args.scope)
    if args.command == "upgrade":
        return workspace.upgrade(UpgradeInput(apply=args.apply, id=args.id))
    if args.command == "registry" and args.registry_command == "install":
        return workspace.install_registry(
            InstallRegistryInput(
                source=args.source,
                scope=args.scope,
                force=args.force,
                version=args.version,
                public_key=args.public_key,
                require_signature=args.require_signature,
                allow_insecure_http=args.allow_insecure_http,
            )
        )
    if args.command == "registry" and args.registry_command == "update":
        return workspace.update_registry(
            UpdateRegistryInput(
                id=args.id,
                scope=args.scope,
                version=args.version,
                apply=args.apply,
                public_key=args.public_key,
                require_signature=args.require_signature,
                allow_insecure_http=args.allow_insecure_http,
            )
        )
    if args.command == "registry" and args.registry_command == "list":
        return workspace.list_registries()
    if args.command == "trust" and args.trust_command == "add":
        return workspace.add_registry_trust_key(
            AddRegistryTrustKeyInput(
                id=args.id,
                registry_id=args.registry,
                public_key=args.public_key,
                scope=args.scope,
            )
        )
    if args.command == "trust" and args.trust_command == "list":
        return workspace.list_registry_trust_keys(args.registry)
    if args.command == "trust" and args.trust_command == "revoke":
        return workspace.revoke_registry_trust_key(
            RevokeRegistryTrustKeyInput(
                id=args.id,
                scope=args.scope,
                reason=args.reason,
                replaced_by=args.replaced_by,
            )
        )
    if args.command == "pack" and args.pack_command == "search":
        return workspace.search_catalog(args.kind, args.query, args.registry)
    if args.command == "pack" and args.pack_command == "install":
        return workspace.install_catalog_pack(
            InstallCatalogPackInput(
                kind=args.kind,
                pack_id=args.id,
                registry_id=args.registry,
                scope=args.scope,
                force=args.force,
            )
        )
    if args.command == "pack" and args.pack_command == "update":
        return workspace.update_catalog_pack(
            UpdateCatalogPackInput(
                kind=args.kind,
                pack_id=args.id,
                registry_id=args.registry,
                scope=args.scope,
                apply=args.apply,
                force=args.force,
            )
        )
    if args.command == "pack" and args.pack_command == "lock":
        return workspace.refresh_pack_lock(RefreshPackLockInput(scope=args.scope))
    if args.command == "pack" and args.pack_command == "remove":
        return workspace.remove_pack(
            RemovePackInput(
                kind=args.kind,
                pack_id=args.id,
                scope=args.scope,
                apply=args.apply,
                with_unused_dependencies=args.with_unused_dependencies,
            )
        )
    if args.command == "start":
        return workspace.start_session(
            StartSessionInput(
                id=args.id,
                actor_id=args.actor,
                swarm_id=args.swarm,
                work_id=args.work,
                runner=args.runner,
                launch=args.launch,
                force=args.force,
            )
        )
    if args.command == "method" and args.method_command == "install":
        return workspace.install_method(
            InstallMethodInput(source=args.source, scope=args.scope, force=args.force)
        )
    if args.command == "method" and args.method_command == "list":
        return workspace.list_methods()
    if args.command == "tool" and args.tool_command == "install":
        return workspace.install_tool(
            InstallToolInput(source=args.source, scope=args.scope, force=args.force)
        )
    if args.command == "tool" and args.tool_command == "show":
        return workspace.show_tool(args.tool)
    if args.command == "tool" and args.tool_command == "list":
        return workspace.list_tools()
    if (
        args.command == "tool"
        and args.tool_command == "adapter"
        and args.tool_adapter_command == "list"
    ):
        return workspace.list_tool_adapters(
            available_only=args.available,
            compatible_only=args.compatible,
            check_runtime=args.check,
        )
    if (
        args.command == "tool"
        and args.tool_command == "adapter"
        and args.tool_adapter_command == "install"
    ):
        return workspace.install_tool_adapter(
            InstallToolAdapterInput(
                adapter_id=args.id,
                scope=args.scope,
                force=args.force,
            )
        )
    if args.command == "tool" and args.tool_command == "runs":
        return workspace.list_tool_runs(args.status)
    if args.command == "tool" and args.tool_command == "authorization":
        return workspace.prepare_tool_authorization(
            PrepareToolAuthorizationInput(
                run_id=args.run,
                output=args.output,
                force=args.force,
            )
        )
    if args.command == "tool" and args.tool_command == "launch":
        return workspace.launch_tool_run(
            LaunchToolRunInput(
                run_id=args.run,
                signature=args.signature,
            )
        )
    if args.command == "tool" and args.tool_command == "invoke":
        return workspace.invoke_tool(
            InvokeToolInput(
                id=args.id,
                tool_id=args.tool,
                operation_id=args.operation,
                actor_id=args.actor,
                swarm_id=args.swarm,
                work_id=args.work,
                inputs=_parse_inputs(args.input),
                launch=args.launch,
                force=args.force,
            )
        )
    if args.command == "delegation" and args.delegation_command == "create":
        return workspace.create_delegation(
            CreateDelegationInput(
                id=args.id,
                parent_swarm_id=args.swarm,
                parent_work_id=args.work,
                child_actor_id=args.to_actor,
                child_work_id=args.child_work,
                actor_id=args.by,
                title=args.title,
                description=args.description,
                acceptance_criteria=[_parse_criterion(item) for item in args.criterion],
                required_artifacts=args.required_artifact,
                result_kind=args.result_kind,
                budget_limits=_parse_budget_limits(args.budget),
                artifact_promotions=_parse_artifact_promotions(args.promote_artifact),
            )
        )
    if args.command == "delegation" and args.delegation_command == "create-prepare":
        return workspace.prepare_create_delegation(
            PrepareCreateDelegationInput(
                action_id=args.action_id,
                delegation=CreateDelegationInput(
                    id=args.id,
                    parent_swarm_id=args.swarm,
                    parent_work_id=args.work,
                    child_actor_id=args.to_actor,
                    child_work_id=args.child_work,
                    actor_id=args.by,
                    title=args.title,
                    description=args.description,
                    acceptance_criteria=[_parse_criterion(item) for item in args.criterion],
                    required_artifacts=args.required_artifact,
                    result_kind=args.result_kind,
                    budget_limits=_parse_budget_limits(args.budget),
                    artifact_promotions=_parse_artifact_promotions(args.promote_artifact),
                ),
            )
        )
    if args.command == "delegation" and args.delegation_command == "accept":
        return workspace.accept_delegation(
            DelegationActorInput(
                delegation_id=args.delegation,
                actor_id=args.by,
            )
        )
    if args.command == "delegation" and args.delegation_command == "accept-prepare":
        return workspace.prepare_accept_delegation(
            PrepareDelegationActionInput(
                id=args.id,
                delegation_id=args.delegation,
                actor_id=args.by,
            )
        )
    if args.command == "delegation" and args.delegation_command == "collect":
        return workspace.collect_delegation(
            DelegationActorInput(
                delegation_id=args.delegation,
                actor_id=args.by,
            )
        )
    if args.command == "delegation" and args.delegation_command == "collect-prepare":
        return workspace.prepare_collect_delegation(
            PrepareDelegationActionInput(
                id=args.id,
                delegation_id=args.delegation,
                actor_id=args.by,
            )
        )
    if args.command == "delegation" and args.delegation_command in {
        "block",
        "resume",
        "reject",
        "cancel",
    }:
        change = ChangeDelegationStatusInput(
            delegation_id=args.delegation,
            actor_id=args.by,
            reason=args.reason,
            id=args.id,
        )
        return {
            "block": workspace.block_delegation,
            "resume": workspace.resume_delegation,
            "reject": workspace.reject_delegation,
            "cancel": workspace.cancel_delegation,
        }[args.delegation_command](change)
    if args.command == "delegation" and args.delegation_command in {
        "block-prepare",
        "resume-prepare",
        "reject-prepare",
        "cancel-prepare",
    }:
        change = ChangeDelegationStatusInput(
            delegation_id=args.delegation,
            actor_id=args.by,
            reason=args.reason,
            id=args.id,
        )
        return {
            "block-prepare": workspace.prepare_block_delegation,
            "resume-prepare": workspace.prepare_resume_delegation,
            "reject-prepare": workspace.prepare_reject_delegation,
            "cancel-prepare": workspace.prepare_cancel_delegation,
        }[args.delegation_command](change)
    if args.command == "delegation" and args.delegation_command == "status-changes":
        return workspace.list_delegation_status_changes(args.delegation)
    if args.command == "delegation" and args.delegation_command == "show":
        return workspace.show_delegation(args.delegation)
    if args.command == "delegation" and args.delegation_command == "list":
        return workspace.list_delegations(args.status)
    if args.command == "actor" and args.actor_command == "add":
        return workspace.add_actor(
            AddActorInput(
                id=args.id,
                name=args.name,
                kind=args.kind,
                capabilities=args.capability,
                scope=args.scope,
                description=args.description,
                integration=args.integration,
                provider=args.provider,
                model=args.model,
                represented_swarm=args.represented_swarm,
                public_key=args.public_key,
                require_authentication=args.require_authentication,
                force=args.force,
            )
        )
    if args.command == "actor" and args.actor_command == "runtime":
        return workspace.set_actor_runtime(
            SetActorRuntimeInput(
                actor_id=args.actor,
                integration=args.integration,
                provider=args.provider,
                model=args.model,
                clear=args.clear,
            )
        )
    if args.command == "actor" and args.actor_command == "runtime-prepare":
        return workspace.prepare_actor_runtime(
            PrepareActorRuntimeInput(
                action_id=args.id,
                swarm_id=args.swarm,
                runtime=SetActorRuntimeInput(
                    actor_id=args.actor,
                    integration=args.integration,
                    provider=args.provider,
                    model=args.model,
                    clear=args.clear,
                ),
            )
        )
    if args.command == "actor" and args.actor_command == "key":
        if args.actor_key_command == "rotate":
            return workspace.rotate_actor_key(
                RotateActorKeyInput(
                    actor_id=args.actor,
                    public_key=args.public_key,
                    reason=args.reason,
                )
            )
        if args.actor_key_command == "rotate-prepare":
            return workspace.prepare_actor_key_rotation(
                PrepareActorKeyRotationInput(
                    action_id=args.id,
                    swarm_id=args.swarm,
                    rotation=RotateActorKeyInput(
                        actor_id=args.actor,
                        public_key=args.public_key,
                        reason=args.reason,
                    ),
                )
            )
        if args.actor_key_command == "revoke":
            return workspace.revoke_actor_key(
                RevokeActorKeyInput(actor_id=args.actor, reason=args.reason)
            )
        if args.actor_key_command == "revoke-prepare":
            return workspace.prepare_actor_key_revocation(
                PrepareActorKeyRevocationInput(
                    action_id=args.id,
                    swarm_id=args.swarm,
                    target_actor_id=args.actor,
                    authorized_by=args.by,
                    reason=args.reason,
                )
            )
        if args.actor_key_command == "recover-prepare":
            return workspace.prepare_actor_key_recovery(
                PrepareActorKeyRecoveryInput(
                    action_id=args.id,
                    swarm_id=args.swarm,
                    target_actor_id=args.actor,
                    authorized_by=args.by,
                    public_key=args.public_key,
                    reason=args.reason,
                )
            )
        if args.actor_key_command == "list":
            return workspace.list_actor_keys(args.actor)
    if args.command == "actor" and args.actor_command == "list":
        return workspace.list_actors(args.scope)
    if args.command == "swarm" and args.swarm_command == "create":
        return workspace.create_swarm(
            CreateSwarmInput(
                id=args.id,
                objective=args.objective,
                method=args.method,
                branch=args.branch,
                create_branch=not args.no_branch,
            )
        )
    if args.command == "swarm" and args.swarm_command == "assign":
        return workspace.assign_actor(
            AssignActorInput(swarm_id=args.swarm, role_id=args.role, actor_id=args.actor)
        )
    if args.command == "swarm" and args.swarm_command == "assign-prepare":
        return workspace.prepare_actor_assignment(
            PrepareActorAssignmentInput(
                action_id=args.id,
                assignment=AssignActorInput(
                    swarm_id=args.swarm,
                    role_id=args.role,
                    actor_id=args.actor,
                ),
                authorized_by=args.by,
            )
        )
    if args.command == "swarm" and args.swarm_command == "handoff":
        return workspace.handoff_actor(
            HandoffActorInput(
                id=args.id,
                swarm_id=args.swarm,
                role_id=args.role,
                from_actor_id=args.from_actor,
                to_actor_id=args.to_actor,
                authorized_by=args.by,
                reason=args.reason,
                work_id=args.work,
            )
        )
    if args.command == "swarm" and args.swarm_command == "handoff-prepare":
        return workspace.prepare_handoff(
            HandoffActorInput(
                id=args.id,
                swarm_id=args.swarm,
                role_id=args.role,
                from_actor_id=args.from_actor,
                to_actor_id=args.to_actor,
                authorized_by=args.by,
                reason=args.reason,
                work_id=args.work,
            )
        )
    if args.command == "swarm" and args.swarm_command == "show":
        return workspace.show_swarm(args.swarm)
    if args.command == "swarm" and args.swarm_command == "list":
        return workspace.list_swarms(args.status)
    if args.command == "swarm" and args.swarm_command == "handoffs":
        return workspace.list_handoffs(args.swarm)
    if args.command == "work" and args.work_command == "create":
        return workspace.create_work(
            CreateWorkInput(
                swarm_id=args.swarm,
                id=args.id,
                title=args.title,
                actor_id=args.by,
                description=args.description,
                acceptance_criteria=[_parse_criterion(item) for item in args.criterion],
                required_artifacts=args.required_artifact,
            )
        )
    if args.command == "work" and args.work_command == "create-prepare":
        return workspace.prepare_create_work(
            PrepareCreateWorkInput(
                action_id=args.action_id,
                work=CreateWorkInput(
                    swarm_id=args.swarm,
                    id=args.id,
                    title=args.title,
                    actor_id=args.by,
                    description=args.description,
                    acceptance_criteria=[_parse_criterion(item) for item in args.criterion],
                    required_artifacts=args.required_artifact,
                ),
            )
        )
    if args.command == "work" and args.work_command == "decompose":
        return workspace.decompose_work(
            DecomposeWorkInput(
                swarm_id=args.swarm,
                parent_work_id=args.work,
                child_work_id=args.child,
                title=args.title,
                actor_id=args.by,
                description=args.description,
                acceptance_criteria=[_parse_criterion(item) for item in args.criterion],
                required_artifacts=args.required_artifact,
            )
        )
    if args.command == "work" and args.work_command == "decompose-prepare":
        return workspace.prepare_decompose_work(
            PrepareDecomposeWorkInput(
                action_id=args.action_id,
                decomposition=DecomposeWorkInput(
                    swarm_id=args.swarm,
                    parent_work_id=args.work,
                    child_work_id=args.child,
                    title=args.title,
                    actor_id=args.by,
                    description=args.description,
                    acceptance_criteria=[_parse_criterion(item) for item in args.criterion],
                    required_artifacts=args.required_artifact,
                ),
            )
        )
    if args.command == "work" and args.work_command == "criterion-satisfy":
        return workspace.satisfy_criterion(
            WorkActorInput(swarm_id=args.swarm, work_id=args.work, actor_id=args.by),
            args.criterion,
        )
    if args.command == "work" and args.work_command == "criterion-satisfy-prepare":
        return workspace.prepare_satisfy_criterion(
            PrepareCriterionInput(
                id=args.id,
                swarm_id=args.swarm,
                work_id=args.work,
                actor_id=args.by,
                criterion_id=args.criterion,
            )
        )
    if args.command == "work" and args.work_command == "transition":
        return workspace.transition_work(
            TransitionWorkInput(
                swarm_id=args.swarm,
                work_id=args.work,
                actor_id=args.by,
                target_state=args.to,
            )
        )
    if args.command == "work" and args.work_command == "transition-prepare":
        return workspace.prepare_work_transition(
            PrepareWorkTransitionInput(
                id=args.id,
                swarm_id=args.swarm,
                work_id=args.work,
                actor_id=args.by,
                target_state=args.to,
            )
        )
    if args.command == "work" and args.work_command in {"block", "resume", "cancel"}:
        change = ChangeWorkStatusInput(
            swarm_id=args.swarm,
            work_id=args.work,
            actor_id=args.by,
            reason=args.reason,
            id=args.id,
        )
        return {
            "block": workspace.block_work,
            "resume": workspace.resume_work,
            "cancel": workspace.cancel_work,
        }[args.work_command](change)
    if args.command == "work" and args.work_command in {
        "block-prepare",
        "resume-prepare",
        "cancel-prepare",
    }:
        change = ChangeWorkStatusInput(
            swarm_id=args.swarm,
            work_id=args.work,
            actor_id=args.by,
            reason=args.reason,
            id=args.id,
        )
        return {
            "block-prepare": workspace.prepare_block_work,
            "resume-prepare": workspace.prepare_resume_work,
            "cancel-prepare": workspace.prepare_cancel_work,
        }[args.work_command](change)
    if args.command == "work" and args.work_command == "status-changes":
        return workspace.list_work_status_changes(args.swarm, args.work)
    if args.command == "work" and args.work_command == "show":
        return workspace.show_work(args.swarm, args.work)
    if args.command == "work" and args.work_command == "list":
        return workspace.list_work(args.swarm, args.state, args.operational_status)
    if args.command == "gate" and args.gate_command in {"waive", "waive-prepare"}:
        waiver = WaiveGateInput(
            id=args.id,
            swarm_id=args.swarm,
            work_id=args.work,
            gate_id=args.gate,
            actor_id=args.by,
            reason=args.reason,
            evidence_refs=args.evidence,
            criteria=args.criterion,
            artifacts=args.artifact,
            successful_evidence=args.successful_evidence,
            approval_roles=args.approval,
        )
        if args.gate_command == "waive-prepare":
            return workspace.prepare_gate_waiver(
                PrepareGateWaiverInput(action_id=args.action_id, waiver=waiver)
            )
        return workspace.waive_gate(waiver)
    if args.command == "gate" and args.gate_command == "list":
        return workspace.list_gate_waivers(args.swarm, args.work, args.gate)
    if args.command == "session" and args.session_command == "list":
        return workspace.list_sessions(args.status)
    if args.command == "session" and args.session_command == "prepare":
        return workspace.prepare_session(
            PrepareSessionInput(
                action_id=args.id,
                session=StartSessionInput(
                    id=args.session,
                    actor_id=args.actor,
                    swarm_id=args.swarm,
                    work_id=args.work,
                    runner=args.runner,
                ),
            )
        )
    if args.command == "session" and args.session_command == "authorization":
        return workspace.prepare_session_authorization(
            PrepareSessionAuthorizationInput(
                session_id=args.session,
                output=args.output,
                force=args.force,
            )
        )
    if args.command == "session" and args.session_command == "launch":
        return workspace.launch_session(
            LaunchSessionInput(session_id=args.session, signature=args.signature)
        )
    if args.command == "action" and args.action_command == "authorization":
        return workspace.prepare_lifecycle_authorization(
            PrepareLifecycleAuthorizationInput(
                action_id=args.action,
                output=args.output,
                force=args.force,
            )
        )
    if args.command == "action" and args.action_command == "apply":
        return workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(action_id=args.action, signature=args.signature)
        )
    if args.command == "action" and args.action_command == "list":
        return workspace.list_lifecycle_actions(args.status)
    if args.command == "event" and args.event_command == "list":
        return workspace.list_events(
            swarm_id=args.swarm,
            work_id=args.work,
            type_=args.type,
            limit=args.limit,
        )
    if args.command == "artifact" and args.artifact_command == "add":
        return workspace.add_artifact(
            AddArtifactInput(
                swarm_id=args.swarm,
                work_id=args.work,
                actor_id=args.by,
                kind=args.kind,
                uri=args.uri,
            )
        )
    if args.command == "artifact" and args.artifact_command == "prepare":
        return workspace.prepare_add_artifact(
            PrepareArtifactInput(
                id=args.id,
                swarm_id=args.swarm,
                work_id=args.work,
                actor_id=args.by,
                kind=args.kind,
                uri=args.uri,
            )
        )
    if args.command == "evidence" and args.evidence_command == "add":
        return workspace.add_evidence(
            AddEvidenceInput(
                swarm_id=args.swarm,
                work_id=args.work,
                actor_id=args.by,
                type=args.type,
                result=args.result,
                artifact_refs=args.artifact,
            )
        )
    if args.command == "evidence" and args.evidence_command == "prepare":
        return workspace.prepare_add_evidence(
            PrepareEvidenceInput(
                id=args.id,
                swarm_id=args.swarm,
                work_id=args.work,
                actor_id=args.by,
                type=args.type,
                result=args.result,
                artifact_refs=args.artifact,
            )
        )
    if args.command == "approval" and args.approval_command == "add":
        return workspace.add_approval(
            AddApprovalInput(
                swarm_id=args.swarm,
                work_id=args.work,
                actor_id=args.by,
                role_id=args.role,
                note=args.note,
                delegation_id=args.delegation,
            )
        )
    if args.command == "approval" and args.approval_command == "prepare":
        return workspace.prepare_approval(
            PrepareApprovalInput(
                id=args.id,
                swarm_id=args.swarm,
                work_id=args.work,
                actor_id=args.by,
                role_id=args.role,
                note=args.note,
                delegation_id=args.delegation,
            )
        )
    if args.command == "approval" and args.approval_command in {
        "delegate",
        "delegate-prepare",
    }:
        delegation = DelegateApprovalInput(
            id=args.id,
            swarm_id=args.swarm,
            work_id=args.work,
            role_id=args.role,
            actor_id=args.by,
            to_actor_id=args.to,
            reason=args.reason,
        )
        if args.approval_command == "delegate-prepare":
            return workspace.prepare_approval_delegation(
                PrepareApprovalDelegationInput(
                    action_id=args.action_id,
                    delegation=delegation,
                )
            )
        return workspace.delegate_approval(delegation)
    if args.command == "approval" and args.approval_command in {
        "delegation-revoke",
        "delegation-revoke-prepare",
    }:
        revocation = RevokeApprovalDelegationInput(
            delegation_id=args.delegation,
            swarm_id=args.swarm,
            work_id=args.work,
            actor_id=args.by,
            reason=args.reason,
            action_id=(
                args.action_id if args.approval_command == "delegation-revoke-prepare" else None
            ),
        )
        if args.approval_command == "delegation-revoke-prepare":
            return workspace.prepare_revoke_approval_delegation(revocation)
        return workspace.revoke_approval_delegation(revocation)
    if args.command == "approval" and args.approval_command == "delegations":
        return workspace.list_approval_delegations(args.swarm, args.work, args.status)
    raise ValueError("Unsupported command")


def _extract_project(arguments: list[str]) -> tuple[str | None, list[str]]:
    cleaned = list(arguments)
    if "--project" not in cleaned:
        return None, cleaned
    index = cleaned.index("--project")
    if index + 1 >= len(cleaned):
        raise ValueError("--project requires a path")
    project = cleaned[index + 1]
    del cleaned[index : index + 2]
    return project, cleaned


def _parse_criterion(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise ValueError(f'Invalid criterion "{value}"; expected id:description')
    criterion_id, description = value.split(":", 1)
    if not criterion_id or not description:
        raise ValueError(f'Invalid criterion "{value}"; expected id:description')
    return criterion_id, description


def _parse_inputs(values: list[str]) -> dict[str, str]:
    inputs: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f'Invalid tool input "{value}"; expected key=value')
        key, item = value.split("=", 1)
        if not key or not item:
            raise ValueError(f'Invalid tool input "{value}"; expected key=value')
        if key in inputs:
            raise ValueError(f"Duplicate tool input: {key}")
        inputs[key] = item
    return inputs


def _parse_budget_limits(values: list[str]) -> dict[str, int] | None:
    if not values:
        return None
    limits: dict[str, int] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f'Invalid delegation budget "{value}"; expected dimension=limit')
        dimension, raw_limit = value.split("=", 1)
        if not dimension or not raw_limit:
            raise ValueError(f'Invalid delegation budget "{value}"; expected dimension=limit')
        if dimension in limits:
            raise ValueError(f"Duplicate delegation budget dimension: {dimension}")
        try:
            limit = int(raw_limit)
        except ValueError as error:
            raise ValueError(f'Delegation budget limit must be an integer: "{value}"') from error
        if limit < 0:
            raise ValueError(f'Delegation budget limit cannot be negative: "{value}"')
        limits[dimension] = limit
    return limits


def _parse_artifact_promotions(values: list[str]) -> dict[str, str]:
    promotions: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(
                f'Invalid artifact promotion "{value}"; expected source-kind=parent-kind'
            )
        source, target = value.split("=", 1)
        if not source or not target:
            raise ValueError(
                f'Invalid artifact promotion "{value}"; expected source-kind=parent-kind'
            )
        if source in promotions:
            raise ValueError(f"Duplicate promoted child artifact kind: {source}")
        promotions[source] = target
    return promotions


def _print_json(output: TextIO, value: Any) -> None:
    def normalize(item: Any) -> Any:
        if is_dataclass(item) and not isinstance(item, type):
            return {key: normalize(child) for key, child in asdict(item).items()}
        if isinstance(item, dict):
            return {key: normalize(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(child) for child in item]
        return item

    print(json.dumps(normalize(value), indent=2), file=output)

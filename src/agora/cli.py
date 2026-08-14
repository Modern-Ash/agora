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
    AddArtifactInput,
    AddEvidenceInput,
    AssignActorInput,
    ConfigureInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    InstallMethodInput,
    TransitionWorkInput,
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
    configure.add_argument("--force", action="store_true")

    initialize = commands.add_parser("init", help="Initialize an Agora project")
    initialize.add_argument("--path")
    initialize.add_argument("--integration", choices=INTEGRATIONS)
    initialize.add_argument("--provider")
    initialize.add_argument("--model")
    initialize.add_argument("--default-method", metavar="METHOD_ID")
    initialize.add_argument("--force", action="store_true")

    commands.add_parser("doctor", help="Validate the current Agora environment")

    method = commands.add_parser("method", help="Manage lifecycle Method Packs").add_subparsers(
        dest="method_command", required=True
    )
    method_install = method.add_parser("install", help="Install a Method Pack from a directory")
    method_install.add_argument("--source", required=True)
    method_install.add_argument("--scope", choices=("user", "project"), default="project")
    method_install.add_argument("--force", action="store_true")

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
    actor_add.add_argument("--force", action="store_true")

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

    swarm_show = swarm.add_parser("show", help="Show a swarm")
    swarm_show.add_argument("--swarm", required=True)

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

    criterion = work.add_parser("criterion-satisfy", help="Satisfy an acceptance criterion")
    criterion.add_argument("--swarm", required=True)
    criterion.add_argument("--work", required=True)
    criterion.add_argument("--criterion", required=True)
    criterion.add_argument("--by", required=True)

    transition = work.add_parser("transition", help="Move work to the next method state")
    transition.add_argument("--swarm", required=True)
    transition.add_argument("--work", required=True)
    transition.add_argument("--to", required=True)
    transition.add_argument("--by", required=True)

    work_show = work.add_parser("show", help="Show a work item")
    work_show.add_argument("--swarm", required=True)
    work_show.add_argument("--work", required=True)

    artifact = commands.add_parser("artifact", help="Manage artifacts").add_subparsers(
        dest="artifact_command", required=True
    )
    artifact_add = artifact.add_parser("add", help="Register an artifact")
    artifact_add.add_argument("--swarm", required=True)
    artifact_add.add_argument("--work", required=True)
    artifact_add.add_argument("--kind", required=True)
    artifact_add.add_argument("--uri", required=True)
    artifact_add.add_argument("--by", required=True)

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
    return parser


def _dispatch(workspace: AgoraWorkspace, args: argparse.Namespace) -> Any:
    if args.command == "configure":
        return workspace.configure(
            ConfigureInput(
                integration=args.integration,
                provider=args.provider,
                model=args.model,
                default_method=args.default_method,
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
                force=args.force,
            )
        )
    if args.command == "doctor":
        checks = workspace.doctor()
        return {"ok": all(item.ok or item.name == "git" for item in checks), "checks": checks}
    if args.command == "method" and args.method_command == "install":
        return workspace.install_method(
            InstallMethodInput(source=args.source, scope=args.scope, force=args.force)
        )
    if args.command == "actor" and args.actor_command == "add":
        return workspace.add_actor(
            AddActorInput(
                id=args.id,
                name=args.name,
                kind=args.kind,
                capabilities=args.capability,
                scope=args.scope,
                description=args.description,
                force=args.force,
            )
        )
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
    if args.command == "swarm" and args.swarm_command == "show":
        return workspace.show_swarm(args.swarm)
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
    if args.command == "work" and args.work_command == "criterion-satisfy":
        return workspace.satisfy_criterion(
            WorkActorInput(swarm_id=args.swarm, work_id=args.work, actor_id=args.by),
            args.criterion,
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
    if args.command == "work" and args.work_command == "show":
        return workspace.show_work(args.swarm, args.work)
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

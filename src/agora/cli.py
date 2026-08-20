import argparse
import json
import re
import shutil
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, TextIO

from agora.application import (
    ActivityFilters,
    ActorFilters,
    AgoraReadService,
    SessionFilters,
    SwarmFilters,
    WorkItemFilters,
)
from agora.application.dto import (
    ActivityEntry,
    ActorSummary,
    ProjectOverview,
    SessionSummary,
    SwarmSummary,
    TraceabilitySummary,
    WorkItemDetail,
    WorkItemSummary,
)
from agora.console import ActivityContext, ConsoleActivity, ConsoleResult, is_human_terminal
from agora.filesystem import agora_home
from agora.git import is_git_repository
from agora.model import (
    ACTOR_KINDS,
    BUILTIN_METHODS,
    DEFAULT_SESSION_MAX_OUTPUT_BYTES,
    DEFAULT_SESSION_TIMEOUT_SECONDS,
    INTEGRATIONS,
    ActorRecord,
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddChecklistInput,
    AddEnvironmentInput,
    AddEvidenceInput,
    AddOrganizationTrustRootInput,
    AddRegistryTrustKeyInput,
    AddTransparencyTrustKeyInput,
    AddUsageInput,
    AdoptionInput,
    AdoptionReport,
    ApplyLifecycleActionInput,
    ApplyPackUpdateAuditInput,
    AssignActorInput,
    AuditPackUpdatesInput,
    AuditRegistryUpdatesInput,
    ChangeDelegationStatusInput,
    ChangeWorkStatusInput,
    CheckChecklistItemInput,
    ConfigureCoordinationInput,
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
    PrepareUsageInput,
    PrepareWorkTransitionInput,
    ProjectConfiguration,
    QuickstartInput,
    RefreshPackLockInput,
    RemovePackInput,
    ResumeSessionInput,
    RevokeActorKeyInput,
    RevokeApprovalDelegationInput,
    RevokeRegistryTrustKeyInput,
    RevokeTransparencyTrustKeyInput,
    RotateActorKeyInput,
    RotateOrganizationTrustRootInput,
    RunLoopEvent,
    RunNextInput,
    RunPreview,
    SetActorRuntimeInput,
    StartSessionInput,
    SyncOrganizationTrustInput,
    TransitionWorkInput,
    UpdateCatalogPackInput,
    UpdateRegistryInput,
    UpgradeInput,
    ValidationReport,
    VerifyTransparencyProofInput,
    WaiveGateInput,
    WorkActorInput,
)
from agora.wizard import Choice, Wizard
from agora.workspace import AgoraWorkspace


def main(
    argv: list[str] | None = None,
    *,
    cwd: Path | str | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    stdin: TextIO | None = None,
) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    output = stdout or sys.stdout
    error_output = stderr or sys.stderr
    input_stream = stdin or sys.stdin
    project, arguments = _extract_project(arguments)
    parser = _build_parser()
    try:
        namespace = parser.parse_args(arguments)
        workspace = AgoraWorkspace(cwd=project or cwd)
        with ConsoleActivity(error_output, _activity_context(workspace, namespace)) as activity:
            if namespace.command == "setup" or (
                namespace.command == "adopt" and not namespace.check
            ):
                result = _run_setup_wizard(
                    workspace,
                    namespace,
                    input_stream=input_stream,
                    output_stream=error_output,
                )
            elif namespace.command == "continue":
                result = _run_continue_wizard(
                    workspace,
                    namespace,
                    input_stream=input_stream,
                    output_stream=error_output,
                )
            elif namespace.command == "work" and namespace.work_command == "start":
                result = _run_work_start_wizard(
                    workspace,
                    namespace,
                    input_stream=input_stream,
                    output_stream=error_output,
                )
            elif namespace.command == "work" and namespace.work_command == "finish":
                result = _run_work_finish_wizard(
                    workspace,
                    namespace,
                    input_stream=input_stream,
                    output_stream=error_output,
                )
            elif namespace.command == "run" and namespace.until_blocked:
                result = _dispatch(
                    workspace,
                    namespace,
                    run_observer=activity.handle_run_event,
                )
            else:
                result = _dispatch(workspace, namespace)
        if result is not None:
            _present_result(output, namespace, result, workspace=workspace)
        if isinstance(result, (AdoptionReport, ValidationReport)) and not result.ok:
            return 1
        if isinstance(result, dict) and result.get("ok") is False:
            return 1
        return 0
    except (FileExistsError, FileNotFoundError, PermissionError, RuntimeError, ValueError) as error:
        print(str(error), file=error_output)
        return 1


def _present_result(
    output: TextIO,
    args: argparse.Namespace,
    result: Any,
    *,
    workspace: AgoraWorkspace,
) -> None:
    if args.command == "status" and args.board:
        print(result, file=output)
        return
    result = _cli_read_payload(result, workspace)
    setup_guided = args.command == "setup" or (args.command == "adopt" and not args.check)
    continue_guided = args.command == "continue"
    work_start_guided = args.command == "work" and args.work_command == "start"
    work_finish_guided = args.command == "work" and args.work_command == "finish"
    guided_dialogue_already_rendered = (
        (setup_guided and not args.non_interactive)
        or (continue_guided and not args.yes)
        or work_start_guided
        or work_finish_guided
    )
    if is_human_terminal(output):
        if not guided_dialogue_already_rendered:
            ConsoleResult(output).render(_command_name(args), result)
        return
    _print_json(output, result)


def _command_name(args: argparse.Namespace) -> str:
    parts = [args.command]
    parts.extend(
        value for key, value in vars(args).items() if key.endswith("_command") and value is not None
    )
    return " ".join(parts)


def _cli_read_payload(value: Any, workspace: AgoraWorkspace) -> Any:
    """Project application DTOs onto the CLI's pre-service JSON contract."""
    if isinstance(value, tuple) and all(
        isinstance(
            item,
            (ActorSummary, SwarmSummary, WorkItemSummary, ActivityEntry, SessionSummary),
        )
        for item in value
    ):
        return [_cli_read_payload(item, workspace) for item in value]
    if isinstance(value, ProjectOverview):
        payload = value.to_dict()
        return {
            "project": value.project,
            "integration": value.integration,
            "default_method": value.default_method,
            "branch": value.branch,
            "counts": payload["counts"],
            "swarm_statuses": payload["swarm_statuses"],
            "work_states": payload["work_states"],
            "work_operational_statuses": payload["work_operational_statuses"],
            "delegation_statuses": payload["delegation_statuses"],
            "session_statuses": payload["session_statuses"],
            "tool_run_statuses": payload["tool_run_statuses"],
            "attention": payload["attention"],
        }
    if isinstance(value, ActorSummary):
        root = workspace.project_root()
        scope, _ = value.reference.split(":", 1)
        actor_root = agora_home() if scope == "user" else root / ".agora"
        payload = {
            "id": value.id,
            "name": value.name,
            "kind": value.kind,
            "capabilities": list(value.capabilities),
            "path": str(actor_root / "actors" / f"{value.id}.md"),
            "reference": value.reference,
            "integration": value.integration,
            "provider": value.provider,
            "model": value.model,
            "represented_swarm": value.represented_swarm,
            "authentication_required": value.authentication_required,
            "authentication_algorithm": value.authentication_algorithm,
            "authentication_public_key": value.authentication_public_key,
            "authentication_fingerprint": value.authentication_fingerprint,
            "authentication_revoked_at": value.authentication_revoked_at,
            "authentication_revoked_reason": value.authentication_revoked_reason,
        }
        if "runtime_fallbacks" in ActorRecord.__dataclass_fields__:
            payload["runtime_fallbacks"] = [dict(item) for item in value.runtime_fallbacks]
        return payload
    if isinstance(value, SwarmSummary):
        root = workspace.project_root()
        return {
            "id": value.id,
            "method": value.method,
            "status": value.status,
            "branch": value.branch,
            "required_roles": list(value.required_roles),
            "assignments": dict(value.assignments),
            "objective": value.objective,
            "path": str(root / ".agora" / "swarms" / value.id),
        }
    if isinstance(value, (WorkItemSummary, WorkItemDetail)):
        root = workspace.project_root()
        return {
            "id": value.id,
            "swarm_id": value.swarm_id,
            "title": value.title,
            "description": value.description,
            "state": value.state,
            "acceptance_criteria": dict(value.acceptance_criteria),
            "satisfied_criteria": list(value.satisfied_criteria),
            "required_artifacts": list(value.required_artifacts),
            "artifact_kinds": list(value.artifact_kinds),
            "evidence_results": list(value.evidence_results),
            "approval_roles": list(value.approval_roles),
            "path": str(root / ".agora" / "swarms" / value.swarm_id / "work" / value.id),
            "child_work_refs": list(value.child_work_refs),
            "budget_limits": dict(value.budget_limits) if value.budget_limits is not None else None,
            "operational_status": value.operational_status,
            "status_reason": value.status_reason,
            "status_by": value.status_by,
            "status_at": value.status_at,
            "delegation_id": value.delegation_id,
            "parent_work_ref": value.parent_work_ref,
            "criterion_statuses": {
                key: list(items) for key, items in value.criterion_statuses.items()
            },
        }
    if isinstance(value, ActivityEntry):
        root = workspace.project_root()
        return {
            "timestamp": value.timestamp,
            "type": value.type,
            "summary": value.summary,
            "actor": value.actor,
            "swarm_id": value.swarm_id,
            "work_id": value.work_id,
            "session_id": value.session_id,
            "tool_run_id": value.tool_run_id,
            "source": value.source,
            "path": str(root / ".agora" / "activity.md"),
        }
    if isinstance(value, SessionSummary):
        root = workspace.project_root()
        session_root = root / ".agora" / "sessions" / value.id
        return {
            "id": value.id,
            "actor": value.actor,
            "swarm_id": value.swarm_id,
            "work_id": value.work_id,
            "roles": list(value.roles),
            "integration": value.integration,
            "provider": value.provider,
            "model": value.model,
            "status": value.status,
            "path": str(session_root),
            "context_path": str(session_root / "CONTEXT.md"),
            "launch_command": list(value.launch_command),
            "runtime_available": value.runtime_available,
            "created_at": value.created_at,
            "exit_code": value.exit_code,
            "timeout_seconds": value.timeout_seconds,
            "max_output_bytes": value.max_output_bytes,
            "output_bytes": value.output_bytes,
            "termination_reason": value.termination_reason,
            "context_sha256": value.context_sha256,
            "authentication_verified": value.authentication_verified,
            "authentication_fingerprint": value.authentication_fingerprint,
            "authentication_public_key": value.authentication_public_key,
            "authorization_sha256": value.authorization_sha256,
            "authorization_signature": value.authorization_signature,
            "preparation_action_id": value.preparation_action_id,
            "executor": value.executor,
        }
    if isinstance(value, TraceabilitySummary):
        payload = value.to_dict()
        return {
            "swarm": value.swarm_id,
            "work": value.work_id,
            "state": value.state,
            "stale": value.stale,
            "criteria": payload["criteria"],
            "clarifications": payload["clarifications"],
            "gherkin": payload["gherkin"],
            "consistency": payload["consistency"],
            "artifacts": [
                {"kind": artifact.kind, "uri": artifact.uri} for artifact in value.artifacts
            ],
            "evidence": [
                {
                    "type": evidence.type,
                    "result": evidence.result,
                    "artifact-references": list(evidence.artifact_references),
                }
                for evidence in value.evidence
            ],
        }
    return value


def _run_input(args: argparse.Namespace) -> RunNextInput:
    return RunNextInput(
        actor_id=args.actor,
        executor_id=getattr(args, "executor", None),
        swarm_id=args.swarm,
        work_id=args.work,
        session_id=args.id,
        runner=args.runner,
        prepare_only=args.prepare_only,
        signature=args.signature,
        timeout_seconds=args.timeout_seconds,
        max_output_bytes=args.max_output_bytes,
    )


def _activity_context(
    workspace: AgoraWorkspace, args: argparse.Namespace
) -> ActivityContext | None:
    if args.command != "run" or args.prepare_only or args.explain:
        return None
    try:
        preview = workspace.preview_run(_run_input(args))
    except (FileNotFoundError, PermissionError, RuntimeError, ValueError):
        return ActivityContext(
            "Resolving governed action",
            args.work or "Next governed work",
            "Agora is checking durable state and actor authority",
            "Phase: preflight",
            args.actor or "next eligible actor",
            live_details=(
                "Resolving project, actor, role, and work references",
                "Checking lifecycle authority and authentication requirements",
                "Computing the bounded runtime before launch",
            ),
        )
    return _preview_activity_context(
        preview,
        args,
        live_detail_provider=_governed_activity_provider(
            workspace,
            swarm_id=preview.task.swarm_id,
            work_id=preview.task.work_id,
        ),
    )


def _preview_activity_context(
    preview: RunPreview,
    args: argparse.Namespace,
    *,
    live_detail_provider: Callable[[], str | None] | None = None,
) -> ActivityContext:
    task = preview.task
    targets = ", ".join(task.target_states) or "governed action"
    capabilities = ", ".join(preview.actor_capabilities) or "none declared"
    executor_capabilities = ", ".join(preview.executor_capabilities) or "none declared"
    authentication = (
        "signed authentication required"
        if preview.authentication_required
        else "local actor identity"
    )
    runtime = (
        "human action; no LLM launch"
        if preview.runtime_source == "not-applicable"
        else f"{preview.integration}/{preview.provider}/{preview.model}"
    )
    reference = f"{task.swarm_id}/{task.work_id}"
    headline = (
        f"Governed agent loop, max {args.max_steps} steps"
        if args.until_blocked
        else "Governed agent action"
    )
    preflight = [
        "AGORA PLAN  Safe execution preview",
        f"  Work       {preview.work_title} [{reference}]",
        f"  Responsible {task.actor} ({task.actor_kind}) as {task.role}",
        f"  Executor   {preview.executor} ({preview.executor_kind})",
        f"  Authority  {capabilities} | {authentication}",
        f"  Runtime    {runtime} ({preview.runtime_source})",
    ]
    boundary = f"  Boundary   {task.state} -> {targets}"
    if preview.timeout_seconds is not None and preview.max_output_bytes is not None:
        boundary += (
            f" | {preview.timeout_seconds}s | {_format_bytes(preview.max_output_bytes)} output"
        )
    preflight.append(boundary)
    if task.blockers:
        preflight.append(f"  Blockers   {'; '.join(task.blockers)}")
    live_details = [
        f"Runtime active within {task.state} -> {targets}",
        f"Executor capabilities: {executor_capabilities}",
        f"Role boundary enforced for {task.role}: {capabilities}",
        "Watching durable artifacts, evidence, tool runs, and transitions",
    ]
    if preview.max_output_bytes is not None:
        live_details.append(
            f"Capturing runner output within the {_format_bytes(preview.max_output_bytes)} limit"
        )
    return ActivityContext(
        headline=headline,
        subject=preview.work_title,
        summary=preview.work_description,
        phase=f"Phase: {task.state} -> {targets}",
        detail=(
            f"responsible={task.actor} | executor={preview.executor} | "
            f"{task.role} | {reference} | {preview.method}"
        ),
        safety=f"Authority: {capabilities} | {authentication} | {runtime}",
        preflight=tuple(preflight),
        live_details=tuple(live_details),
        live_detail_provider=live_detail_provider,
    )


def _governed_activity_provider(
    workspace: AgoraWorkspace,
    *,
    swarm_id: str,
    work_id: str,
    read_service: AgoraReadService | None = None,
) -> Callable[[], str | None]:
    reads = read_service or AgoraReadService(workspace)
    filters = ActivityFilters(swarm_id=swarm_id, work_id=work_id, limit=1)
    try:
        baseline = reads.activity(filters)
    except (OSError, RuntimeError, ValueError):
        baseline = []
    last_seen = _activity_identity(baseline[-1]) if baseline else None
    current_detail: str | None = None
    observed_at = 0.0
    next_poll = 0.0

    def latest_detail() -> str | None:
        nonlocal current_detail, last_seen, next_poll, observed_at
        now = time.monotonic()
        if now >= next_poll:
            next_poll = now + 0.75
            records = reads.activity(filters)
            if records:
                latest = records[-1]
                identity = _activity_identity(latest)
                if identity != last_seen:
                    last_seen = identity
                    current_detail = _activity_live_detail(latest.type, latest.summary)
                    observed_at = now
        if current_detail is not None and now - observed_at <= 6:
            return current_detail
        return None

    return latest_detail


def _activity_identity(record: Any) -> tuple[str, str, str]:
    return record.timestamp, record.type, record.source


def _activity_live_detail(type_: str, summary: str) -> str:
    labels = {
        "session.prepared": "Session prepared",
        "session.progress": "Agent progress",
        "artifact.added": "Artifact registered",
        "evidence.added": "Evidence recorded",
        "work.criterion-satisfied": "Acceptance criterion recorded",
        "work.transitioned": "Lifecycle advanced",
        "tool.prepared": "Tool run prepared",
        "tool.completed": "Tool run completed",
        "tool.failed": "Tool run failed",
    }
    label = labels.get(type_, type_.replace(".", " ").replace("-", " ").title())
    return f"{label} · {summary}"


def _format_bytes(value: int) -> str:
    if value >= 1024 * 1024:
        return f"{value / (1024 * 1024):g} MiB"
    if value >= 1024:
        return f"{value / 1024:g} KiB"
    return f"{value} B"


def _truncate_cell(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    return f"{value[: width - 1]}…"


def _render_status_board(reads: AgoraReadService) -> str:
    swarms = reads.list_swarms()
    if not swarms:
        return "Agora status board\n\nNo swarms in this project yet."
    lines = ["Agora status board"]
    cell_width = 36
    all_work = reads.list_work_items()
    for swarm in swarms:
        states = swarm.work_states
        grouped = {
            state: [item for item in all_work if item.swarm_id == swarm.id and item.state == state]
            for state in states
        }
        lines.extend(["", f"Swarm: {swarm.id}  method={swarm.method}"])
        border = "  +" + "+".join("-" * (cell_width + 2) for _ in states) + "+"
        lines.append(border)
        lines.append(
            "  |"
            + "|".join(f" {_truncate_cell(state, cell_width):<{cell_width}} " for state in states)
            + "|"
        )
        lines.append(border)
        row_count = max((len(items) for items in grouped.values()), default=0)
        for index in range(max(1, row_count)):
            cells: list[str] = []
            for state in states:
                items = grouped[state]
                if index >= len(items):
                    value = ""
                else:
                    item = items[index]
                    marker = "[!] " if item.operational_status == "blocked" else ""
                    value = f"{marker}{item.id}: {item.title}"
                cells.append(f" {_truncate_cell(value, cell_width):<{cell_width}} ")
            lines.append("  |" + "|".join(cells) + "|")
        lines.append(border)
    return "\n".join(lines)


def _run_continue_wizard(
    workspace: AgoraWorkspace,
    args: argparse.Namespace,
    *,
    input_stream: TextIO,
    output_stream: TextIO,
) -> dict[str, Any]:
    interactive = not args.yes
    if interactive and not input_stream.isatty():
        raise ValueError("agora continue needs an interactive terminal; use --yes for automation")
    tasks = workspace.next_actions(
        actor_id=args.actor,
        swarm_id=args.swarm,
        human_only=False,
        limit=1000,
    )
    if args.work is not None:
        tasks = [item for item in tasks if item.work_id == args.work]
    wizard = Wizard(input_stream, output_stream, brand="Agora Continue")
    if not tasks:
        if interactive:
            wizard.success("No governed action is currently eligible")
            wizard.next_steps((("agora status", "Review completed work and project attention."),))
        return {"ok": True, "applied": False, "status": "clear", "next_actions": []}

    task = tasks[0]
    if interactive and len(tasks) > 1:
        choices = [
            Choice(
                f"{item.swarm_id}/{item.work_id}",
                item.id,
                f"{item.actor or 'unassigned'} ({item.role or 'no role'}) · "
                f"{item.state or item.kind} -> {', '.join(item.target_states) or 'attention'}",
            )
            for item in tasks
        ]
        wizard.heading("Choose work", "Select one bounded governed action to inspect.")
        selected = wizard.choose("Eligible actions", choices)
        task = next(item for item in tasks if item.id == selected)

    scope = f"{task.swarm_id}/{task.work_id}"
    executor_id = getattr(args, "executor", None)
    diagnosis: dict[str, Any] | None = None
    if task.kind == "retry-session" and task.session_id is not None:
        failed_session = workspace.show_session(task.session_id)
        diagnosis = workspace.diagnose_session(task.session_id)
        if executor_id is None and failed_session.executor != failed_session.actor:
            executor_id = failed_session.executor
    if (task.actor_kind == "human" and executor_id is None) or task.actor is None:
        if interactive:
            wizard.heading(
                "Human attention",
                "The responsible role stays human. Choose how to continue without "
                "losing that boundary.",
            )
            wizard.rows(
                (
                    ("Work", scope),
                    ("Actor", task.actor or "unassigned"),
                    ("Role", task.role or "unassigned"),
                    ("State", task.state or "pending"),
                    ("Next", ", ".join(task.target_states) or "resolve assignment"),
                )
            )
            for blocker in task.blockers:
                wizard.warning(blocker)
            terminal_target = task.swarm_id is not None and workspace.is_terminal_work_target(
                task.swarm_id, task.target_states
            )
            choices = [
                Choice(
                    "Review and finish this work"
                    if terminal_target
                    else "Handle this decision myself",
                    "finish" if terminal_target else "human",
                    "Review evidence, record approval, and close through the Method Pack."
                    if terminal_target
                    else "Stop here with the exact governed boundary and no LLM session.",
                )
            ]
            executor_candidates: list[dict[str, str]] = []
            if (
                task.actor is not None
                and task.role is not None
                and task.swarm_id is not None
                and not terminal_target
            ):
                executor_candidates = workspace.executor_candidates(task.swarm_id, task.role)
                if executor_candidates:
                    choices.append(
                        Choice(
                            "Ask an AI actor to assist",
                            "assist",
                            "The human keeps the role; a compatible actor executes "
                            "this bounded step.",
                        )
                    )
            handoff_candidates = (
                workspace.handoff_candidates(task.swarm_id, task.role)
                if task.actor is not None and task.role is not None and task.swarm_id is not None
                else []
            )
            if handoff_candidates:
                choices.append(
                    Choice(
                        "Transfer role responsibility",
                        "handoff",
                        "Create a durable handoff because the responsible actor should "
                        "really change.",
                    )
                )
            decision = wizard.choose("How should Agora proceed", choices)
            if decision == "finish":
                return _finish_work_interactively(
                    workspace,
                    swarm_id=task.swarm_id,
                    work_id=task.work_id,
                    actor_hint=task.actor,
                    wizard=wizard,
                )
            if decision == "assist":
                selected = wizard.choose(
                    "Compatible AI executor",
                    [
                        Choice(
                            f"{item['name']} ({item['kind']})",
                            item["actor"],
                            item["capabilities"],
                        )
                        for item in executor_candidates
                    ],
                )
                executor_id = selected
            elif decision == "handoff":
                selected = wizard.choose(
                    "New responsible actor",
                    [
                        Choice(
                            f"{item['name']} ({item['kind']})",
                            item["actor"],
                            item["capabilities"],
                        )
                        for item in handoff_candidates
                    ],
                )
                reason = wizard.text("Reason for transferring responsibility")
                if not wizard.confirm("Create this formal role handoff", default=False):
                    wizard.success("Handoff cancelled", "No project mutation was created.")
                    return {"ok": True, "applied": False, "status": "cancelled"}
                handoff = workspace.handoff_actor(
                    HandoffActorInput(
                        swarm_id=task.swarm_id,
                        role_id=task.role,
                        from_actor_id=task.actor,
                        to_actor_id=selected,
                        authorized_by=task.actor,
                        reason=reason,
                        work_id=task.work_id,
                    )
                )
                wizard.success(
                    "Responsibility transferred",
                    f"{task.role} now belongs to {selected}; no LLM session was launched.",
                )
                wizard.next_steps(
                    (("agora continue", "Inspect the next action under the new assignment."),)
                )
                return {
                    "ok": True,
                    "applied": True,
                    "status": "handed-off",
                    "handoff": handoff,
                }
            else:
                wizard.next_steps(
                    (
                        (
                            f"agora next --swarm {task.swarm_id}",
                            "Review the exact gate obligations before recording the "
                            "human decision.",
                        ),
                        (
                            f"agora run --actor {task.actor} --swarm {task.swarm_id} "
                            f"--work {task.work_id} --explain",
                            "Inspect the role boundary without launching an LLM.",
                        ),
                    )
                )
                return {
                    "ok": True,
                    "applied": False,
                    "status": "human-attention",
                    "task": task,
                }
        else:
            return {
                "ok": True,
                "applied": False,
                "status": "human-attention",
                "task": task,
            }

    timeout_seconds = None
    max_output_bytes = None
    if diagnosis is not None:
        timeout_seconds = int(diagnosis["recommended_timeout_seconds"])
        max_output_bytes = int(diagnosis["recommended_max_output_bytes"])
        if interactive:
            wizard.heading(
                "Recover failed session",
                "Agora preserves the failed record and creates a bounded retry.",
            )
            wizard.rows(
                (
                    ("Session", str(diagnosis["id"])),
                    ("Cause", str(diagnosis["diagnosis"])),
                    ("Previous output", _format_bytes(int(diagnosis["output_bytes"]))),
                    ("Retry timeout", f"{timeout_seconds}s"),
                    ("Retry output", _format_bytes(max_output_bytes)),
                )
            )
            if not wizard.confirm("Retry with these reviewed bounds", default=True):
                wizard.success("Retry cancelled", "The failed session remains unchanged.")
                return {"ok": True, "applied": False, "status": "cancelled"}

    run_input = RunNextInput(
        actor_id=task.actor,
        executor_id=executor_id,
        swarm_id=task.swarm_id,
        work_id=task.work_id,
        runner=args.runner,
        timeout_seconds=timeout_seconds,
        max_output_bytes=max_output_bytes,
    )
    preview = workspace.preview_run(run_input)
    if interactive:
        wizard.heading(
            "Next governed action",
            "Review one bounded LLM action before Agora launches the configured runtime.",
        )
        wizard.rows(
            (
                ("Work", scope),
                ("Responsible", f"{task.actor} ({task.role})"),
                ("Executor", preview.executor or task.actor),
                ("Phase", f"{task.state} -> {', '.join(task.target_states)}"),
                ("Runtime", f"{preview.integration}/{preview.provider}/{preview.model}"),
                ("Timeout", f"{preview.timeout_seconds}s"),
                ("Output", _format_bytes(preview.max_output_bytes or 0)),
            )
        )
        for blocker in task.blockers:
            wizard.warning(blocker)
        if not wizard.confirm("Run this governed agent action", default=True):
            wizard.success("Execution cancelled", "No session or project mutation was created.")
            return {
                "ok": True,
                "applied": False,
                "status": "cancelled",
                "preview": preview,
            }

    context = _preview_activity_context(
        preview,
        args,
        live_detail_provider=_governed_activity_provider(
            workspace,
            swarm_id=task.swarm_id or "",
            work_id=task.work_id or "",
        ),
    )
    with ConsoleActivity(output_stream, context) as activity:
        if args.until_blocked:
            result: Any = workspace.run_until_blocked(
                run_input,
                max_steps=args.max_steps,
                observer=activity.handle_run_event,
            )
        else:
            result = workspace.run_next(run_input)
    next_actions = workspace.next_actions(swarm_id=task.swarm_id, limit=20)
    if interactive:
        wizard.success("Governed action completed", f"Agora persisted the session for {scope}.")
        if any(item.actor_kind == "human" for item in next_actions):
            wizard.warning("Human attention is now required; Agora stopped before that decision.")
        wizard.next_steps(
            (
                ("agora continue", "Inspect and perform the next governed action."),
                (f"agora next --swarm {task.swarm_id}", "Review all currently eligible actions."),
            )
        )
    return {
        "ok": True,
        "applied": True,
        "status": "completed",
        "result": result,
        "next_actions": next_actions,
    }


def _run_work_start_wizard(
    workspace: AgoraWorkspace,
    args: argparse.Namespace,
    *,
    input_stream: TextIO,
    output_stream: TextIO,
) -> dict[str, Any]:
    if not input_stream.isatty():
        raise ValueError(
            "agora work start needs an interactive terminal; use work create in automation"
        )
    wizard = Wizard(input_stream, output_stream, brand="Agora Work")
    swarms = [item for item in workspace.list_swarms() if item.status in {"ready", "running"}]
    if not swarms:
        raise ValueError(
            "No ready swarm is available; finish role assignments before starting work"
        )
    swarm = next((item for item in swarms if item.id == args.swarm), None)
    if args.swarm is not None and swarm is None:
        raise ValueError(f"Swarm {args.swarm} is not ready or does not exist")
    if swarm is None:
        wizard.heading("Swarm", "Choose the governed team and Method Pack for this work.")
        selected = wizard.choose(
            "Ready swarms",
            [
                Choice(
                    item.id,
                    item.id,
                    f"{item.method} · {item.objective}",
                )
                for item in swarms
            ],
        )
        swarm = next(item for item in swarms if item.id == selected)

    candidates = workspace.action_candidates(swarm.id, "work.create", "artifact.add")
    if not candidates:
        raise ValueError(
            f"Swarm {swarm.id} has no assigned actor allowed to create work and register artifacts"
        )
    if len(candidates) == 1:
        creator = candidates[0]
    else:
        wizard.heading("Responsible actor", "Select who owns creation of this durable work item.")
        selected_actor = wizard.choose(
            "Compatible assigned actors",
            [
                Choice(
                    str(item["name"]),
                    str(item["actor"]),
                    f"{item['actor']} · {item['kind']} as {item['role']}",
                )
                for item in candidates
            ],
        )
        creator = next(item for item in candidates if item["actor"] == selected_actor)

    wizard.heading("Work", "Describe one reviewable increment. Nothing is written before review.")
    title = wizard.text("Title")
    default_id = _work_id_from_title(title)
    work_id = wizard.text(
        "Work id",
        default=default_id,
        validate=lambda value: (
            None
            if re.fullmatch(r"[a-z][a-z0-9-]*", value)
            else "Use a lowercase id with letters, digits, and hyphens."
        ),
    )
    description = wizard.text("Description", default=title)
    criterion_count = wizard.integer("Number of acceptance criteria", default=1, minimum=1)
    criteria: list[tuple[str, str]] = []
    for index in range(1, criterion_count + 1):
        criterion_description = wizard.text(f"Criterion {index}")
        default_criterion_id = _work_id_from_title(criterion_description)[:48].rstrip("-")
        criterion_id = wizard.text(
            f"Criterion {index} id",
            default=default_criterion_id,
            validate=lambda value: (
                None
                if re.fullmatch(r"[a-z][a-z0-9-]*", value)
                else "Use a lowercase id with letters, digits, and hyphens."
            ),
        )
        criteria.append((criterion_id, criterion_description))

    default_artifacts = "spec" if swarm.method == "spec-driven" else "none"
    artifact_text = wizard.text(
        "Required artifact kinds (comma separated, or none)", default=default_artifacts
    )
    required_artifacts = (
        []
        if artifact_text.strip().lower() == "none"
        else list(dict.fromkeys(item.strip() for item in artifact_text.split(",") if item.strip()))
    )
    if any(re.fullmatch(r"[a-z][a-z0-9-]*", item) is None for item in required_artifacts):
        raise ValueError("Required artifact kinds must be lowercase ids")

    spec_uri: str | None = None
    if "spec" in required_artifacts:
        wizard.note("Press Enter to register the specification later through the assigned role.")
        spec_value = wizard.optional_text("Existing specification path")
        if spec_value is not None:
            root = workspace.project_root()
            spec_path = (root / spec_value).resolve()
            try:
                relative_spec = spec_path.relative_to(root)
            except ValueError as error:
                raise ValueError("Specification path must stay inside the project") from error
            if not spec_path.is_file():
                raise FileNotFoundError(f"Specification file not found: {spec_path}")
            spec_uri = f"repo://{relative_spec.as_posix()}"

    wizard.review(
        (
            ("Swarm", swarm.id),
            ("Method", swarm.method),
            ("Actor", f"{creator['actor']} ({creator['role']})"),
            ("Work", work_id),
            ("Title", title),
            ("Criteria", str(len(criteria))),
            ("Required artifacts", ", ".join(required_artifacts) or "none"),
            ("Registered spec", spec_uri or "later"),
        )
    )
    if not wizard.confirm("Create this governed work item", default=True):
        wizard.success("Work creation cancelled", "No project files were changed.")
        return {"ok": True, "applied": False, "status": "cancelled"}

    work = workspace.create_work(
        CreateWorkInput(
            swarm_id=swarm.id,
            id=work_id,
            title=title,
            actor_id=str(creator["actor"]),
            acceptance_criteria=criteria,
            required_artifacts=required_artifacts,
            description=description,
        )
    )
    if spec_uri is not None:
        work = workspace.add_artifact(
            AddArtifactInput(
                swarm_id=swarm.id,
                work_id=work_id,
                actor_id=str(creator["actor"]),
                kind="spec",
                uri=spec_uri,
            )
        )
    wizard.success("Governed work created", f"{swarm.id}/{work_id} is ready in {work.state}.")
    wizard.next_steps(
        (
            ("agora continue", "Inspect and perform the next bounded governed action."),
            (f"agora next --swarm {swarm.id}", "Review every currently eligible action."),
        )
    )
    return {
        "ok": True,
        "applied": True,
        "status": "created",
        "work": work,
        "spec_registered": spec_uri is not None,
    }


def _run_work_finish_wizard(
    workspace: AgoraWorkspace,
    args: argparse.Namespace,
    *,
    input_stream: TextIO,
    output_stream: TextIO,
) -> dict[str, Any]:
    if not input_stream.isatty():
        raise ValueError(
            "agora work finish needs an interactive terminal; use approval add and "
            "work transition in automation"
        )
    wizard = Wizard(input_stream, output_stream, brand="Agora Finish")
    candidates = [
        item
        for item in workspace.next_actions(swarm_id=args.swarm, limit=1000)
        if item.work_id is not None
        and item.swarm_id is not None
        and workspace.is_terminal_work_target(item.swarm_id, item.target_states)
        and (args.work is None or item.work_id == args.work)
    ]
    if not candidates:
        raise ValueError("No work item is currently at a Method Pack completion boundary")
    task = candidates[0]
    if len(candidates) > 1:
        selected = wizard.choose(
            "Work to review",
            [
                Choice(
                    f"{item.swarm_id}/{item.work_id}",
                    item.id,
                    f"{item.actor} ({item.role}) · {item.state} -> {', '.join(item.target_states)}",
                )
                for item in candidates
            ],
        )
        task = next(item for item in candidates if item.id == selected)
    return _finish_work_interactively(
        workspace,
        swarm_id=task.swarm_id or "",
        work_id=task.work_id or "",
        actor_hint=args.by or task.actor,
        wizard=wizard,
    )


def _finish_work_interactively(
    workspace: AgoraWorkspace,
    *,
    swarm_id: str,
    work_id: str,
    actor_hint: str | None,
    wizard: Wizard,
) -> dict[str, Any]:
    readiness = workspace.completion_readiness(swarm_id, work_id)
    gate = readiness["gate"]
    wizard.heading(
        "Human review",
        "Agora will record approval only after you explicitly confirm the durable evidence.",
    )
    wizard.rows(
        (
            ("Work", f"{swarm_id}/{work_id}"),
            ("Title", readiness["title"]),
            ("Method", readiness["method"]),
            ("Phase", f"{readiness['state']} -> {readiness['target_state']}"),
            ("Gate", gate["gate"] or "none"),
            ("Criterion stage", gate["required_criterion_stage"]),
        )
    )
    review_rows = (
        ("Criteria", gate["unsatisfied"]),
        ("Artifacts", gate["missing_artifacts"]),
        ("Evidence types", gate["missing_evidence_types"]),
        ("Git", gate["git_issues"]),
        ("Dependencies", readiness["blockers"]),
    )
    for label, missing in review_rows:
        wizard.check(
            label,
            "ready" if not missing else "missing: " + ", ".join(missing),
            ok=not missing,
        )
    wizard.check(
        "Successful evidence",
        "recorded" if not gate["evidence_missing"] else "missing",
        ok=not gate["evidence_missing"],
    )
    if not readiness["ready_for_human_approval"]:
        wizard.warning("Delivery evidence is incomplete; Agora did not record an approval.")
        wizard.next_steps(
            (
                (
                    f"agora next --swarm {swarm_id}",
                    "Resolve the listed Method Pack obligations, then run agora work finish.",
                ),
            )
        )
        return {
            "ok": True,
            "applied": False,
            "status": "evidence-incomplete",
            "readiness": readiness,
        }

    approved_by: list[str] = []
    for role_id in gate["missing_approvals"]:
        role_candidates = sorted(
            [
                item
                for item in workspace.action_candidates(swarm_id, "approval.add")
                if item["role"] == role_id
            ],
            key=lambda item: (
                item["actor"] != actor_hint if actor_hint is not None else False,
                item["kind"] != "human",
                item["actor"],
            ),
        )
        if not role_candidates:
            wizard.warning(
                f"Approval {role_id} still needs its assigned actor; no approval was invented."
            )
            return {
                "ok": True,
                "applied": False,
                "status": "approval-required",
                "readiness": readiness,
            }
        candidate = role_candidates[0]
        wizard.section(f"Approval: {role_id}")
        wizard.rows((("Responsible", f"{candidate['actor']} ({candidate['kind']})"),))
        if not wizard.confirm(
            "I reviewed the implementation and evidence for this approval",
            default=False,
        ):
            wizard.success("Review paused", "No approval or completion transition was recorded.")
            return {"ok": True, "applied": False, "status": "review-paused"}
        note = wizard.text("Approval note", default="Reviewed and accepted")
        workspace.add_approval(
            AddApprovalInput(
                swarm_id=swarm_id,
                work_id=work_id,
                role_id=role_id,
                actor_id=candidate["actor"],
                note=note,
            )
        )
        approved_by.append(candidate["actor"])

    readiness = workspace.completion_readiness(swarm_id, work_id)
    if not readiness["ready_to_complete"]:
        wizard.warning("Approval was recorded, but the completion gate still needs attention.")
        return {
            "ok": True,
            "applied": bool(approved_by),
            "status": "completion-blocked",
            "readiness": readiness,
        }
    transition_candidates = sorted(
        [
            item
            for item in workspace.action_candidates(swarm_id, "work.transition")
            if item["role"] in readiness["roles"]
        ],
        key=lambda item: (
            item["actor"] != actor_hint if actor_hint is not None else False,
            item["kind"] != "human",
            item["actor"],
        ),
    )
    if not transition_candidates:
        raise PermissionError("No assigned actor can apply the Method Pack completion transition")
    transition_actor = transition_candidates[0]["actor"]
    if not wizard.confirm("Complete this work item", default=True):
        wizard.success("Approval recorded", "The work remains at its review boundary.")
        return {
            "ok": True,
            "applied": bool(approved_by),
            "status": "approved",
            "readiness": readiness,
        }
    completed = workspace.transition_work(
        TransitionWorkInput(
            swarm_id=swarm_id,
            work_id=work_id,
            actor_id=transition_actor,
            target_state=readiness["target_state"],
        )
    )
    wizard.success(
        "Work completed",
        f"{swarm_id}/{work_id} reached {readiness['target_state']} through its Method Pack.",
    )
    wizard.next_steps((("agora continue", "Move to the next governed work item."),))
    return {
        "ok": True,
        "applied": True,
        "status": "completed",
        "work": completed,
        "approved_by": approved_by,
    }


def _work_id_from_title(title: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not value or not value[0].isalpha():
        value = f"work-{value}".rstrip("-")
    return value[:64].rstrip("-")


def _add_guided_setup_arguments(parser: argparse.ArgumentParser, *, default_id: str) -> None:
    parser.add_argument("--path", help="Project directory (default: current directory)")
    parser.add_argument(
        "--id", default=default_id, help=f"Starter swarm id (default: {default_id})"
    )
    parser.add_argument("--objective", help="First governed objective")
    parser.add_argument("--integration", choices=INTEGRATIONS)
    parser.add_argument("--provider", help="Provider label persisted in project configuration")
    parser.add_argument("--model", help="Model selection or native CLI configuration marker")
    parser.add_argument("--method", metavar="METHOD_ID")
    parser.add_argument("--max-delegation-depth", type=int)
    parser.add_argument("--base", help="Expected current Git branch")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Accept reviewed existing working-tree changes",
    )
    parser.add_argument("--secure", action="store_true", help="Generate signed actor identities")
    parser.add_argument("--key-dir", help="External directory for generated actor keypairs")
    parser.add_argument(
        "--save-user-defaults",
        action="store_true",
        help="Reuse the selected runtime and method for future projects",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Use flags only; requires --yes and an objective for new projects",
    )
    parser.add_argument("--yes", action="store_true", help="Apply the reviewed setup plan")


def _run_setup_wizard(
    workspace: AgoraWorkspace,
    args: argparse.Namespace,
    *,
    input_stream: TextIO,
    output_stream: TextIO,
) -> dict[str, Any]:
    mode = "adopt" if args.command == "adopt" else "setup"
    interactive = not args.non_interactive
    if interactive and not input_stream.isatty():
        raise ValueError(
            f"agora {mode} needs an interactive terminal; use --non-interactive --yes "
            "with explicit flags for automation"
        )
    if not interactive and not args.yes:
        raise ValueError("--non-interactive requires --yes before applying setup")

    wizard = Wizard(input_stream, output_stream)
    if interactive:
        wizard.heading(
            "Project",
            (
                "Adopt an existing Git repository through a read-only preflight."
                if mode == "adopt"
                else "Select a project to initialize or review its existing Agora configuration."
            ),
        )
    path_value = args.path or "."
    if interactive and args.path is None:
        path_value = wizard.text("Project path", default=".")
    target = (workspace.cwd / path_value).resolve()
    initialized = (target / ".agora" / "project.md").is_file()
    if mode == "adopt" and initialized:
        raise ValueError("This repository is already initialized; use agora setup")
    if mode == "adopt" and (not target.is_dir() or not is_git_repository(target)):
        raise ValueError("agora adopt requires an existing Git repository")

    target_workspace = AgoraWorkspace(cwd=target)
    existing = target_workspace.show_project() if initialized else None
    detected_clis = [
        executable
        for executable in (
            "codex",
            "claude",
            "gh",
            "glab",
            "acli",
            "terraform",
            "aws",
            "gcloud",
            "twg",
        )
        if shutil.which(executable) is not None
    ]

    if existing is not None:
        return _review_existing_setup(
            target_workspace,
            existing,
            args,
            wizard=wizard,
            interactive=interactive,
            detected_clis=detected_clis,
        )
    if not interactive and not args.objective:
        raise ValueError("--non-interactive requires --objective for a new project")

    default_integration = (
        "codex"
        if shutil.which("codex") is not None
        else "claude"
        if shutil.which("claude") is not None
        else "generic"
    )
    integration = args.integration or default_integration
    if interactive and args.integration is None:
        runtime_choices = [
            Choice("Codex CLI", "codex", "Use the installed native Codex runtime."),
            Choice("Claude CLI", "claude", "Use the installed native Claude runtime."),
            Choice("Generic runner", "generic", "Provide a structured runner when executing."),
        ]
        default_index = next(
            index
            for index, choice in enumerate(runtime_choices)
            if choice.value == default_integration
        )
        wizard.heading("LLM runtime")
        integration = wizard.choose(
            "Select the project runtime", runtime_choices, default=default_index
        )
    provider_defaults = {
        "codex": "openai",
        "claude": "anthropic",
        "generic": "configured-by-runner",
    }
    model_defaults = {
        "codex": "configured-by-codex",
        "claude": "configured-by-claude",
        "generic": "configured-by-runner",
    }
    provider = args.provider or provider_defaults[integration]
    model = args.model or model_defaults[integration]
    if interactive and args.provider is None:
        provider = wizard.text("Provider label", default=provider)
    if interactive and args.model is None:
        model = wizard.text("Model", default=model)
    maximum_depth = args.max_delegation_depth if args.max_delegation_depth is not None else 3
    if interactive and args.max_delegation_depth is None:
        maximum_depth = wizard.integer("Maximum swarm delegation depth", default=maximum_depth)

    method = args.method or "spec-driven"
    if interactive and args.method is None:
        wizard.heading("Development method")
        method_choices = [
            Choice(
                "Spec-Driven", "spec-driven", "Clarify a durable specification before planning."
            ),
            Choice("Scrum", "scrum", "Deliver increments through explicit team roles and gates."),
            Choice("Kanban", "kanban", "Pull continuous work under WIP and acceptance policy."),
        ]
        method_choices.append(
            Choice("Custom installed Method Pack", "custom", "Enter an installed Method Pack id.")
        )
        default_index = next(
            index for index, choice in enumerate(method_choices) if choice.value == method
        )
        method = wizard.choose("Select the work lifecycle", method_choices, default=default_index)
        if method == "custom":
            method = wizard.text("Method Pack id")

    swarm_id = args.id
    objective = args.objective or ""
    if interactive:
        wizard.heading("Starter team")
        if args.objective is None:
            objective = wizard.text("First governed objective")
        swarm_id = wizard.text("Starter swarm id", default=swarm_id)

    secure = args.secure
    key_directory = args.key_dir
    if interactive and not args.secure:
        wizard.heading("Actor security")
        secure = (
            wizard.choose(
                "Select actor authentication",
                (
                    Choice(
                        "Local identity",
                        "local",
                        "Fast onboarding; filesystem and Method Pack rules still apply.",
                    ),
                    Choice(
                        "Signed Ed25519 actors",
                        "signed",
                        "Generate external local keypairs and require signed operations.",
                    ),
                ),
            )
            == "signed"
        )
    if secure and interactive and key_directory is None:
        if not wizard.confirm("Use Agora's default external key directory", default=True):
            key_directory = wizard.text("External actor key directory")

    git_enabled = target.is_dir() and is_git_repository(target)
    base_branch = args.base
    if git_enabled:
        initial_report = target_workspace.check_adoption(
            AdoptionInput(
                swarm_id=swarm_id,
                base_branch=None,
                allow_dirty=False,
                integration=integration,
                model=model,
            )
        )
        if interactive and args.base is None:
            base_branch = wizard.text("Git base branch", default=initial_report.branch or "main")
        dirty = next((check for check in initial_report.checks if check.name == "git-clean"), None)
        allow_dirty = args.allow_dirty
        if dirty is not None and not dirty.ok and interactive and not allow_dirty:
            allow_dirty = wizard.confirm(
                "The working tree has changes. Continue without discarding them", default=False
            )
        report = target_workspace.check_adoption(
            AdoptionInput(
                swarm_id=swarm_id,
                base_branch=base_branch,
                allow_dirty=allow_dirty,
                integration=integration,
                model=model,
            )
        )
        failed = [check for check in report.checks if not check.ok]
        if failed:
            detail = "; ".join(f"{check.name}: {check.detail}" for check in failed)
            raise ValueError(f"Setup preflight failed: {detail}")
    else:
        allow_dirty = args.allow_dirty
        base_branch = None
        report = None

    save_user_defaults = args.save_user_defaults
    if interactive and not args.save_user_defaults:
        save_user_defaults = wizard.confirm(
            "Reuse this runtime and method as defaults for future projects", default=False
        )
    if (
        save_user_defaults
        and method not in BUILTIN_METHODS
        and not (agora_home() / "methods" / method / "METHOD.md").is_file()
    ):
        raise ValueError(
            "A custom Method Pack must be installed at user scope before it can become a "
            "user default"
        )

    if interactive:
        wizard.review(
            (
                ("Mode", mode),
                ("Project", str(target)),
                ("Runtime", f"{integration}/{provider}/{model}"),
                ("Method", method),
                ("Swarm", swarm_id),
                ("Objective", objective),
                ("Security", "signed Ed25519" if secure else "local identity"),
                ("Git branch", f"agora/{swarm_id}" if git_enabled else "filesystem-only"),
                ("Detected CLIs", ", ".join(detected_clis) or "none"),
                ("User defaults", "update" if save_user_defaults else "unchanged"),
            )
        )
        if not args.yes and not wizard.confirm("Apply this setup plan", default=True):
            wizard.note("Setup cancelled; no project files were changed.")
            return {"ok": True, "applied": False, "mode": mode, "target": str(target)}

    result = target_workspace.quickstart(
        QuickstartInput(
            swarm_id=swarm_id,
            objective=objective,
            method=method,
            secure=secure,
            key_directory=key_directory,
            base_branch=base_branch,
            allow_dirty=allow_dirty,
            integration=integration,
            provider=provider,
            model=model,
            max_delegation_depth=maximum_depth,
            entrypoint=mode,
        )
    )
    if save_user_defaults:
        target_workspace.configure(
            ConfigureInput(
                integration=integration,
                provider=provider,
                model=model,
                default_method=method,
                max_delegation_depth=maximum_depth,
                force=True,
            )
        )
    validation = target_workspace.validate()
    doctor = target_workspace.doctor()
    doctor_ok = all(check.ok or check.name == "git" for check in doctor)
    if interactive:
        if validation.ok and doctor_ok:
            wizard.success(
                "Agora project is ready",
                "The starter team is governed, persisted, and ready to receive work.",
            )
        else:
            wizard.warning("Setup completed, but one or more checks need attention")
        wizard.section("Project")
        wizard.rows(
            (
                ("Path", str(target)),
                ("Runtime", f"{integration}/{provider}/{model}"),
                ("Method", method),
                ("Swarm", f"{result.swarm.id} ({result.swarm.status})"),
                ("Actors", f"{result.human_actor}, {result.ai_actor}"),
                ("Security", "signed Ed25519" if secure else "local identity"),
            )
        )
        wizard.section("Checks")
        wizard.check("Doctor", f"{sum(check.ok for check in doctor)}/{len(doctor)} passed")
        wizard.check("Validation", f"{len(validation.issues)} issues", ok=validation.ok)
        wizard.check("Persistence", "Project state and activity ledger written")
        wizard.next_steps(
            (
                ("agora status", "See the governed project at a glance."),
                ("agora work start", "Create the first work item through a reviewed wizard."),
                ("agora continue", "Inspect and perform one bounded governed action."),
            )
        )
    return {
        "ok": validation.ok and doctor_ok,
        "applied": True,
        "mode": mode,
        "target": str(target),
        "setup": result,
        "user_defaults_saved": save_user_defaults,
        "doctor": doctor,
        "validation": validation,
    }


def _review_existing_setup(
    workspace: AgoraWorkspace,
    existing: ProjectConfiguration,
    args: argparse.Namespace,
    *,
    wizard: Wizard,
    interactive: bool,
    detected_clis: list[str],
) -> dict[str, Any]:
    requested_values = {
        "integration": args.integration,
        "provider": args.provider,
        "model": args.model,
        "default_method": args.method,
        "max_delegation_depth": args.max_delegation_depth,
    }
    changed = [
        name.replace("default_method", "method").replace("max_delegation_depth", "depth")
        for name, requested in requested_values.items()
        if requested is not None and requested != getattr(existing, name)
    ]
    if changed:
        raise ValueError(
            "This Agora project is already initialized; setup will not replace its "
            f"{', '.join(changed)}. Use explicit configuration and migration commands."
        )
    if args.secure or args.key_dir is not None:
        raise ValueError(
            "This Agora project is already initialized; setup cannot replace existing actor "
            "identities. Add or rotate authenticated actors explicitly."
        )

    status = workspace.status()
    if interactive:
        wizard.heading(
            "Existing project",
            "Agora is already initialized. Setup will review and validate it without recreating "
            "actors, swarms, or work.",
        )
        wizard.review(
            (
                ("Project", existing.project),
                ("Path", str(workspace.project_root())),
                (
                    "Runtime",
                    f"{existing.integration}/{existing.provider}/{existing.model}",
                ),
                ("Method", existing.default_method),
                ("Git branch", status.branch),
                ("Actors", str(status.counts["actors"])),
                ("Swarms", str(status.counts["swarms"])),
                ("Work items", str(status.counts["work"])),
                ("Detected CLIs", ", ".join(detected_clis) or "none"),
            )
        )

    save_user_defaults = args.save_user_defaults
    if interactive and not args.save_user_defaults:
        save_user_defaults = wizard.confirm(
            "Reuse this project's runtime and method as defaults for future projects",
            default=False,
        )
    if (
        save_user_defaults
        and existing.default_method not in BUILTIN_METHODS
        and not (agora_home() / "methods" / existing.default_method / "METHOD.md").is_file()
    ):
        raise ValueError(
            "A custom Method Pack must be installed at user scope before it can become a "
            "user default"
        )

    if interactive and not args.yes:
        if not wizard.confirm("Run doctor and validation checks", default=True):
            wizard.note("Setup review cancelled; no project files were changed.")
            return {
                "ok": True,
                "applied": False,
                "mode": "setup-existing",
                "action": "cancelled",
                "target": str(workspace.project_root()),
            }

    if save_user_defaults:
        workspace.configure(
            ConfigureInput(
                integration=existing.integration,
                provider=existing.provider,
                model=existing.model,
                default_method=existing.default_method,
                max_delegation_depth=existing.max_delegation_depth,
                force=True,
            )
        )
    doctor = workspace.doctor()
    validation = workspace.validate()
    doctor_ok = all(check.ok or check.name == "git" for check in doctor)
    if interactive:
        passed_doctor = sum(check.ok for check in doctor)
        if validation.ok and doctor_ok:
            wizard.success(
                "Agora project is ready",
                "Existing governance state was checked without recreating actors, swarms, or work.",
            )
        else:
            wizard.warning("Agora project needs attention before governed work continues")
        wizard.section("Project")
        wizard.rows(
            (
                ("Name", existing.project),
                ("Runtime", f"{existing.integration}/{existing.provider}/{existing.model}"),
                ("Method", existing.default_method),
                ("Branch", status.branch),
                (
                    "State",
                    f"{status.counts['actors']} actors · {status.counts['swarms']} swarms · "
                    f"{status.counts['work']} work items · {status.counts['sessions']} sessions",
                ),
            )
        )
        wizard.section("Checks")
        wizard.check("Doctor", f"{passed_doctor}/{len(doctor)} passed", ok=doctor_ok)
        wizard.check("Validation", f"{len(validation.issues)} issues", ok=validation.ok)
        wizard.check("State preserved", "No actors, swarms, or work were recreated")
        wizard.check(
            "User defaults",
            "Saved for future projects" if save_user_defaults else "Unchanged",
        )
        attention = status.attention
        active_work = attention["active-work"]
        failed_sessions = attention["failed-sessions"]
        if active_work or failed_sessions:
            wizard.section("Attention")
            if active_work:
                wizard.rows((("Active work", ", ".join(active_work)),))
            if failed_sessions:
                wizard.warning(f"{len(failed_sessions)} previous failed sessions remain recorded")
        next_commands: list[tuple[str, str]] = [
            ("agora status", "Review active work and recorded attention."),
        ]
        if active_work:
            swarm_id = active_work[0].split("/", 1)[0]
            next_commands.append(
                (
                    f"agora continue --swarm {swarm_id}",
                    "Inspect and perform one bounded governed action.",
                )
            )
        else:
            next_commands.append(
                ("agora work start", "Create governed work through a reviewed wizard.")
            )
        wizard.next_steps(next_commands)
    return {
        "ok": validation.ok and doctor_ok,
        "applied": save_user_defaults,
        "mode": "setup-existing",
        "action": "validated-existing-project",
        "target": str(workspace.project_root()),
        "user_defaults_saved": save_user_defaults,
        "status": status,
        "doctor": doctor,
        "validation": validation,
    }


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

    setup = commands.add_parser(
        "setup", help="Configure and bootstrap Agora through a guided workflow"
    )
    _add_guided_setup_arguments(setup, default_id="delivery")

    configure = commands.add_parser("configure", help="Persist user-level defaults")
    configure.add_argument("--integration", choices=INTEGRATIONS, default="generic")
    configure.add_argument("--provider", default="configured-by-integration")
    configure.add_argument("--model", default="configured-by-integration")
    configure.add_argument(
        "--default-method",
        default="spec-driven",
        metavar="METHOD_ID",
        help="Installed Method Pack to use by default (default: spec-driven)",
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

    adopt = commands.add_parser(
        "adopt", help="Adopt an existing Git repository or run its read-only preflight"
    )
    adopt.add_argument(
        "--check", action="store_true", help="Run only the read-only adoption preflight"
    )
    _add_guided_setup_arguments(adopt, default_id="delivery")

    quickstart = commands.add_parser(
        "quickstart",
        help="Scaffold a runnable project: init, a human and an AI actor, a swarm, and roles",
    )
    quickstart.add_argument("--path")
    quickstart.add_argument("--id", default="quickstart", help="Swarm id (default: quickstart)")
    quickstart.add_argument("--objective", default="Deliver the objective")
    quickstart.add_argument("--method", metavar="METHOD_ID")
    quickstart.add_argument("--base", help="Expected current base branch")
    quickstart.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Accept existing working-tree changes after reporting them",
    )
    quickstart.add_argument(
        "--secure",
        action="store_true",
        help=(
            "Require signed authentication for the created actors. Generates a local "
            "Ed25519 keypair per actor for quickstart use; see docs/guides/"
            "actor-authentication.md before relying on this for production actors."
        ),
    )
    quickstart.add_argument(
        "--key-dir",
        help="External directory for quickstart keypairs (secure mode only)",
    )

    commands.add_parser("doctor", help="Check environment prerequisites")
    commands.add_parser(
        "self-test",
        help="Exercise bundled methods with human, AI, and swarm role holders",
    )
    status = commands.add_parser("status", help="Summarize operational project state")
    status.add_argument(
        "--board", action="store_true", help="Render a terminal-native board across swarms"
    )
    commands.add_parser("validate", help="Validate every Agora record and reference")
    next_action = commands.add_parser("next", help="Show the next governed operational actions")
    next_action.add_argument("--actor")
    next_action.add_argument("--swarm")
    next_action.add_argument("--limit", type=int, default=20)
    inbox = commands.add_parser("inbox", help="Show work requiring human attention")
    inbox.add_argument("--actor")
    inbox.add_argument("--swarm")
    inbox.add_argument("--limit", type=int, default=20)
    continue_action = commands.add_parser(
        "continue", help="Interactively inspect and perform the next governed action"
    )
    continue_action.add_argument("--actor")
    continue_action.add_argument("--executor")
    continue_action.add_argument("--swarm")
    continue_action.add_argument("--work")
    continue_action.add_argument(
        "--runner", help="External structured runner command for a generic integration"
    )
    continue_action.add_argument(
        "--yes", action="store_true", help="Run the selected agent action without prompting"
    )
    continue_action.add_argument(
        "--until-blocked",
        action="store_true",
        help="Repeat agent actions until human attention or no governed progress",
    )
    continue_action.add_argument("--max-steps", type=int, default=20)
    run = commands.add_parser("run", help="Prepare or launch the next eligible agent action")
    run.add_argument("--actor")
    run.add_argument("--executor")
    run.add_argument("--swarm")
    run.add_argument("--work")
    run.add_argument("--id")
    run.add_argument("--runner", help="External structured runner command")
    run.add_argument("--prepare-only", action="store_true")
    run.add_argument("--signature", help="Signature for an already prepared session")
    run.add_argument("--timeout-seconds", type=int)
    run.add_argument("--max-output-bytes", type=int)
    run.add_argument(
        "--explain",
        action="store_true",
        help="Explain the next governed action and security boundary without executing it",
    )
    run.add_argument(
        "--until-blocked",
        action="store_true",
        help="Repeat bounded agent steps until human attention or no governed progress",
    )
    run.add_argument("--max-steps", type=int, default=20)
    resume = commands.add_parser("resume", help="Resume a prepared or failed actor session")
    resume.add_argument("--session", required=True)
    resume.add_argument("--id", help="Replacement id when retrying a failed session")
    resume.add_argument("--runner", help="Replacement external runner command")
    resume.add_argument("--prepare-only", action="store_true")
    resume.add_argument("--signature", help="Raw Ed25519 session authorization signature")
    resume.add_argument("--timeout-seconds", type=int)
    resume.add_argument("--max-output-bytes", type=int)
    environment = commands.add_parser(
        "environment", help="Manage project-defined execution environment policies"
    ).add_subparsers(dest="environment_command", required=True)
    environment_add = environment.add_parser("add", help="Add an environment policy")
    environment_add.add_argument("--id", required=True)
    environment_add.add_argument("--name", required=True)
    environment_add.add_argument("--capability", action="append", default=[])
    environment_add.add_argument("--required-approval-role", action="append", default=[])
    environment_add.add_argument("--require-successful-evidence", action="store_true")
    environment_add.add_argument("--force", action="store_true")
    environment_show = environment.add_parser("show", help="Show an environment policy")
    environment_show.add_argument("--id", required=True)
    environment.add_parser("list", help="List environment policies")
    lock = commands.add_parser("lock", help="Inspect local writer coordination").add_subparsers(
        dest="lock_command", required=True
    )
    lock_status = lock.add_parser("status", help="Show a project or user write lock")
    lock_status.add_argument("--scope", choices=("project", "user"), default="project")
    coordination = commands.add_parser(
        "coordination", help="Configure optional cross-host writer leases"
    ).add_subparsers(dest="coordination_command", required=True)
    coordination_configure = coordination.add_parser(
        "configure", help="Persist project writer coordination policy"
    )
    coordination_configure.add_argument(
        "--mode", choices=("local", "external-lease"), required=True
    )
    coordination_configure.add_argument("--resource-id")
    coordination_configure.add_argument("--executable")
    coordination_configure.add_argument("--argument", action="append", default=[])
    coordination_configure.add_argument("--version-argument", action="append", default=[])
    coordination_configure.add_argument("--minimum-runtime-version")
    coordination_configure.add_argument("--lease-seconds", type=int, default=300)
    coordination_configure.add_argument("--command-timeout-seconds", type=int, default=10)
    coordination_configure.add_argument("--force", action="store_true")
    coordination.add_parser("show", help="Show effective writer coordination policy")
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
        "--signature-threshold",
        type=int,
        default=0,
        help="Require this many distinct trusted release signatures",
    )
    registry_install.add_argument(
        "--require-transparency",
        action="store_true",
        help="Require a previously recorded transparency proof for the selected release",
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
    registry_update.add_argument(
        "--signature-threshold",
        type=int,
        help="Raise the persisted minimum number of trusted release signatures",
    )
    registry_update.add_argument(
        "--require-transparency",
        action="store_true",
        help="Require and persist transparency proof policy for the selected release",
    )
    registry_update.add_argument("--allow-insecure-http", action="store_true")
    registry_update.add_argument("--apply", action="store_true")
    registry_audit = registry.add_parser(
        "audit", help="Check every remote registry and optionally record a notification"
    )
    registry_audit.add_argument("--scope", choices=("user", "project"), default="project")
    registry_audit.add_argument("--record", action="store_true")
    registry_audit.add_argument("--allow-insecure-http", action="store_true")
    registry.add_parser("list", help="List bundled and installed registries")
    registry_verify_transparency = registry.add_parser(
        "verify-transparency", help="Verify a signed registry release inclusion proof"
    )
    registry_verify_transparency.add_argument("--source", required=True)
    registry_verify_transparency.add_argument(
        "--scope", choices=("user", "project"), default="project"
    )
    registry_verify_transparency.add_argument(
        "--record", action="store_true", help="Persist the verified proof in Agora"
    )

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
    trust_transparency = trust.add_parser(
        "transparency", help="Manage independent transparency log checkpoint keys"
    ).add_subparsers(dest="transparency_trust_command", required=True)
    transparency_add = trust_transparency.add_parser(
        "add", help="Trust an Ed25519 transparency log checkpoint key"
    )
    transparency_add.add_argument("--id", required=True)
    transparency_add.add_argument("--log", required=True)
    transparency_add.add_argument("--public-key", required=True)
    transparency_add.add_argument("--scope", choices=("user", "project"), default="user")
    transparency_list = trust_transparency.add_parser("list", help="List transparency log keys")
    transparency_list.add_argument("--log")
    transparency_revoke = trust_transparency.add_parser(
        "revoke", help="Revoke a transparency log checkpoint key"
    )
    transparency_revoke.add_argument("--id", required=True)
    transparency_revoke.add_argument("--scope", choices=("user", "project"), default="user")
    transparency_revoke.add_argument("--reason", required=True)
    transparency_revoke.add_argument("--replaced-by")
    trust_organization = trust.add_parser(
        "organization", help="Manage signed organization trust feeds"
    ).add_subparsers(dest="organization_trust_command", required=True)
    organization_add = trust_organization.add_parser(
        "add", help="Pin an organization trust root public key"
    )
    organization_add.add_argument("--id", required=True)
    organization_add.add_argument("--public-key", required=True)
    organization_add.add_argument("--scope", choices=("user", "project"), default="user")
    organization_show = trust_organization.add_parser(
        "show", help="Show an organization trust root and sync position"
    )
    organization_show.add_argument("--id", required=True)
    organization_show.add_argument("--scope", choices=("user", "project"), default="user")
    organization_sync = trust_organization.add_parser(
        "sync", help="Preview or apply the next signed organization trust bundle"
    )
    organization_sync.add_argument("--id", required=True)
    organization_sync.add_argument("--scope", choices=("user", "project"), default="user")
    organization_sync.add_argument("--source")
    organization_sync.add_argument("--apply", action="store_true")
    organization_sync.add_argument("--allow-insecure-http", action="store_true")
    organization_rotate = trust_organization.add_parser(
        "rotate", help="Preview or apply a dual-signed organization root rotation"
    )
    organization_rotate.add_argument("--id", required=True)
    organization_rotate.add_argument("--scope", choices=("user", "project"), default="user")
    organization_rotate.add_argument("--source", required=True)
    organization_rotate.add_argument("--apply", action="store_true")
    organization_rotate.add_argument("--allow-insecure-http", action="store_true")

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
    pack_audit = pack.add_parser(
        "audit", help="Check every catalog-installed pack and optionally record a notification"
    )
    pack_audit.add_argument("--scope", choices=("user", "project"), default="project")
    pack_audit.add_argument("--record", action="store_true")
    pack_apply_audit = pack.add_parser(
        "apply-audit", help="Apply one unchanged, reviewed pack update audit transactionally"
    )
    pack_apply_audit.add_argument("--id", required=True)
    pack_apply_audit.add_argument("--scope", choices=("user", "project"), default="project")
    pack_apply_audit.add_argument("--force", action="store_true")
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
    start.add_argument("--executor", help="AI, service, automation, or swarm executing for actor")
    start.add_argument("--swarm", required=True)
    start.add_argument("--work")
    start.add_argument("--runner", help="External command that executes the prepared session")
    start.add_argument("--timeout-seconds", type=int, default=DEFAULT_SESSION_TIMEOUT_SECONDS)
    start.add_argument("--max-output-bytes", type=int, default=DEFAULT_SESSION_MAX_OUTPUT_BYTES)
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

    tool_credentials = tool.add_parser(
        "credentials",
        help="Report whether a Tool Pack can authenticate right now, and how (never a value)",
    )
    tool_credentials.add_argument("--tool", required=True)

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

    tool_result = tool.add_parser(
        "result", help="Show one Tool Run and its captured provider output"
    )
    tool_result.add_argument("--run", required=True)

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
    tool_invoke.add_argument("--environment")
    tool_invoke.add_argument("--input", action="append", default=[])
    tool_invoke.add_argument("--launch", action="store_true")
    tool_invoke.add_argument("--force", action="store_true")

    tool_sync = tool.add_parser(
        "sync", help="Launch one governed read and persist its external snapshot"
    )
    tool_sync.add_argument("--id", required=True)
    tool_sync.add_argument("--tool", required=True)
    tool_sync.add_argument("--operation", required=True)
    tool_sync.add_argument("--actor", required=True)
    tool_sync.add_argument("--swarm", required=True)
    tool_sync.add_argument("--work")
    tool_sync.add_argument("--input", action="append", default=[])

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
    actor_runtime.add_argument(
        "--fallback",
        action="append",
        help="Ordered fallback as integration:provider:model (repeatable)",
    )
    actor_runtime.add_argument("--clear-fallbacks", action="store_true")

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
    actor_runtime_prepare.add_argument(
        "--fallback",
        action="append",
        help="Ordered fallback as integration:provider:model (repeatable)",
    )
    actor_runtime_prepare.add_argument("--clear-fallbacks", action="store_true")

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
    work_start = work.add_parser(
        "start", help="Create governed work through an interactive reviewed workflow"
    )
    work_start.add_argument("--swarm", help="Ready swarm to use (otherwise choose interactively)")
    work_finish = work.add_parser(
        "finish", help="Review evidence, approve, and complete work interactively"
    )
    work_finish.add_argument("--swarm", help="Swarm to review")
    work_finish.add_argument("--work", help="Work item to review")
    work_finish.add_argument("--by", help="Responsible actor performing the review")
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
    criterion.add_argument(
        "--stage",
        help="Record one Method Pack criterion stage; omit to satisfy all stages",
    )
    criterion_prepare = work.add_parser(
        "criterion-satisfy-prepare", help="Prepare a signed criterion satisfaction intent"
    )
    criterion_prepare.add_argument("--id", required=True)
    criterion_prepare.add_argument("--swarm", required=True)
    criterion_prepare.add_argument("--work", required=True)
    criterion_prepare.add_argument("--criterion", required=True)
    criterion_prepare.add_argument("--by", required=True)
    criterion_prepare.add_argument("--stage")

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
    traceability = work.add_parser(
        "traceability", help="Trace criteria through generated artifacts and evidence"
    )
    traceability.add_argument("--swarm", required=True)
    traceability.add_argument("--work", required=True)

    clarify = work.add_parser("clarify", help="Generate guided pre-drafting clarifications")
    clarify.add_argument("--swarm", required=True)
    clarify.add_argument("--work", required=True)
    clarify.add_argument("--by", required=True)
    clarify.add_argument("--runner", help="Structured runner for a generic integration")
    clarify_prepare = work.add_parser(
        "clarify-prepare", help="Prepare a signed clarification intent"
    )
    clarify_prepare.add_argument("--id", required=True)
    clarify_prepare.add_argument("--swarm", required=True)
    clarify_prepare.add_argument("--work", required=True)
    clarify_prepare.add_argument("--by", required=True)
    clarify_prepare.add_argument("--runner", help="Structured runner for a generic integration")

    consistency = work.add_parser(
        "verify-consistency", help="Check artifacts against acceptance criteria"
    )
    consistency.add_argument("--swarm", required=True)
    consistency.add_argument("--work", required=True)
    consistency.add_argument("--by", required=True)
    consistency.add_argument("--runner", help="Structured runner for a generic integration")
    consistency_prepare = work.add_parser(
        "verify-consistency-prepare", help="Prepare a signed consistency-check intent"
    )
    consistency_prepare.add_argument("--id", required=True)
    consistency_prepare.add_argument("--swarm", required=True)
    consistency_prepare.add_argument("--work", required=True)
    consistency_prepare.add_argument("--by", required=True)
    consistency_prepare.add_argument("--runner", help="Structured runner for a generic integration")

    gherkin = work.add_parser("gherkin", help="Generate Gherkin features from criteria")
    gherkin.add_argument("--swarm", required=True)
    gherkin.add_argument("--work", required=True)
    gherkin.add_argument("--by", required=True)
    gherkin.add_argument("--runner", help="Structured runner for a generic integration")
    gherkin_prepare = work.add_parser(
        "gherkin-prepare", help="Prepare a signed Gherkin-generation intent"
    )
    gherkin_prepare.add_argument("--id", required=True)
    gherkin_prepare.add_argument("--swarm", required=True)
    gherkin_prepare.add_argument("--work", required=True)
    gherkin_prepare.add_argument("--by", required=True)
    gherkin_prepare.add_argument("--runner", help="Structured runner for a generic integration")

    checklist = work.add_parser(
        "checklist", help="Manage non-binding quality checklists"
    ).add_subparsers(dest="checklist_command", required=True)
    checklist_add = checklist.add_parser("add", help="Add a non-binding checklist")
    checklist_add.add_argument("--swarm", required=True)
    checklist_add.add_argument("--work", required=True)
    checklist_add.add_argument("--title", required=True)
    checklist_add.add_argument("--item", action="append", required=True)
    checklist_add.add_argument("--by", required=True)
    checklist_add_prepare = checklist.add_parser(
        "add-prepare", help="Prepare a signed checklist creation intent"
    )
    checklist_add_prepare.add_argument("--id", required=True)
    checklist_add_prepare.add_argument("--swarm", required=True)
    checklist_add_prepare.add_argument("--work", required=True)
    checklist_add_prepare.add_argument("--title", required=True)
    checklist_add_prepare.add_argument("--item", action="append", required=True)
    checklist_add_prepare.add_argument("--by", required=True)
    checklist_check = checklist.add_parser("check", help="Check one checklist item")
    checklist_check.add_argument("--swarm", required=True)
    checklist_check.add_argument("--work", required=True)
    checklist_check.add_argument("--checklist", required=True)
    checklist_check.add_argument("--item", type=int, required=True)
    checklist_check.add_argument("--by", required=True)
    checklist_check_prepare = checklist.add_parser(
        "check-prepare", help="Prepare a signed checklist-item toggle intent"
    )
    checklist_check_prepare.add_argument("--id", required=True)
    checklist_check_prepare.add_argument("--swarm", required=True)
    checklist_check_prepare.add_argument("--work", required=True)
    checklist_check_prepare.add_argument("--checklist", required=True)
    checklist_check_prepare.add_argument("--item", type=int, required=True)
    checklist_check_prepare.add_argument("--by", required=True)
    checklist_show = checklist.add_parser("show", help="Show one checklist")
    checklist_show.add_argument("--swarm", required=True)
    checklist_show.add_argument("--work", required=True)
    checklist_show.add_argument("--checklist", required=True)
    checklist_list = checklist.add_parser("list", help="List work checklists")
    checklist_list.add_argument("--swarm", required=True)
    checklist_list.add_argument("--work", required=True)

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
    session_show = session.add_parser("show", help="Show one durable session")
    session_show.add_argument("--session", required=True)
    session_diagnose = session.add_parser(
        "diagnose", help="Explain a session outcome and its safe recovery action"
    )
    session_diagnose.add_argument("--session", required=True)
    session_progress = session.add_parser(
        "progress", help="Record one concise execution milestone for a running session"
    )
    session_progress.add_argument("--session", required=True)
    session_progress.add_argument("--by", required=True, help="Bound session executor")
    session_progress.add_argument("--summary", required=True)
    session_prepare = session.add_parser("prepare", help="Prepare a signed session context intent")
    session_prepare.add_argument("--id", required=True, help="Lifecycle Action id")
    session_prepare.add_argument("--session", required=True)
    session_prepare.add_argument("--actor", required=True)
    session_prepare.add_argument("--executor")
    session_prepare.add_argument("--swarm", required=True)
    session_prepare.add_argument("--work")
    session_prepare.add_argument("--runner")
    session_prepare.add_argument(
        "--timeout-seconds", type=int, default=DEFAULT_SESSION_TIMEOUT_SECONDS
    )
    session_prepare.add_argument(
        "--max-output-bytes", type=int, default=DEFAULT_SESSION_MAX_OUTPUT_BYTES
    )
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

    activity = commands.add_parser(
        "activity", help="Inspect the linked project Activity Ledger"
    ).add_subparsers(dest="activity_command", required=True)
    activity_list = activity.add_parser("list", help="List recent governed activity")
    activity_list.add_argument("--actor")
    activity_list.add_argument("--swarm")
    activity_list.add_argument("--work")
    activity_list.add_argument("--session")
    activity_list.add_argument("--tool-run")
    activity_list.add_argument("--type")
    activity_list.add_argument("--limit", type=int, default=50)
    activity.add_parser("rebuild", help="Rebuild the ledger from existing durable project records")

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

    usage = commands.add_parser(
        "usage", help="Manage externally measured work usage"
    ).add_subparsers(dest="usage_command", required=True)
    usage_add = usage.add_parser("add", help="Append an evidence-backed usage record")
    usage_add.add_argument("--id", required=True)
    usage_add.add_argument("--swarm", required=True)
    usage_add.add_argument("--work", required=True)
    usage_add.add_argument("--by", required=True)
    usage_add.add_argument("--amount", action="append", default=[], metavar="DIMENSION=VALUE")
    usage_add.add_argument("--evidence", action="append", default=[])
    usage_prepare = usage.add_parser("prepare", help="Prepare a signed usage intent")
    usage_prepare.add_argument("--action-id", required=True)
    usage_prepare.add_argument("--id", required=True)
    usage_prepare.add_argument("--swarm", required=True)
    usage_prepare.add_argument("--work", required=True)
    usage_prepare.add_argument("--by", required=True)
    usage_prepare.add_argument("--amount", action="append", default=[], metavar="DIMENSION=VALUE")
    usage_prepare.add_argument("--evidence", action="append", default=[])
    usage_list = usage.add_parser("list", help="List durable usage records")
    usage_list.add_argument("--swarm", required=True)
    usage_list.add_argument("--work", required=True)
    usage_status = usage.add_parser("status", help="Summarize usage and remaining budget")
    usage_status.add_argument("--swarm", required=True)
    usage_status.add_argument("--work", required=True)

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


def _dispatch(
    workspace: AgoraWorkspace,
    args: argparse.Namespace,
    *,
    run_observer: Callable[[RunLoopEvent], None] | None = None,
) -> Any:
    reads = AgoraReadService(workspace)
    if args.command == "coordination" and args.coordination_command == "configure":
        return workspace.configure_coordination(
            ConfigureCoordinationInput(
                mode=args.mode,
                resource_id=args.resource_id,
                executable=args.executable,
                arguments=args.argument,
                version_arguments=args.version_argument,
                minimum_runtime_version=args.minimum_runtime_version,
                lease_seconds=args.lease_seconds,
                command_timeout_seconds=args.command_timeout_seconds,
                force=args.force,
            )
        )
    if args.command == "coordination" and args.coordination_command == "show":
        return workspace.show_coordination()
    if args.command == "environment" and args.environment_command == "add":
        return workspace.add_environment(
            AddEnvironmentInput(
                id=args.id,
                name=args.name,
                allowed_tool_capabilities=args.capability,
                required_approval_roles=args.required_approval_role,
                require_successful_evidence=args.require_successful_evidence,
                force=args.force,
            )
        )
    if args.command == "environment" and args.environment_command == "show":
        return workspace.show_environment(args.id)
    if args.command == "environment" and args.environment_command == "list":
        return workspace.list_environments()
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
    if args.command == "adopt":
        return workspace.check_adoption(
            AdoptionInput(
                path=args.path,
                swarm_id=args.id,
                base_branch=args.base,
                allow_dirty=args.allow_dirty,
                integration=args.integration,
                model=args.model,
            )
        )
    if args.command == "quickstart":
        return workspace.quickstart(
            QuickstartInput(
                swarm_id=args.id,
                objective=args.objective,
                method=args.method,
                secure=args.secure,
                path=args.path,
                key_directory=args.key_dir,
                base_branch=args.base,
                allow_dirty=args.allow_dirty,
            )
        )
    if args.command == "doctor":
        checks = workspace.doctor()
        return {"ok": all(item.ok or item.name == "git" for item in checks), "checks": checks}
    if args.command == "self-test":
        from agora.self_test import run_role_self_test

        return run_role_self_test()
    if args.command == "status":
        return _render_status_board(reads) if args.board else reads.project_overview()
    if args.command == "validate":
        return workspace.validate()
    if args.command == "next":
        return workspace.next_actions(
            actor_id=args.actor,
            swarm_id=args.swarm,
            human_only=False,
            limit=args.limit,
        )
    if args.command == "inbox":
        return workspace.next_actions(
            actor_id=args.actor,
            swarm_id=args.swarm,
            human_only=True,
            limit=args.limit,
        )
    if args.command == "run":
        run_input = _run_input(args)
        if args.explain:
            if args.prepare_only:
                raise ValueError("--explain cannot be combined with --prepare-only")
            if args.signature is not None:
                raise ValueError("--explain does not accept a session signature")
            return workspace.preview_run(run_input)
        if args.until_blocked:
            return workspace.run_until_blocked(
                run_input,
                max_steps=args.max_steps,
                observer=run_observer,
            )
        return workspace.run_next(run_input)
    if args.command == "resume":
        return workspace.resume_session(
            ResumeSessionInput(
                session_id=args.session,
                replacement_id=args.id,
                runner=args.runner,
                prepare_only=args.prepare_only,
                signature=args.signature,
                timeout_seconds=args.timeout_seconds,
                max_output_bytes=args.max_output_bytes,
            )
        )
    if args.command == "session" and args.session_command == "show":
        return reads.get_session(args.session)
    if args.command == "session" and args.session_command == "diagnose":
        return workspace.diagnose_session(args.session)
    if args.command == "session" and args.session_command == "progress":
        return workspace.record_session_progress(args.session, args.by, args.summary)
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
                signature_threshold=args.signature_threshold,
                require_transparency=args.require_transparency,
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
                signature_threshold=args.signature_threshold,
                require_transparency=args.require_transparency,
                allow_insecure_http=args.allow_insecure_http,
            )
        )
    if args.command == "registry" and args.registry_command == "audit":
        return workspace.audit_registry_updates(
            AuditRegistryUpdatesInput(
                scope=args.scope,
                record=args.record,
                allow_insecure_http=args.allow_insecure_http,
            )
        )
    if args.command == "registry" and args.registry_command == "list":
        return workspace.list_registries()
    if args.command == "registry" and args.registry_command == "verify-transparency":
        return workspace.verify_transparency_inclusion(
            VerifyTransparencyProofInput(
                source=args.source,
                scope=args.scope,
                record=args.record,
            )
        )
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
    if args.command == "trust" and args.trust_command == "transparency":
        if args.transparency_trust_command == "add":
            return workspace.add_transparency_trust_key(
                AddTransparencyTrustKeyInput(
                    id=args.id,
                    log=args.log,
                    public_key=args.public_key,
                    scope=args.scope,
                )
            )
        if args.transparency_trust_command == "list":
            return workspace.list_transparency_trust_keys(args.log)
        if args.transparency_trust_command == "revoke":
            return workspace.revoke_transparency_trust_key(
                RevokeTransparencyTrustKeyInput(
                    id=args.id,
                    scope=args.scope,
                    reason=args.reason,
                    replaced_by=args.replaced_by,
                )
            )
    if args.command == "trust" and args.trust_command == "organization":
        if args.organization_trust_command == "add":
            return workspace.add_organization_trust_root(
                AddOrganizationTrustRootInput(
                    id=args.id,
                    public_key=args.public_key,
                    scope=args.scope,
                )
            )
        if args.organization_trust_command == "show":
            return workspace.get_organization_trust_root(args.id, args.scope)
        if args.organization_trust_command == "sync":
            return workspace.sync_organization_trust(
                SyncOrganizationTrustInput(
                    id=args.id,
                    scope=args.scope,
                    source=args.source,
                    apply=args.apply,
                    allow_insecure_http=args.allow_insecure_http,
                )
            )
        if args.organization_trust_command == "rotate":
            return workspace.rotate_organization_trust_root(
                RotateOrganizationTrustRootInput(
                    id=args.id,
                    scope=args.scope,
                    source=args.source,
                    apply=args.apply,
                    allow_insecure_http=args.allow_insecure_http,
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
    if args.command == "pack" and args.pack_command == "audit":
        return workspace.audit_pack_updates(
            AuditPackUpdatesInput(scope=args.scope, record=args.record)
        )
    if args.command == "pack" and args.pack_command == "apply-audit":
        return workspace.apply_pack_update_audit(
            ApplyPackUpdateAuditInput(id=args.id, scope=args.scope, force=args.force)
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
                executor_id=args.executor,
                swarm_id=args.swarm,
                work_id=args.work,
                runner=args.runner,
                launch=args.launch,
                force=args.force,
                timeout_seconds=args.timeout_seconds,
                max_output_bytes=args.max_output_bytes,
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
    if args.command == "tool" and args.tool_command == "credentials":
        return workspace.resolve_tool_credentials(args.tool)
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
    if args.command == "tool" and args.tool_command == "result":
        return workspace.show_tool_run(args.run)
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
                environment_id=args.environment,
                inputs=_parse_inputs(args.input),
                launch=args.launch,
                force=args.force,
            )
        )
    if args.command == "tool" and args.tool_command == "sync":
        return workspace.invoke_tool(
            InvokeToolInput(
                id=args.id,
                tool_id=args.tool,
                operation_id=args.operation,
                actor_id=args.actor,
                swarm_id=args.swarm,
                work_id=args.work,
                inputs=_parse_inputs(args.input),
                launch=True,
                read_only_sync=True,
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
                fallbacks=args.fallback,
                clear_fallbacks=args.clear_fallbacks,
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
                    fallbacks=args.fallback,
                    clear_fallbacks=args.clear_fallbacks,
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
        return reads.list_actors(ActorFilters(scope=args.scope))
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
        return reads.get_swarm(args.swarm)
    if args.command == "swarm" and args.swarm_command == "list":
        return reads.list_swarms(SwarmFilters(status=args.status))
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
            args.stage,
        )
    if args.command == "work" and args.work_command == "criterion-satisfy-prepare":
        return workspace.prepare_satisfy_criterion(
            PrepareCriterionInput(
                id=args.id,
                swarm_id=args.swarm,
                work_id=args.work,
                actor_id=args.by,
                criterion_id=args.criterion,
                stage=args.stage,
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
        return reads.get_work_item(args.swarm, args.work)
    if args.command == "work" and args.work_command == "list":
        return reads.list_work_items(
            WorkItemFilters(
                swarm_id=args.swarm,
                state=args.state,
                operational_status=args.operational_status,
            )
        )
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
        return reads.list_sessions(SessionFilters(status=args.status))
    if args.command == "session" and args.session_command == "prepare":
        return workspace.prepare_session(
            PrepareSessionInput(
                action_id=args.id,
                session=StartSessionInput(
                    id=args.session,
                    actor_id=args.actor,
                    executor_id=args.executor,
                    swarm_id=args.swarm,
                    work_id=args.work,
                    runner=args.runner,
                    timeout_seconds=args.timeout_seconds,
                    max_output_bytes=args.max_output_bytes,
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
    if args.command == "activity" and args.activity_command == "list":
        return reads.activity(
            ActivityFilters(
                actor_id=args.actor,
                swarm_id=args.swarm,
                work_id=args.work,
                session_id=args.session,
                tool_run_id=args.tool_run,
                type=args.type,
                limit=args.limit,
            )
        )
    if args.command == "activity" and args.activity_command == "rebuild":
        return workspace.rebuild_activity()
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
    if args.command == "work" and args.work_command == "checklist":
        if args.checklist_command == "add":
            return workspace.add_checklist(
                AddChecklistInput(
                    swarm_id=args.swarm,
                    work_id=args.work,
                    actor_id=args.by,
                    title=args.title,
                    items=args.item,
                )
            )
        if args.checklist_command == "check":
            return workspace.check_checklist_item(
                CheckChecklistItemInput(
                    swarm_id=args.swarm,
                    work_id=args.work,
                    actor_id=args.by,
                    checklist_id=args.checklist,
                    item_index=args.item,
                )
            )
        if args.checklist_command == "add-prepare":
            return workspace.prepare_checklist_action(
                args.id,
                AddChecklistInput(
                    swarm_id=args.swarm,
                    work_id=args.work,
                    actor_id=args.by,
                    title=args.title,
                    items=args.item,
                ),
            )
        if args.checklist_command == "check-prepare":
            return workspace.prepare_checklist_action(
                args.id,
                CheckChecklistItemInput(
                    swarm_id=args.swarm,
                    work_id=args.work,
                    actor_id=args.by,
                    checklist_id=args.checklist,
                    item_index=args.item,
                ),
            )
        if args.checklist_command == "show":
            return workspace.show_checklist(args.swarm, args.work, args.checklist)
        if args.checklist_command == "list":
            return workspace.list_checklists(args.swarm, args.work)
    if args.command == "work" and args.work_command == "traceability":
        return reads.work_traceability(args.swarm, args.work)
    if args.command == "work" and args.work_command == "clarify":
        return workspace.clarify_work(
            WorkActorInput(swarm_id=args.swarm, work_id=args.work, actor_id=args.by),
            runner=args.runner,
        )
    if args.command == "work" and args.work_command == "clarify-prepare":
        return workspace.prepare_work_clarification(
            args.id,
            WorkActorInput(swarm_id=args.swarm, work_id=args.work, actor_id=args.by),
            runner=args.runner,
        )
    if args.command == "work" and args.work_command == "verify-consistency":
        return workspace.verify_work_consistency(
            WorkActorInput(swarm_id=args.swarm, work_id=args.work, actor_id=args.by),
            runner=args.runner,
        )
    if args.command == "work" and args.work_command == "verify-consistency-prepare":
        return workspace.prepare_advisory_work_action(
            args.id,
            WorkActorInput(swarm_id=args.swarm, work_id=args.work, actor_id=args.by),
            "work.verify-consistency",
            runner=args.runner,
        )
    if args.command == "work" and args.work_command == "gherkin":
        return workspace.generate_work_gherkin(
            WorkActorInput(swarm_id=args.swarm, work_id=args.work, actor_id=args.by),
            runner=args.runner,
        )
    if args.command == "work" and args.work_command == "gherkin-prepare":
        return workspace.prepare_advisory_work_action(
            args.id,
            WorkActorInput(swarm_id=args.swarm, work_id=args.work, actor_id=args.by),
            "work.gherkin",
            runner=args.runner,
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
    if args.command == "usage" and args.usage_command in {"add", "prepare"}:
        usage_input = AddUsageInput(
            id=args.id,
            swarm_id=args.swarm,
            work_id=args.work,
            actor_id=args.by,
            amounts=_parse_usage_amounts(args.amount),
            evidence_refs=args.evidence,
        )
        if args.usage_command == "prepare":
            return workspace.prepare_add_usage(
                PrepareUsageInput(action_id=args.action_id, usage=usage_input)
            )
        return workspace.add_usage(usage_input)
    if args.command == "usage" and args.usage_command == "list":
        return workspace.list_usage(args.swarm, args.work)
    if args.command == "usage" and args.usage_command == "status":
        return workspace.summarize_usage(args.swarm, args.work)
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


def _parse_usage_amounts(values: list[str]) -> dict[str, int]:
    amounts: dict[str, int] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f'Invalid usage amount "{value}"; expected dimension=value')
        dimension, raw_amount = value.split("=", 1)
        if not dimension or not raw_amount:
            raise ValueError(f'Invalid usage amount "{value}"; expected dimension=value')
        if dimension in amounts:
            raise ValueError(f"Duplicate usage dimension: {dimension}")
        try:
            amount = int(raw_amount)
        except ValueError as error:
            raise ValueError(f'Usage amount must be an integer: "{value}"') from error
        if amount <= 0:
            raise ValueError(f'Usage amount must be positive: "{value}"')
        amounts[dimension] = amount
    return amounts


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

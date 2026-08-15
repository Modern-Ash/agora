import json
import subprocess
from io import StringIO
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agora.cli import main as cli_main
from agora.model import (
    AddActorInput,
    AddApprovalInput,
    ApplyLifecycleActionInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    InvokeToolInput,
    LaunchSessionInput,
    LaunchToolRunInput,
    PrepareApprovalInput,
    PrepareLifecycleAuthorizationInput,
    PrepareSessionAuthorizationInput,
    PrepareToolAuthorizationInput,
    PrepareWorkTransitionInput,
    RevokeActorKeyInput,
    RotateActorKeyInput,
    StartSessionInput,
    TransitionWorkInput,
)
from agora.workspace import AgoraWorkspace


def _write_public_key(private_key: Ed25519PrivateKey, path: Path) -> Path:
    path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return path


def _authenticated_project(
    tmp_path: Path, monkeypatch
) -> tuple[Path, AgoraWorkspace, Ed25519PrivateKey, list[list[str]]]:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "agora.workspace.shutil.which",
        lambda executable: f"/usr/bin/{executable}",
    )
    calls: list[list[str]] = []

    def run_tool(
        command: list[str], cwd: Path, environment: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="clean", stderr="")

    private_key = Ed25519PrivateKey.generate()
    workspace = AgoraWorkspace(cwd=root, tool_runner=run_tool)
    workspace.initialize(InitInput(integration="generic", default_method="scrum"))
    for actor in (
        AddActorInput(
            id="owner",
            name="Product Owner",
            kind="human",
            capabilities=["backlog-management", "acceptance"],
            scope="project",
            public_key=str(tmp_path / "developer.pem"),
            require_authentication=True,
        ),
        AddActorInput(
            id="facilitator",
            name="Scrum Master",
            kind="ai-agent",
            capabilities=["facilitation", "governance"],
            scope="project",
        ),
        AddActorInput(
            id="developer",
            name="Authenticated Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
            public_key=str(_write_public_key(private_key, tmp_path / "developer.pem")),
            require_authentication=True,
        ),
    ):
        workspace.add_actor(actor)
    workspace.create_swarm(
        CreateSwarmInput(id="delivery", objective="Ship signed work", create_branch=False)
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        workspace.assign_actor(
            AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor_id)
        )
    return root, workspace, private_key, calls


def _create_authenticated_work(workspace: AgoraWorkspace) -> None:
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="signed-work",
            title="Apply a signed lifecycle mutation",
            actor_id="owner",
        )
    )


def test_applies_a_signed_work_transition_as_a_durable_lifecycle_action(
    tmp_path: Path, monkeypatch
) -> None:
    root, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    _create_authenticated_work(workspace)
    transition = TransitionWorkInput(
        swarm_id="delivery",
        work_id="signed-work",
        actor_id="developer",
        target_state="planned",
    )

    with pytest.raises(PermissionError, match="requires a signed lifecycle action"):
        workspace.transition_work(transition)

    prepared = workspace.prepare_work_transition(
        PrepareWorkTransitionInput(id="plan-signed-work", **transition.__dict__)
    )
    payload_path = tmp_path / "lifecycle-authorization.json"
    authorization = workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=prepared.id,
            output=str(payload_path),
        )
    )
    payload = json.loads(payload_path.read_text(encoding="ascii"))
    assert payload["schema"] == "agora/lifecycle-authorization/v1"
    assert payload["kind"] == "work.transition"
    assert payload["parameters"] == {"to": "planned"}
    assert payload["precondition-sha256"] == prepared.precondition_sha256
    signature_path = tmp_path / "lifecycle-authorization.sig"
    signature_path.write_bytes(private_key.sign(payload_path.read_bytes()))

    applied = workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(action_id=prepared.id, signature=str(signature_path))
    )

    assert applied.status == "applied"
    assert applied.authentication_verified is True
    assert applied.authentication_fingerprint == authorization.fingerprint
    assert workspace.show_work("delivery", "signed-work").state == "planned"
    assert workspace.list_lifecycle_actions("applied") == [applied]
    action_path = root / ".agora" / "actions" / prepared.id / "ACTION.md"
    assert action_path.is_file()
    assert workspace.validate().ok

    assert applied.authorization_signature is not None
    replacement = (
        "A" if applied.authorization_signature[0] != "A" else "B"
    ) + applied.authorization_signature[1:]
    action_path.write_text(
        action_path.read_text(encoding="utf-8").replace(
            applied.authorization_signature,
            replacement,
        ),
        encoding="utf-8",
    )
    report = workspace.validate()
    assert not report.ok
    assert any(issue.code == "lifecycle-action.invalid" for issue in report.issues)


def test_rejects_lifecycle_signature_replay_and_stale_work_state(
    tmp_path: Path, monkeypatch
) -> None:
    _, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    _create_authenticated_work(workspace)
    base = {
        "swarm_id": "delivery",
        "work_id": "signed-work",
        "actor_id": "developer",
        "target_state": "planned",
    }
    first = workspace.prepare_work_transition(
        PrepareWorkTransitionInput(id="first-transition", **base)
    )
    second = workspace.prepare_work_transition(
        PrepareWorkTransitionInput(id="second-transition", **base)
    )
    payload_path = tmp_path / "first-transition.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=first.id,
            output=str(payload_path),
        )
    )
    signature_path = tmp_path / "first-transition.sig"
    signature_path.write_bytes(private_key.sign(payload_path.read_bytes()))

    with pytest.raises(ValueError, match="signature is invalid"):
        workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(action_id=second.id, signature=str(signature_path))
        )

    workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(action_id=first.id, signature=str(signature_path))
    )
    with pytest.raises(ValueError, match="precondition digest mismatch"):
        workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(action_id=second.id, signature=str(signature_path))
        )
    report = workspace.validate()
    assert report.ok
    assert any(issue.code == "lifecycle-action.precondition-stale" for issue in report.issues)


def test_applies_a_signed_approval_with_role_and_note_bound_to_the_action(
    tmp_path: Path, monkeypatch
) -> None:
    root, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    _create_authenticated_work(workspace)
    approval = AddApprovalInput(
        swarm_id="delivery",
        work_id="signed-work",
        actor_id="owner",
        role_id="product-owner",
        note="Accepted | externally signed",
    )

    with pytest.raises(PermissionError, match="prepare the approval"):
        workspace.add_approval(approval)

    prepared = workspace.prepare_approval(
        PrepareApprovalInput(id="accept-signed-work", **approval.__dict__)
    )
    payload_path = tmp_path / "approval-authorization.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=prepared.id,
            output=str(payload_path),
        )
    )
    payload = json.loads(payload_path.read_text(encoding="ascii"))
    assert payload["kind"] == "approval.add"
    assert payload["parameters"] == {
        "note": "Accepted | externally signed",
        "role": "product-owner",
    }
    signature_path = tmp_path / "approval-authorization.sig"
    signature_path.write_bytes(private_key.sign(payload_path.read_bytes()))

    applied = workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(action_id=prepared.id, signature=str(signature_path))
    )

    assert applied.status == "applied"
    assert applied.authentication_verified
    assert workspace.show_work("delivery", "signed-work").approval_roles == ["product-owner"]
    approval_path = root / ".agora" / "swarms" / "delivery" / "work" / "signed-work"
    assert "Accepted \\| externally signed" in (approval_path / "approvals.md").read_text()
    assert workspace.validate().ok


def test_launches_an_authenticated_actor_run_with_external_signature(
    tmp_path: Path, monkeypatch
) -> None:
    root, workspace, private_key, calls = _authenticated_project(tmp_path, monkeypatch)
    prepared = workspace.invoke_tool(
        InvokeToolInput(
            id="signed-status",
            tool_id="repository",
            operation_id="status",
            actor_id="developer",
            swarm_id="delivery",
        )
    )
    payload_path = tmp_path / "authorization.json"
    authorization = workspace.prepare_tool_authorization(
        PrepareToolAuthorizationInput(
            run_id=prepared.id,
            output=str(payload_path),
        )
    )
    signature_path = tmp_path / "authorization.sig"
    signature_path.write_bytes(private_key.sign(payload_path.read_bytes()))
    payload = json.loads(payload_path.read_text(encoding="ascii"))
    assert payload["timeout-seconds"] == 300
    assert payload["max-output-bytes"] == 1048576

    completed = workspace.launch_tool_run(
        LaunchToolRunInput(run_id=prepared.id, signature=str(signature_path))
    )

    assert completed.status == "completed"
    assert completed.authentication_verified is True
    assert completed.authentication_fingerprint == authorization.fingerprint
    assert completed.authorization_sha256 == authorization.payload_sha256
    assert calls == [["git", "status", "--short"]]
    run_root = root / ".agora" / "tool-runs" / prepared.id
    assert (run_root / "RESULT.md").is_file()
    assert workspace.validate().ok

    assert completed.authorization_signature is not None
    replacement = (
        "A" if completed.authorization_signature[0] != "A" else "B"
    ) + completed.authorization_signature[1:]
    run_path = run_root / "RUN.md"
    run_path.write_text(
        run_path.read_text(encoding="utf-8").replace(
            completed.authorization_signature,
            replacement,
        ),
        encoding="utf-8",
    )
    report = workspace.validate()
    assert not report.ok
    assert any(issue.code == "tool-run.invalid" for issue in report.issues)


def test_rejects_unsigned_immediate_launch_and_signature_replay(
    tmp_path: Path, monkeypatch
) -> None:
    root, workspace, private_key, calls = _authenticated_project(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="requires signed launch"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="immediate-status",
                tool_id="repository",
                operation_id="status",
                actor_id="developer",
                swarm_id="delivery",
                launch=True,
            )
        )
    assert not (root / ".agora" / "tool-runs" / "immediate-status").exists()

    first = workspace.invoke_tool(
        InvokeToolInput(
            id="first-status",
            tool_id="repository",
            operation_id="status",
            actor_id="developer",
            swarm_id="delivery",
        )
    )
    first_payload = tmp_path / "first.json"
    workspace.prepare_tool_authorization(
        PrepareToolAuthorizationInput(run_id=first.id, output=str(first_payload))
    )
    replayed_signature = tmp_path / "first.sig"
    replayed_signature.write_bytes(private_key.sign(first_payload.read_bytes()))
    second = workspace.invoke_tool(
        InvokeToolInput(
            id="second-status",
            tool_id="repository",
            operation_id="status",
            actor_id="developer",
            swarm_id="delivery",
        )
    )

    with pytest.raises(PermissionError, match="requires a signed tool authorization"):
        workspace.launch_tool_run(LaunchToolRunInput(run_id=second.id))
    with pytest.raises(ValueError, match="signature is invalid"):
        workspace.launch_tool_run(
            LaunchToolRunInput(run_id=second.id, signature=str(replayed_signature))
        )
    assert calls == []


def test_rejects_missing_and_tampered_actor_identity_keys(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic"))

    with pytest.raises(ValueError, match="must declare --public-key"):
        workspace.add_actor(
            AddActorInput(
                id="developer",
                name="Developer",
                kind="human",
                capabilities=["implementation"],
                scope="project",
                require_authentication=True,
            )
        )

    private_key = Ed25519PrivateKey.generate()
    actor = workspace.add_actor(
        AddActorInput(
            id="developer",
            name="Developer",
            kind="human",
            capabilities=["implementation"],
            scope="project",
            public_key=str(_write_public_key(private_key, tmp_path / "developer.pem")),
            require_authentication=True,
        )
    )
    actor_path = Path(actor.path)
    actor_path.write_text(
        actor_path.read_text(encoding="utf-8").replace(
            actor.authentication_fingerprint or "missing",
            "0" * 64,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="authentication fingerprint mismatch"):
        workspace.list_actors("project")


def test_rotates_actor_keys_and_rejects_the_previous_signer(tmp_path: Path, monkeypatch) -> None:
    root, workspace, previous_private_key, calls = _authenticated_project(tmp_path, monkeypatch)
    prepared = workspace.invoke_tool(
        InvokeToolInput(
            id="before-rotation",
            tool_id="repository",
            operation_id="status",
            actor_id="developer",
            swarm_id="delivery",
        )
    )
    previous_payload = tmp_path / "before-rotation.json"
    workspace.prepare_tool_authorization(
        PrepareToolAuthorizationInput(run_id=prepared.id, output=str(previous_payload))
    )
    previous_signature = tmp_path / "before-rotation.sig"
    previous_signature.write_bytes(previous_private_key.sign(previous_payload.read_bytes()))

    replacement_private_key = Ed25519PrivateKey.generate()
    replacement = workspace.rotate_actor_key(
        RotateActorKeyInput(
            actor_id="developer",
            public_key=str(
                _write_public_key(replacement_private_key, tmp_path / "replacement.pem")
            ),
            reason="Scheduled credential rotation",
        )
    )
    keys = {record.fingerprint: record for record in workspace.list_actor_keys("developer")}
    previous = next(
        record for record in keys.values() if record.fingerprint != replacement.fingerprint
    )
    assert replacement.status == "active"
    assert len(keys) == 2
    assert previous.status == "rotated"
    assert previous.replaced_by == replacement.fingerprint

    with pytest.raises(ValueError, match="signature is invalid"):
        workspace.launch_tool_run(
            LaunchToolRunInput(run_id=prepared.id, signature=str(previous_signature))
        )

    current = workspace.invoke_tool(
        InvokeToolInput(
            id="after-rotation",
            tool_id="repository",
            operation_id="status",
            actor_id="developer",
            swarm_id="delivery",
        )
    )
    current_payload = tmp_path / "after-rotation.json"
    workspace.prepare_tool_authorization(
        PrepareToolAuthorizationInput(run_id=current.id, output=str(current_payload))
    )
    current_signature = tmp_path / "after-rotation.sig"
    current_signature.write_bytes(replacement_private_key.sign(current_payload.read_bytes()))
    completed = workspace.launch_tool_run(
        LaunchToolRunInput(run_id=current.id, signature=str(current_signature))
    )

    assert completed.authentication_fingerprint == replacement.fingerprint
    assert calls == [["git", "status", "--short"]]
    assert workspace.validate().ok
    output = StringIO()
    assert cli_main(["actor", "key", "list", "--actor", "developer"], cwd=root, stdout=output) == 0
    assert len(json.loads(output.getvalue())) == 2

    previous_path = Path(previous.path)
    previous_path.write_text(
        previous_path.read_text(encoding="utf-8").replace(
            replacement.fingerprint,
            "0" * 64,
        ),
        encoding="utf-8",
    )
    report = workspace.validate()
    assert not report.ok
    assert any(issue.code == "actor-key.replacement-missing" for issue in report.issues)


def test_revokes_and_recovers_an_actor_key(tmp_path: Path, monkeypatch) -> None:
    _, workspace, _, calls = _authenticated_project(tmp_path, monkeypatch)
    revoked = workspace.revoke_actor_key(
        RevokeActorKeyInput(actor_id="developer", reason="Credential exposure")
    )

    assert revoked.status == "revoked"
    with pytest.raises(PermissionError, match="authentication key is revoked"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="revoked-status",
                tool_id="repository",
                operation_id="status",
                actor_id="developer",
                swarm_id="delivery",
            )
        )
    assert calls == []
    assert workspace.validate().ok

    recovery_private_key = Ed25519PrivateKey.generate()
    recovered = workspace.rotate_actor_key(
        RotateActorKeyInput(
            actor_id="developer",
            public_key=str(_write_public_key(recovery_private_key, tmp_path / "recovery.pem")),
            reason="Replace the revoked credential",
        )
    )
    actor = next(record for record in workspace.list_actors("project") if record.id == "developer")
    keys = {record.fingerprint: record for record in workspace.list_actor_keys("developer")}
    assert actor.authentication_revoked_at is None
    assert keys[revoked.fingerprint].replaced_by == recovered.fingerprint
    assert keys[recovered.fingerprint].status == "active"
    assert workspace.validate().ok


def test_signs_session_launch_and_binds_its_materialized_context(
    tmp_path: Path, monkeypatch
) -> None:
    root, _, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    calls: list[list[str]] = []

    def launch(command: list[str], cwd: Path, environment: dict[str, str]) -> int:
        calls.append(command)
        return 0

    workspace = AgoraWorkspace(cwd=root, launcher=launch)
    immediate = StartSessionInput(
        id="unsigned-session",
        actor_id="developer",
        swarm_id="delivery",
        runner="/bin/true --agent",
        launch=True,
    )
    with pytest.raises(ValueError, match="requires signed session launch"):
        workspace.start_session(immediate)
    assert not (root / ".agora" / "sessions" / "unsigned-session").exists()

    prepared = workspace.start_session(
        StartSessionInput(
            id="signed-session",
            actor_id="developer",
            swarm_id="delivery",
            runner="/bin/true --agent",
        )
    )
    payload_path = tmp_path / "session-authorization.json"
    authorization = workspace.prepare_session_authorization(
        PrepareSessionAuthorizationInput(
            session_id=prepared.id,
            output=str(payload_path),
        )
    )
    payload = json.loads(payload_path.read_text(encoding="ascii"))
    assert payload["context-sha256"] == prepared.context_sha256
    assert payload["launch-command"] == ["/bin/true", "--agent"]
    signature_path = tmp_path / "session-authorization.sig"
    signature_path.write_bytes(private_key.sign(payload_path.read_bytes()))

    completed = workspace.launch_session(
        LaunchSessionInput(session_id=prepared.id, signature=str(signature_path))
    )
    assert completed.status == "completed"
    assert completed.authentication_verified is True
    assert completed.authentication_fingerprint == authorization.fingerprint
    assert calls == [["/bin/true", "--agent"]]
    assert workspace.validate().ok

    tampered = workspace.start_session(
        StartSessionInput(
            id="tampered-context",
            actor_id="developer",
            swarm_id="delivery",
            runner="/bin/true --agent",
        )
    )
    context_path = Path(tampered.context_path)
    original_context = context_path.read_text(encoding="utf-8")
    context_path.write_text(f"{original_context}\nUnapproved context.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="context digest mismatch"):
        workspace.launch_session(LaunchSessionInput(session_id=tampered.id))
    context_path.write_text(original_context, encoding="utf-8")

    cli_payload = tmp_path / "cli-session-authorization.json"
    cli_output = StringIO()
    assert (
        cli_main(
            [
                "session",
                "authorization",
                "--session",
                tampered.id,
                "--output",
                str(cli_payload),
            ],
            cwd=root,
            stdout=cli_output,
        )
        == 0
    )
    cli_signature = tmp_path / "cli-session-authorization.sig"
    cli_signature.write_bytes(private_key.sign(cli_payload.read_bytes()))
    cli_output = StringIO()
    assert (
        cli_main(
            [
                "session",
                "launch",
                "--session",
                tampered.id,
                "--signature",
                str(cli_signature),
            ],
            cwd=root,
            stdout=cli_output,
        )
        == 0
    )
    assert json.loads(cli_output.getvalue())["status"] == "completed"

    assert completed.authorization_signature is not None
    session_path = Path(completed.path) / "SESSION.md"
    replacement = (
        "A" if completed.authorization_signature[0] != "A" else "B"
    ) + completed.authorization_signature[1:]
    session_path.write_text(
        session_path.read_text(encoding="utf-8").replace(
            completed.authorization_signature,
            replacement,
        ),
        encoding="utf-8",
    )
    report = workspace.validate()
    assert not report.ok
    assert any(issue.code == "session.invalid" for issue in report.issues)

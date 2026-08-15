import os
import subprocess
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agora.model import (
    AddActorInput,
    AddApprovalInput,
    ApplyLifecycleActionInput,
    AssignActorInput,
    ChangeWorkStatusInput,
    CreateSwarmInput,
    CreateWorkInput,
    HandoffActorInput,
    InitInput,
    InvokeToolInput,
    LaunchSessionInput,
    LaunchToolRunInput,
    PrepareActorKeyRecoveryInput,
    PrepareActorKeyRevocationInput,
    PrepareActorKeyRotationInput,
    PrepareActorRuntimeInput,
    PrepareApprovalInput,
    PrepareCreateWorkInput,
    PrepareLifecycleAuthorizationInput,
    PrepareSessionAuthorizationInput,
    PrepareSessionInput,
    PrepareToolAuthorizationInput,
    PrepareWorkTransitionInput,
    RotateActorKeyInput,
    SetActorRuntimeInput,
    StartSessionInput,
)
from agora.workspace import AgoraWorkspace


def main() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="agora-actor-authentication-sample-"))
    project = runtime / "project"
    project.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")

    private_key = Ed25519PrivateKey.generate()
    public_key = runtime / "developer-public.pem"
    public_key.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    owner_private_key = Ed25519PrivateKey.generate()
    owner_public_key = runtime / "owner-public.pem"
    owner_public_key.write_bytes(
        owner_private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    facilitator_private_key = Ed25519PrivateKey.generate()
    facilitator_public_key = runtime / "facilitator-public.pem"
    facilitator_public_key.write_bytes(
        facilitator_private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    def run_tool(
        command: list[str], cwd: Path, environment: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout="clean", stderr="")

    agora = AgoraWorkspace(cwd=project, tool_runner=run_tool)
    agora.initialize(InitInput(integration="generic", default_method="scrum"))
    for actor in (
        AddActorInput(
            id="owner",
            name="Product Owner",
            kind="human",
            capabilities=["backlog-management", "acceptance"],
            scope="project",
            public_key=str(owner_public_key),
            require_authentication=True,
        ),
        AddActorInput(
            id="facilitator",
            name="Scrum Master",
            kind="ai-agent",
            capabilities=["facilitation", "governance"],
            scope="project",
            public_key=str(facilitator_public_key),
            require_authentication=True,
        ),
        AddActorInput(
            id="developer",
            name="Authenticated Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
            public_key=str(public_key),
            require_authentication=True,
        ),
        AddActorInput(
            id="human-developer",
            name="Human Developer",
            kind="human",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        agora.add_actor(actor)
    agora.create_swarm(
        CreateSwarmInput(id="delivery", objective="Execute signed work", create_branch=False)
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        agora.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor_id))

    prepared_work = agora.prepare_create_work(
        PrepareCreateWorkInput(
            action_id="create-signed-work",
            work=CreateWorkInput(
                swarm_id="delivery",
                id="signed-work",
                title="Apply a signed lifecycle mutation",
                actor_id="owner",
            ),
        )
    )
    work_payload = runtime / "work-creation-authorization.json"
    agora.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=prepared_work.id,
            output=str(work_payload),
        )
    )
    work_signature = runtime / "work-creation-authorization.sig"
    work_signature.write_bytes(owner_private_key.sign(work_payload.read_bytes()))
    applied_work = agora.apply_lifecycle_action(
        ApplyLifecycleActionInput(
            action_id=prepared_work.id,
            signature=str(work_signature),
        )
    )
    for action_id, reason, prepare in (
        ("pause-signed-work", "Dependency is unavailable", agora.prepare_block_work),
        ("resume-signed-work", "Dependency recovered", agora.prepare_resume_work),
    ):
        prepared_status = prepare(
            ChangeWorkStatusInput(
                id=action_id,
                swarm_id="delivery",
                work_id="signed-work",
                actor_id="developer",
                reason=reason,
            )
        )
        status_payload = runtime / f"{action_id}.json"
        agora.prepare_lifecycle_authorization(
            PrepareLifecycleAuthorizationInput(
                action_id=prepared_status.id,
                output=str(status_payload),
            )
        )
        status_signature = runtime / f"{action_id}.sig"
        status_signature.write_bytes(private_key.sign(status_payload.read_bytes()))
        agora.apply_lifecycle_action(
            ApplyLifecycleActionInput(
                action_id=prepared_status.id,
                signature=str(status_signature),
            )
        )
    prepared_action = agora.prepare_work_transition(
        PrepareWorkTransitionInput(
            id="plan-signed-work",
            swarm_id="delivery",
            work_id="signed-work",
            actor_id="developer",
            target_state="planned",
        )
    )
    action_payload = runtime / "lifecycle-authorization.json"
    agora.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=prepared_action.id,
            output=str(action_payload),
        )
    )
    action_signature = runtime / "lifecycle-authorization.sig"
    action_signature.write_bytes(private_key.sign(action_payload.read_bytes()))
    applied_action = agora.apply_lifecycle_action(
        ApplyLifecycleActionInput(
            action_id=prepared_action.id,
            signature=str(action_signature),
        )
    )
    approval = AddApprovalInput(
        swarm_id="delivery",
        work_id="signed-work",
        actor_id="owner",
        role_id="product-owner",
        note="Accepted by the external signer",
    )
    prepared_approval = agora.prepare_approval(
        PrepareApprovalInput(id="accept-signed-work", **approval.__dict__)
    )
    approval_payload = runtime / "approval-authorization.json"
    agora.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=prepared_approval.id,
            output=str(approval_payload),
        )
    )
    approval_signature = runtime / "approval-authorization.sig"
    approval_signature.write_bytes(owner_private_key.sign(approval_payload.read_bytes()))
    applied_approval = agora.apply_lifecycle_action(
        ApplyLifecycleActionInput(
            action_id=prepared_approval.id,
            signature=str(approval_signature),
        )
    )

    prepared = agora.invoke_tool(
        InvokeToolInput(
            id="signed-status",
            tool_id="repository",
            operation_id="status",
            actor_id="developer",
            swarm_id="delivery",
        )
    )
    payload = runtime / "authorization.json"
    authorization = agora.prepare_tool_authorization(
        PrepareToolAuthorizationInput(run_id=prepared.id, output=str(payload))
    )
    signature = runtime / "authorization.sig"
    signature.write_bytes(private_key.sign(payload.read_bytes()))
    completed = agora.launch_tool_run(
        LaunchToolRunInput(run_id=prepared.id, signature=str(signature))
    )

    runtime_action = agora.prepare_actor_runtime(
        PrepareActorRuntimeInput(
            action_id="update-signed-actor-runtime",
            swarm_id="delivery",
            runtime=SetActorRuntimeInput(
                actor_id="developer",
                integration="generic",
                provider="sample-gateway",
                model="sample-reviewed-model",
            ),
        )
    )
    runtime_payload = runtime / "runtime-authorization.json"
    agora.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=runtime_action.id,
            output=str(runtime_payload),
        )
    )
    runtime_signature = runtime / "runtime-authorization.sig"
    runtime_signature.write_bytes(private_key.sign(runtime_payload.read_bytes()))
    applied_runtime = agora.apply_lifecycle_action(
        ApplyLifecycleActionInput(
            action_id=runtime_action.id,
            signature=str(runtime_signature),
        )
    )

    session_action = agora.prepare_session(
        PrepareSessionInput(
            action_id="prepare-signed-agent-session",
            session=StartSessionInput(
                id="signed-agent-session",
                actor_id="developer",
                swarm_id="delivery",
                runner="/bin/true --agent",
            ),
        )
    )
    session_preparation_payload = runtime / "session-preparation-authorization.json"
    agora.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=session_action.id,
            output=str(session_preparation_payload),
        )
    )
    session_preparation_signature = runtime / "session-preparation-authorization.sig"
    session_preparation_signature.write_bytes(
        private_key.sign(session_preparation_payload.read_bytes())
    )
    agora.apply_lifecycle_action(
        ApplyLifecycleActionInput(
            action_id=session_action.id,
            signature=str(session_preparation_signature),
        )
    )
    prepared_session = next(
        session for session in agora.list_sessions() if session.id == "signed-agent-session"
    )
    session_payload = runtime / "session-authorization.json"
    agora.prepare_session_authorization(
        PrepareSessionAuthorizationInput(
            session_id=prepared_session.id,
            output=str(session_payload),
        )
    )
    session_signature = runtime / "session-authorization.sig"
    session_signature.write_bytes(private_key.sign(session_payload.read_bytes()))
    completed_session = agora.launch_session(
        LaunchSessionInput(
            session_id=prepared_session.id,
            signature=str(session_signature),
        )
    )

    replacement_private_key = Ed25519PrivateKey.generate()
    replacement_public_key = runtime / "developer-replacement-public.pem"
    replacement_public_key.write_bytes(
        replacement_private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    key_rotation = agora.prepare_actor_key_rotation(
        PrepareActorKeyRotationInput(
            action_id="rotate-developer-key",
            swarm_id="delivery",
            rotation=RotateActorKeyInput(
                actor_id="developer",
                public_key=str(replacement_public_key),
                reason="Scheduled sample rotation",
            ),
        )
    )
    key_rotation_payload = runtime / "key-rotation-authorization.json"
    agora.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=key_rotation.id,
            output=str(key_rotation_payload),
        )
    )
    key_rotation_signature = runtime / "key-rotation-authorization.sig"
    key_rotation_signature.write_bytes(private_key.sign(key_rotation_payload.read_bytes()))
    applied_key_rotation = agora.apply_lifecycle_action(
        ApplyLifecycleActionInput(
            action_id=key_rotation.id,
            signature=str(key_rotation_signature),
        )
    )
    replacement = next(
        key
        for key in agora.list_actor_keys("developer")
        if key.fingerprint == key_rotation.parameters["fingerprint"]
    )

    revocation = agora.prepare_actor_key_revocation(
        PrepareActorKeyRevocationInput(
            action_id="revoke-developer-key",
            swarm_id="delivery",
            target_actor_id="developer",
            authorized_by="facilitator",
            reason="Demonstrate independent emergency revocation",
        )
    )
    revocation_payload = runtime / "key-revocation-authorization.json"
    agora.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=revocation.id,
            output=str(revocation_payload),
        )
    )
    revocation_signature = runtime / "key-revocation-authorization.sig"
    revocation_signature.write_bytes(facilitator_private_key.sign(revocation_payload.read_bytes()))
    applied_revocation = agora.apply_lifecycle_action(
        ApplyLifecycleActionInput(
            action_id=revocation.id,
            signature=str(revocation_signature),
        )
    )

    recovery_private_key = Ed25519PrivateKey.generate()
    recovery_public_key = runtime / "developer-recovery-public.pem"
    recovery_public_key.write_bytes(
        recovery_private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    recovery = agora.prepare_actor_key_recovery(
        PrepareActorKeyRecoveryInput(
            action_id="recover-developer-key",
            swarm_id="delivery",
            target_actor_id="developer",
            authorized_by="facilitator",
            public_key=str(recovery_public_key),
            reason="Restore the developer with a separately generated key",
        )
    )
    recovery_payload = runtime / "key-recovery-authorization.json"
    agora.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=recovery.id,
            output=str(recovery_payload),
        )
    )
    recovery_signature = runtime / "key-recovery-authorization.sig"
    recovery_signature.write_bytes(facilitator_private_key.sign(recovery_payload.read_bytes()))
    applied_recovery = agora.apply_lifecycle_action(
        ApplyLifecycleActionInput(
            action_id=recovery.id,
            signature=str(recovery_signature),
        )
    )
    recovered = next(
        key
        for key in agora.list_actor_keys("developer")
        if key.fingerprint == recovery.parameters["fingerprint"]
    )
    revoked = next(
        key
        for key in agora.list_actor_keys("developer")
        if key.fingerprint == replacement.fingerprint
    )
    prepared_handoff = agora.prepare_handoff(
        HandoffActorInput(
            id="handoff-to-human",
            swarm_id="delivery",
            role_id="developer",
            from_actor_id="developer",
            to_actor_id="human-developer",
            authorized_by="developer",
            reason="Continue with human judgment",
            work_id="signed-work",
        )
    )
    handoff_payload = runtime / "handoff-authorization.json"
    agora.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=prepared_handoff.id,
            output=str(handoff_payload),
        )
    )
    handoff_signature = runtime / "handoff-authorization.sig"
    handoff_signature.write_bytes(recovery_private_key.sign(handoff_payload.read_bytes()))
    applied_handoff = agora.apply_lifecycle_action(
        ApplyLifecycleActionInput(
            action_id=prepared_handoff.id,
            signature=str(handoff_signature),
        )
    )

    assert completed.authentication_verified
    assert completed_session.authentication_verified
    assert applied_work.authentication_verified
    assert applied_action.authentication_verified
    assert applied_approval.authentication_verified
    assert applied_runtime.authentication_verified
    assert applied_key_rotation.authentication_verified
    assert applied_revocation.authentication_verified
    assert applied_recovery.authentication_verified
    assert applied_handoff.authentication_verified
    assert revoked.status == "revoked"
    assert revoked.replaced_by == recovered.fingerprint
    assert recovered.status == "active"
    assert agora.validate().ok
    print(f"Project: {project}")
    print(f"Actor fingerprint: {authorization.fingerprint}")
    print(f"Authorization SHA-256: {authorization.payload_sha256}")
    print(f"Run status: {completed.status}")
    print(f"Session status: {completed_session.status}")
    print(f"Revoked fingerprint: {revoked.fingerprint}")
    print(f"Current status: {recovered.status}")
    print(f"Key records: {len(agora.list_actor_keys('developer'))}")


if __name__ == "__main__":
    main()

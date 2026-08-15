import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agora.model import (
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddEvidenceInput,
    ApplyLifecycleActionInput,
    AssignActorInput,
    ChangeDelegationStatusInput,
    CreateDelegationInput,
    CreateSwarmInput,
    CreateWorkInput,
    DelegationActorInput,
    InitInput,
    PrepareLifecycleAuthorizationInput,
    PrepareWorkTransitionInput,
    TransitionWorkInput,
    WorkActorInput,
)
from agora.workspace import AgoraWorkspace


def main() -> None:
    project = Path(tempfile.mkdtemp(prefix="agora-delegated-work-project-"))
    os.environ["AGORA_HOME"] = tempfile.mkdtemp(prefix="agora-delegated-work-home-")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic", default_method="scrum"))
    facilitator_private_key = Ed25519PrivateKey.generate()
    facilitator_public_key = project / "facilitator-public.pem"
    facilitator_public_key.write_bytes(
        facilitator_private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    def sign_and_apply(action_id: str) -> None:
        payload = project / f"{action_id}.json"
        agora.prepare_lifecycle_authorization(
            PrepareLifecycleAuthorizationInput(action_id=action_id, output=str(payload))
        )
        signature = project / f"{action_id}.sig"
        signature.write_bytes(facilitator_private_key.sign(payload.read_bytes()))
        agora.apply_lifecycle_action(
            ApplyLifecycleActionInput(action_id=action_id, signature=str(signature))
        )

    for actor in (
        AddActorInput(
            id="owner",
            name="Product Owner",
            kind="human",
            capabilities=["backlog-management", "acceptance"],
            scope="project",
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
            id="specialist",
            name="Specialist Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        agora.add_actor(actor)

    def form_swarm(swarm_id: str, objective: str, developer: str) -> None:
        agora.create_swarm(CreateSwarmInput(id=swarm_id, objective=objective, create_branch=False))
        for role, actor_id in (
            ("product-owner", "owner"),
            ("scrum-master", "facilitator"),
            ("developer", developer),
        ):
            agora.assign_actor(AssignActorInput(swarm_id=swarm_id, role_id=role, actor_id=actor_id))

    form_swarm("specialists", "Produce a verified specialist result", "specialist")
    agora.add_actor(
        AddActorInput(
            id="specialist-swarm",
            name="Specialist Swarm",
            kind="swarm",
            capabilities=["implementation"],
            scope="project",
            represented_swarm="specialists",
        )
    )
    form_swarm(
        "delivery",
        "Integrate a governed specialist result",
        "specialist-swarm",
    )
    agora.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="parent-slice",
            title="Integrate the specialist result",
            actor_id="owner",
            required_artifacts=["delegated-result"],
        )
    )

    proposed = agora.create_delegation(
        CreateDelegationInput(
            id="specialist-task",
            parent_swarm_id="delivery",
            parent_work_id="parent-slice",
            child_actor_id="specialist-swarm",
            child_work_id="child-slice",
            actor_id="specialist-swarm",
            title="Produce the specialist result",
            description="Return a result that the parent can integrate.",
            acceptance_criteria=[("usable", "The result can be integrated")],
            required_artifacts=["child-result"],
            result_kind="delegated-result",
        )
    )
    for action_id, reason, prepare in (
        (
            "pause-specialist-task",
            "Clarify the delegated boundary",
            agora.prepare_block_delegation,
        ),
        (
            "resume-specialist-task",
            "The delegated boundary is explicit",
            agora.prepare_resume_delegation,
        ),
    ):
        prepared = prepare(
            ChangeDelegationStatusInput(
                id=action_id,
                delegation_id=proposed.id,
                actor_id="facilitator",
                reason=reason,
            )
        )
        sign_and_apply(prepared.id)
    accepted = agora.accept_delegation(
        DelegationActorInput(delegation_id=proposed.id, actor_id="owner")
    )

    for state in ("planned", "implementing", "reviewing"):
        agora.transition_work(
            TransitionWorkInput(
                swarm_id="specialists",
                work_id="child-slice",
                actor_id="specialist",
                target_state=state,
            )
        )
    verify_action = agora.prepare_work_transition(
        PrepareWorkTransitionInput(
            id="verify-child-slice",
            swarm_id="specialists",
            work_id="child-slice",
            actor_id="facilitator",
            target_state="verifying",
        )
    )
    sign_and_apply(verify_action.id)
    agora.satisfy_criterion(
        WorkActorInput(swarm_id="specialists", work_id="child-slice", actor_id="owner"),
        "usable",
    )
    agora.add_artifact(
        AddArtifactInput(
            swarm_id="specialists",
            work_id="child-slice",
            actor_id="specialist",
            kind="child-result",
            uri="repo://specialists/result.md",
        )
    )
    agora.add_evidence(
        AddEvidenceInput(
            swarm_id="specialists",
            work_id="child-slice",
            actor_id="facilitator",
            type="review",
            result="success",
            artifact_refs=["repo://specialists/result.md"],
        )
    )
    agora.add_approval(
        AddApprovalInput(
            swarm_id="specialists",
            work_id="child-slice",
            actor_id="owner",
            role_id="product-owner",
        )
    )
    agora.transition_work(
        TransitionWorkInput(
            swarm_id="specialists",
            work_id="child-slice",
            actor_id="owner",
            target_state="completed",
        )
    )
    collected = agora.collect_delegation(
        DelegationActorInput(delegation_id=proposed.id, actor_id="specialist-swarm")
    )

    parent_work = agora.show_work("delivery", "parent-slice")
    print(f"Project: {project}")
    print(f"Delegation: {proposed.status} -> {accepted.status} -> {collected.status}")
    print(f"Child swarm: {agora.show_swarm('specialists').status}")
    print(f"Parent artifacts: {', '.join(parent_work.artifact_kinds)}")
    print(f"Parent evidence: {', '.join(parent_work.evidence_results)}")
    print(f"Record: {collected.path}")


if __name__ == "__main__":
    main()

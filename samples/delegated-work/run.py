import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agora.model import (
    AddActorInput,
    AddArtifactInput,
    ApplyLifecycleActionInput,
    AssignActorInput,
    ChangeDelegationStatusInput,
    CreateDelegationInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    PrepareApprovalInput,
    PrepareCreateDelegationInput,
    PrepareCreateWorkInput,
    PrepareCriterionInput,
    PrepareDelegationActionInput,
    PrepareEvidenceInput,
    PrepareLifecycleAuthorizationInput,
    PrepareWorkTransitionInput,
    TransitionWorkInput,
)
from agora.workspace import AgoraWorkspace


def main() -> None:
    project = Path(tempfile.mkdtemp(prefix="agora-delegated-work-project-"))
    os.environ["AGORA_HOME"] = tempfile.mkdtemp(prefix="agora-delegated-work-home-")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic", default_method="scrum"))

    private_keys: dict[str, Ed25519PrivateKey] = {}
    public_keys: dict[str, Path] = {}
    for actor_id in ("owner", "facilitator", "specialist-swarm"):
        private_key = Ed25519PrivateKey.generate()
        public_key = project / f"{actor_id}-public.pem"
        public_key.write_bytes(
            private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        private_keys[actor_id] = private_key
        public_keys[actor_id] = public_key

    def sign_and_apply(action_id: str, actor_id: str) -> None:
        payload = project / f"{action_id}.json"
        agora.prepare_lifecycle_authorization(
            PrepareLifecycleAuthorizationInput(action_id=action_id, output=str(payload))
        )
        signature = project / f"{action_id}.sig"
        signature.write_bytes(private_keys[actor_id].sign(payload.read_bytes()))
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
            public_key=str(public_keys["owner"]),
            require_authentication=True,
        ),
        AddActorInput(
            id="facilitator",
            name="Scrum Master",
            kind="ai-agent",
            capabilities=["facilitation", "governance"],
            scope="project",
            public_key=str(public_keys["facilitator"]),
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
            public_key=str(public_keys["specialist-swarm"]),
            require_authentication=True,
        )
    )
    form_swarm(
        "delivery",
        "Integrate a governed specialist result",
        "specialist-swarm",
    )
    parent_work = CreateWorkInput(
        swarm_id="delivery",
        id="parent-slice",
        title="Integrate the specialist result",
        actor_id="owner",
        required_artifacts=["delegated-result"],
    )
    parent_creation = agora.prepare_create_work(
        PrepareCreateWorkInput(action_id="create-parent-slice", work=parent_work)
    )
    sign_and_apply(parent_creation.id, "owner")

    proposal = CreateDelegationInput(
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
        budget_limits={"effort": 8, "tokens": 50000},
        artifact_promotions={"child-result": "specialist-result"},
    )
    created = agora.prepare_create_delegation(
        PrepareCreateDelegationInput(
            action_id="propose-specialist-task",
            delegation=proposal,
        )
    )
    sign_and_apply(created.id, "specialist-swarm")
    proposed = agora.show_delegation("specialist-task")
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
        sign_and_apply(prepared.id, "facilitator")
    acceptance = agora.prepare_accept_delegation(
        PrepareDelegationActionInput(
            id="accept-specialist-task",
            delegation_id=proposed.id,
            actor_id="owner",
        )
    )
    sign_and_apply(acceptance.id, "owner")
    accepted = agora.show_delegation(proposed.id)

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
    sign_and_apply(verify_action.id, "facilitator")
    criterion = agora.prepare_satisfy_criterion(
        PrepareCriterionInput(
            id="satisfy-child-result",
            swarm_id="specialists",
            work_id="child-slice",
            actor_id="owner",
            criterion_id="usable",
        )
    )
    sign_and_apply(criterion.id, "owner")
    agora.add_artifact(
        AddArtifactInput(
            swarm_id="specialists",
            work_id="child-slice",
            actor_id="specialist",
            kind="child-result",
            uri="repo://specialists/result.md",
        )
    )
    evidence = agora.prepare_add_evidence(
        PrepareEvidenceInput(
            id="record-child-review",
            swarm_id="specialists",
            work_id="child-slice",
            actor_id="facilitator",
            type="review",
            result="success",
            artifact_refs=["repo://specialists/result.md"],
        )
    )
    sign_and_apply(evidence.id, "facilitator")
    approval = agora.prepare_approval(
        PrepareApprovalInput(
            id="approve-child-slice",
            swarm_id="specialists",
            work_id="child-slice",
            actor_id="owner",
            role_id="product-owner",
        )
    )
    sign_and_apply(approval.id, "owner")
    completion = agora.prepare_work_transition(
        PrepareWorkTransitionInput(
            id="complete-child-slice",
            swarm_id="specialists",
            work_id="child-slice",
            actor_id="owner",
            target_state="completed",
        )
    )
    sign_and_apply(completion.id, "owner")
    collection = agora.prepare_collect_delegation(
        PrepareDelegationActionInput(
            id="collect-specialist-task",
            delegation_id=proposed.id,
            actor_id="specialist-swarm",
        )
    )
    sign_and_apply(collection.id, "specialist-swarm")
    collected = agora.show_delegation(proposed.id)

    parent_work = agora.show_work("delivery", "parent-slice")
    print(f"Project: {project}")
    print(f"Delegation: {proposed.status} -> {accepted.status} -> {collected.status}")
    print(f"Child swarm: {agora.show_swarm('specialists').status}")
    print(f"Child budget: {agora.show_work('specialists', 'child-slice').budget_limits}")
    print(f"Parent artifacts: {', '.join(parent_work.artifact_kinds)}")
    print(f"Parent evidence: {', '.join(parent_work.evidence_results)}")
    print(f"Record: {collected.path}")


if __name__ == "__main__":
    main()

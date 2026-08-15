import os
import tempfile
from pathlib import Path

from agora.model import (
    AddActorInput,
    AddApprovalInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    DelegateApprovalInput,
    InitInput,
    RevokeApprovalDelegationInput,
)
from agora.workspace import AgoraWorkspace


def main() -> None:
    project = Path(tempfile.mkdtemp(prefix="agora-approval-delegation-project-"))
    os.environ["AGORA_HOME"] = tempfile.mkdtemp(prefix="agora-approval-delegation-home-")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic", default_method="scrum"))

    actors = (
        ("owner", "Product Owner", ["backlog-management", "acceptance"]),
        ("alternate", "Alternate Owner", ["backlog-management", "acceptance"]),
        ("facilitator", "Scrum Master", ["facilitation", "governance"]),
        ("developer", "Developer", ["implementation"]),
    )
    for actor_id, name, capabilities in actors:
        agora.add_actor(
            AddActorInput(
                id=actor_id,
                name=name,
                kind="human",
                capabilities=capabilities,
                scope="project",
            )
        )
    agora.create_swarm(
        CreateSwarmInput(
            id="delivery",
            objective="Demonstrate bounded approval authority",
            create_branch=False,
        )
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        agora.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor_id))

    for work_id in ("delegated-release", "revoked-release"):
        agora.create_work(
            CreateWorkInput(
                swarm_id="delivery",
                id=work_id,
                title=f"Review {work_id}",
                actor_id="owner",
            )
        )

    agora.delegate_approval(
        DelegateApprovalInput(
            id="release-approval",
            swarm_id="delivery",
            work_id="delegated-release",
            role_id="product-owner",
            actor_id="owner",
            to_actor_id="alternate",
            reason="The alternate owner will review this release",
        )
    )
    agora.add_approval(
        AddApprovalInput(
            swarm_id="delivery",
            work_id="delegated-release",
            actor_id="alternate",
            role_id="product-owner",
            delegation_id="release-approval",
            note="Accepted under delegated authority",
        )
    )

    agora.delegate_approval(
        DelegateApprovalInput(
            id="temporary-approval",
            swarm_id="delivery",
            work_id="revoked-release",
            role_id="product-owner",
            actor_id="owner",
            to_actor_id="alternate",
            reason="Temporary release coverage",
        )
    )
    agora.revoke_approval_delegation(
        RevokeApprovalDelegationInput(
            delegation_id="temporary-approval",
            swarm_id="delivery",
            work_id="revoked-release",
            actor_id="owner",
            reason="The primary owner resumed the review",
        )
    )

    used = agora.list_approval_delegations("delivery", "delegated-release")[0]
    revoked = agora.list_approval_delegations("delivery", "revoked-release")[0]
    assigned_owner = agora.show_swarm("delivery").assignments["product-owner"]
    print(f"Project: {project}")
    print(f"Used delegation: {used.id} ({used.status})")
    print(f"Revoked delegation: {revoked.id} ({revoked.status})")
    print(f"Product Owner remains assigned: {assigned_owner}")
    print(f"Validation issues: {len(agora.validate().issues)}")


if __name__ == "__main__":
    main()

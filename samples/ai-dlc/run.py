import json
import os
import subprocess
import tempfile
from pathlib import Path

from agora.model import (
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddEvidenceInput,
    AssignActorInput,
    ConfigureInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    TransitionWorkInput,
    WorkActorInput,
)
from agora.workspace import AgoraWorkspace

ROLES = {
    "product-owner": ("po", "human", ["specification", "acceptance"]),
    "architect": ("arch", "ai-agent", ["specification"]),
    "builder": ("build", "ai-agent", ["implementation"]),
    "operator": ("ops", "ai-agent", ["implementation"]),
    "quality-reviewer": ("qa", "human", ["acceptance"]),
}


def main() -> None:
    project = Path(tempfile.mkdtemp(prefix="agora-ai-dlc-project-"))
    os.environ["AGORA_HOME"] = tempfile.mkdtemp(prefix="agora-ai-dlc-home-")
    for name in ("intent", "units-of-work", "architecture", "domain-model"):
        (project / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")

    def advisory(command, cwd, environment):
        return subprocess.CompletedProcess(command, 0, json.dumps({"questions": []}), "")

    agora = AgoraWorkspace(cwd=project, tool_runner=advisory)
    agora.configure(
        ConfigureInput(
            integration="generic",
            provider="any-provider",
            model="any-model",
            default_method="ai-dlc",
        )
    )
    agora.initialize(InitInput())

    for _role_id, (actor_id, kind, caps) in ROLES.items():
        agora.add_actor(
            AddActorInput(id=actor_id, name=actor_id, kind=kind, capabilities=caps, scope="project")
        )
    agora.create_swarm(
        CreateSwarmInput(id="delivery", objective="Deliver via AI-DLC", create_branch=False)
    )
    for role_id, (actor_id, _k, _c) in ROLES.items():
        agora.assign_actor(
            AssignActorInput(swarm_id="delivery", role_id=role_id, actor_id=actor_id)
        )

    def wa(actor: str) -> WorkActorInput:
        return WorkActorInput(swarm_id="delivery", work_id="feature", actor_id=actor)

    def artifact(actor: str, kind: str) -> None:
        agora.add_artifact(
            AddArtifactInput(
                swarm_id="delivery",
                work_id="feature",
                actor_id=actor,
                kind=kind,
                uri=f"repo://{kind}.md",
            )
        )

    def approve(actor: str, role: str) -> None:
        agora.add_approval(
            AddApprovalInput(
                swarm_id="delivery",
                work_id="feature",
                actor_id=actor,
                role_id=role,
                note="ok",
            )
        )

    def evidence(actor: str, evidence_type: str) -> None:
        agora.add_evidence(
            AddEvidenceInput(
                swarm_id="delivery",
                work_id="feature",
                actor_id=actor,
                type=evidence_type,
                result="success",
                artifact_refs=["repo://intent.md"],
            )
        )

    def move(actor: str, target: str) -> str:
        return agora.transition_work(
            TransitionWorkInput(
                swarm_id="delivery", work_id="feature", actor_id=actor, target_state=target
            )
        ).state

    agora.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="feature",
            title="Ship a feature via AI-DLC",
            actor_id="po",
            acceptance_criteria=[("value", "The feature delivers its value")],
            required_artifacts=["intent"],
        )
    )

    artifact("po", "intent")
    agora.clarify_work(wa("po"), runner="/bin/true")
    print("initiation -> ideation:", move("po", "ideation"))

    agora.satisfy_criterion(wa("po"), "value", stage="elaborated")
    artifact("po", "units-of-work")
    approve("po", "product-owner")
    print("ideation -> inception:", move("po", "inception"))

    agora.satisfy_criterion(wa("arch"), "value", stage="designed")
    artifact("arch", "architecture")
    artifact("arch", "domain-model")
    approve("arch", "architect")
    approve("po", "product-owner")
    print("inception -> construction:", move("arch", "construction"))

    agora.satisfy_criterion(wa("build"), "value", stage="built")
    agora.satisfy_criterion(wa("qa"), "value", stage="verified")
    evidence("build", "test-suite")
    approve("qa", "quality-reviewer")
    print("construction -> operation:", move("qa", "operation"))

    print("operation -> construction (rework):", move("qa", "construction"))
    print("construction -> operation (forward again):", move("qa", "operation"))

    agora.satisfy_criterion(wa("ops"), "value", stage="deployed")
    agora.satisfy_criterion(wa("po"), "value", stage="accepted")
    evidence("ops", "deployment")
    approve("po", "product-owner")
    final = move("po", "completed")
    print("operation -> completed:", final)
    assert final == "completed"


if __name__ == "__main__":
    main()

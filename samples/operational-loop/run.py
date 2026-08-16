import os
import shlex
import sys
import tempfile
from pathlib import Path

from agora.model import (
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddEvidenceInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    InstallToolAdapterInput,
    InvokeToolInput,
    RunNextInput,
    TransitionWorkInput,
    WorkActorInput,
)
from agora.workspace import AgoraWorkspace


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="agora-operational-loop-") as temporary:
        root = Path(temporary) / "project"
        root.mkdir()
        os.environ["AGORA_HOME"] = str(Path(temporary) / "home")
        workspace = AgoraWorkspace(cwd=root)
        workspace.initialize(InitInput(integration="generic", default_method="scrum"))
        for actor in (
            AddActorInput(
                id="owner",
                name="Human Owner",
                kind="human",
                capabilities=["backlog-management", "acceptance"],
                scope="project",
            ),
            AddActorInput(
                id="facilitator",
                name="AI Facilitator",
                kind="ai-agent",
                capabilities=["facilitation", "governance"],
                scope="project",
            ),
            AddActorInput(
                id="developer",
                name="AI Developer",
                kind="ai-agent",
                capabilities=["implementation"],
                scope="project",
            ),
        ):
            workspace.add_actor(actor)
        workspace.create_swarm(
            CreateSwarmInput(
                id="delivery",
                objective="Exercise the operational loop",
                create_branch=False,
            )
        )
        for role, actor in (
            ("product-owner", "owner"),
            ("scrum-master", "facilitator"),
            ("developer", "developer"),
        ):
            workspace.assign_actor(
                AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor)
            )
        workspace.create_work(
            CreateWorkInput(
                swarm_id="delivery",
                id="increment",
                title="Execute one governed increment",
                actor_id="owner",
                acceptance_criteria=[("operational", "The external runner advances governed work")],
                required_artifacts=["source-code"],
            )
        )

        next_task = workspace.next_actions()[0]
        assert next_task.actor == "project:developer"
        runner = shlex.join(
            [sys.executable, str(Path(__file__).with_name("agent_runner.py").resolve())]
        )
        session = workspace.run_next(RunNextInput(actor_id="developer", runner=runner))
        assert session.status == "completed"
        assert workspace.show_work("delivery", "increment").state == "planned"

        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="delivery",
                work_id="increment",
                actor_id="developer",
                target_state="implementing",
            )
        )
        source_artifact = root / "src" / "operational-loop.py"
        source_artifact.parent.mkdir(parents=True, exist_ok=True)
        source_artifact.write_text("# Verified operational result\n", encoding="utf-8")
        workspace.add_artifact(
            AddArtifactInput(
                swarm_id="delivery",
                work_id="increment",
                actor_id="developer",
                kind="source-code",
                uri="repo://src/operational-loop.py",
            )
        )
        workspace.add_evidence(
            AddEvidenceInput(
                swarm_id="delivery",
                work_id="increment",
                actor_id="developer",
                type="sample-run",
                result="success",
                artifact_refs=["repo://src/operational-loop.py"],
            )
        )
        workspace.install_tool_adapter(
            InstallToolAdapterInput(adapter_id="github-pull-requests", scope="project")
        )
        review = workspace.invoke_tool(
            InvokeToolInput(
                id="prepared-review",
                tool_id="github-pull-requests",
                operation_id="create",
                actor_id="developer",
                swarm_id="delivery",
                work_id="increment",
                inputs={
                    "project": "example/agora",
                    "base": "main",
                    "head": "agora/delivery",
                    "title": "feat(runtime): exercise the operational loop",
                    "description": "Prepared without contacting GitHub.",
                },
            )
        )
        assert review.status == "prepared"
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="delivery",
                work_id="increment",
                actor_id="developer",
                target_state="reviewing",
            )
        )
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="delivery",
                work_id="increment",
                actor_id="facilitator",
                target_state="verifying",
            )
        )
        inbox = workspace.next_actions(human_only=True)
        assert inbox[0].actor == "project:owner"
        workspace.satisfy_criterion(
            WorkActorInput(swarm_id="delivery", work_id="increment", actor_id="owner"),
            criterion_id="operational",
        )
        workspace.add_approval(
            AddApprovalInput(
                swarm_id="delivery",
                work_id="increment",
                actor_id="owner",
                role_id="product-owner",
            )
        )
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="delivery",
                work_id="increment",
                actor_id="owner",
                target_state="completed",
            )
        )
        assert workspace.validate().ok
        print("Operational loop sample completed and validated.")


if __name__ == "__main__":
    main()

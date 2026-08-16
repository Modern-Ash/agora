import os
import sys
import tempfile
from pathlib import Path

from agora.markdown import MarkdownDocument, render_markdown
from agora.model import (
    AddActorInput,
    AssignActorInput,
    CreateSwarmInput,
    InitInput,
    InstallToolInput,
    InvokeToolInput,
    ToolRunRecord,
)
from agora.workspace import AgoraWorkspace


def _sample_pack(runtime: Path) -> Path:
    source = runtime / "bounded-provider"
    operations = source / "operations"
    operations.mkdir(parents=True)
    provider = Path(__file__).with_name("provider.py").resolve()
    (source / "TOOL.md").write_text(
        render_markdown(
            MarkdownDocument(
                attributes={
                    "schema": "agora/tool/v1",
                    "id": "bounded-provider",
                    "name": "Bounded sample provider",
                    "version": "1.0.0",
                    "dependencies": [],
                    "category": "repository",
                    "executable": sys.executable,
                    "timeout-seconds": 1,
                    "max-output-bytes": 512,
                },
                body="# Bounded sample provider",
            )
        ),
        encoding="utf-8",
    )
    for operation_id, mode in (("healthy", "healthy"), ("slow", "sleep"), ("noisy", "flood")):
        (operations / f"{operation_id}.md").write_text(
            render_markdown(
                MarkdownDocument(
                    attributes={
                        "schema": "agora/tool-operation/v1",
                        "id": operation_id,
                        "name": operation_id.title(),
                        "capability": "repository.read",
                        "risk": "read",
                        "arguments": [str(provider), mode],
                        "inputs": [],
                        "result-kind": "sample",
                    },
                    body=f"# {operation_id.title()}",
                )
            ),
            encoding="utf-8",
        )
    return source


def main() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="agora-execution-boundaries-"))
    project = runtime / "project"
    project.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")
    agora = AgoraWorkspace(cwd=project)
    agora.install_tool(InstallToolInput(source=str(_sample_pack(runtime)), scope="user"))
    agora.initialize(InitInput(integration="generic", default_method="scrum"))
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
        ),
        AddActorInput(
            id="developer",
            name="Delivery Agent",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        agora.add_actor(actor)
    agora.create_swarm(
        CreateSwarmInput(
            id="bounded-delivery",
            objective="Exercise portable tool execution boundaries",
            create_branch=False,
        )
    )
    for role_id, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        agora.assign_actor(
            AssignActorInput(swarm_id="bounded-delivery", role_id=role_id, actor_id=actor_id)
        )

    healthy = _invoke(agora, "healthy")
    failures: dict[str, str] = {}
    for operation_id in ("slow", "noisy"):
        try:
            _invoke(agora, operation_id)
        except RuntimeError as error:
            failures[operation_id] = str(error)
        else:
            raise AssertionError(f"{operation_id} operation crossed its execution boundary")

    runs = {record.operation_id: record for record in agora.list_tool_runs()}
    assert healthy.status == "completed"
    assert runs["slow"].exit_code == 124
    assert runs["noisy"].exit_code == 125
    assert agora.validate().ok
    print(f"Project: {project}")
    print(f"Healthy: {healthy.status}")
    print(f"Timeout: {failures['slow']}")
    print(f"Output limit: {failures['noisy']}")


def _invoke(agora: AgoraWorkspace, operation_id: str) -> ToolRunRecord:
    return agora.invoke_tool(
        InvokeToolInput(
            id=f"boundary-{operation_id}",
            tool_id="bounded-provider",
            operation_id=operation_id,
            actor_id="developer",
            swarm_id="bounded-delivery",
            launch=True,
        )
    )


if __name__ == "__main__":
    main()

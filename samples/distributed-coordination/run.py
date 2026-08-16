import os
import sys
import tempfile
from pathlib import Path

from agora.model import AddActorInput, ConfigureCoordinationInput, InitInput
from agora.workspace import AgoraWorkspace


def main() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="agora-distributed-coordination-sample-"))
    project = runtime / "project"
    project.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")
    state = runtime / "remote-lease.json"
    provider = Path(__file__).with_name("provider.py").resolve()
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic"))
    policy = agora.configure_coordination(
        ConfigureCoordinationInput(
            mode="external-lease",
            resource_id="sample:agora-project",
            executable=sys.executable,
            arguments=[str(provider), "--state", str(state)],
            version_arguments=[str(provider), "--version"],
            minimum_runtime_version="1.0.0",
            lease_seconds=60,
        )
    )
    actor = agora.add_actor(
        AddActorInput(
            id="developer",
            name="Distributed Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        )
    )

    assert not state.exists()
    assert agora.validate().ok
    print(f"Project: {project}")
    print(f"Coordination: {policy.mode} for {policy.resource_id}")
    print(f"Actor created under lease: {actor.reference}")


if __name__ == "__main__":
    main()

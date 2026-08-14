import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from agora.locking import WorkspaceLock, WorkspaceLockedError
from agora.model import AddActorInput, InitInput
from agora.workspace import AgoraWorkspace


def main() -> None:
    project = Path(tempfile.mkdtemp(prefix="agora-lock-project-"))
    os.environ["AGORA_HOME"] = tempfile.mkdtemp(prefix="agora-lock-home-")
    os.environ["AGORA_LOCK_HOME"] = tempfile.mkdtemp(prefix="agora-lock-runtime-")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic"))
    actor = AddActorInput(
        id="developer",
        name="Developer",
        kind="ai-agent",
        capabilities=["implementation"],
        scope="project",
    )

    with WorkspaceLock(project, "external-writer"):
        active = agora.lock_status()
        try:
            agora.add_actor(actor)
        except WorkspaceLockedError as error:
            contention = str(error)
        else:
            raise AssertionError("The competing mutation unexpectedly acquired the lock")

    assert not (project / ".agora" / "actors" / "developer.md").exists()
    created = agora.add_actor(actor)
    released = agora.lock_status()
    assert released.active is False

    print(f"Project: {project}")
    print("Active lock:")
    print(json.dumps(asdict(active), indent=2))
    print(f"Rejected mutation: {contention}")
    print("Created after release:")
    print(json.dumps(asdict(created), indent=2))
    print("Released lock:")
    print(json.dumps(asdict(released), indent=2))


if __name__ == "__main__":
    main()

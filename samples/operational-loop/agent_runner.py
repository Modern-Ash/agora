import os
from pathlib import Path

from agora.model import TransitionWorkInput
from agora.workspace import AgoraWorkspace


def main() -> None:
    project = Path(os.environ["AGORA_PROJECT"])
    context = Path(os.environ["AGORA_CONTEXT"])
    if "Agora session context" not in context.read_text(encoding="utf-8"):
        raise RuntimeError("Runner did not receive a valid Agora context")
    workspace = AgoraWorkspace(cwd=project)
    workspace.transition_work(
        TransitionWorkInput(
            swarm_id=os.environ["AGORA_SWARM"],
            work_id=os.environ["AGORA_WORK"],
            actor_id=os.environ["AGORA_ACTOR"],
            target_state="planned",
        )
    )


if __name__ == "__main__":
    main()

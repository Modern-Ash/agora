import os
import tempfile
from pathlib import Path

from agora.model import ConfigureInput, CreateSwarmInput, InitInput, InstallMethodInput
from agora.workspace import AgoraWorkspace


def main() -> None:
    sample_root = Path(__file__).resolve().parent
    project = Path(tempfile.mkdtemp(prefix="agora-custom-lifecycle-project-"))
    os.environ["AGORA_HOME"] = tempfile.mkdtemp(prefix="agora-custom-lifecycle-home-")
    agora = AgoraWorkspace(cwd=project)

    installed = agora.install_method(
        InstallMethodInput(source=str(sample_root / "release-flow"), scope="user")
    )
    agora.configure(
        ConfigureInput(
            integration="generic",
            provider="any-provider",
            model="any-model",
            default_method=installed.id,
        )
    )
    agora.initialize(InitInput())
    swarm = agora.create_swarm(
        CreateSwarmInput(
            id="custom-cycle",
            objective="Deliver work without assuming a language, model, or methodology",
            create_branch=False,
        )
    )

    print(f"Method Pack: {installed.id}")
    print(f"Work states: {', '.join(installed.work_states)}")
    print(f"Swarm: {swarm.id} ({swarm.status})")
    print(f"Persisted at: {project / '.agora' / 'methods' / installed.id}")


if __name__ == "__main__":
    main()

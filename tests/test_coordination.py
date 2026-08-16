import io
import json
import subprocess
import time
from pathlib import Path

import pytest

from agora.cli import main
from agora.coordination import DistributedLeaseError, ExternalLease, load_coordination_policy
from agora.model import (
    AddActorInput,
    ConfigureCoordinationInput,
    CoordinationPolicyRecord,
    InitInput,
)
from agora.workspace import AgoraWorkspace


def _lease_result(command: list[str], returncode: int = 0) -> subprocess.CompletedProcess[str]:
    if "--version" in command:
        output = "team-leasectl 1.2.0"
    elif "acquire" in command:
        output = json.dumps({"lease-id": "lease-42", "fencing-token": "fence-7"})
    else:
        output = ""
    return subprocess.CompletedProcess(command, returncode, output, "")


def test_wraps_project_mutations_in_an_external_distributed_lease(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    calls: list[tuple[list[str], Path, float]] = []

    def run_lease(
        command: list[str], cwd: Path, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        calls.append((command, cwd, timeout))
        return _lease_result(command)

    workspace = AgoraWorkspace(cwd=root, lease_runner=run_lease)
    workspace.initialize(InitInput(integration="generic"))
    workspace.configure_coordination(
        ConfigureCoordinationInput(
            mode="external-lease",
            resource_id="repository:payments",
            executable="team-leasectl",
            arguments=["--format", "json"],
            version_arguments=["--version"],
            minimum_runtime_version="1.1.0",
            lease_seconds=90,
            command_timeout_seconds=4,
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="developer",
            name="Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        )
    )

    assert calls[0][0] == ["team-leasectl", "--version"]
    assert calls[1][0] == [
        "team-leasectl",
        "--format",
        "json",
        "acquire",
        "--resource",
        "repository:payments",
        "--owner",
        calls[1][0][7],
        "--operation",
        "add_actor",
        "--ttl-seconds",
        "90",
    ]
    assert calls[1][1] == root
    assert calls[1][2] == 4
    assert calls[2][0][-4:] == ["--lease-id", "lease-42", "--fencing-token", "fence-7"]
    assert (root / ".agora" / "actors" / "developer.md").is_file()


def test_rejects_mutation_when_distributed_lease_acquisition_fails(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(
        cwd=root,
        lease_runner=lambda command, cwd, timeout: subprocess.CompletedProcess(
            command,
            0 if "--version" in command else 9,
            "team-leasectl 1.2.0" if "--version" in command else "",
            "" if "--version" in command else "lease held by another host",
        ),
    )
    workspace.initialize(InitInput(integration="generic"))
    workspace.configure_coordination(
        ConfigureCoordinationInput(
            mode="external-lease",
            resource_id="repository:payments",
            executable="team-leasectl",
            version_arguments=["--version"],
            minimum_runtime_version="1.0.0",
        )
    )

    with pytest.raises(DistributedLeaseError, match="lease held by another host"):
        workspace.add_actor(
            AddActorInput(
                id="developer",
                name="Developer",
                kind="ai-agent",
                capabilities=["implementation"],
                scope="project",
            )
        )
    assert not (root / ".agora" / "actors" / "developer.md").exists()
    assert workspace.lock_status().active is False


def test_rejects_an_outdated_distributed_lease_cli(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))

    def run_lease(
        command: list[str], cwd: Path, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "team-leasectl 0.9.0", "")

    workspace = AgoraWorkspace(cwd=root, lease_runner=run_lease)
    workspace.initialize(InitInput(integration="generic"))
    workspace.configure_coordination(
        ConfigureCoordinationInput(
            mode="external-lease",
            resource_id="repository:payments",
            executable="team-leasectl",
            version_arguments=["--version"],
            minimum_runtime_version="1.0.0",
        )
    )

    with pytest.raises(DistributedLeaseError, match="older than required 1.0.0"):
        workspace.add_actor(
            AddActorInput(
                id="developer",
                name="Developer",
                kind="ai-agent",
                capabilities=["implementation"],
                scope="project",
            )
        )
    assert not (root / ".agora" / "actors" / "developer.md").exists()


def test_renews_a_held_distributed_lease(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def run_lease(
        command: list[str], cwd: Path, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return _lease_result(command)

    policy = CoordinationPolicyRecord(
        mode="external-lease",
        resource_id="repository:payments",
        executable="team-leasectl",
        arguments=[],
        version_arguments=["--version"],
        minimum_runtime_version="1.0.0",
        lease_seconds=1,
        command_timeout_seconds=2,
        path=str(tmp_path / "coordination.md"),
    )
    with ExternalLease(policy, "long_mutation", tmp_path, runner=run_lease):
        time.sleep(1.1)

    assert any("renew" in command for command in calls)
    assert "release" in calls[-1]


def test_rejects_credential_arguments_in_coordination_policy(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic"))

    with pytest.raises(ValueError, match="credential or token"):
        workspace.configure_coordination(
            ConfigureCoordinationInput(
                mode="external-lease",
                resource_id="repository:payments",
                executable="team-leasectl",
                arguments=["--token", "secret"],
                version_arguments=["--version"],
                minimum_runtime_version="1.0.0",
            )
        )
    assert not (root / ".agora" / "coordination.md").exists()


def test_configures_and_shows_local_coordination_from_the_cli(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    output = io.StringIO()
    errors = io.StringIO()
    assert main(["init"], cwd=root, stdout=output, stderr=errors) == 0
    assert (
        main(
            ["coordination", "configure", "--mode", "local"],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert main(["coordination", "show"], cwd=root, stdout=output, stderr=errors) == 0

    policy = load_coordination_policy(root / ".agora" / "coordination.md")
    assert policy.mode == "local"
    assert errors.getvalue() == ""
    assert '"mode": "local"' in output.getvalue()

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from agora.model import (
    AddApprovalInput,
    AddArtifactInput,
    AddEvidenceInput,
    AdoptionInput,
    CreateWorkInput,
    QuickstartInput,
    TransitionWorkInput,
    WorkActorInput,
)
from agora.workspace import AgoraWorkspace


def _run(command: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return result


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="agora-existing-feature-") as temporary:
        temporary_root = Path(temporary)
        root = temporary_root / "calculator-service"
        shutil.copytree(Path(__file__).with_name("fixture"), root)
        os.environ["AGORA_HOME"] = str(temporary_root / "home")

        _run(["git", "init", "--initial-branch", "main"], root)
        _run(["git", "config", "user.name", "Agora Sample"], root)
        _run(["git", "config", "user.email", "agora@example.test"], root)
        _run(["git", "add", "calculator.py", "test_calculator.py"], root)
        _run(["git", "commit", "-m", "chore: import existing calculator"], root)
        baseline = _run([sys.executable, "-B", "test_calculator.py"], root)

        workspace = AgoraWorkspace(cwd=root)
        preflight = workspace.check_adoption(
            AdoptionInput(swarm_id="percentage-discount", base_branch="main")
        )
        if not preflight.ok:
            raise RuntimeError("Existing repository failed the adoption preflight")
        quickstart = workspace.quickstart(
            QuickstartInput(
                swarm_id="percentage-discount",
                objective="Add percentage discounts without breaking existing totals",
                base_branch="main",
            )
        )

        workspace.create_work(
            CreateWorkInput(
                swarm_id=quickstart.swarm.id,
                id="discount-feature",
                title="Add percentage discounts",
                actor_id="owner",
                description="Preserve total() and add a validated discounted_total() API.",
                acceptance_criteria=[
                    ("compatible", "Existing totals remain unchanged and discounts are bounded")
                ],
                required_artifacts=["spec"],
            )
        )
        specification = root / "docs" / "specs" / "percentage-discount.md"
        specification.parent.mkdir(parents=True)
        specification.write_text(
            "# Percentage discount\n\nAccept integer percentages from 0 through 100.\n",
            encoding="utf-8",
        )
        workspace.add_artifact(
            AddArtifactInput(
                swarm_id=quickstart.swarm.id,
                work_id="discount-feature",
                actor_id="owner",
                kind="spec",
                uri="repo://docs/specs/percentage-discount.md",
            )
        )
        workspace.satisfy_criterion(
            WorkActorInput(
                swarm_id=quickstart.swarm.id,
                work_id="discount-feature",
                actor_id="owner",
            ),
            "compatible",
        )
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id=quickstart.swarm.id,
                work_id="discount-feature",
                actor_id="owner",
                target_state="clarified",
            )
        )
        for state in ("planned", "implementing"):
            workspace.transition_work(
                TransitionWorkInput(
                    swarm_id=quickstart.swarm.id,
                    work_id="discount-feature",
                    actor_id="agent",
                    target_state=state,
                )
            )

        (root / "calculator.py").write_text(
            "def total(values: list[int]) -> int:\n"
            "    return sum(values)\n\n\n"
            "def discounted_total(values: list[int], percent: int) -> int:\n"
            "    if not 0 <= percent <= 100:\n"
            "        raise ValueError('percent must be between 0 and 100')\n"
            "    return total(values) * (100 - percent) // 100\n",
            encoding="utf-8",
        )
        with (root / "test_calculator.py").open("a", encoding="utf-8") as tests:
            tests.write(
                "\nfrom calculator import discounted_total\n"
                "assert discounted_total([50, 50], 25) == 75\n"
            )
        feature_test = _run([sys.executable, "-B", "test_calculator.py"], root)
        report = root / "reports" / "discount-tests.txt"
        report.parent.mkdir()
        report.write_text(feature_test.stdout, encoding="utf-8")

        for kind, uri in (
            ("source-code", "repo://calculator.py"),
            ("test-report", "repo://reports/discount-tests.txt"),
        ):
            workspace.add_artifact(
                AddArtifactInput(
                    swarm_id=quickstart.swarm.id,
                    work_id="discount-feature",
                    actor_id="agent",
                    kind=kind,
                    uri=uri,
                )
            )
        workspace.add_evidence(
            AddEvidenceInput(
                swarm_id=quickstart.swarm.id,
                work_id="discount-feature",
                actor_id="agent",
                type="test-run",
                result="success",
                artifact_refs=["repo://reports/discount-tests.txt"],
            )
        )
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id=quickstart.swarm.id,
                work_id="discount-feature",
                actor_id="agent",
                target_state="verifying",
            )
        )
        workspace.add_approval(
            AddApprovalInput(
                swarm_id=quickstart.swarm.id,
                work_id="discount-feature",
                actor_id="owner",
                role_id="spec-owner",
                note="Compatibility and discount behavior accepted",
            )
        )
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id=quickstart.swarm.id,
                work_id="discount-feature",
                actor_id="owner",
                target_state="completed",
            )
        )
        validation = workspace.validate()
        if not validation.ok:
            raise RuntimeError("The completed pilot did not validate")

        print(
            json.dumps(
                {
                    "baseline": baseline.stdout.strip(),
                    "branch": quickstart.swarm.branch,
                    "feature": feature_test.stdout.strip(),
                    "validated": validation.ok,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()

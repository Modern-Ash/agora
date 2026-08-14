import runpy
from pathlib import Path

ROOT = Path(__file__).parents[1]
build_steps = runpy.run_path(str(ROOT / "scripts" / "verify_all.py"))["build_steps"]


def test_builds_a_python_only_full_verification_plan() -> None:
    root = ROOT

    steps = build_steps(root)
    names = [step.name for step in steps]
    executables = [Path(step.command[0]).name for step in steps]

    assert names[:4] == ["format", "lint", "tests", "documentation links"]
    assert names[-1] == "distribution build"
    assert [name for name in names if name.startswith("sample: ")] == [
        "sample: basic-swarm",
        "sample: ci-cd",
        "sample: concurrent-writes",
        "sample: custom-lifecycle",
        "sample: delegated-work",
        "sample: handoffs",
        "sample: interruptions",
        "sample: llm-environments",
        "sample: operational-query",
        "sample: pack-dependencies",
        "sample: pack-registry",
        "sample: pack-removal",
        "sample: project-upgrade",
        "sample: recursive-swarms",
        "sample: remote-registry",
        "sample: tool-integration",
        "sample: work-management",
    ]
    assert not {"node", "npm", "npx"}.intersection(executables)


def test_can_build_a_fast_verification_plan() -> None:
    root = ROOT

    steps = build_steps(root, include_samples=False, include_build=False)

    assert [step.name for step in steps] == [
        "format",
        "lint",
        "tests",
        "documentation links",
    ]

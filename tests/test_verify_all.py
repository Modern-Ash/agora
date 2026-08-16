import re
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
        "sample: actor-authentication",
        "sample: approval-delegation",
        "sample: basic-swarm",
        "sample: ci-cd",
        "sample: cli-runtime-compatibility",
        "sample: cloud-infrastructure",
        "sample: cloud-inventory-cli",
        "sample: concurrent-writes",
        "sample: custom-lifecycle",
        "sample: delegated-work",
        "sample: distributed-coordination",
        "sample: environment-permissions",
        "sample: execution-boundaries",
        "sample: gate-waivers",
        "sample: github-actions-cli",
        "sample: github-issues-cli",
        "sample: gitlab-issues-cli",
        "sample: gitlab-merge-requests-cli",
        "sample: handoffs",
        "sample: interruptions",
        "sample: jira-cli",
        "sample: knowledge-base",
        "sample: llm-environments",
        "sample: observability",
        "sample: operational-loop",
        "sample: operational-query",
        "sample: organization-trust",
        "sample: pack-dependencies",
        "sample: pack-registry",
        "sample: pack-removal",
        "sample: project-upgrade",
        "sample: recursive-swarms",
        "sample: remote-registry",
        "sample: terraform-cli",
        "sample: tool-integration",
        "sample: twg-confluence-cli",
        "sample: work-decomposition",
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


def test_github_ci_uses_the_locked_python_verifier_and_pinned_actions() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    action_references = re.findall(r"^\s*uses: ([^\s#]+)", workflow, flags=re.MULTILINE)

    assert 'python-version: ["3.11", "3.12", "3.13"]' in workflow
    assert "uv sync --locked --extra dev" in workflow
    assert "python scripts/verify_all.py --quiet" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert action_references
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", reference) for reference in action_references)


def test_github_release_verifies_tags_and_uses_native_cli() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    action_references = re.findall(r"^\s*uses: ([^\s#]+)", workflow, flags=re.MULTILINE)

    assert 'tags:\n      - "v*.*.*"' in workflow
    assert "python scripts/verify_all.py --quiet" in workflow
    assert 'python scripts/prepare_release.py --tag "$GITHUB_REF_NAME"' in workflow
    assert "gh release create" in workflow
    assert "dist/SHA256SUMS" in workflow
    assert action_references
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", reference) for reference in action_references)

import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from agora.filesystem import template_root
from agora.tools import (
    load_tool_contract,
    probe_tool_runtime,
    validate_conventional_commit,
    validate_operation_inputs,
    validate_tool_adapter_contract,
)


def test_loads_a_provider_neutral_tool_pack() -> None:
    contract = load_tool_contract(template_root() / "tools" / "repository")

    assert contract.id == "repository"
    assert contract.executable == "git"
    assert contract.operations["status"].capability == "repository.read"
    assert contract.operations["create-branch"].risk == "write"
    assert contract.operations["create-branch"].inputs == ["branch"]
    assert contract.operations["commit"].input_rules == {"message": "conventional-commits/v1.0.0"}
    assert contract.timeout_seconds == 300
    assert contract.max_output_bytes == 1048576


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("timeout-seconds", "0"),
        ("timeout-seconds", "true"),
        ("timeout-seconds", "3601"),
        ("max-output-bytes", "0"),
        ("max-output-bytes", "10485761"),
    ],
)
def test_rejects_invalid_tool_execution_boundaries(
    tmp_path: Path, attribute: str, value: str
) -> None:
    source = template_root() / "tools" / "repository"
    tool = tmp_path / "repository"
    shutil.copytree(source, tool)
    manifest = tool / "TOOL.md"
    contents = manifest.read_text(encoding="utf-8")
    default = "300" if attribute == "timeout-seconds" else "1048576"
    contents = contents.replace(f"{attribute}: {default}", f"{attribute}: {value}")
    manifest.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=attribute):
        load_tool_contract(tool)


def test_loads_the_bundled_work_management_contract() -> None:
    contract = load_tool_contract(template_root() / "tools" / "work-management")

    assert contract.id == "work-management"
    assert contract.executable == "workctl"
    assert list(contract.operations) == ["comment", "create", "search", "transition", "view"]
    assert contract.operations["search"].capability == "issue.read"
    assert contract.operations["create"].capability == "issue.write"
    assert contract.operations["transition"].capability == "issue.transition"
    assert contract.operations["transition"].risk == "write"


def test_loads_the_bundled_ci_cd_contract() -> None:
    contract = load_tool_contract(template_root() / "tools" / "ci-cd")

    assert contract.id == "ci-cd"
    assert contract.executable == "cictl"
    assert list(contract.operations) == [
        "cancel-run",
        "create-deployment",
        "list-runs",
        "trigger",
        "view-deployment",
        "view-run",
    ]
    assert contract.operations["list-runs"].capability == "ci.read"
    assert contract.operations["trigger"].capability == "ci.run"
    assert contract.operations["cancel-run"].capability == "ci.cancel"
    assert contract.operations["cancel-run"].risk == "destructive"
    assert contract.operations["create-deployment"].capability == "deployment.create"


def test_loads_the_github_actions_cli_adapter() -> None:
    contract = load_tool_contract(template_root() / "adapters" / "cli" / "github-actions")

    assert contract.id == "github-actions"
    assert contract.executable == "gh"
    assert contract.provider == "github"
    assert contract.transport == "cli"
    assert contract.implements == "ci-cd"
    assert contract.version_command == ["--version"]
    assert contract.minimum_runtime_version == "2.45.0"
    assert contract.operations["list-runs"].capability == "ci.read"
    assert contract.operations["trigger"].arguments[:2] == ["workflow", "run"]
    assert contract.operations["cancel-run"].risk == "destructive"


def test_loads_the_gitlab_ci_adapter_as_an_explicit_subset() -> None:
    contract = load_tool_contract(template_root() / "adapters" / "cli" / "gitlab-ci")
    implemented = load_tool_contract(template_root() / "tools" / "ci-cd")

    validate_tool_adapter_contract(contract, implemented)
    assert contract.provider == "gitlab"
    assert contract.executable == "glab"
    assert contract.version_command == ["version"]
    assert contract.minimum_runtime_version == "1.109.0"
    assert contract.implements_operations == ["list-runs", "view-run", "cancel-run"]
    assert sorted(contract.operations) == ["cancel-run", "list-runs", "view-run"]
    assert contract.operations["view-run"].arguments[:3] == ["ci", "get", "--pipeline-id"]
    assert contract.operations["cancel-run"].risk == "destructive"
    assert "trigger" not in contract.operations


def test_loads_the_terraform_cli_adapter() -> None:
    contract = load_tool_contract(template_root() / "adapters" / "cli" / "terraform")
    implemented = load_tool_contract(template_root() / "tools" / "cloud-infrastructure")

    validate_tool_adapter_contract(contract, implemented)
    assert contract.id == "terraform"
    assert contract.executable == "terraform"
    assert contract.provider == "hashicorp"
    assert contract.transport == "cli"
    assert contract.implements == "cloud-infrastructure"
    assert contract.operations["plan"].arguments == [
        "-chdir={environment}",
        "plan",
        "-input=false",
        "-no-color",
        "-out={change}",
    ]
    assert contract.operations["apply-plan"].capability == "cloud.deploy"
    assert contract.operations["destroy-resource"].risk == "destructive"


def test_loads_the_github_issues_cli_adapter_and_restricts_transitions() -> None:
    contract = load_tool_contract(template_root() / "adapters" / "cli" / "github-issues")
    implemented = load_tool_contract(template_root() / "tools" / "work-management")

    validate_tool_adapter_contract(contract, implemented)
    assert contract.provider == "github"
    assert contract.transport == "cli"
    assert contract.implements == "work-management"
    transition = contract.operations["transition"]
    assert transition.input_values == {"state": ["close", "reopen"]}
    validate_operation_inputs(transition, {"issue": "42", "state": "close"})
    with pytest.raises(ValueError, match="state must be one of: close, reopen"):
        validate_operation_inputs(transition, {"issue": "42", "state": "delete"})


def test_loads_the_gitlab_issues_adapter_as_an_explicit_subset() -> None:
    contract = load_tool_contract(template_root() / "adapters" / "cli" / "gitlab-issues")
    implemented = load_tool_contract(template_root() / "tools" / "work-management")

    validate_tool_adapter_contract(contract, implemented)
    assert contract.provider == "gitlab"
    assert contract.executable == "glab"
    assert contract.version_command == ["version"]
    assert contract.minimum_runtime_version == "1.109.0"
    assert contract.implements_operations == ["search", "view", "comment", "transition"]
    assert "create" not in contract.operations
    transition = contract.operations["transition"]
    assert transition.input_values == {"state": ["close", "reopen"]}
    with pytest.raises(ValueError, match="state must be one of: close, reopen"):
        validate_operation_inputs(transition, {"issue": "42", "state": "delete"})


def test_loads_the_gitlab_merge_request_adapter_as_an_explicit_subset() -> None:
    contract = load_tool_contract(template_root() / "adapters" / "cli" / "gitlab-merge-requests")
    implemented = load_tool_contract(template_root() / "tools" / "code-review")

    validate_tool_adapter_contract(contract, implemented)
    assert contract.provider == "gitlab"
    assert contract.executable == "glab"
    assert contract.version_command == ["version"]
    assert contract.minimum_runtime_version == "1.109.0"
    assert contract.implements_operations == ["view", "create", "comment", "checks"]
    assert sorted(contract.operations) == ["checks", "comment", "create", "view"]
    assert contract.operations["checks"].arguments[:3] == ["ci", "get", "--merge-request"]
    assert "approve" not in contract.operations
    assert "merge" not in contract.operations


@pytest.mark.parametrize(
    ("adapter_id", "provider", "executable"),
    [
        ("aws-resource-inventory", "aws", "aws"),
        ("gcp-asset-inventory", "google-cloud", "gcloud"),
    ],
)
def test_loads_a_read_only_cloud_inventory_adapter(
    adapter_id: str, provider: str, executable: str
) -> None:
    contract = load_tool_contract(template_root() / "adapters" / "cli" / adapter_id)
    implemented = load_tool_contract(template_root() / "tools" / "cloud-infrastructure")

    validate_tool_adapter_contract(contract, implemented)
    assert contract.provider == provider
    assert contract.executable == executable
    assert contract.implements_operations == ["list-resources", "inspect-resource"]
    assert sorted(contract.operations) == ["inspect-resource", "list-resources"]
    assert all(operation.risk == "read" for operation in contract.operations.values())


def test_loads_the_jira_acli_adapter() -> None:
    contract = load_tool_contract(template_root() / "adapters" / "cli" / "jira")
    implemented = load_tool_contract(template_root() / "tools" / "work-management")

    validate_tool_adapter_contract(contract, implemented)
    assert contract.provider == "atlassian"
    assert contract.executable == "acli"
    assert contract.implements == "work-management"
    assert contract.version_command == ["--version"]
    assert contract.minimum_runtime_version == "1.3.0"
    assert contract.operations["search"].arguments[:4] == [
        "jira",
        "workitem",
        "search",
        "--jql",
    ]
    assert contract.operations["transition"].arguments[-2:] == ["--yes", "--json"]


def test_loads_the_twg_confluence_adapter_as_an_explicit_subset() -> None:
    contract = load_tool_contract(template_root() / "adapters" / "cli" / "twg-confluence")
    implemented = load_tool_contract(template_root() / "tools" / "knowledge-base")

    validate_tool_adapter_contract(contract, implemented)
    assert contract.provider == "atlassian-confluence"
    assert contract.executable == "twg"
    assert contract.version_command == ["-v"]
    assert contract.minimum_runtime_version == "1.2.5"
    assert contract.implements_operations == [
        "view",
        "create",
        "update",
        "publish",
        "archive",
    ]
    assert "search" not in contract.operations
    assert contract.operations["update"].inputs == [
        "document",
        "title",
        "body",
        "snapshot-token",
    ]
    assert contract.operations["archive"].risk == "destructive"


@pytest.mark.parametrize(
    ("adapter_id", "output", "expected_version"),
    [
        ("github-actions", "gh version 2.82.1 (2025-10-22)", "2.82.1"),
        ("terraform", "Terraform v1.7.0\non linux_amd64", "1.7.0"),
        ("aws-resource-inventory", "aws-cli/2.0.30 Python/3.7.3", "2.0.30"),
        ("gcp-asset-inventory", "Google Cloud SDK 568.0.0", "568.0.0"),
        ("jira", "acli version 1.3.15", "1.3.15"),
        ("twg-confluence", "1.2.5", "1.2.5"),
        ("gitlab-issues", "glab version 1.109.0", "1.109.0"),
        ("gitlab-merge-requests", "glab version 1.109.0", "1.109.0"),
        ("gitlab-ci", "glab version 1.109.0", "1.109.0"),
    ],
)
def test_probes_compatible_cli_adapter_versions(
    adapter_id: str, output: str, expected_version: str
) -> None:
    contract = load_tool_contract(template_root() / "adapters" / "cli" / adapter_id)

    probe = probe_tool_runtime(
        contract,
        f"/usr/bin/{contract.executable}",
        runner=lambda command: subprocess.CompletedProcess(command, 0, output, ""),
    )

    assert probe.available is True
    assert probe.version == expected_version
    assert probe.compatible is True
    assert "satisfies minimum version" in probe.detail


def test_reports_missing_old_and_unverifiable_cli_runtimes() -> None:
    contract = load_tool_contract(template_root() / "adapters" / "cli" / "terraform")

    missing = probe_tool_runtime(contract, None)
    old = probe_tool_runtime(
        contract,
        "/usr/bin/terraform",
        runner=lambda command: subprocess.CompletedProcess(command, 0, "Terraform v0.14.0", ""),
    )
    unknown = probe_tool_runtime(
        contract,
        "/usr/bin/terraform",
        runner=lambda command: subprocess.CompletedProcess(command, 0, "development build", ""),
    )

    assert missing.compatible is False
    assert missing.version is None
    assert old.compatible is False
    assert old.version == "0.14.0"
    assert unknown.compatible is None
    assert "no MAJOR.MINOR.PATCH" in unknown.detail


def test_rejects_an_extra_operation_in_a_partial_adapter() -> None:
    adapter = load_tool_contract(template_root() / "adapters" / "cli" / "aws-resource-inventory")
    implemented = load_tool_contract(template_root() / "tools" / "cloud-infrastructure")
    adapter.operations["plan"] = implemented.operations["plan"]

    with pytest.raises(ValueError, match=r"extra=\[plan\]"):
        validate_tool_adapter_contract(adapter, implemented)


def test_rejects_an_adapter_that_weakens_environment_governance() -> None:
    adapter = load_tool_contract(template_root() / "adapters" / "cli" / "terraform")
    implemented = load_tool_contract(template_root() / "tools" / "cloud-infrastructure")
    adapter.operations["plan"] = replace(adapter.operations["plan"], environment_required=False)

    with pytest.raises(ValueError, match="environment requirement must match"):
        validate_tool_adapter_contract(adapter, implemented)


def test_loads_the_bundled_knowledge_base_contract() -> None:
    contract = load_tool_contract(template_root() / "tools" / "knowledge-base")

    assert contract.id == "knowledge-base"
    assert contract.executable == "docsctl"
    assert list(contract.operations) == ["archive", "create", "publish", "search", "update", "view"]
    assert contract.operations["search"].capability == "docs.read"
    assert contract.operations["create"].capability == "docs.write"
    assert contract.operations["publish"].capability == "docs.publish"
    assert contract.operations["archive"].capability == "docs.archive"
    assert contract.operations["archive"].risk == "destructive"


def test_loads_the_bundled_cloud_infrastructure_contract() -> None:
    contract = load_tool_contract(template_root() / "tools" / "cloud-infrastructure")

    assert contract.id == "cloud-infrastructure"
    assert contract.executable == "cloudctl"
    assert list(contract.operations) == [
        "apply-plan",
        "destroy-resource",
        "inspect-resource",
        "list-resources",
        "plan",
    ]
    assert contract.operations["list-resources"].capability == "cloud.read"
    assert contract.operations["plan"].capability == "cloud.plan"
    assert contract.operations["apply-plan"].capability == "cloud.deploy"
    assert contract.operations["destroy-resource"].capability == "cloud.destroy"
    assert contract.operations["plan"].environment_required is True
    assert contract.operations["destroy-resource"].risk == "destructive"


def test_loads_the_bundled_observability_contract() -> None:
    contract = load_tool_contract(template_root() / "tools" / "observability")

    assert contract.id == "observability"
    assert contract.executable == "observectl"
    assert list(contract.operations) == [
        "create-incident",
        "query-metrics",
        "resolve-incident",
        "search-logs",
        "service-health",
        "update-incident",
    ]
    assert contract.operations["service-health"].capability == "observability.read"
    assert contract.operations["create-incident"].capability == "incident.write"
    assert contract.operations["resolve-incident"].capability == "incident.resolve"


@pytest.mark.parametrize(
    "message",
    [
        "feat: add governed commits",
        "fix(parser): reject an empty description",
        "feat(api)!: remove the legacy endpoint",
        "docs: explain the policy\n\nThis body adds context.",
        "refactor!: change the contract\n\nBREAKING CHANGE: callers must pass an actor",
    ],
)
def test_accepts_conventional_commit_messages(message: str) -> None:
    validate_conventional_commit(message)


@pytest.mark.parametrize(
    ("message", "error"),
    [
        ("record governed work", "must match Conventional Commits"),
        ("feat:add missing space", "must match Conventional Commits"),
        ("feat: ", "must match Conventional Commits"),
        ("feat(core): add rule\nBody without separator", "must begin after a blank line"),
        ("feat: invalid\x00message", "must not contain a null byte"),
    ],
)
def test_rejects_non_conventional_commit_messages(message: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        validate_conventional_commit(message)


def test_rejects_undeclared_command_placeholders(tmp_path: Path) -> None:
    tool = tmp_path / "tool"
    (tool / "operations").mkdir(parents=True)
    (tool / "TOOL.md").write_text(
        '---\nschema: "agora/tool/v1"\nid: "tracker"\nname: "Tracker"\n'
        'category: "issue-tracker"\nexecutable: "tracker"\n---\n\n# Tracker\n'
    )
    (tool / "operations" / "view.md").write_text(
        '---\nschema: "agora/tool-operation/v1"\nid: "view"\nname: "View issue"\n'
        'capability: "issue.read"\nrisk: "read"\narguments: ["view","{issue}"]\n'
        "inputs: []\n---\n\n# View issue\n"
    )

    with pytest.raises(ValueError, match="undeclared placeholders: issue"):
        load_tool_contract(tool)


def test_rejects_unknown_tool_input_rules(tmp_path: Path) -> None:
    tool = tmp_path / "tool"
    (tool / "operations").mkdir(parents=True)
    (tool / "TOOL.md").write_text(
        '---\nschema: "agora/tool/v1"\nid: "repository"\nname: "Repository"\n'
        'category: "repository"\nexecutable: "git"\n---\n\n# Repository\n'
    )
    (tool / "operations" / "commit.md").write_text(
        '---\nschema: "agora/tool-operation/v1"\nid: "commit"\nname: "Commit"\n'
        'capability: "repository.write"\nrisk: "write"\n'
        'arguments: ["commit","-m","{message}"]\ninputs: ["message"]\n'
        'input-rules: {"message":"unregistered-rule/v1"}\n---\n\n# Commit\n'
    )

    with pytest.raises(ValueError, match="unsupported input rules: unregistered-rule/v1"):
        load_tool_contract(tool)


def test_rejects_incomplete_tool_adapter_metadata(tmp_path: Path) -> None:
    tool = tmp_path / "tool"
    (tool / "operations").mkdir(parents=True)
    (tool / "TOOL.md").write_text(
        '---\nschema: "agora/tool/v1"\nid: "vendor"\nname: "Vendor"\n'
        'category: "ci"\nexecutable: "vendor"\nprovider: "vendor"\n'
        'transport: "cli"\n---\n\n# Vendor\n'
    )
    (tool / "operations" / "view.md").write_text(
        '---\nschema: "agora/tool-operation/v1"\nid: "view"\nname: "View"\n'
        'capability: "ci.read"\nrisk: "read"\narguments: ["view"]\ninputs: []\n'
        "---\n\n# View\n"
    )

    with pytest.raises(ValueError, match="requires provider, transport, and implements"):
        load_tool_contract(tool)


def test_rejects_incomplete_runtime_version_metadata(tmp_path: Path) -> None:
    tool = tmp_path / "tool"
    (tool / "operations").mkdir(parents=True)
    (tool / "TOOL.md").write_text(
        '---\nschema: "agora/tool/v1"\nid: "tracker"\nname: "Tracker"\n'
        'category: "issue-tracker"\nexecutable: "tracker"\n'
        'version-command: ["--version"]\n---\n\n# Tracker\n'
    )
    (tool / "operations" / "view.md").write_text(
        '---\nschema: "agora/tool-operation/v1"\nid: "view"\nname: "View"\n'
        'capability: "issue.read"\nrisk: "read"\narguments: ["view"]\ninputs: []\n'
        "---\n\n# View\n"
    )

    with pytest.raises(ValueError, match="must be declared together"):
        load_tool_contract(tool)


def test_rejects_an_adapter_that_weakens_the_implemented_contract(tmp_path: Path) -> None:
    adapter = load_tool_contract(template_root() / "adapters" / "cli" / "github-actions")
    implemented = load_tool_contract(template_root() / "tools" / "ci-cd")
    adapter.operations["cancel-run"] = replace(
        adapter.operations["cancel-run"], capability="ci.read"
    )

    with pytest.raises(ValueError, match="cancel-run capability must be ci.cancel"):
        validate_tool_adapter_contract(adapter, implemented)

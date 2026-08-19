from dataclasses import replace

from agora.credentials import env_var_name, resolve_credential_chain
from agora.filesystem import packs_root
from agora.tools import load_tool_contract


def test_resolves_env_source_from_a_declared_variable() -> None:
    contract = load_tool_contract(packs_root() / "adapters" / "cli" / "terraform")

    resolution = resolve_credential_chain(contract, environ={})
    assert resolution.resolved_source is None
    assert resolution.checks[0].source == "env"
    assert resolution.checks[0].satisfied is False

    var = env_var_name(contract)
    resolution = resolve_credential_chain(contract, environ={var: "irrelevant-presence-check-only"})
    assert resolution.resolved_source == "env"


def test_never_reports_a_credential_value_only_presence() -> None:
    contract = load_tool_contract(packs_root() / "adapters" / "cli" / "terraform")
    var = env_var_name(contract)
    secret = "super-secret-token-value"  # noqa: S105 - test fixture, not a real credential

    resolution = resolve_credential_chain(contract, environ={var: secret})

    rendered = str(resolution)
    assert secret not in rendered


def test_workload_identity_and_keychain_are_unknown_not_false() -> None:
    contract = load_tool_contract(packs_root() / "adapters" / "cli" / "gcp-asset-inventory")

    resolution = resolve_credential_chain(contract, environ={})

    workload_check = next(c for c in resolution.checks if c.source == "workload-identity")
    assert workload_check.satisfied is None


def test_cli_session_resolves_when_executable_is_on_path(monkeypatch) -> None:
    contract = load_tool_contract(packs_root() / "adapters" / "cli" / "jira")
    contract = replace(contract, executable="python3")

    resolution = resolve_credential_chain(contract, environ={})

    assert resolution.resolved_source == "cli-session"


def test_env_var_name_is_derived_from_the_provider() -> None:
    contract = load_tool_contract(packs_root() / "adapters" / "cli" / "jira")

    assert env_var_name(contract) == "AGORA_ATLASSIAN_TOKEN"

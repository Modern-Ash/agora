"""Credential Source Chain: how Agora resolves whether a Tool Pack adapter can
authenticate, without ever holding, transmitting, or displaying the credential
itself.

Every Tool Pack adapter declares an ordered `credential-sources` list in its
TOOL.md front matter. This module resolves that list against the local
environment to a plain availability signal — never a secret value. Agora
delegates the actual authentication to the provider's own CLI, environment
variable, OS keychain, or workload identity; this module only answers
"would this adapter be able to authenticate right now, and how".
"""

import os
import shutil
from dataclasses import dataclass

from agora.model import ToolContract

CLI_SESSION = "cli-session"
ENV = "env"
KEYCHAIN = "keychain"
WORKLOAD_IDENTITY = "workload-identity"

CREDENTIAL_SOURCES = (CLI_SESSION, ENV, KEYCHAIN, WORKLOAD_IDENTITY)


@dataclass(frozen=True)
class CredentialSourceResolution:
    source: str
    satisfied: bool | None
    detail: str


@dataclass(frozen=True)
class CredentialChainResolution:
    tool_id: str
    resolved_source: str | None
    checks: list[CredentialSourceResolution]


def env_var_name(contract: ToolContract) -> str:
    """The one standard env var name Agora looks for, per adapter.

    Never read elsewhere in the codebase for its value beyond a presence
    check — the value itself is passed through to the adapter subprocess
    verbatim by the OS environment, not logged or echoed by Agora.
    """
    slug = (contract.provider or contract.id).replace("-", "_").upper()
    return f"AGORA_{slug}_TOKEN"


def _check_source(
    source: str, contract: ToolContract, environ: dict[str, str]
) -> CredentialSourceResolution:
    if source == CLI_SESSION:
        found = shutil.which(contract.executable) is not None
        detail = (
            f"{contract.executable} is on PATH; session state is not inspected"
            if found
            else f"{contract.executable} not found on PATH"
        )
        return CredentialSourceResolution(source, found or None, detail)
    if source == ENV:
        var = env_var_name(contract)
        present = bool(environ.get(var))
        detail = f"{var} is set" if present else f"{var} is not set"
        return CredentialSourceResolution(source, present, detail)
    if source == KEYCHAIN:
        return CredentialSourceResolution(
            source, None, "OS keychain presence is not locally inspectable"
        )
    if source == WORKLOAD_IDENTITY:
        return CredentialSourceResolution(
            source, None, "Ambient identity (IAM role, OIDC) is not locally inspectable"
        )
    raise ValueError(f"Unsupported credential source: {source}")


def resolve_credential_chain(
    contract: ToolContract, environ: dict[str, str] | None = None
) -> CredentialChainResolution:
    """Walk the adapter's declared credential sources in order and report the
    first one that is confirmed available. Sources that cannot be verified
    locally (keychain, workload identity) are reported as unknown, not false.
    """
    environ = os.environ if environ is None else environ
    checks = [_check_source(source, contract, environ) for source in contract.credential_sources]
    resolved = next((check.source for check in checks if check.satisfied), None)
    return CredentialChainResolution(tool_id=contract.id, resolved_source=resolved, checks=checks)

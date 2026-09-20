from dataclasses import replace
from pathlib import Path

import pytest
from test_adr_0002 import _project

from agora.application import AgoraReadService
from agora.identity import session_authorization_payload
from agora.model import SessionProvenance, SetActorRuntimeInput, StartSessionInput
from agora.workspace import AgoraWorkspace


def _start(workspace: AgoraWorkspace, session_id: str, **extra: object):
    return workspace.start_session(
        StartSessionInput(
            id=session_id,
            actor_id="developer",
            swarm_id="delivery",
            work_id="feature",
            **extra,  # type: ignore[arg-type]
        )
    )


def _rewrite(session_path: Path, transform) -> None:
    file = session_path / "SESSION.md"
    file.write_text(transform(file.read_text(encoding="utf-8")), encoding="utf-8")


def test_new_session_persists_declared_provenance_and_round_trips(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("agora.workspace.shutil.which", lambda executable: "/bin/codex")
    workspace = _project(tmp_path, monkeypatch)

    session = _start(workspace, "primary", runtime_version="1.2.3")

    assert session.provenance == SessionProvenance(
        runtime_basis="declared",
        provider_basis="declared",
        model_basis="declared",
        selection_reason="primary",
        runtime_version="1.2.3",
    )
    assert workspace.show_session("primary").provenance == session.provenance
    text = (Path(session.path) / "SESSION.md").read_text(encoding="utf-8")
    assert "provenance-selection-reason" in text
    assert "fallback-from" not in text


def test_fallback_records_original_selection_and_reason(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "agora.workspace.shutil.which",
        lambda executable: "/usr/bin/claude" if executable == "claude" else None,
    )
    workspace = _project(tmp_path, monkeypatch)
    workspace.set_actor_runtime(
        SetActorRuntimeInput(
            actor_id="developer",
            integration="codex",
            provider="openai",
            model="primary",
            fallbacks=["claude:anthropic:fallback-model"],
        )
    )

    session = _start(workspace, "fallback")

    assert (session.integration, session.provider, session.model) == (
        "claude",
        "anthropic",
        "fallback-model",
    )
    provenance = workspace.show_session("fallback").provenance
    assert provenance is not None
    assert provenance.fallback_used is True
    assert (
        provenance.fallback_from_integration,
        provenance.fallback_from_provider,
        provenance.fallback_from_model,
    ) == ("codex", "openai", "primary")
    assert provenance.selection_reason == provenance.fallback_reason
    assert provenance.selection_reason == "fallback-executable-unavailable"


def test_runner_override_and_unavailable_candidates_are_explicit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("agora.workspace.shutil.which", lambda executable: None)
    workspace = _project(tmp_path, monkeypatch)

    none_available = _start(workspace, "none-available")
    override = _start(workspace, "override", runner="echo")

    assert none_available.provenance is not None
    assert none_available.provenance.selection_reason == "no-candidate-available"
    assert none_available.provenance.fallback_used is False
    assert override.provenance is not None
    assert override.provenance.selection_reason == "runner-override"


def test_legacy_session_without_provenance_stays_loadable_and_reports_unavailable(
    tmp_path, monkeypatch
) -> None:
    workspace = _project(tmp_path, monkeypatch)
    session = _start(workspace, "legacy")
    _rewrite(
        Path(session.path),
        lambda text: (
            "\n".join(line for line in text.splitlines() if not line.startswith("provenance-"))
            + "\n"
        ),
    )

    loaded = workspace.show_session("legacy")
    summary = AgoraReadService(workspace).get_session("legacy").provenance

    assert loaded.provenance is None
    assert (summary.runtime_basis, summary.provider_basis, summary.model_basis) == (
        "unavailable",
        "unavailable",
        "unavailable",
    )
    assert summary.selection_reason is None
    assert summary.fallback_used is False


@pytest.mark.parametrize(
    "value",
    ["https://api.example.com/v1", "sk-abcdefghijkl", "token=abc123", "x" * 201, "two\nlines"],
)
def test_runtime_version_rejects_endpoints_credentials_and_oversized_text(
    tmp_path, monkeypatch, value: str
) -> None:
    workspace = _project(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="without credentials or endpoints"):
        _start(workspace, "unsafe", runtime_version=value)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            'provenance-model-basis: "declared"',
            'provenance-model-basis: "guessed"',
            "Unsupported Session provenance basis",
        ),
        (
            'provenance-selection-reason: "no-candidate-available"',
            'provenance-selection-reason: "because"',
            "Unsupported Session selection reason",
        ),
        (
            "provenance-fallback-used: false",
            "provenance-fallback-used: true",
            "inconsistent",
        ),
    ],
)
def test_tampered_provenance_fails_closed_on_load(
    tmp_path, monkeypatch, old: str, new: str, message: str
) -> None:
    monkeypatch.setattr("agora.workspace.shutil.which", lambda executable: None)
    workspace = _project(tmp_path, monkeypatch)
    session = _start(workspace, "tampered")
    _rewrite(Path(session.path), lambda text: text.replace(old, new))

    with pytest.raises(ValueError, match=message):
        workspace.show_session("tampered")


def test_authorization_payload_binds_provenance_only_when_present(tmp_path, monkeypatch) -> None:
    workspace = _project(tmp_path, monkeypatch)
    session = _start(workspace, "signed")
    assert session.provenance is not None
    bound = session_authorization_payload(session)
    legacy = session_authorization_payload(replace(session, provenance=None))

    assert b'"provenance"' in bound
    assert b'"provenance"' not in legacy
    changed = SessionProvenance(
        **{**session.provenance.__dict__, "selection_reason": "runner-override"}
    )
    rebound = session_authorization_payload(replace(session, provenance=changed))
    assert rebound != bound

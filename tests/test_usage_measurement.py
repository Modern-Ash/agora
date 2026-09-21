import io
import json
from pathlib import Path

import pytest
from test_usage_accounting import _budgeted_workspace

from agora.cli import main
from agora.markdown import read_markdown, render_markdown
from agora.model import AddUsageInput, ApplyLifecycleActionInput, PrepareUsageInput


def _usage(workspace, usage_id, amounts, measurement=None, **extra):
    return workspace.add_usage(
        AddUsageInput(
            id=usage_id,
            swarm_id="delivery",
            work_id="increment",
            actor_id="developer",
            amounts=amounts,
            evidence_refs=["repo://evidence/metering.md"],
            measurement=measurement,
            **extra,
        )
    )


def _strip_measurement(record):
    path = Path(record.path)
    document = read_markdown(path)
    document.attributes.pop("measurement", None)
    path.write_text(render_markdown(document), encoding="utf-8")


def test_records_persist_and_reload_their_measurement_basis(tmp_path, monkeypatch):
    workspace = _budgeted_workspace(tmp_path, monkeypatch)
    measured = _usage(workspace, "m1", {"tokens": 10}, "measured")
    reported = _usage(workspace, "r1", {"cost-cents": 5}, "provider-reported")

    assert (measured.measurement, reported.measurement) == ("measured", "provider-reported")
    loaded = {
        record.id: record.measurement for record in workspace.list_usage("delivery", "increment")
    }
    assert loaded == {"m1": "measured", "r1": "provider-reported"}
    assert "measurement: " in Path(measured.path).read_text(encoding="utf-8")


def test_legacy_records_have_no_measurement_and_files_stay_byte_identical(tmp_path, monkeypatch):
    workspace = _budgeted_workspace(tmp_path, monkeypatch)
    record = _usage(workspace, "legacy", {"tokens": 10})

    assert record.measurement is None
    assert "measurement" not in Path(record.path).read_text(encoding="utf-8")
    assert workspace.list_usage("delivery", "increment")[0].measurement is None


def test_summary_reports_the_weakest_basis_per_dimension_and_never_upgrades_to_measured(
    tmp_path, monkeypatch
):
    workspace = _budgeted_workspace(tmp_path, monkeypatch)
    _usage(workspace, "m1", {"tokens": 10, "cost-cents": 5}, "measured")
    _usage(workspace, "r1", {"tokens": 10}, "provider-reported")
    assert workspace.summarize_usage("delivery", "increment").consumed_measurement == {
        "cost-cents": "measured",
        "tokens": "provider-reported",
    }

    _usage(workspace, "legacy", {"cost-cents": 5})
    summary = workspace.summarize_usage("delivery", "increment")
    assert summary.consumed_measurement == {"cost-cents": "unknown", "tokens": "provider-reported"}
    assert summary.consumed == {"cost-cents": 10, "tokens": 20}


def test_explicit_unknown_is_accepted_and_invalid_values_are_rejected(tmp_path, monkeypatch):
    workspace = _budgeted_workspace(tmp_path, monkeypatch)
    assert _usage(workspace, "u1", {"tokens": 1}, "unknown").measurement == "unknown"
    with pytest.raises(ValueError, match="Usage measurement must be one of"):
        _usage(workspace, "bad", {"tokens": 1}, "estimated")
    assert [record.id for record in workspace.list_usage("delivery", "increment")] == ["u1"]


def test_tampered_measurement_fails_validation_on_load(tmp_path, monkeypatch):
    workspace = _budgeted_workspace(tmp_path, monkeypatch)
    record = _usage(workspace, "m1", {"tokens": 10}, "measured")
    path = Path(record.path)
    path.write_text(
        path.read_text(encoding="utf-8").replace('"measured"', '"guessed"'), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="measurement is not supported"):
        workspace.list_usage("delivery", "increment")


def test_budget_enforcement_does_not_depend_on_the_measurement_basis(tmp_path, monkeypatch):
    workspace = _budgeted_workspace(tmp_path, monkeypatch)
    _usage(workspace, "r1", {"tokens": 90}, "provider-reported")
    with pytest.raises(ValueError, match="Usage exceeds work budget"):
        _usage(workspace, "m1", {"tokens": 20}, "measured")


def test_prepared_action_binds_the_measurement_and_apply_persists_it(tmp_path, monkeypatch):
    workspace = _budgeted_workspace(tmp_path, monkeypatch)
    usage = AddUsageInput(
        id="prepared",
        swarm_id="delivery",
        work_id="increment",
        actor_id="developer",
        amounts={"tokens": 7},
        evidence_refs=["repo://evidence/metering.md"],
        measurement="provider-reported",
    )
    action = workspace.prepare_add_usage(PrepareUsageInput(action_id="usage-action", usage=usage))
    assert action.parameters["measurement"] == "provider-reported"
    workspace.apply_lifecycle_action(ApplyLifecycleActionInput(action_id=action.id))
    (record,) = workspace.list_usage("delivery", "increment")
    assert record.measurement == "provider-reported" and record.action_id == action.id

    plain = workspace.prepare_add_usage(
        PrepareUsageInput(
            action_id="usage-plain",
            usage=AddUsageInput(**{**usage.__dict__, "id": "plain", "measurement": None}),
        )
    )
    assert "measurement" not in plain.parameters


def test_cli_accepts_the_measurement_flag_and_status_reports_it(tmp_path, monkeypatch):
    workspace = _budgeted_workspace(tmp_path, monkeypatch)
    root = workspace.project_root()
    base = ["usage", "add", "--swarm", "delivery", "--work", "increment", "--by", "developer"]
    assert (
        main(
            [
                *base,
                "--id",
                "cli-1",
                "--amount",
                "tokens=3",
                "--evidence",
                "repo://e.md",
                "--measurement",
                "measured",
            ],
            cwd=root,
            stdout=io.StringIO(),
        )
        == 0
    )
    output = io.StringIO()
    assert (
        main(
            ["usage", "status", "--swarm", "delivery", "--work", "increment"],
            cwd=root,
            stdout=output,
        )
        == 0
    )
    assert json.loads(output.getvalue())["consumed_measurement"] == {"tokens": "measured"}
    with pytest.raises(SystemExit):
        main(
            [
                *base,
                "--id",
                "cli-2",
                "--amount",
                "tokens=1",
                "--evidence",
                "e",
                "--measurement",
                "guess",
            ],
            cwd=root,
            stdout=io.StringIO(),
        )


def test_validation_detects_a_measurement_changed_after_the_action_was_applied(
    tmp_path, monkeypatch
):
    workspace = _budgeted_workspace(tmp_path, monkeypatch)
    usage = AddUsageInput(
        id="bound",
        swarm_id="delivery",
        work_id="increment",
        actor_id="developer",
        amounts={"tokens": 7},
        evidence_refs=["repo://evidence/metering.md"],
        measurement="provider-reported",
    )
    action = workspace.prepare_add_usage(PrepareUsageInput(action_id="usage-bound", usage=usage))
    workspace.apply_lifecycle_action(ApplyLifecycleActionInput(action_id=action.id))
    (record,) = workspace.list_usage("delivery", "increment")
    path = Path(record.path)
    path.write_text(
        path.read_text(encoding="utf-8").replace("provider-reported", "measured"), encoding="utf-8"
    )

    issues = [item for item in workspace.validate().issues if "usage" in item.code]
    assert any(item.code == "lifecycle-action.usage-mismatch" for item in issues)

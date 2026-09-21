from pathlib import Path

from test_adr_0002 import _project

from agora.application import AgoraReadService
from agora.model import AddUsageInput


START = "2000-01-01T00:00:00Z"
END = "2100-01-01T00:00:00Z"
FUTURE_START = "2100-01-01T00:00:00Z"
FUTURE_END = "2200-01-01T00:00:00Z"


def _usage(workspace, usage_id: str, amounts: dict[str, int], measurement: str | None = None):
    return workspace.add_usage(
        AddUsageInput(
            id=usage_id,
            swarm_id="delivery",
            work_id="feature",
            actor_id="developer",
            amounts=amounts,
            evidence_refs=[f"evidence:{usage_id}"],
            measurement=measurement,
        )
    )


def _by_key(items):
    return {item.key: item for item in items}


def test_unknown_metric_key_is_unavailable_not_zero(tmp_path: Path, monkeypatch) -> None:
    workspace = _project(tmp_path, monkeypatch)
    service = AgoraReadService(workspace)

    item = service.metric_windows(
        "delivery",
        "feature",
        start=START,
        end=END,
        keys=("usage.not-recorded",),
    )[0]

    assert item.status == "unavailable"
    assert item.value is None
    assert item.count == 0
    assert item.source_refs == ()


def test_known_usage_dimension_can_be_available_zero_in_empty_window(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _project(tmp_path, monkeypatch)
    _usage(workspace, "known-tokens", {"tokens": 10}, "measured")
    service = AgoraReadService(workspace)

    item = service.metric_windows(
        "delivery",
        "feature",
        start=FUTURE_START,
        end=FUTURE_END,
        keys=("usage.tokens",),
    )[0]

    assert item.status == "available"
    assert item.value == 0
    assert item.count == 0
    assert item.measurement is None


def test_unknown_measurement_marks_usage_window_partial(tmp_path: Path, monkeypatch) -> None:
    workspace = _project(tmp_path, monkeypatch)
    _usage(workspace, "measured", {"tokens": 10}, "measured")
    _usage(workspace, "legacy", {"tokens": 5})
    service = AgoraReadService(workspace)

    item = service.metric_windows(
        "delivery",
        "feature",
        start=START,
        end=END,
        keys=("usage.tokens",),
    )[0]

    assert item.status == "partial"
    assert item.value == 15
    assert item.count == 2
    assert item.measurement == "unknown"
    assert item.source_refs == ("usage:measured", "usage:legacy")


def test_populated_windows_preserve_provider_neutral_sources_and_measurement(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _project(tmp_path, monkeypatch)
    _usage(workspace, "m1", {"cost-cents": 7}, "measured")
    _usage(workspace, "r1", {"cost-cents": 3}, "provider-reported")
    service = AgoraReadService(workspace)

    metrics = _by_key(
        service.metric_windows(
            "delivery",
            "feature",
            start=START,
            end=END,
            keys=("usage.cost-cents", "sessions.count", "artifacts.count"),
        )
    )

    usage = metrics["usage.cost-cents"]
    assert usage.status == "available"
    assert usage.value == 10
    assert usage.count == 2
    assert usage.measurement == "provider-reported"
    assert usage.source_refs == ("usage:m1", "usage:r1")

    assert metrics["sessions.count"].status == "available"
    assert metrics["sessions.count"].value == 0
    assert metrics["artifacts.count"].status == "available"
    assert metrics["artifacts.count"].value == 0


def test_flavor_projection_context_contains_derived_metric_windows(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _project(tmp_path, monkeypatch)
    _usage(workspace, "m1", {"tokens": 12}, "measured")
    service = AgoraReadService(workspace)

    context = service._flavor_projection_context("delivery", "feature")
    metrics = _by_key(context.metrics)

    assert metrics["usage.tokens"].value == 12
    assert metrics["usage.tokens"].measurement == "measured"
    assert metrics["usage.tokens"].status == "available"
    assert "artifacts.count" in metrics
    assert all(not ref.startswith(("/", "file:", "http:", "https:")) for item in context.metrics for ref in item.source_refs)

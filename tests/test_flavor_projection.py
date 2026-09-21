import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import swarm_dir
from jsonschema import Draft202012Validator

from agora.application import (
    AgoraReadService,
    ConcurrentDurableEditError,
    FlavorProjectionContribution,
    InvalidDurableStateError,
    InvalidReadQueryError,
    ReadResourceNotFoundError,
)
from agora.model import (
    AddActorInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
)
from agora.workspace import AgoraWorkspace

TIMESTAMP = datetime(2026, 9, 20, 12, tzinfo=UTC)
SCHEMA = "agora-ai-sdlc/studio-projection/v1"
FLAVOR_SECTIONS = ("flavor", "profiles", "provenance", "separation", "metrics")
CONTRACT_SECTIONS = (*FLAVOR_SECTIONS[:2], "lifecycle", "clarifications", *FLAVOR_SECTIONS[2:])
CONTRACT_ROOT = Path(__file__).parent / "contracts" / "ai-sdlc-studio-projection-v1"
CONTRACT_SCHEMA = json.loads((CONTRACT_ROOT / "schema.json").read_text(encoding="utf-8"))


class ExampleProjector:
    projection_schema = SCHEMA
    projection_schema_document = CONTRACT_SCHEMA
    required_sections = FLAVOR_SECTIONS

    def __init__(self, sections=None, presentation=None):
        self.sections = complete_sections() if sections is None else sections
        self.presentation = (
            {
                "authoritative": False,
                "labels": {"specified": "Specified"},
                "section_order": ["lifecycle", "clarifications"],
            }
            if presentation is None
            else presentation
        )
        self.contexts = []

    def project(self, context):
        self.contexts.append(context)
        return FlavorProjectionContribution(
            sections=self.sections,
            presentation=self.presentation,
        )


def complete_sections():
    return {
        "flavor": {
            "status": "available",
            "value": {
                "id": "example",
                "name": "Example flavor",
                "version": "1.0.0",
                "manifest_schema": "agora/flavor/v1",
                "supported_core": ">=0.8,<0.9",
            },
        },
        "profiles": {
            "status": "available",
            "value": [{"id": "regulated", "depth": "regulated", "active": True}],
        },
        "provenance": {
            "status": "unavailable",
            "reason": {
                "code": "projection.provenance-unavailable",
                "message": "Runtime provenance is unavailable",
            },
        },
        "separation": {
            "status": "available",
            "value": {
                "source_schema": "example/separation/v1",
                "decision": "blocked",
                "required_dimensions": ["actor", "provider"],
                "blockers": [],
            },
        },
        "metrics": {
            "status": "available",
            "value": {
                "source_schema": "example/metrics/v1",
                "window": "2026-W38",
                "items": [],
            },
        },
    }


def assert_contract_shape(payload):
    assert {
        "schema",
        "generated_at",
        "project",
        *CONTRACT_SECTIONS,
        "presentation",
    } <= payload.keys()
    assert re.fullmatch(r"[0-9a-f]{64}", payload["project"]["snapshot"])
    for name in CONTRACT_SECTIONS:
        section = payload[name]
        assert section["status"] in {"available", "unavailable"}
        if section["status"] == "available":
            assert "value" in section and "reason" not in section
        else:
            assert "value" not in section
            assert {"code", "message"} <= section["reason"].keys()
    assert payload["presentation"]["authoritative"] is False


@pytest.fixture
def projection_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=root, now=lambda: TIMESTAMP)
    workspace.initialize(
        InitInput(
            integration="generic",
            provider="local-provider",
            model="local-model",
            default_method="scrum",
        )
    )
    for actor in (
        AddActorInput(
            id="owner",
            name="Owner",
            kind="human",
            capabilities=["backlog-management", "acceptance"],
            scope="project",
        ),
        AddActorInput(
            id="facilitator",
            name="Facilitator",
            kind="ai-agent",
            capabilities=["facilitation", "governance"],
            scope="project",
        ),
        AddActorInput(
            id="developer",
            name="Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        workspace.add_actor(actor)
    workspace.create_swarm(
        CreateSwarmInput(id="delivery", objective="Project flavor state", create_branch=False)
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        workspace.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor))
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="projection",
            title="Project installed flavor state",
            actor_id="owner",
        )
    )
    clarifications = swarm_dir(root, "delivery") / "work" / "projection" / "clarifications.md"
    clarifications.write_text(
        """---
schema: "agora/clarifications/v1"
swarm: "delivery"
work: "projection"
created-at: "2026-09-20T12:00:00Z"
---

# Clarifications for projection

| Question | Answer | Actor | Timestamp | Input SHA-256 |
| --- | --- | --- | --- | --- |
| Which timeout applies? |  | project:owner | 2026-09-20T11:00:00Z |  |
| Is retry bounded? | Yes | project:owner | 2026-09-20T11:05:00Z |  |
""",
        encoding="utf-8",
    )
    return root, workspace


def service_for(workspace, projector):
    return AgoraReadService(
        workspace,
        flavor_projectors=(projector,),
        now=lambda: TIMESTAMP,
    )


def test_produces_complete_path_free_projection_from_real_application_services(
    projection_project,
):
    root, workspace = projection_project
    projector = ExampleProjector()
    projection = service_for(workspace, projector).flavor_projection(
        SCHEMA, "selected-01J7W9X4", "delivery", "projection"
    )
    payload = projection.to_dict()

    assert_contract_shape(payload)
    assert payload["schema"] == SCHEMA
    assert payload["generated_at"] == "2026-09-20T12:00:00Z"
    assert payload["project"] == {
        "selection_id": "selected-01J7W9X4",
        "id": "project",
        "swarm_id": "delivery",
        "work_id": "projection",
        "snapshot": payload["project"]["snapshot"],
    }
    assert re.fullmatch(r"[0-9a-f]{64}", payload["project"]["snapshot"])
    assert payload["lifecycle"]["value"]["current_state"] == "specified"
    assert payload["lifecycle"]["value"]["source_schema"].endswith("lifecycle-projection/v3")
    assert [item["status"] for item in payload["clarifications"]["value"]["open"]] == ["open"]
    assert [item["status"] for item in payload["clarifications"]["value"]["resolved"]] == [
        "resolved"
    ]
    assert payload["presentation"]["authoritative"] is False
    assert projector.contexts[0].project.id == "project"
    assert projector.contexts[0].selection is None
    assert set(projector.contexts[0].project.to_dict()) == {
        "id",
        "version",
        "integration",
        "default_method",
        "created_at",
        "schema",
    }
    assert str(root) not in projection.to_json()
    assert "repo://" not in projection.to_json()



def test_projector_context_exposes_optional_active_flavor_selection(projection_project):
    root, _ = projection_project
    project_file = root / ".agora" / "project.md"
    contents = project_file.read_text(encoding="utf-8")
    contents = contents.replace(
        'created-at: "2026-09-20T12:00:00Z"',
        'active-flavor: "ai-sdlc"\n'
        'active-profile: "lg-enterprise"\n'
        'active-depth: "regulated"\n'
        'created-at: "2026-09-20T12:00:00Z"',
    )
    project_file.write_text(contents, encoding="utf-8")

    workspace = AgoraWorkspace(cwd=root, now=lambda: TIMESTAMP)
    projector = ExampleProjector()
    service_for(workspace, projector).flavor_projection(
        SCHEMA, "selected-active-profile", "delivery", "projection"
    )

    assert projector.contexts[0].selection is not None
    assert projector.contexts[0].selection.to_dict() == {
        "flavor": "ai-sdlc",
        "profile": "lg-enterprise",
        "depth": "regulated",
        "schema": "agora/application/flavor-selection-summary/v1",
    }


@pytest.mark.parametrize("fixture_name", ["complete", "unavailable", "future-state"])
def test_producer_preserves_downstream_fixture_variants(projection_project, fixture_name):
    _, workspace = projection_project
    sections = complete_sections()
    if fixture_name == "unavailable":
        sections = {
            name: {
                "status": "unavailable",
                "reason": {
                    "code": f"projection.{name}-unavailable",
                    "message": f"{name.title()} projection is unavailable",
                },
            }
            for name in FLAVOR_SECTIONS
        }
    elif fixture_name == "future-state":
        sections["metrics"]["value"]["future_metric_field"] = True
        sections["future_top_level_section"] = {"status": "available", "value": {}}
    payload = (
        service_for(workspace, ExampleProjector(sections=sections))
        .flavor_projection(SCHEMA, f"selected-{fixture_name}", "delivery", "projection")
        .to_dict()
    )

    assert_contract_shape(payload)
    expected = {*FLAVOR_SECTIONS, "lifecycle", "clarifications"}
    assert expected <= payload.keys()
    assert all(payload[name]["status"] in {"available", "unavailable"} for name in expected)
    assert payload["lifecycle"]["value"]["current_state"] == "specified"
    if fixture_name == "future-state":
        assert payload["future_top_level_section"] == {"status": "available", "value": {}}
        assert payload["metrics"]["value"]["future_metric_field"] is True


@pytest.mark.parametrize("fixture_name", ["complete", "unavailable", "future-state"])
def test_matches_the_published_downstream_contract_fixtures(fixture_name):
    payload = json.loads((CONTRACT_ROOT / f"{fixture_name}.json").read_text(encoding="utf-8"))

    Draft202012Validator(CONTRACT_SCHEMA).validate(payload)
    assert CONTRACT_SCHEMA["properties"]["schema"]["const"] == payload["schema"]
    assert_contract_shape(payload)
    if fixture_name == "future-state":
        assert payload["lifecycle"]["value"]["current_state"] == "assurance-review"
        assert payload["lifecycle"]["value"]["states"][0]["future_hint"] == "render-generically"


@pytest.mark.parametrize(
    "sections,presentation",
    [
        ({}, {"authoritative": False}),
        (
            {**complete_sections(), "lifecycle": {"status": "available", "value": {}}},
            {"authoritative": False},
        ),
        (
            {**complete_sections(), "future": {"status": "available"}},
            {"authoritative": False},
        ),
        (
            {
                **complete_sections(),
                "future": {"status": "unavailable", "reason": {"code": "bad"}},
            },
            {"authoritative": False},
        ),
        (complete_sections(), {"authoritative": True}),
        (
            {
                **complete_sections(),
                "future": {"status": "available", "value": {"project_path": "/tmp/x"}},
            },
            {"authoritative": False},
        ),
        (
            {
                **complete_sections(),
                "future": {"status": "available", "value": {"note": "Bearer abcdef"}},
            },
            {"authoritative": False},
        ),
        (
            {
                **complete_sections(),
                "future": {"status": "available", "value": {"privateKey": "redacted"}},
            },
            {"authoritative": False},
        ),
        (
            {
                **complete_sections(),
                "future": {"status": "available", "value": {"note": "  FILE://secret"}},
            },
            {"authoritative": False},
        ),
        (
            {
                **complete_sections(),
                "future": {"status": "available", "value": {"note": "../outside"}},
            },
            {"authoritative": False},
        ),
        (
            {
                **complete_sections(),
                "future": {
                    "status": "available",
                    "value": {"note": "log at /home/alice/.ssh/id_rsa"},
                },
            },
            {"authoritative": False},
        ),
        (
            {
                **complete_sections(),
                "future": {
                    "status": "available",
                    "value": {"note": "connect to https://internal.example/api"},
                },
            },
            {"authoritative": False},
        ),
        (
            {
                **complete_sections(),
                "future": {
                    "status": "available",
                    "value": {"note": "github_pat_1234567890abcdef"},
                },
            },
            {"authoritative": False},
        ),
        (
            {
                **complete_sections(),
                "future": {
                    "status": "available",
                    "value": {"note": "glpat-1234567890abcdef"},
                },
            },
            {"authoritative": False},
        ),
        (
            {
                **complete_sections(),
                "future": {
                    "status": "available",
                    "value": {"note": "AKIAIOSFODNN7EXAMPLE"},
                },
            },
            {"authoritative": False},
        ),
        (
            {**complete_sections(), "flavor": {"status": "available", "value": {}}},
            {"authoritative": False},
        ),
        (
            {**complete_sections(), "profiles": {"status": "available", "value": []}},
            {"authoritative": False},
        ),
        (
            {**complete_sections(), "separation": {"status": "available", "value": {}}},
            {"authoritative": False},
        ),
    ],
)
def test_rejects_malformed_or_unsafe_extension_output(projection_project, sections, presentation):
    _, workspace = projection_project
    service = service_for(
        workspace,
        ExampleProjector(sections=sections, presentation=presentation),
    )

    with pytest.raises(InvalidDurableStateError):
        service.flavor_projection(SCHEMA, "selected-invalid", "delivery", "projection")


def test_rejects_invalid_registration_selection_and_unknown_schema(projection_project):
    _, workspace = projection_project
    with pytest.raises(InvalidReadQueryError, match="already registered"):
        AgoraReadService(
            workspace,
            flavor_projectors=(ExampleProjector(), ExampleProjector()),
        )
    service = service_for(workspace, ExampleProjector())
    with pytest.raises(InvalidReadQueryError, match="opaque"):
        service.flavor_projection(SCHEMA, "../project", "delivery", "projection")
    with pytest.raises(ReadResourceNotFoundError, match="No flavor projector"):
        service.flavor_projection(
            "unknown/projection/v1", "selected-unknown", "delivery", "projection"
        )


def test_rejects_missing_mismatched_or_remote_projector_schema(projection_project):
    _, workspace = projection_project
    missing = ExampleProjector()
    missing.projection_schema_document = None
    with pytest.raises(InvalidReadQueryError, match="JSON Schema document"):
        AgoraReadService(workspace, flavor_projectors=(missing,))

    mismatched = ExampleProjector()
    mismatched.projection_schema_document = {
        **CONTRACT_SCHEMA,
        "properties": {
            **CONTRACT_SCHEMA["properties"],
            "schema": {"const": "other/projection/v1"},
        },
    }
    with pytest.raises(InvalidReadQueryError, match="does not match"):
        AgoraReadService(workspace, flavor_projectors=(mismatched,))

    remote = ExampleProjector()
    remote.projection_schema_document = {
        **CONTRACT_SCHEMA,
        "$defs": {
            **CONTRACT_SCHEMA["$defs"],
            "remote": {"$ref": "https://example.test/schema"},
        },
    }
    with pytest.raises(InvalidReadQueryError, match="references must be local"):
        AgoraReadService(workspace, flavor_projectors=(remote,))


def test_retries_then_rejects_a_concurrently_changing_snapshot(
    projection_project, monkeypatch: pytest.MonkeyPatch
):
    _, workspace = projection_project
    service = service_for(workspace, ExampleProjector())
    fingerprints = iter(("before", "after") * 3)
    monkeypatch.setattr(
        workspace,
        "work_control_read_set_sha256",
        lambda swarm_id, work_id: next(fingerprints),
    )

    with pytest.raises(ConcurrentDurableEditError, match="three read attempts"):
        service.flavor_projection(SCHEMA, "selected-changing", "delivery", "projection")


def test_projection_snapshot_is_stable_across_observation_times(projection_project):
    _, workspace = projection_project
    projector = ExampleProjector()
    first = service_for(workspace, projector).flavor_projection(
        SCHEMA, "selected-stable", "delivery", "projection"
    )
    later = AgoraReadService(
        workspace,
        flavor_projectors=(ExampleProjector(),),
        now=lambda: datetime(2026, 9, 20, 13, tzinfo=UTC),
    ).flavor_projection(SCHEMA, "selected-stable", "delivery", "projection")

    assert first.generated_at != later.generated_at
    assert first.project["snapshot"] == later.project["snapshot"]
    assert json.loads(first.to_json()) == first.to_dict()


def _record_usage(workspace, usage_id, amounts, measurement=None):
    from agora.model import AddUsageInput

    return workspace.add_usage(
        AddUsageInput(
            id=usage_id,
            swarm_id="delivery",
            work_id="projection",
            actor_id="developer",
            amounts=amounts,
            evidence_refs=["repo://evidence/metering.md"],
            measurement=measurement,
        )
    )


def test_projector_context_carries_core_usage_with_the_weakest_measurement_basis(
    projection_project,
):
    _, workspace = projection_project
    projector = ExampleProjector()
    service = service_for(workspace, projector)

    service.flavor_projection(SCHEMA, "selected-usage", "delivery", "projection")
    empty = projector.contexts[-1].usage
    assert (empty.records, dict(empty.consumed), dict(empty.consumed_measurement)) == (0, {}, {})

    _record_usage(workspace, "m1", {"tokens": 10, "cost-cents": 5}, "measured")
    _record_usage(workspace, "r1", {"tokens": 4}, "provider-reported")
    _record_usage(workspace, "legacy", {"cost-cents": 1})
    service.flavor_projection(SCHEMA, "selected-usage", "delivery", "projection")
    usage = projector.contexts[-1].usage

    assert usage.schema == "agora/application/usage-summary/v1"
    assert usage.records == 3 and dict(usage.consumed) == {"cost-cents": 6, "tokens": 14}
    assert dict(usage.consumed_measurement) == {
        "cost-cents": "unknown",
        "tokens": "provider-reported",
    }
    assert usage.budget_limits is None and usage.remaining is None
    assert json.loads(usage.to_json())["consumed_measurement"]["tokens"] == "provider-reported"


def test_usage_summary_is_a_public_read_with_validated_scope(projection_project):
    _, workspace = projection_project
    service = AgoraReadService(workspace, now=lambda: TIMESTAMP)
    _record_usage(workspace, "m1", {"tokens": 10}, "measured")

    summary = service.usage_summary("delivery", "projection")
    assert summary.consumed_measurement == {"tokens": "measured"}
    assert summary.swarm_id == "delivery" and summary.work_id == "projection"

    with pytest.raises(InvalidReadQueryError):
        service.usage_summary("../escape", "projection")
    with pytest.raises(ReadResourceNotFoundError):
        service.usage_summary("delivery", "missing-work")

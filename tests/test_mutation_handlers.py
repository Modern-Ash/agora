from unittest.mock import Mock

import pytest

from agora.model import ActorRecord, MethodContract, PrepareCriterionInput, SwarmRecord, WorkRecord
from agora.mutation_handlers import CriterionMutationContext, WorkLifecycleHandlers


def test_work_lifecycle_handler_dispatches_with_explicit_context_only() -> None:
    satisfy = Mock(return_value="applied")
    handlers = WorkLifecycleHandlers(
        satisfy_criterion=satisfy,
        add_artifact=Mock(),
        add_evidence=Mock(),
    )
    context = CriterionMutationContext(
        command=PrepareCriterionInput(
            id="satisfy-one",
            swarm_id="delivery",
            work_id="work",
            actor_id="developer",
            criterion_id="done",
        ),
        swarm=SwarmRecord(
            id="delivery",
            method="scrum",
            status="ready",
            branch="main",
            required_roles=[],
            assignments={},
            objective="Deliver",
            path=".agora/swarms/delivery/SWARM.md",
        ),
        actor=ActorRecord(
            id="developer",
            reference="project:developer",
            name="Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            path=".agora/actors/developer.md",
        ),
        work=WorkRecord(
            id="work",
            swarm_id="delivery",
            title="Work",
            description="",
            state="implementing",
            acceptance_criteria={"done": "Done"},
            satisfied_criteria=[],
            required_artifacts=[],
            artifact_kinds=[],
            evidence_results=[],
            approval_roles=[],
            path=".agora/swarms/delivery/work/work",
        ),
        method=MethodContract(
            id="scrum",
            name="Scrum",
            version="1.0.0",
            dependencies=[],
            required_roles=[],
            work_states=[],
            terminal_state="completed",
            transitions=[],
            gates={},
            wip_limits={},
            criterion_stages=[],
        ),
    )

    assert handlers.actions == ("criterion.satisfy", "artifact.add", "evidence.add")
    assert handlers.dispatch("criterion.satisfy", context) == "applied"
    satisfy.assert_called_once_with(context)


def test_work_lifecycle_handler_rejects_unknown_actions_and_wrong_context() -> None:
    handlers = WorkLifecycleHandlers(
        satisfy_criterion=Mock(),
        add_artifact=Mock(),
        add_evidence=Mock(),
    )

    with pytest.raises(ValueError, match="No Work Lifecycle handler"):
        handlers.dispatch("work.transition", object())
    with pytest.raises(TypeError, match="CriterionMutationContext"):
        handlers.dispatch("criterion.satisfy", object())

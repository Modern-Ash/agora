import io
from pathlib import Path

from agora.cli import main
from agora.self_test import ACTOR_KINDS, BUNDLED_METHODS, run_role_self_test


def test_exercises_every_bundled_method_with_every_supported_actor_form() -> None:
    result = run_role_self_test()

    assert result["ok"] is True
    assert result["methods"] == 3
    assert result["actor_kinds"] == ["human", "ai-agent", "swarm"]
    assert len(result["cases"]) == len(BUNDLED_METHODS) * len(ACTOR_KINDS)
    assert result["role_assignments_verified"] == 24
    assert result["disallowed_assignments_rejected"] == 24
    assert {(case["method"], case["actor_kind"]) for case in result["cases"]} == {
        (method_id, actor_kind) for method_id in BUNDLED_METHODS for actor_kind in ACTOR_KINDS
    }
    assert all(case["terminal_state"] in {"completed", "done"} for case in result["cases"])


def test_self_test_is_available_without_an_initialized_project(tmp_path: Path) -> None:
    output = io.StringIO()
    errors = io.StringIO()

    assert main(["self-test"], cwd=tmp_path, stdout=output, stderr=errors) == 0
    assert errors.getvalue() == ""
    assert '"scope": "bundled-role-conformance"' in output.getvalue()
    assert '"role_assignments_verified": 24' in output.getvalue()

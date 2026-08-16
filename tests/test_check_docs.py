import runpy
from pathlib import Path

ROOT = Path(__file__).parents[1]
is_ignored_document = runpy.run_path(str(ROOT / "scripts" / "check_docs.py"))["is_ignored_document"]


def test_documentation_link_check_excludes_plugin_run_output() -> None:
    assert is_ignored_document(Path(".superpowers/sdd/generated.md")) is True
    assert is_ignored_document(Path("docs/superpowers/plans/generated.md")) is True
    assert is_ignored_document(Path("docs/superpowers/specs/generated.md")) is True
    assert is_ignored_document(Path("docs/guides/quickstart.md")) is False
    assert is_ignored_document(Path("templates/commands/execute.md")) is False

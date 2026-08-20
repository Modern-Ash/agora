from pathlib import Path

import pytest

from agora import filesystem
from agora.filesystem import FilesystemTransactionFailure, atomic_write, filesystem_transaction


@pytest.mark.parametrize("fail_at", [1, 2, 3])
def test_compound_transaction_restores_contents_modes_and_new_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_at: int
) -> None:
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    created = tmp_path / "new" / "third.md"
    first.write_text("first-before\n", encoding="utf-8")
    second.write_text("second-before\n", encoding="utf-8")
    first.chmod(0o640)
    original = filesystem._atomic_write_direct
    calls = 0

    def injected(path: Path, contents: str) -> None:
        nonlocal calls
        calls += 1
        if calls == fail_at:
            raise OSError(f"failure-{fail_at}")
        original(path, contents)

    monkeypatch.setattr(filesystem, "_atomic_write_direct", injected)

    with pytest.raises(FilesystemTransactionFailure) as captured:
        with filesystem_transaction():
            atomic_write(first, "first-after\n")
            atomic_write(second, "second-after\n")
            atomic_write(created, "new\n")

    assert captured.value.phase == "commit"
    assert captured.value.indeterminate is False
    assert first.read_text(encoding="utf-8") == "first-before\n"
    assert second.read_text(encoding="utf-8") == "second-before\n"
    assert first.stat().st_mode & 0o777 == 0o640
    assert not created.exists()
    assert not created.parent.exists()


def test_compound_transaction_reports_indeterminate_when_rollback_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("first-before\n", encoding="utf-8")
    second.write_text("second-before\n", encoding="utf-8")
    original = filesystem._atomic_write_direct
    calls = 0

    def injected(path: Path, contents: str) -> None:
        nonlocal calls
        calls += 1
        if calls in {2, 3}:
            raise OSError(f"failure-{calls}")
        original(path, contents)

    monkeypatch.setattr(filesystem, "_atomic_write_direct", injected)

    with pytest.raises(FilesystemTransactionFailure) as captured:
        with filesystem_transaction():
            atomic_write(first, "first-after\n")
            atomic_write(second, "second-after\n")

    assert captured.value.phase == "rollback"
    assert captured.value.indeterminate is True
    assert captured.value.rollback_errors
    assert "inspect Git" in captured.value.recovery_hint

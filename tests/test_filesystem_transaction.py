from pathlib import Path

import pytest

from agora import filesystem
from agora.filesystem import (
    FilesystemTransactionFailure,
    atomic_write,
    filesystem_fingerprint,
    filesystem_transaction,
)


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
    assert captured.value.verification_errors
    assert "inspect Git" in captured.value.recovery_hint


def test_rollback_error_is_distinct_when_post_verification_proves_restoration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("first-before\n", encoding="utf-8")
    second.write_text("second-before\n", encoding="utf-8")
    original = filesystem._atomic_write_direct
    calls = 0

    def restore_then_report_error(path: Path, contents: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("commit failure")
        original(path, contents)
        if calls == 3:
            raise OSError("rollback reported failure after restoration")

    monkeypatch.setattr(filesystem, "_atomic_write_direct", restore_then_report_error)

    with pytest.raises(FilesystemTransactionFailure) as captured:
        with filesystem_transaction():
            atomic_write(first, "first-after\n")
            atomic_write(second, "second-after\n")

    failure = captured.value
    assert failure.phase == "rollback"
    assert failure.indeterminate is False
    assert failure.rollback_errors
    assert failure.verification_errors == ()
    assert first.read_text(encoding="utf-8") == "first-before\n"
    assert second.read_text(encoding="utf-8") == "second-before\n"


def test_permission_restoration_mismatch_is_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("first-before\n", encoding="utf-8")
    second.write_text("second-before\n", encoding="utf-8")
    first.chmod(0o640)
    original_write = filesystem._atomic_write_direct
    original_chmod = Path.chmod
    writes = 0
    chmod_calls = 0

    def fail_second_write(path: Path, contents: str) -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("commit failure")
        original_write(path, contents)

    def fail_rollback_chmod(path: Path, mode: int) -> None:
        nonlocal chmod_calls
        chmod_calls += 1
        if chmod_calls == 2:
            raise OSError("permission restoration failure")
        original_chmod(path, mode)

    monkeypatch.setattr(filesystem, "_atomic_write_direct", fail_second_write)
    monkeypatch.setattr(Path, "chmod", fail_rollback_chmod)

    with pytest.raises(FilesystemTransactionFailure) as captured:
        with filesystem_transaction():
            atomic_write(first, "first-after\n")
            atomic_write(second, "second-after\n")

    assert captured.value.indeterminate is True
    assert "restored-snapshot-mismatch" in captured.value.verification_errors


def test_failed_new_file_removal_is_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.md"
    created = tmp_path / "new" / "created.md"
    last = tmp_path / "last.md"
    first.write_text("before\n", encoding="utf-8")
    last.write_text("last-before\n", encoding="utf-8")
    original_write = filesystem._atomic_write_direct
    original_unlink = Path.unlink
    writes = 0

    def fail_last_write(path: Path, contents: str) -> None:
        nonlocal writes
        writes += 1
        if writes == 3:
            raise OSError("last write failure")
        original_write(path, contents)

    def fail_created_unlink(path: Path, missing_ok: bool = False) -> None:
        if path == created:
            raise OSError("new file removal failure")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(filesystem, "_atomic_write_direct", fail_last_write)
    monkeypatch.setattr(Path, "unlink", fail_created_unlink)

    with pytest.raises(FilesystemTransactionFailure) as captured:
        with filesystem_transaction():
            atomic_write(first, "after\n")
            atomic_write(created, "created\n")
            atomic_write(last, "last-after\n")

    assert captured.value.indeterminate is True
    assert created.exists()
    assert captured.value.verification_errors


def test_external_edit_after_staging_aborts_before_any_transaction_write(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("first-before\n", encoding="utf-8")
    second.write_text("second-before\n", encoding="utf-8")

    with pytest.raises(FilesystemTransactionFailure) as captured:
        with filesystem_transaction():
            atomic_write(first, "first-after\n")
            atomic_write(second, "second-after\n")
            second.write_text("external-edit\n", encoding="utf-8")

    assert captured.value.phase == "concurrent-edit"
    assert captured.value.indeterminate is False
    assert first.read_text(encoding="utf-8") == "first-before\n"
    assert second.read_text(encoding="utf-8") == "external-edit\n"


def test_interleaved_external_edit_rolls_back_applied_writes_without_overwriting_editor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("first-before\n", encoding="utf-8")
    second.write_text("second-before\n", encoding="utf-8")
    original = filesystem._atomic_write_direct
    writes = 0

    def edit_second_after_first(path: Path, contents: str) -> None:
        nonlocal writes
        writes += 1
        original(path, contents)
        if writes == 1:
            second.write_text("external-edit\n", encoding="utf-8")

    monkeypatch.setattr(filesystem, "_atomic_write_direct", edit_second_after_first)

    with pytest.raises(FilesystemTransactionFailure) as captured:
        with filesystem_transaction():
            atomic_write(first, "first-after\n")
            atomic_write(second, "second-after\n")

    assert captured.value.phase == "concurrent-edit"
    assert captured.value.indeterminate is False
    assert first.read_text(encoding="utf-8") == "first-before\n"
    assert second.read_text(encoding="utf-8") == "external-edit\n"


def test_prepared_expected_fingerprint_detects_change_before_staging(
    tmp_path: Path,
) -> None:
    path = tmp_path / "prepared.md"
    path.write_text("prepared-version\n", encoding="utf-8")
    expected = filesystem_fingerprint(path)
    path.write_text("external-version\n", encoding="utf-8")

    with pytest.raises(FilesystemTransactionFailure) as captured:
        with filesystem_transaction({path: expected}):
            atomic_write(path, "transaction-version\n")

    assert captured.value.phase == "concurrent-edit"
    assert path.read_text(encoding="utf-8") == "external-version\n"


def test_post_commit_verification_rolls_back_unexpected_written_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("first-before\n", encoding="utf-8")
    second.write_text("second-before\n", encoding="utf-8")
    original = filesystem._atomic_write_direct
    writes = 0

    def tamper_after_last_write(path: Path, contents: str) -> None:
        nonlocal writes
        writes += 1
        original(path, contents)
        if writes == 2:
            first.write_text("external-after-write\n", encoding="utf-8")

    monkeypatch.setattr(filesystem, "_atomic_write_direct", tamper_after_last_write)

    with pytest.raises(FilesystemTransactionFailure) as captured:
        with filesystem_transaction():
            atomic_write(first, "first-after\n")
            atomic_write(second, "second-after\n")

    assert captured.value.phase == "commit"
    assert captured.value.indeterminate is False
    assert first.read_text(encoding="utf-8") == "first-before\n"
    assert second.read_text(encoding="utf-8") == "second-before\n"

import hashlib
import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path


def agora_home() -> Path:
    return Path(os.environ.get("AGORA_HOME", Path.home() / ".agora")).expanduser().resolve()


def packs_root() -> Path:
    override = os.environ.get("AGORA_PACKS_ROOT")
    if override:
        return Path(override).resolve()
    installed = Path(__file__).resolve().parent / "packs"
    if installed.exists():
        return installed
    return Path(__file__).resolve().parents[2] / "packs"


def _atomic_write_direct(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        temporary.write_text(contents, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class _FileSnapshot:
    contents: str | None
    mode: int | None

    @property
    def fingerprint(self) -> "FileFingerprint":
        return FileFingerprint(
            exists=self.contents is not None,
            content_sha256=(
                hashlib.sha256(self.contents.encode("utf-8")).hexdigest()
                if self.contents is not None
                else None
            ),
            mode=self.mode,
        )


@dataclass(frozen=True)
class FileFingerprint:
    """Content, existence, and permission identity for one durable Markdown path."""

    exists: bool
    content_sha256: str | None
    mode: int | None


class FilesystemTransactionFailure(OSError):
    """A compound Markdown commit failed, optionally leaving indeterminate state."""

    def __init__(
        self,
        message: str,
        *,
        phase: str,
        write_set: tuple[str, ...],
        rollback_errors: tuple[str, ...] = (),
        verification_errors: tuple[str, ...] = (),
        indeterminate: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.phase = phase
        self.write_set = write_set
        self.rollback_errors = rollback_errors
        self.verification_errors = verification_errors
        self.indeterminate = bool(verification_errors) if indeterminate is None else indeterminate
        if self.indeterminate:
            self.recovery_hint = (
                "Stop mutations, inspect Git and run `agora validate` before recovery."
            )
        elif phase == "rollback":
            self.recovery_hint = (
                "Rollback reported an error, but verification matched the original snapshots; "
                "inspect the project before a reviewed retry."
            )
        elif phase == "concurrent-edit":
            self.recovery_hint = "Refresh durable state and retry after the external writer stops."
        else:
            self.recovery_hint = "Correct the persistence failure and retry the complete operation."


class FilesystemTransaction:
    """Stage related Markdown writes and commit or roll them back as one mutation."""

    def __init__(
        self,
        expected_fingerprints: dict[Path, FileFingerprint] | None = None,
    ) -> None:
        self._writes: dict[Path, str] = {}
        self._expected_fingerprints = dict(expected_fingerprints or {})

    def write(self, path: Path, contents: str) -> None:
        self._capture_expected(path)
        self._writes[path] = contents

    def contains(self, path: Path) -> bool:
        return path in self._writes

    def contents(self, path: Path) -> str | None:
        return self._writes.get(path)

    def write_new(self, path: Path, contents: str, force: bool = False) -> None:
        if path in self._writes and self._writes[path] == contents and not force:
            return
        if (path in self._writes or path.exists()) and not force:
            raise FileExistsError(
                f"Refusing to overwrite existing file: {path}. Pass --force to replace it."
            )
        self.write(path, contents)

    def append(self, path: Path, entry: str) -> None:
        self._capture_expected(path)
        contents = self._writes.get(path)
        if contents is None:
            contents = path.read_text(encoding="utf-8") if path.exists() else ""
        self._writes[path] = f"{contents}{entry.rstrip()}\n"

    def expect(self, path: Path, fingerprint: FileFingerprint) -> None:
        """Bind a prepared operation to the exact path identity it reviewed."""

        current = self._expected_fingerprints.get(path)
        if current is not None and current != fingerprint:
            raise ValueError(f"Conflicting expected fingerprint for {path}")
        self._expected_fingerprints[path] = fingerprint

    def _capture_expected(self, path: Path) -> None:
        if path not in self._expected_fingerprints:
            self._expected_fingerprints[path] = filesystem_fingerprint(path)

    def commit(self) -> None:
        snapshots = {path: _file_snapshot(path) for path in self._writes}
        write_set = tuple(str(path) for path in self._writes)
        changed_before_commit = [
            path
            for path, snapshot in snapshots.items()
            if snapshot.fingerprint != self._expected_fingerprints[path]
        ]
        if changed_before_commit:
            raise FilesystemTransactionFailure(
                "Filesystem transaction aborted because durable state changed before commit",
                phase="concurrent-edit",
                write_set=write_set,
            )
        applied: list[Path] = []
        created_directories = {
            directory
            for path in self._writes
            for directory in _missing_parent_directories(path.parent)
        }
        try:
            for path, contents in self._writes.items():
                if _file_snapshot(path) != snapshots[path]:
                    raise _ConcurrentFilesystemEdit(
                        "Durable state changed while the transaction was committing"
                    )
                _atomic_write_direct(path, contents)
                applied.append(path)
                if snapshots[path].mode is not None:
                    path.chmod(snapshots[path].mode)
            post_commit_errors = _verify_committed_writes(self._writes, snapshots)
            if post_commit_errors:
                raise OSError("Post-commit verification did not match staged contents")
        except Exception as error:
            rollback_errors: list[Exception] = []
            for path in reversed(applied):
                snapshot = snapshots[path]
                try:
                    if snapshot.contents is None:
                        path.unlink(missing_ok=True)
                    else:
                        _atomic_write_direct(path, snapshot.contents)
                        if snapshot.mode is not None:
                            path.chmod(snapshot.mode)
                except Exception as rollback_error:  # pragma: no cover - catastrophic filesystem
                    rollback_errors.append(rollback_error)
            ordered_directories = sorted(
                created_directories, key=lambda item: len(item.parts), reverse=True
            )
            for directory in ordered_directories:
                try:
                    directory.rmdir()
                except FileNotFoundError:
                    continue
                except OSError as rollback_error:
                    rollback_errors.append(rollback_error)
            verification_paths = (
                applied if isinstance(error, _ConcurrentFilesystemEdit) else list(self._writes)
            )
            verification_errors = _verify_restored_snapshots(
                snapshots,
                verification_paths,
                created_directories,
            )
            if verification_errors:
                raise FilesystemTransactionFailure(
                    "Filesystem transaction failed and restoration could not be verified",
                    phase="rollback",
                    write_set=write_set,
                    rollback_errors=tuple(str(item) for item in rollback_errors),
                    verification_errors=verification_errors,
                    indeterminate=True,
                ) from error
            if isinstance(error, _ConcurrentFilesystemEdit):
                raise FilesystemTransactionFailure(
                    "Filesystem transaction aborted because durable state changed during commit",
                    phase="concurrent-edit",
                    write_set=write_set,
                    rollback_errors=tuple(str(item) for item in rollback_errors),
                    indeterminate=False,
                ) from error
            if rollback_errors:
                raise FilesystemTransactionFailure(
                    "Filesystem transaction rollback reported an error but verification passed",
                    phase="rollback",
                    write_set=write_set,
                    rollback_errors=tuple(str(item) for item in rollback_errors),
                    indeterminate=False,
                ) from error
            raise FilesystemTransactionFailure(
                f"Filesystem transaction commit failed: {error}",
                phase="commit",
                write_set=write_set,
            ) from error


_ACTIVE_TRANSACTION: ContextVar[FilesystemTransaction | None] = ContextVar(
    "agora_filesystem_transaction", default=None
)


@contextmanager
def filesystem_transaction(
    expected_fingerprints: dict[Path, FileFingerprint] | None = None,
) -> Iterator[FilesystemTransaction]:
    current = _ACTIVE_TRANSACTION.get()
    if current is not None:
        for path, fingerprint in (expected_fingerprints or {}).items():
            current.expect(path, fingerprint)
        yield current
        return
    transaction = FilesystemTransaction(expected_fingerprints)
    token = _ACTIVE_TRANSACTION.set(transaction)
    try:
        yield transaction
    except Exception:
        _ACTIVE_TRANSACTION.reset(token)
        raise
    else:
        _ACTIVE_TRANSACTION.reset(token)
        transaction.commit()


def atomic_write(path: Path, contents: str) -> None:
    transaction = _ACTIVE_TRANSACTION.get()
    if transaction is not None:
        transaction.write(path, contents)
        return
    _atomic_write_direct(path, contents)


def write_new(path: Path, contents: str, force: bool = False) -> None:
    transaction = _ACTIVE_TRANSACTION.get()
    if transaction is not None:
        transaction.write_new(path, contents, force)
        return
    if path.exists() and not force:
        raise FileExistsError(
            f"Refusing to overwrite existing file: {path}. Pass --force to replace it."
        )
    atomic_write(path, contents)


def append_entry(path: Path, entry: str) -> None:
    transaction = _ACTIVE_TRANSACTION.get()
    if transaction is not None:
        transaction.append(path, entry)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"{entry.rstrip()}\n")


def has_staged_write(path: Path) -> bool:
    """Return whether the active compound transaction already owns this path."""

    transaction = _ACTIVE_TRANSACTION.get()
    return transaction is not None and transaction.contains(path)


def staged_contents(path: Path) -> str | None:
    """Read the latest staged value for transaction-local read-your-writes semantics."""

    transaction = _ACTIVE_TRANSACTION.get()
    return None if transaction is None else transaction.contents(path)


def filesystem_fingerprint(path: Path) -> FileFingerprint:
    """Return a content-based identity without relying on filesystem timestamps."""

    return _file_snapshot(path).fingerprint


class _ConcurrentFilesystemEdit(OSError):
    pass


def _file_snapshot(path: Path) -> _FileSnapshot:
    if not path.exists():
        return _FileSnapshot(contents=None, mode=None)
    return _FileSnapshot(
        contents=path.read_text(encoding="utf-8"),
        mode=stat.S_IMODE(path.stat().st_mode),
    )


def _verify_committed_writes(
    writes: dict[Path, str], snapshots: dict[Path, _FileSnapshot]
) -> tuple[str, ...]:
    failures: list[str] = []
    for path, contents in writes.items():
        try:
            current = _file_snapshot(path)
        except OSError:
            failures.append("unreadable-written-path")
            continue
        if current.contents != contents:
            failures.append("written-content-mismatch")
        expected_mode = snapshots[path].mode
        if expected_mode is not None and current.mode != expected_mode:
            failures.append("written-permission-mismatch")
    return tuple(failures)


def _verify_restored_snapshots(
    snapshots: dict[Path, _FileSnapshot],
    paths: list[Path],
    created_directories: set[Path],
) -> tuple[str, ...]:
    failures: list[str] = []
    for path in paths:
        try:
            current = _file_snapshot(path)
        except OSError:
            failures.append("unreadable-restored-path")
            continue
        if current != snapshots[path]:
            failures.append("restored-snapshot-mismatch")
    if any(directory.exists() for directory in created_directories):
        failures.append("new-directory-remains")
    return tuple(failures)


def _missing_parent_directories(path: Path) -> list[Path]:
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    return missing


def copy_template_tree(
    source: Path,
    destination: Path,
    replacements: dict[str, str],
    force: bool = False,
) -> None:
    for source_path in source.rglob("*"):
        if not source_path.is_file():
            continue
        relative = source_path.relative_to(source)
        contents = source_path.read_text(encoding="utf-8")
        for key, value in replacements.items():
            contents = contents.replace(f"{{{{{key}}}}}", value)
        write_new(destination / relative, contents, force)


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".agora" / "project.md").exists():
            return candidate
    raise FileNotFoundError(f'No Agora project found from {current}. Run "agora init" first.')


def assert_slug(value: str, label: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9-]*", value):
        raise ValueError(f"{label} must match /^[a-z][a-z0-9-]*$/: {value}")

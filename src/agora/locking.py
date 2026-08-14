import hashlib
import math
import os
import socket
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from agora.markdown import MarkdownDocument, parse_markdown, render_markdown
from agora.model import WorkspaceLockStatus

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt
except ImportError:  # pragma: no cover - exercised on POSIX
    msvcrt = None  # type: ignore[assignment]


class WorkspaceLockedError(RuntimeError):
    pass


class WorkspaceLock:
    def __init__(
        self,
        resource: Path,
        operation: str,
        *,
        timeout: float = 0,
        now: datetime | None = None,
    ) -> None:
        if not math.isfinite(timeout) or timeout < 0:
            raise ValueError("Lock timeout must be a finite non-negative number")
        self.resource = resource.resolve()
        self.operation = operation
        self.timeout = timeout
        self.acquired_at = (now or datetime.now(UTC)).astimezone(UTC)
        self.path = workspace_lock_path(self.resource)
        self._descriptor: int | None = None

    def __enter__(self) -> "WorkspaceLock":
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()

    def acquire(self) -> None:
        if self._descriptor is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        _ensure_lock_byte(descriptor)
        deadline = time.monotonic() + self.timeout
        try:
            while True:
                try:
                    _lock_descriptor(descriptor, blocking=False)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        status = inspect_workspace_lock(self.resource)
                        detail = _owner_detail(status)
                        raise WorkspaceLockedError(
                            f"Workspace is locked for {status.operation or 'another mutation'}"
                            f"{detail}. Retry after it completes or set AGORA_LOCK_TIMEOUT."
                        ) from None
                    time.sleep(min(0.05, max(0, deadline - time.monotonic())))
        except Exception:
            os.close(descriptor)
            raise

        self._descriptor = descriptor
        try:
            contents = render_markdown(
                MarkdownDocument(
                    attributes={
                        "schema": "agora/workspace-lock/v1",
                        "resource": str(self.resource),
                        "operation": self.operation,
                        "pid": os.getpid(),
                        "hostname": socket.gethostname(),
                        "acquired-at": self.acquired_at.isoformat().replace("+00:00", "Z"),
                    },
                    body="# Agora workspace lock\n\nRuntime-only local writer coordination.",
                )
            )
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.ftruncate(descriptor, 0)
            os.write(descriptor, contents.encode("utf-8"))
            os.fsync(descriptor)
        except Exception:
            self.release()
            raise

    def release(self) -> None:
        if self._descriptor is None:
            return
        descriptor = self._descriptor
        self._descriptor = None
        try:
            _unlock_descriptor(descriptor)
        finally:
            os.close(descriptor)


def workspace_lock_path(resource: Path) -> Path:
    digest = hashlib.sha256(str(resource.resolve()).encode("utf-8")).hexdigest()
    configured = os.environ.get("AGORA_LOCK_HOME")
    lock_home = (
        Path(configured).expanduser() if configured else Path(tempfile.gettempdir()) / "agora-locks"
    )
    return lock_home.resolve() / digest / "workspace.md"


def inspect_workspace_lock(resource: Path) -> WorkspaceLockStatus:
    resolved = resource.resolve()
    path = workspace_lock_path(resolved)
    if not path.exists():
        return WorkspaceLockStatus(
            resource=str(resolved),
            path=str(path),
            active=False,
            operation=None,
            pid=None,
            hostname=None,
            acquired_at=None,
        )

    descriptor = os.open(path, os.O_RDWR)
    active = True
    try:
        try:
            _lock_descriptor(descriptor, blocking=False)
        except BlockingIOError:
            pass
        else:
            active = False
            _unlock_descriptor(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        contents = os.read(descriptor, max(os.fstat(descriptor).st_size, 1)).decode(
            "utf-8", errors="replace"
        )
    finally:
        os.close(descriptor)

    attributes: dict[str, object] = {}
    try:
        attributes = parse_markdown(contents).attributes
    except ValueError:
        pass
    pid = attributes.get("pid")
    return WorkspaceLockStatus(
        resource=str(resolved),
        path=str(path),
        active=active,
        operation=_optional_text(attributes.get("operation")),
        pid=pid if isinstance(pid, int) and not isinstance(pid, bool) else None,
        hostname=_optional_text(attributes.get("hostname")),
        acquired_at=_optional_text(attributes.get("acquired-at")),
    )


def _lock_descriptor(descriptor: int, *, blocking: bool) -> None:
    if fcntl is not None:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(descriptor, flags)
        except BlockingIOError:
            raise
        return
    if msvcrt is not None:  # pragma: no cover - exercised on Windows
        os.lseek(descriptor, 0, os.SEEK_SET)
        mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
        try:
            msvcrt.locking(descriptor, mode, 1)
        except OSError as error:
            raise BlockingIOError from error
        return
    raise RuntimeError("No supported operating-system file locking API is available")


def _unlock_descriptor(descriptor: int) -> None:
    if fcntl is not None:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        return
    if msvcrt is not None:  # pragma: no cover - exercised on Windows
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)


def _ensure_lock_byte(descriptor: int) -> None:
    if os.fstat(descriptor).st_size:
        return
    os.write(descriptor, b"\n")
    os.fsync(descriptor)


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _owner_detail(status: WorkspaceLockStatus) -> str:
    parts = []
    if status.pid is not None:
        parts.append(f"pid={status.pid}")
    if status.hostname is not None:
        parts.append(f"host={status.hostname}")
    if status.acquired_at is not None:
        parts.append(f"since={status.acquired_at}")
    return f" ({', '.join(parts)})" if parts else ""

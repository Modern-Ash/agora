from collections.abc import Callable
from pathlib import Path

import pytest

from agora import filesystem


class AtomicWriteFault:
    """Inject one atomic-write failure while preserving the real writer for retries."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch
        self._original: Callable[[Path, str], None] = filesystem._atomic_write_direct
        self.paths: list[Path] = []

    def arm(self, fail_at: int) -> None:
        self.paths = []

        def injected(path: Path, contents: str) -> None:
            self.paths.append(path)
            if len(self.paths) == fail_at:
                raise OSError(f"injected atomic write failure {fail_at}: {path.name}")
            self._original(path, contents)

        self._monkeypatch.setattr(filesystem, "_atomic_write_direct", injected)

    def restore(self) -> None:
        self._monkeypatch.setattr(filesystem, "_atomic_write_direct", self._original)


@pytest.fixture
def atomic_write_fault(monkeypatch: pytest.MonkeyPatch) -> AtomicWriteFault:
    return AtomicWriteFault(monkeypatch)

from collections.abc import Callable
from pathlib import Path

import pytest

from agora import filesystem


def swarm_dir(root: Path, swarm_id: str) -> Path:
    """Resolve a swarm id to its actual directory under .agora/swarms/,
    whether legacy (unnumbered) or created with the sequential '00x-'
    prefix (see AgoraWorkspace._next_swarm_directory). Tests that assert
    against raw filesystem paths should use this instead of hardcoding
    `.agora/swarms/<id>` — the directory name is no longer guaranteed to
    equal the swarm id."""
    base = root / ".agora" / "swarms"
    direct = base / swarm_id
    if direct.exists():
        return direct
    if base.is_dir():
        matches = sorted(base.glob(f"[0-9][0-9][0-9]-{swarm_id}"))
        if matches:
            return matches[0]
    return direct


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

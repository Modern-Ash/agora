"""Content fingerprints for optimistic consistency around external filesystem writers."""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Iterable
from pathlib import Path


def durable_read_set_sha256(
    root: Path,
    paths: Iterable[Path],
    *,
    include_git_state: bool = False,
) -> str:
    """Hash paths and local Git identity without following symlinks or accessing a network."""

    project = root.resolve()
    digest = hashlib.sha256()
    digest.update(b"agora/durable-read-set/v1\0")
    expanded: set[Path] = set()
    for candidate in paths:
        path = candidate if candidate.is_absolute() else project / candidate
        if path.is_dir() and not path.is_symlink():
            expanded.update(item for item in path.rglob("*") if not item.is_dir())
        else:
            expanded.add(path)
    for path in sorted(expanded, key=lambda item: str(item)):
        _hash_path(digest, project, path)
    if include_git_state:
        for arguments in (("rev-parse", "HEAD"), ("status", "--porcelain=v1", "-z")):
            result = subprocess.run(
                ["git", *arguments],
                cwd=project,
                capture_output=True,
                check=False,
                timeout=5,
            )
            digest.update(b"git\0")
            digest.update("\0".join(arguments).encode("ascii"))
            digest.update(b"\0")
            digest.update(str(result.returncode).encode("ascii"))
            digest.update(b"\0")
            digest.update(result.stdout)
            digest.update(b"\0")
    return digest.hexdigest()


def _hash_path(digest: object, root: Path, path: Path) -> None:
    hasher = digest
    try:
        relative = path.absolute().relative_to(root)
    except ValueError:
        relative = Path("outside-project")
    hasher.update(relative.as_posix().encode("utf-8"))  # type: ignore[attr-defined]
    hasher.update(b"\0")  # type: ignore[attr-defined]
    if path.is_symlink():
        hasher.update(b"symlink\0")  # type: ignore[attr-defined]
        hasher.update(str(path.readlink()).encode("utf-8"))  # type: ignore[attr-defined]
        return
    if not path.exists():
        hasher.update(b"missing\0")  # type: ignore[attr-defined]
        return
    if not path.is_file():
        hasher.update(b"non-file\0")  # type: ignore[attr-defined]
        return
    hasher.update(b"file\0")  # type: ignore[attr-defined]
    with path.open("rb") as source:
        while chunk := source.read(128 * 1024):
            hasher.update(chunk)  # type: ignore[attr-defined]
    hasher.update(b"\0")  # type: ignore[attr-defined]

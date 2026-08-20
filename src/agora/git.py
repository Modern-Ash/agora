import os
import re
import subprocess
from pathlib import Path

from agora.model import (
    SpecificationHistoryRecord,
    SpecificationRevisionDetailRecord,
    SpecificationRevisionRecord,
)

_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SPECIFICATION_MAX_BYTES = 131_072
_SPECIFICATION_MAX_LINES = 2_000


def is_git_repository(cwd: Path) -> bool:
    return _run_git(cwd, "rev-parse", "--is-inside-work-tree", check=False).returncode == 0


def current_branch(cwd: Path) -> str:
    result = _run_git(cwd, "branch", "--show-current")
    return result.stdout.strip() or "detached"


def repository_root(cwd: Path) -> Path:
    result = _run_git(cwd, "rev-parse", "--show-toplevel")
    return Path(result.stdout.strip()).resolve()


def working_tree_changes(cwd: Path) -> list[str]:
    result = _run_git(cwd, "status", "--porcelain", "--untracked-files=normal")
    return [line for line in result.stdout.splitlines() if line]


def ref_exists(cwd: Path, ref: str) -> bool:
    return _run_git(cwd, "show-ref", "--verify", "--quiet", ref, check=False).returncode == 0


def commit_exists(cwd: Path, commit: str) -> bool:
    return _run_git(cwd, "cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode == 0


def commit_is_ancestor(cwd: Path, commit: str, descendant: str = "HEAD") -> bool:
    return (
        _run_git(cwd, "merge-base", "--is-ancestor", commit, descendant, check=False).returncode
        == 0
    )


def path_is_ignored(cwd: Path, path: Path) -> bool:
    root = repository_root(cwd)
    try:
        relative = path.resolve().relative_to(root)
    except ValueError:
        return False
    return (
        _run_git(
            cwd,
            "check-ignore",
            "--no-index",
            "--quiet",
            "--",
            relative.as_posix(),
            check=False,
        ).returncode
        == 0
    )


def ignored_paths(cwd: Path, paths: list[Path]) -> set[str]:
    root = repository_root(cwd)
    relatives = []
    for path in paths:
        try:
            relatives.append(path.resolve().relative_to(root).as_posix())
        except ValueError:
            continue
    if not relatives:
        return set()
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-z", "--stdin"],
        cwd=cwd,
        input="\0".join(relatives) + "\0",
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(f"Git command failed: {result.stderr.strip()}")
    return {item for item in result.stdout.split("\0") if item}


def file_history(
    cwd: Path,
    relative_path: str,
    *,
    max_revisions: int = 80,
    max_output_bytes: int = 262_144,
) -> SpecificationHistoryRecord:
    """Read bounded, local Git history for one already-validated repository file."""

    if not is_git_repository(cwd):
        return SpecificationHistoryRecord(
            available=False,
            uri=None,
            revisions=[],
            has_history=False,
            working_tree=False,
            truncated=False,
            reason="Project is not a Git repository",
        )
    log = _run_bounded_git(
        cwd,
        (
            "log",
            "--follow",
            f"--max-count={max_revisions}",
            "--format=%H%x1f%aI%x1f%an%x1f%s",
            "--",
            relative_path,
        ),
        max_output_bytes,
    )
    revisions: list[SpecificationRevisionRecord] = []
    for line in log[0].splitlines():
        values = line.split("\x1f", 3)
        if len(values) != 4 or _COMMIT_SHA.fullmatch(values[0]) is None:
            continue
        sha, timestamp, author, subject = values
        revisions.append(
            SpecificationRevisionRecord(
                id=sha,
                kind="commit",
                sha=sha,
                short_sha=sha[:10],
                timestamp=timestamp,
                author=author,
                subject=subject,
                uncommitted=False,
            )
        )
    status = _run_bounded_git(
        cwd,
        ("status", "--porcelain=v1", "--", relative_path),
        max_output_bytes,
    )
    working_tree = bool(status[0].strip())
    if working_tree:
        revisions.insert(
            0,
            SpecificationRevisionRecord(
                id="working-tree",
                kind="working-tree",
                sha=None,
                short_sha="WORKTREE",
                timestamp=None,
                author=None,
                subject="Modified, uncommitted specification",
                uncommitted=True,
            ),
        )
    return SpecificationHistoryRecord(
        available=True,
        uri=None,
        revisions=revisions,
        has_history=any(not revision.uncommitted for revision in revisions),
        working_tree=working_tree,
        truncated=log[1] or status[1] or len(revisions) >= max_revisions,
    )


def file_revision(
    cwd: Path,
    relative_path: str,
    revision_id: str,
    *,
    max_output_bytes: int = _SPECIFICATION_MAX_BYTES,
    max_lines: int = _SPECIFICATION_MAX_LINES,
) -> SpecificationRevisionDetailRecord:
    """Read one bounded revision of an already validated repository file."""

    if revision_id != "working-tree" and _COMMIT_SHA.fullmatch(revision_id) is None:
        return _unavailable_revision(revision_id, "Specification revision id is invalid")
    if not is_git_repository(cwd):
        return _unavailable_revision(revision_id, "Project is not a Git repository")

    try:
        history = file_history(cwd, relative_path)
    except RuntimeError:
        return _unavailable_revision(revision_id, "Git could not read specification history")
    revision = next((item for item in history.revisions if item.id == revision_id), None)
    if revision is None:
        return _unavailable_revision(
            revision_id,
            "Specification revision is not present in the registered file history",
        )
    index = history.revisions.index(revision)
    previous = next(
        (item.id for item in history.revisions[index + 1 :] if item.id != "working-tree"),
        None,
    )
    try:
        if revision.kind == "working-tree":
            raw_content = (cwd / relative_path).read_bytes()
            raw_diff, diff_capture_truncated, _ = _run_bounded_git_bytes(
                cwd,
                ("diff", "--no-ext-diff", "--", relative_path),
                max_output_bytes,
            )
            content_capture_truncated = len(raw_content) > max_output_bytes
            content_size = len(raw_content)
        else:
            assert revision.sha is not None
            raw_content, content_capture_truncated, content_size = _run_bounded_git_bytes(
                cwd,
                ("show", f"{revision.sha}:{relative_path}"),
                max_output_bytes,
            )
            raw_diff, diff_capture_truncated, _ = _run_bounded_git_bytes(
                cwd,
                (
                    "show",
                    "--format=",
                    "--no-ext-diff",
                    "--unified=3",
                    revision.sha,
                    "--",
                    relative_path,
                ),
                max_output_bytes,
            )
    except (OSError, RuntimeError):
        return _unavailable_revision(revision_id, "Git could not read specification revision")

    binary = b"\0" in raw_content
    content, content_truncated, encoding = _bounded_text(
        raw_content,
        max_output_bytes=max_output_bytes,
        max_lines=max_lines,
        allow_binary=False,
    )
    diff, diff_truncated, _ = _bounded_text(
        raw_diff,
        max_output_bytes=max_output_bytes,
        max_lines=max_lines,
        allow_binary=True,
    )
    return SpecificationRevisionDetailRecord(
        available=True,
        uri=None,
        revision_id=revision.id,
        kind=revision.kind,
        sha=revision.sha,
        previous_revision_id=previous,
        timestamp=revision.timestamp,
        author=revision.author,
        subject=revision.subject,
        content=None if binary else content,
        diff=diff,
        size_bytes=content_size,
        content_truncated=content_capture_truncated or content_truncated,
        diff_truncated=diff_capture_truncated or diff_truncated,
        encoding="binary" if binary else encoding,
        binary=binary,
    )


def _unavailable_revision(revision_id: str, reason: str) -> SpecificationRevisionDetailRecord:
    return SpecificationRevisionDetailRecord(
        available=False,
        uri=None,
        revision_id=revision_id,
        kind=None,
        sha=None,
        previous_revision_id=None,
        timestamp=None,
        author=None,
        subject=None,
        content=None,
        diff=None,
        size_bytes=0,
        content_truncated=False,
        diff_truncated=False,
        encoding="unavailable",
        binary=False,
        reason=reason,
    )


def _bounded_text(
    value: bytes,
    *,
    max_output_bytes: int,
    max_lines: int,
    allow_binary: bool,
) -> tuple[str | None, bool, str]:
    if b"\0" in value and not allow_binary:
        return None, False, "binary"
    byte_truncated = len(value) > max_output_bytes
    bounded = value[:max_output_bytes]
    decoded = bounded.decode("utf-8", errors="replace")
    lines = decoded.splitlines(keepends=True)
    line_truncated = len(lines) > max_lines
    if line_truncated:
        decoded = "".join(lines[:max_lines])
    encoding = "utf-8" if "\ufffd" not in decoded else "utf-8-replacement"
    return decoded, byte_truncated or line_truncated, encoding


def _run_bounded_git_bytes(
    cwd: Path, arguments: tuple[str, ...], max_output_bytes: int
) -> tuple[bytes, bool, int]:
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_PAGER": "cat",
        "PAGER": "cat",
    }
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), *arguments],
            capture_output=True,
            check=False,
            timeout=5,
            env=environment,
            shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as error:
        raise RuntimeError("Bounded Git revision read failed") from error
    if result.returncode != 0:
        raise RuntimeError(
            f"Git could not read specification revision (exit code {result.returncode})"
        )
    size = len(result.stdout)
    return result.stdout[:max_output_bytes], size > max_output_bytes, size


def _run_bounded_git(
    cwd: Path, arguments: tuple[str, ...], max_output_bytes: int
) -> tuple[str, bool]:
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_PAGER": "cat",
        "PAGER": "cat",
    }
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            env=environment,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as error:
        raise RuntimeError("Bounded Git history read failed") from error
    if result.returncode != 0:
        raise RuntimeError(
            f"Git could not read specification history (exit code {result.returncode})"
        )
    encoded = result.stdout.encode("utf-8", errors="replace")
    truncated = len(encoded) > max_output_bytes
    return encoded[:max_output_bytes].decode("utf-8", errors="replace"), truncated


def create_branch(cwd: Path, branch: str) -> None:
    result = _run_git(cwd, "switch", "-c", branch, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Unable to create Git branch {branch}: {result.stderr.strip()}")


def switch_branch(cwd: Path, branch: str) -> None:
    _run_git(cwd, "switch", branch)


def delete_branch(cwd: Path, branch: str) -> None:
    _run_git(cwd, "branch", "-D", branch)


def _run_git(cwd: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *arguments], cwd=cwd, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"Git command failed: {result.stderr.strip()}")
    return result

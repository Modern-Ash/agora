import os
import re
import subprocess
from pathlib import Path

from agora.model import SpecificationHistoryRecord, SpecificationRevisionRecord

_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


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

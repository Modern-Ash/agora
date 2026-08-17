import subprocess
from pathlib import Path


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

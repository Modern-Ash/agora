import subprocess
from pathlib import Path


def is_git_repository(cwd: Path) -> bool:
    return _run_git(cwd, "rev-parse", "--is-inside-work-tree", check=False).returncode == 0


def current_branch(cwd: Path) -> str:
    result = _run_git(cwd, "branch", "--show-current")
    return result.stdout.strip() or "detached"


def create_branch(cwd: Path, branch: str) -> None:
    result = _run_git(cwd, "switch", "-c", branch, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Unable to create Git branch {branch}: {result.stderr.strip()}")


def _run_git(cwd: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *arguments], cwd=cwd, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"Git command failed: {result.stderr.strip()}")
    return result

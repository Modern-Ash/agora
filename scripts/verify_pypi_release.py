import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

RELEASE_TAG_PATTERN = re.compile(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
PYPI_INDEX = "https://pypi.org/simple/"
MAX_CAPTURED_OUTPUT = 4_000

Runner = Callable[..., subprocess.CompletedProcess[str]]


def release_version(tag: str) -> str:
    match = RELEASE_TAG_PATTERN.fullmatch(tag)
    if match is None:
        raise ValueError("Release tag must use vMAJOR.MINOR.PATCH")
    return ".".join(match.groups())


def _failure_output(result: subprocess.CompletedProcess[str]) -> str:
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    return output[-MAX_CAPTURED_OUTPUT:]


def install_release(
    python: Path,
    version: str,
    *,
    attempts: int = 6,
    runner: Runner = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    if attempts < 1:
        raise ValueError("Install attempts must be positive")
    command = [
        str(python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-cache-dir",
        "--index-url",
        PYPI_INDEX,
        f"agora-framework=={version}",
    ]
    last_result: subprocess.CompletedProcess[str] | None = None
    for attempt in range(1, attempts + 1):
        last_result = runner(command, capture_output=True, text=True, timeout=120)
        if last_result.returncode == 0:
            return
        if attempt < attempts:
            sleeper(min(attempt * 10, 30))
    assert last_result is not None
    raise RuntimeError(
        f"Could not install agora-framework=={version} after {attempts} attempts: "
        f"{_failure_output(last_result)}"
    )


def _run_checked(
    command: list[str],
    *,
    runner: Runner,
    cwd: Path | None = None,
) -> str:
    result = runner(command, cwd=cwd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(command)}: {_failure_output(result)}")
    return result.stdout


def verify_installed_release(
    python: Path,
    version: str,
    project: Path,
    *,
    runner: Runner = subprocess.run,
) -> None:
    installed_version = _run_checked(
        [
            str(python),
            "-c",
            "from importlib.metadata import version; print(version('agora-framework'))",
        ],
        runner=runner,
    ).strip()
    if installed_version != version:
        raise ValueError(f"Installed Agora version {installed_version} does not match {version}")

    executable = python.parent / ("agora.exe" if sys.platform == "win32" else "agora")
    executable_version = _run_checked([str(executable), "--version"], runner=runner).strip()
    if executable_version != f"agora {version}":
        raise ValueError(
            f"Installed Agora executable reports {executable_version!r}, expected 'agora {version}'"
        )
    quickstart = json.loads(
        _run_checked(
            [str(executable), "quickstart", "--objective", f"Verify PyPI release {version}"],
            runner=runner,
            cwd=project,
        )
    )
    if quickstart.get("swarm", {}).get("status") != "ready":
        raise ValueError("PyPI quickstart did not create a ready swarm")

    validation = json.loads(_run_checked([str(executable), "validate"], runner=runner, cwd=project))
    if validation.get("ok") is not True:
        raise ValueError("PyPI installation did not validate successfully")


def verify_pypi_release(
    tag: str,
    *,
    python: Path = Path(sys.executable),
    runner: Runner = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
) -> str:
    version = release_version(tag)
    install_release(python, version, runner=runner, sleeper=sleeper)
    with tempfile.TemporaryDirectory(prefix="agora-pypi-") as directory:
        project = Path(directory) / "project"
        project.mkdir()
        verify_installed_release(python, version, project, runner=runner)
    return version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install and validate an exact Agora release from PyPI"
    )
    parser.add_argument("--tag", required=True)
    args = parser.parse_args(argv)
    version = verify_pypi_release(args.tag)
    print(f"Verified agora-framework=={version} from PyPI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

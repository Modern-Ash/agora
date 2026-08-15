import os
import subprocess
import sys
from pathlib import Path

from agora.workspace import _bound_tool_output, _run_tool_process


def test_terminates_a_tool_that_exceeds_its_timeout(tmp_path: Path) -> None:
    command = [sys.executable, "-c", "import time; time.sleep(5)"]

    result = _run_tool_process(
        command,
        tmp_path,
        dict(os.environ),
        timeout_seconds=0.05,
        max_output_bytes=1024,
    )

    assert result.returncode == 124
    assert "terminated the tool after 0.05 seconds" in result.stderr


def test_terminates_or_rejects_a_tool_that_exceeds_its_output_limit(tmp_path: Path) -> None:
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stdout.write('x' * 100000); sys.stdout.flush()",
    ]

    result = _run_tool_process(
        command,
        tmp_path,
        dict(os.environ),
        timeout_seconds=5,
        max_output_bytes=128,
    )

    assert result.returncode == 125
    assert len(result.stdout.encode("utf-8")) <= 128
    assert "128 bytes" in result.stderr


def test_bounds_output_from_an_injected_runner() -> None:
    result = subprocess.CompletedProcess(["tool"], 0, "x" * 1000, "")

    bounded = _bound_tool_output(result, 64)

    assert bounded.returncode == 125
    assert len(bounded.stdout.encode("utf-8")) <= 64
    assert "limited captured tool output" in bounded.stderr

import os
import shutil
import subprocess

import pytest

REPOSITORY = os.environ.get("AGORA_GITHUB_E2E_REPOSITORY")


@pytest.mark.skipif(
    not REPOSITORY or shutil.which("gh") is None,
    reason="Set AGORA_GITHUB_E2E_REPOSITORY and authenticate gh for live GitHub reads",
)
def test_live_github_cli_read_surface() -> None:
    commands = (
        ["gh", "repo", "view", REPOSITORY, "--json", "nameWithOwner,defaultBranchRef"],
        ["gh", "issue", "list", "--repo", REPOSITORY, "--limit", "1", "--json", "number"],
        ["gh", "pr", "list", "--repo", REPOSITORY, "--limit", "1", "--json", "number"],
        ["gh", "run", "list", "--repo", REPOSITORY, "--limit", "1", "--json", "databaseId"],
        ["gh", "release", "list", "--repo", REPOSITORY, "--limit", "1", "--json", "tagName"],
    )

    for command in commands:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, f"{' '.join(command)} failed: {result.stderr}"

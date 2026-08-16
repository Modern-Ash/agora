import hashlib
import runpy
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
release_script = runpy.run_path(str(ROOT / "scripts" / "prepare_release.py"))
prepare_release = release_script["prepare_release"]


def test_release_versions_remain_synchronized() -> None:
    with (ROOT / "pyproject.toml").open("rb") as source:
        project_version = tomllib.load(source)["project"]["version"]
    version_line = next(
        line
        for line in (ROOT / "src" / "agora" / "__init__.py").read_text().splitlines()
        if line.startswith("__version__ = ")
    )
    package_version = version_line.split('"')[1]

    assert project_version == "0.3.1"
    assert package_version == project_version
    assert f'version = "{project_version}"' in (ROOT / "uv.lock").read_text()


def test_release_uses_separate_oidc_pypi_publication() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()

    assert "needs: release" in workflow
    assert "name: pypi" in workflow
    assert "id-token: write" in workflow
    assert "https://pypi.org/p/agora-framework" in workflow
    assert "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33" in workflow
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in workflow


def _release_tree(tmp_path: Path, version: str = "1.2.3") -> tuple[Path, Path]:
    root = tmp_path / "project"
    dist = root / "dist"
    dist.mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "agora-framework"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    (dist / f"agora_framework-{version}-py3-none-any.whl").write_bytes(b"wheel")
    (dist / f"agora_framework-{version}.tar.gz").write_bytes(b"source")
    return root, dist


def test_prepares_version_matched_release_checksums(tmp_path: Path) -> None:
    root, dist = _release_tree(tmp_path)

    artifacts = prepare_release(root, "v1.2.3", dist)

    assert [path.name for path in artifacts] == [
        "agora_framework-1.2.3-py3-none-any.whl",
        "agora_framework-1.2.3.tar.gz",
        "SHA256SUMS",
    ]
    assert (dist / "SHA256SUMS").read_text(encoding="utf-8").splitlines() == [
        f"{hashlib.sha256(b'wheel').hexdigest()}  agora_framework-1.2.3-py3-none-any.whl",
        f"{hashlib.sha256(b'source').hexdigest()}  agora_framework-1.2.3.tar.gz",
    ]


def test_rejects_mismatched_tags_and_missing_distributions(tmp_path: Path) -> None:
    root, dist = _release_tree(tmp_path)

    with pytest.raises(ValueError, match="does not match project version"):
        prepare_release(root, "v1.2.4", dist)
    (dist / "agora_framework-1.2.3.tar.gz").unlink()
    with pytest.raises(FileNotFoundError, match="agora_framework-1.2.3.tar.gz"):
        prepare_release(root, "v1.2.3", dist)

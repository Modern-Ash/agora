import argparse
import hashlib
import re
import tomllib
from pathlib import Path

RELEASE_TAG_PATTERN = re.compile(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")


def project_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as source:
        configuration = tomllib.load(source)
    version = configuration.get("project", {}).get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("pyproject.toml must declare a non-empty project.version")
    return version


def prepare_release(root: Path, tag: str, dist: Path) -> list[Path]:
    match = RELEASE_TAG_PATTERN.fullmatch(tag)
    if match is None:
        raise ValueError("Release tag must use vMAJOR.MINOR.PATCH")
    version = ".".join(match.groups())
    configured_version = project_version(root)
    if version != configured_version:
        raise ValueError(f"Release tag {tag} does not match project version {configured_version}")

    expected = [
        dist / f"agora_framework-{version}-py3-none-any.whl",
        dist / f"agora_framework-{version}.tar.gz",
    ]
    missing = [path.name for path in expected if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing release distributions: {', '.join(missing)}")

    checksum_path = dist / "SHA256SUMS"
    lines = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in expected]
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [*expected, checksum_path]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate an Agora release tag and create distribution checksums"
    )
    parser.add_argument("--tag", required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dist", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    dist = args.dist.resolve() if args.dist else root / "dist"
    artifacts = prepare_release(root, args.tag, dist)
    for artifact in artifacts:
        print(artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

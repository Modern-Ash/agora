import os
import re
from pathlib import Path


def agora_home() -> Path:
    return Path(os.environ.get("AGORA_HOME", Path.home() / ".agora")).expanduser().resolve()


def packs_root() -> Path:
    override = os.environ.get("AGORA_PACKS_ROOT")
    if override:
        return Path(override).resolve()
    installed = Path(__file__).resolve().parent / "packs"
    if installed.exists():
        return installed
    return Path(__file__).resolve().parents[2] / "packs"


def atomic_write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(contents, encoding="utf-8")
    temporary.replace(path)


def write_new(path: Path, contents: str, force: bool = False) -> None:
    if path.exists() and not force:
        raise FileExistsError(
            f"Refusing to overwrite existing file: {path}. Pass --force to replace it."
        )
    atomic_write(path, contents)


def append_entry(path: Path, entry: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"{entry.rstrip()}\n")


def copy_template_tree(
    source: Path,
    destination: Path,
    replacements: dict[str, str],
    force: bool = False,
) -> None:
    for source_path in source.rglob("*"):
        if not source_path.is_file():
            continue
        relative = source_path.relative_to(source)
        contents = source_path.read_text(encoding="utf-8")
        for key, value in replacements.items():
            contents = contents.replace(f"{{{{{key}}}}}", value)
        write_new(destination / relative, contents, force)


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".agora" / "project.md").exists():
            return candidate
    raise FileNotFoundError(f'No Agora project found from {current}. Run "agora init" first.')


def assert_slug(value: str, label: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9-]*", value):
        raise ValueError(f"{label} must match /^[a-z][a-z0-9-]*$/: {value}")

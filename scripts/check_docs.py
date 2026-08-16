import re
import sys
from pathlib import Path

LINK_PATTERN = re.compile(r"\[[^]]*]\(([^)]+)\)")
IGNORED_DIRECTORIES = {".git", ".venv", "dist", "node_modules"}
PLUGIN_OUTPUT_ROOTS = {Path("docs/superpowers")}


def is_ignored_document(relative_path: Path) -> bool:
    if any(part in IGNORED_DIRECTORIES for part in relative_path.parts):
        return True
    return any(
        root == relative_path or root in relative_path.parents for root in PLUGIN_OUTPUT_ROOTS
    )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors: list[str] = []

    for document in sorted(root.rglob("*.md")):
        if is_ignored_document(document.relative_to(root)):
            continue
        contents = document.read_text(encoding="utf-8")
        for target in LINK_PATTERN.findall(contents):
            path_text = target.split("#", 1)[0]
            if not path_text or "://" in path_text or path_text.startswith("mailto:"):
                continue
            linked_path = (document.parent / path_text).resolve()
            if not linked_path.exists():
                errors.append(f"{document.relative_to(root)}: missing link target {target}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("All local Markdown links resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

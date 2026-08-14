import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Attributes = dict[str, Any]


@dataclass
class MarkdownDocument:
    attributes: Attributes
    body: str


def parse_markdown(contents: str) -> MarkdownDocument:
    lines = contents.replace("\r\n", "\n").split("\n")
    if not lines or lines[0] != "---":
        raise ValueError("Markdown document must start with YAML front matter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("Markdown document has unterminated front matter") from error

    attributes: Attributes = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"Invalid front matter line: {line}")
        key, value = line.split(":", 1)
        attributes[key.strip()] = _parse_value(value.strip())

    body = "\n".join(lines[end + 1 :])
    if body.startswith("\n"):
        body = body[1:]
    return MarkdownDocument(attributes=attributes, body=body)


def read_markdown(path: Path) -> MarkdownDocument:
    return parse_markdown(path.read_text(encoding="utf-8"))


def render_markdown(document: MarkdownDocument) -> str:
    front_matter = "\n".join(
        f"{key}: {_render_value(value)}" for key, value in document.attributes.items()
    )
    return f"---\n{front_matter}\n---\n\n{document.body.strip()}\n"


def string_attribute(attributes: Attributes, key: str) -> str:
    value = attributes.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Expected non-empty string attribute: {key}")
    return value


def strings_attribute(attributes: Attributes, key: str) -> list[str]:
    value = attributes.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"Expected string array attribute: {key}")
    return value


def record_attribute(attributes: Attributes, key: str) -> dict[str, str]:
    value = attributes.get(key)
    if not isinstance(value, dict) or any(
        not isinstance(name, str) or not isinstance(item, str) for name, item in value.items()
    ):
        raise ValueError(f"Expected string map attribute: {key}")
    return value


def _parse_value(value: str) -> Any:
    if not value:
        return ""
    if value[0] in {'"', "[", "{"} or value in {"true", "false", "null"}:
        try:
            return json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Front matter value is not valid JSON-compatible YAML: {value}"
            ) from error
    return value


def _render_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))

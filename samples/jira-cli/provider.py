#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic ACLI-compatible Jira sample")
    domains = parser.add_subparsers(dest="domain", required=True)
    jira = domains.add_parser("jira")
    resources = jira.add_subparsers(dest="resource", required=True)
    workitem = resources.add_parser("workitem")
    operations = workitem.add_subparsers(dest="operation", required=True)

    search = operations.add_parser("search")
    search.add_argument("--jql", required=True)
    search.add_argument("--limit", type=int, required=True)
    search.add_argument("--fields", required=True)
    search.add_argument("--json", action="store_true", required=True)

    view = operations.add_parser("view")
    view.add_argument("key")
    view.add_argument("--fields", required=True)
    view.add_argument("--json", action="store_true", required=True)

    create = operations.add_parser("create")
    create.add_argument("--project", required=True)
    create.add_argument("--type", required=True)
    create.add_argument("--summary", required=True)
    create.add_argument("--description", required=True)
    create.add_argument("--json", action="store_true", required=True)

    comment = operations.add_parser("comment")
    comment_actions = comment.add_subparsers(dest="comment_operation", required=True)
    comment_create = comment_actions.add_parser("create")
    comment_create.add_argument("--key", required=True)
    comment_create.add_argument("--body", required=True)
    comment_create.add_argument("--json", action="store_true", required=True)

    transition = operations.add_parser("transition")
    transition.add_argument("--key", required=True)
    transition.add_argument("--status", required=True)
    transition.add_argument("--yes", action="store_true", required=True)
    transition.add_argument("--json", action="store_true", required=True)
    return parser


def _state_path() -> Path:
    value = os.environ.get("AGORA_JIRA_SAMPLE_STATE")
    if not value:
        raise RuntimeError("AGORA_JIRA_SAMPLE_STATE is required")
    return Path(value)


def _load_state(path: Path) -> dict[str, object]:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "next": 43,
        "items": {
            "AGORA-42": {
                "key": "AGORA-42",
                "type": "Task",
                "summary": "Demonstrate governed Jira interaction",
                "description": "A deterministic sample work item.",
                "status": "To Do",
                "comments": [],
            }
        },
    }


def _save_state(path: Path, state: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _item(state: dict[str, object], key: str) -> dict[str, object]:
    items = state["items"]
    assert isinstance(items, dict)
    item = items.get(key)
    if not isinstance(item, dict):
        raise ValueError(f"Jira work item not found: {key}")
    return item


def main() -> None:
    if sys.argv[1:] == ["--version"]:
        print("acli version 1.3.15")
        return
    args = _parser().parse_args()
    path = _state_path()
    state = _load_state(path)
    items = state["items"]
    assert isinstance(items, dict)

    if args.operation == "search":
        payload = {
            "jql": args.jql,
            "issues": list(items.values())[: args.limit],
        }
    elif args.operation == "view":
        payload = _item(state, args.key)
    elif args.operation == "create":
        number = state["next"]
        assert isinstance(number, int)
        key = f"{args.project}-{number}"
        payload = {
            "key": key,
            "type": args.type,
            "summary": args.summary,
            "description": args.description,
            "status": "To Do",
            "comments": [],
        }
        items[key] = payload
        state["next"] = number + 1
        _save_state(path, state)
    elif args.operation == "comment":
        item = _item(state, args.key)
        comments = item["comments"]
        assert isinstance(comments, list)
        comments.append(args.body)
        _save_state(path, state)
        payload = {"key": args.key, "comment": args.body}
    else:
        item = _item(state, args.key)
        previous = item["status"]
        item["status"] = args.status
        _save_state(path, state)
        payload = {"key": args.key, "from": previous, "status": args.status}
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()

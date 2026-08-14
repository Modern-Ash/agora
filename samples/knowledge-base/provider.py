import argparse
import json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic sample knowledge-base provider")
    resources = parser.add_subparsers(dest="resource", required=True)
    page = resources.add_parser("page")
    operations = page.add_subparsers(dest="operation", required=True)

    search = operations.add_parser("search")
    search.add_argument("--space", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--output", choices=("json",), required=True)
    view = operations.add_parser("view")
    view.add_argument("document")
    view.add_argument("--output", choices=("json",), required=True)
    create = operations.add_parser("create")
    create.add_argument("--space", required=True)
    create.add_argument("--parent", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--body", required=True)
    create.add_argument("--output", choices=("json",), required=True)
    update = operations.add_parser("update")
    update.add_argument("document")
    update.add_argument("--title", required=True)
    update.add_argument("--body", required=True)
    update.add_argument("--output", choices=("json",), required=True)
    for operation in ("publish", "archive"):
        command = operations.add_parser(operation)
        command.add_argument("document")
        command.add_argument("--output", choices=("json",), required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.operation == "search":
        payload = {"documents": [{"id": "DOC-42", "space": args.space, "title": args.query}]}
    elif args.operation == "view":
        payload = {"id": args.document, "status": "draft", "title": "Governed knowledge"}
    elif args.operation == "create":
        payload = {
            "id": "DOC-43",
            "space": args.space,
            "parent": args.parent,
            "title": args.title,
            "body": args.body,
            "status": "draft",
        }
    elif args.operation == "update":
        payload = {
            "id": args.document,
            "title": args.title,
            "body": args.body,
            "status": "draft",
        }
    else:
        payload = {
            "id": args.document,
            "status": "published" if args.operation == "publish" else "archived",
        }
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()

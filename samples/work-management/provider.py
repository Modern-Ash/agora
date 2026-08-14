import argparse
import json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic sample work-management provider")
    domains = parser.add_subparsers(dest="domain", required=True)
    issue = domains.add_parser("issue")
    operations = issue.add_subparsers(dest="operation", required=True)

    search = operations.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--output", choices=("json",), required=True)

    view = operations.add_parser("view")
    view.add_argument("issue")
    view.add_argument("--output", choices=("json",), required=True)

    create = operations.add_parser("create")
    create.add_argument("--project", required=True)
    create.add_argument("--type", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--description", required=True)
    create.add_argument("--output", choices=("json",), required=True)

    comment = operations.add_parser("comment")
    comment.add_argument("issue")
    comment.add_argument("--body", required=True)
    comment.add_argument("--output", choices=("json",), required=True)

    transition = operations.add_parser("transition")
    transition.add_argument("issue")
    transition.add_argument("--to", required=True)
    transition.add_argument("--output", choices=("json",), required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.operation == "search":
        payload = {"items": [{"id": "AGORA-42", "title": "Govern work management"}]}
    elif args.operation == "view":
        payload = {"id": args.issue, "state": "Ready", "title": "Govern work management"}
    elif args.operation == "create":
        payload = {
            "id": f"{args.project}-43",
            "type": args.type,
            "title": args.title,
            "description": args.description,
            "state": "Open",
        }
    elif args.operation == "comment":
        payload = {"id": args.issue, "comment": args.body}
    else:
        payload = {"id": args.issue, "state": args.to}
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()

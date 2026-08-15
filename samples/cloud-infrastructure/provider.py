import argparse
import json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic sample cloud provider")
    resources = parser.add_subparsers(dest="resource_type", required=True)

    resource = resources.add_parser("resource")
    resource_operations = resource.add_subparsers(dest="operation", required=True)
    list_resources = resource_operations.add_parser("list")
    list_resources.add_argument("--environment", required=True)
    list_resources.add_argument("--output", choices=("json",), required=True)
    inspect = resource_operations.add_parser("inspect")
    inspect.add_argument("resource")
    inspect.add_argument("--environment", required=True)
    inspect.add_argument("--output", choices=("json",), required=True)
    destroy = resource_operations.add_parser("destroy")
    destroy.add_argument("resource")
    destroy.add_argument("--environment", required=True)
    destroy.add_argument("--output", choices=("json",), required=True)

    change = resources.add_parser("change")
    change_operations = change.add_subparsers(dest="operation", required=True)
    plan = change_operations.add_parser("plan")
    plan.add_argument("--environment", required=True)
    plan.add_argument("--change", required=True)
    plan.add_argument("--output", choices=("json",), required=True)
    apply_plan = change_operations.add_parser("apply")
    apply_plan.add_argument("plan")
    apply_plan.add_argument("--environment", required=True)
    apply_plan.add_argument("--output", choices=("json",), required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.resource_type == "resource" and args.operation == "list":
        payload = {
            "resources": [
                {"id": "service/api", "environment": args.environment, "status": "healthy"}
            ]
        }
    elif args.resource_type == "resource" and args.operation == "inspect":
        payload = {"id": args.resource, "environment": args.environment, "status": "healthy"}
    elif args.resource_type == "resource":
        payload = {"id": args.resource, "environment": args.environment, "status": "destroyed"}
    elif args.operation == "plan":
        payload = {
            "id": "plan-42",
            "environment": args.environment,
            "change": args.change,
            "changes": 1,
            "destructive": False,
        }
    else:
        payload = {"plan": args.plan, "environment": args.environment, "status": "applied"}
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()

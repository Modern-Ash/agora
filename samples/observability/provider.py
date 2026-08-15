import argparse
import json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic sample observability provider")
    resources = parser.add_subparsers(dest="resource", required=True)
    service = resources.add_parser("service")
    service_ops = service.add_subparsers(dest="operation", required=True)
    health = service_ops.add_parser("health")
    health.add_argument("service")
    health.add_argument("--environment", required=True)
    health.add_argument("--output", choices=("json",), required=True)
    for resource_name in ("metrics", "logs"):
        resource = resources.add_parser(resource_name)
        operations = resource.add_subparsers(dest="operation", required=True)
        operation = operations.add_parser("query" if resource_name == "metrics" else "search")
        operation.add_argument("--service", required=True)
        operation.add_argument("--window", required=True)
        operation.add_argument("--query", required=True)
        operation.add_argument("--output", choices=("json",), required=True)
    incident = resources.add_parser("incident")
    incident_ops = incident.add_subparsers(dest="operation", required=True)
    create = incident_ops.add_parser("create")
    create.add_argument("--service", required=True)
    create.add_argument("--severity", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--summary", required=True)
    create.add_argument("--output", choices=("json",), required=True)
    update = incident_ops.add_parser("update")
    update.add_argument("incident")
    update.add_argument("--status", required=True)
    update.add_argument("--summary", required=True)
    update.add_argument("--output", choices=("json",), required=True)
    resolve = incident_ops.add_parser("resolve")
    resolve.add_argument("incident")
    resolve.add_argument("--resolution", required=True)
    resolve.add_argument("--output", choices=("json",), required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.resource == "service":
        payload = {"service": args.service, "environment": args.environment, "status": "healthy"}
    elif args.resource in {"metrics", "logs"}:
        payload = {"service": args.service, "window": args.window, "results": 1}
    elif args.operation == "create":
        payload = {
            "id": "INC-42",
            "service": args.service,
            "severity": args.severity,
            "status": "open",
        }
    elif args.operation == "update":
        payload = {"id": args.incident, "status": args.status, "summary": args.summary}
    else:
        payload = {"id": args.incident, "status": "resolved", "resolution": args.resolution}
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()

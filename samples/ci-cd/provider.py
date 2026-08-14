import argparse
import json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic sample CI/CD provider")
    resources = parser.add_subparsers(dest="resource", required=True)

    run = resources.add_parser("run")
    run_operations = run.add_subparsers(dest="operation", required=True)
    list_runs = run_operations.add_parser("list")
    list_runs.add_argument("--pipeline", required=True)
    list_runs.add_argument("--output", choices=("json",), required=True)
    view_run = run_operations.add_parser("view")
    view_run.add_argument("run")
    view_run.add_argument("--output", choices=("json",), required=True)
    cancel_run = run_operations.add_parser("cancel")
    cancel_run.add_argument("run")
    cancel_run.add_argument("--output", choices=("json",), required=True)

    pipeline = resources.add_parser("pipeline")
    pipeline_operations = pipeline.add_subparsers(dest="operation", required=True)
    trigger = pipeline_operations.add_parser("trigger")
    trigger.add_argument("pipeline")
    trigger.add_argument("--ref", required=True)
    trigger.add_argument("--parameters", required=True)
    trigger.add_argument("--output", choices=("json",), required=True)

    deployment = resources.add_parser("deployment")
    deployment_operations = deployment.add_subparsers(dest="operation", required=True)
    create = deployment_operations.add_parser("create")
    create.add_argument("--environment", required=True)
    create.add_argument("--artifact", required=True)
    create.add_argument("--output", choices=("json",), required=True)
    view_deployment = deployment_operations.add_parser("view")
    view_deployment.add_argument("deployment")
    view_deployment.add_argument("--output", choices=("json",), required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.resource == "run" and args.operation == "list":
        payload = {"runs": [{"id": "run-42", "pipeline": args.pipeline, "status": "passed"}]}
    elif args.resource == "run" and args.operation == "view":
        payload = {"id": args.run, "status": "passed", "artifact": "sha256:verified"}
    elif args.resource == "run":
        payload = {"id": args.run, "status": "cancelled"}
    elif args.resource == "pipeline":
        payload = {
            "id": "run-43",
            "pipeline": args.pipeline,
            "ref": args.ref,
            "parameters": args.parameters,
            "status": "queued",
        }
    elif args.operation == "create":
        payload = {
            "id": "deployment-42",
            "environment": args.environment,
            "artifact": args.artifact,
            "status": "created",
        }
    else:
        payload = {"id": args.deployment, "status": "healthy"}
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()

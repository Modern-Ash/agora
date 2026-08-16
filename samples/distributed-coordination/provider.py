import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version="sample-leasectl 1.0.0")
    parser.add_argument("--state", required=True)
    parser.add_argument("action", choices=("acquire", "renew", "release"))
    parser.add_argument("--resource", required=True)
    parser.add_argument("--owner")
    parser.add_argument("--operation")
    parser.add_argument("--ttl-seconds")
    parser.add_argument("--lease-id")
    parser.add_argument("--fencing-token")
    args = parser.parse_args()
    state = Path(args.state)

    if args.action == "acquire":
        if state.exists():
            print("lease already held", flush=True)
            return 9
        value = {
            "resource": args.resource,
            "owner": args.owner,
            "lease-id": "sample-lease",
            "fencing-token": "sample-fence-1",
        }
        state.write_text(json.dumps(value), encoding="utf-8")
        print(json.dumps(value))
        return 0

    if not state.exists():
        print("lease is not active", flush=True)
        return 8
    value = json.loads(state.read_text(encoding="utf-8"))
    if args.lease_id != value["lease-id"] or args.fencing_token != value["fencing-token"]:
        print("lease identity mismatch", flush=True)
        return 7
    if args.action == "release":
        state.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

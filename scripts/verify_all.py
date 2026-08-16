import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VerificationStep:
    name: str
    command: list[str]


def build_steps(
    root: Path,
    *,
    include_samples: bool = True,
    include_build: bool = True,
) -> list[VerificationStep]:
    python = sys.executable
    steps = [
        VerificationStep("format", [python, "-m", "ruff", "format", "--check", "."]),
        VerificationStep("lint", [python, "-m", "ruff", "check", "."]),
        VerificationStep("tests", [python, "-m", "pytest", "-q"]),
        VerificationStep(
            "documentation links",
            [python, str(root / "scripts" / "check_docs.py")],
        ),
        VerificationStep(
            "role conformance self-test",
            [python, "-m", "agora", "self-test"],
        ),
    ]
    if include_samples:
        steps.extend(
            VerificationStep(
                f"sample: {sample.parent.name}",
                [python, str(sample)],
            )
            for sample in sorted((root / "samples").glob("*/run.py"))
        )
    if include_build:
        uv = shutil.which("uv")
        command = [uv, "build"] if uv is not None else [python, "-m", "build"]
        steps.append(VerificationStep("distribution build", command))
    return steps


def run_steps(root: Path, steps: list[VerificationStep], *, quiet: bool = False) -> int:
    failures: list[str] = []
    for index, step in enumerate(steps, start=1):
        print(f"[{index}/{len(steps)}] {step.name}", flush=True)
        result = subprocess.run(
            step.command,
            cwd=root,
            check=False,
            capture_output=quiet,
            text=True,
        )
        if result.returncode == 0:
            print("  passed", flush=True)
            continue
        failures.append(step.name)
        print(f"  failed with exit code {result.returncode}", file=sys.stderr)
        if quiet:
            if result.stdout:
                print(result.stdout.rstrip(), file=sys.stderr)
            if result.stderr:
                print(result.stderr.rstrip(), file=sys.stderr)

    if failures:
        print(f"Verification failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    print(f"Verification passed: {len(steps)} steps")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify Agora code, Markdown contracts, adapters, samples, and distribution"
    )
    parser.add_argument("--skip-samples", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Show subprocess output only when a step fails",
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    steps = build_steps(
        root,
        include_samples=not args.skip_samples,
        include_build=not args.skip_build,
    )
    return run_steps(root, steps, quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())

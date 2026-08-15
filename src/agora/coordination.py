import json
import os
import re
import socket
import subprocess
import threading
import uuid
from collections.abc import Callable
from pathlib import Path

from agora.markdown import (
    MarkdownDocument,
    optional_string_attribute,
    read_markdown,
    render_markdown,
    string_attribute,
    strings_attribute,
)
from agora.model import CoordinationPolicyRecord

MAX_LEASE_OUTPUT_BYTES = 65536
VERSION_PATTERN = re.compile(r"(?<!\d)(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?!\d)")
LeaseRunner = Callable[[list[str], Path, float], subprocess.CompletedProcess[str]]


class DistributedLeaseError(RuntimeError):
    pass


def load_coordination_policy(path: Path) -> CoordinationPolicyRecord:
    document = read_markdown(path)
    if string_attribute(document.attributes, "schema") != "agora/coordination/v1":
        raise ValueError(f"Coordination schema must be agora/coordination/v1: {path}")
    mode = string_attribute(document.attributes, "mode")
    if mode not in {"local", "external-lease"}:
        raise ValueError(f"Unsupported coordination mode: {mode}")
    resource_id = optional_string_attribute(document.attributes, "resource-id")
    executable = optional_string_attribute(document.attributes, "executable")
    arguments = strings_attribute(document.attributes, "arguments")
    version_arguments = strings_attribute(document.attributes, "version-arguments")
    minimum_version = optional_string_attribute(document.attributes, "minimum-runtime-version")
    lease_seconds = _positive_integer(document.attributes, "lease-seconds", maximum=86400)
    command_timeout = _positive_integer(document.attributes, "command-timeout-seconds", maximum=300)
    if any(not argument for argument in [*arguments, *version_arguments]):
        raise ValueError("Coordination arguments must be non-empty strings")
    if any(
        "credential" in argument.lower() or "token" in argument.lower()
        for argument in [*arguments, *version_arguments]
    ):
        raise ValueError("Coordination arguments must not contain credential or token inputs")
    if mode == "external-lease" and (
        resource_id is None
        or executable is None
        or not version_arguments
        or minimum_version is None
    ):
        raise ValueError(
            "External lease coordination requires resource-id, executable, version-arguments, "
            "and minimum-runtime-version"
        )
    if (
        resource_id is not None
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@#-]{0,255}", resource_id) is None
    ):
        raise ValueError("Coordination resource-id must be a stable non-path identifier")
    if minimum_version is not None and VERSION_PATTERN.fullmatch(minimum_version) is None:
        raise ValueError("Coordination minimum-runtime-version must be MAJOR.MINOR.PATCH")
    if mode == "local" and (
        any(value is not None for value in (resource_id, executable, minimum_version))
        or arguments
        or version_arguments
    ):
        raise ValueError("Local coordination must not declare external lease command settings")
    return CoordinationPolicyRecord(
        mode=mode,
        resource_id=resource_id,
        executable=executable,
        arguments=arguments,
        version_arguments=version_arguments,
        minimum_runtime_version=minimum_version,
        lease_seconds=lease_seconds,
        command_timeout_seconds=command_timeout,
        path=str(path),
    )


def render_coordination_policy(record: CoordinationPolicyRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/coordination/v1",
                "mode": record.mode,
                "resource-id": record.resource_id,
                "executable": record.executable,
                "arguments": record.arguments,
                "version-arguments": record.version_arguments,
                "minimum-runtime-version": record.minimum_runtime_version,
                "lease-seconds": record.lease_seconds,
                "command-timeout-seconds": record.command_timeout_seconds,
            },
            body=(
                "# Writer coordination\n\n"
                "The local operating-system lock remains mandatory. External lease credentials "
                "belong to the configured executable and its environment."
            ),
        )
    )


class ExternalLease:
    def __init__(
        self,
        policy: CoordinationPolicyRecord,
        operation: str,
        cwd: Path,
        *,
        runner: LeaseRunner | None = None,
    ) -> None:
        if policy.mode != "external-lease" or not policy.executable or not policy.resource_id:
            raise ValueError("ExternalLease requires an external-lease coordination policy")
        self.policy = policy
        self.operation = operation
        self.cwd = cwd
        self.runner = runner or _run_lease_command
        self.owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"
        self.lease_id: str | None = None
        self.fencing_token: str | None = None
        self._stop = threading.Event()
        self._renewal_error: Exception | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "ExternalLease":
        self._assert_compatible_runtime()
        response = self._call(
            "acquire",
            "--resource",
            self.policy.resource_id or "",
            "--owner",
            self.owner,
            "--operation",
            self.operation,
            "--ttl-seconds",
            str(self.policy.lease_seconds),
            expect_response=True,
        )
        self.lease_id = _response_value(response, "lease-id")
        self.fencing_token = _response_value(response, "fencing-token")
        self._thread = threading.Thread(
            target=self._renew_loop,
            name="agora-distributed-lease",
            daemon=True,
        )
        self._thread.start()
        return self

    def _assert_compatible_runtime(self) -> None:
        command = [self.policy.executable or "", *self.policy.version_arguments]
        try:
            result = self.runner(command, self.cwd, self.policy.command_timeout_seconds)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise DistributedLeaseError(
                f"Distributed lease version command failed: {error}"
            ) from error
        output = f"{result.stdout}\n{result.stderr}"
        if len(output.encode("utf-8")) > MAX_LEASE_OUTPUT_BYTES:
            raise DistributedLeaseError("Distributed lease version output exceeded its limit")
        if result.returncode != 0:
            raise DistributedLeaseError(
                f"Distributed lease version command failed with code {result.returncode}"
            )
        match = VERSION_PATTERN.search(output)
        if match is None:
            raise DistributedLeaseError(
                "Distributed lease version command returned no MAJOR.MINOR.PATCH"
            )
        detected = tuple(int(part) for part in match.groups())
        minimum = tuple(
            int(part) for part in (self.policy.minimum_runtime_version or "").split(".")
        )
        if detected < minimum:
            raise DistributedLeaseError(
                f"Distributed lease runtime {match.group(0)} is older than required "
                f"{self.policy.minimum_runtime_version}"
            )

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.policy.command_timeout_seconds + 1)
        renewal_error = self._renewal_error
        release_error: Exception | None = None
        try:
            if self.lease_id is not None and self.fencing_token is not None:
                self._call(
                    "release",
                    "--resource",
                    self.policy.resource_id or "",
                    "--lease-id",
                    self.lease_id,
                    "--fencing-token",
                    self.fencing_token,
                )
        except Exception as error:  # preserve an error raised by the governed mutation
            release_error = error
        if exc_type is None:
            if renewal_error is not None:
                raise DistributedLeaseError(
                    f"Distributed lease renewal failed: {renewal_error}"
                ) from renewal_error
            if release_error is not None:
                raise release_error

    def _renew_loop(self) -> None:
        interval = max(1.0, self.policy.lease_seconds / 3)
        while not self._stop.wait(interval):
            try:
                self._call(
                    "renew",
                    "--resource",
                    self.policy.resource_id or "",
                    "--lease-id",
                    self.lease_id or "",
                    "--fencing-token",
                    self.fencing_token or "",
                    "--ttl-seconds",
                    str(self.policy.lease_seconds),
                )
            except Exception as error:
                self._renewal_error = error
                self._stop.set()

    def _call(
        self, action: str, *arguments: str, expect_response: bool = False
    ) -> dict[str, object]:
        command = [self.policy.executable or "", *self.policy.arguments, action, *arguments]
        try:
            result = self.runner(command, self.cwd, self.policy.command_timeout_seconds)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise DistributedLeaseError(
                f"Distributed lease {action} command failed: {error}"
            ) from error
        output_size = len(result.stdout.encode("utf-8")) + len(result.stderr.encode("utf-8"))
        if output_size > MAX_LEASE_OUTPUT_BYTES:
            raise DistributedLeaseError(
                f"Distributed lease {action} output exceeded {MAX_LEASE_OUTPUT_BYTES} bytes"
            )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "no provider detail"
            raise DistributedLeaseError(
                f"Distributed lease {action} failed with code {result.returncode}: {detail}"
            )
        if not expect_response:
            return {}
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise DistributedLeaseError(
                f"Distributed lease {action} returned invalid JSON"
            ) from error
        if not isinstance(value, dict):
            raise DistributedLeaseError(
                f"Distributed lease {action} response must be a JSON object"
            )
        return value


def _run_lease_command(
    command: list[str], cwd: Path, timeout: float
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _response_value(response: dict[str, object], key: str) -> str:
    value = response.get(key)
    if not isinstance(value, str) or not value or len(value) > 256:
        raise DistributedLeaseError(
            f"Distributed lease response requires a bounded non-empty {key}"
        )
    return value


def _positive_integer(attributes: dict[str, object], key: str, *, maximum: int) -> int:
    value = attributes.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > maximum:
        raise ValueError(f"Coordination {key} must be an integer between 1 and {maximum}")
    return value

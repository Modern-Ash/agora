import re
from pathlib import Path

from agora.filesystem import assert_slug
from agora.markdown import (
    optional_string_attribute,
    read_markdown,
    string_attribute,
    strings_attribute,
)
from agora.model import ToolContract, ToolOperation
from agora.packs import pack_manifest_metadata

TOOL_RISKS = ("read", "write", "destructive")
TOOL_ADAPTER_TRANSPORTS = ("cli",)
CAPABILITY_PATTERN = re.compile(r"[a-z][a-z0-9.-]*")
PLACEHOLDER_PATTERN = re.compile(r"\{([a-z][a-z0-9-]*)\}")
CONVENTIONAL_COMMIT_HEADER = re.compile(r"[A-Za-z][A-Za-z0-9-]*(?:\([^()\r\n]+\))?!?: \S.*")
SUPPORTED_INPUT_RULES = {"conventional-commits/v1.0.0"}


def load_tool_contract(root: Path) -> ToolContract:
    document = read_markdown(root / "TOOL.md")
    if string_attribute(document.attributes, "schema") != "agora/tool/v1":
        raise ValueError("Tool Pack schema must be agora/tool/v1")

    tool_id = string_attribute(document.attributes, "id")
    assert_slug(tool_id, "Tool id")
    name = string_attribute(document.attributes, "name")
    version, dependencies = pack_manifest_metadata(document.attributes, f"tool/{tool_id}")
    category = string_attribute(document.attributes, "category")
    assert_slug(category, "Tool category")
    executable = string_attribute(document.attributes, "executable")
    authentication_reference = optional_string_attribute(
        document.attributes, "authentication-reference"
    )
    provider = optional_string_attribute(document.attributes, "provider")
    transport = optional_string_attribute(document.attributes, "transport")
    implements = optional_string_attribute(document.attributes, "implements")
    adapter_values = (provider, transport, implements)
    if any(value is not None for value in adapter_values) and any(
        value is None for value in adapter_values
    ):
        raise ValueError("Tool adapter metadata requires provider, transport, and implements")
    if provider is not None:
        assert_slug(provider, "Tool adapter provider")
        assert_slug(implements, "Tool adapter implementation")
        if transport not in TOOL_ADAPTER_TRANSPORTS:
            raise ValueError(f"Unsupported Tool adapter transport: {transport}")

    operation_root = root / "operations"
    paths = sorted(operation_root.glob("*.md")) if operation_root.exists() else []
    if not paths:
        raise ValueError(f"Tool Pack {tool_id} must define at least one operation")

    operations: dict[str, ToolOperation] = {}
    for path in paths:
        operation = _load_operation(path)
        if operation.id in operations:
            raise ValueError(f"Tool Pack {tool_id} has duplicate operation: {operation.id}")
        operations[operation.id] = operation

    return ToolContract(
        id=tool_id,
        name=name,
        version=version,
        dependencies=dependencies,
        category=category,
        executable=executable,
        authentication_reference=authentication_reference,
        operations=operations,
        provider=provider,
        transport=transport,
        implements=implements,
    )


def _load_operation(path: Path) -> ToolOperation:
    document = read_markdown(path)
    if string_attribute(document.attributes, "schema") != "agora/tool-operation/v1":
        raise ValueError(f"Tool operation schema must be agora/tool-operation/v1: {path}")
    operation_id = string_attribute(document.attributes, "id")
    assert_slug(operation_id, "Tool operation id")
    name = string_attribute(document.attributes, "name")
    capability = string_attribute(document.attributes, "capability")
    if not CAPABILITY_PATTERN.fullmatch(capability):
        raise ValueError(f"Invalid tool capability: {capability}")
    risk = string_attribute(document.attributes, "risk")
    if risk not in TOOL_RISKS:
        raise ValueError(f"Unsupported tool operation risk: {risk}")
    arguments = strings_attribute(document.attributes, "arguments")
    inputs = strings_attribute(document.attributes, "inputs")
    if len(set(inputs)) != len(inputs):
        raise ValueError(f"Tool operation {operation_id} input ids must be unique")
    for input_id in inputs:
        assert_slug(input_id, "Tool input id")

    input_rules = document.attributes.get("input-rules", {})
    if not isinstance(input_rules, dict) or any(
        not isinstance(input_id, str) or not isinstance(rule, str)
        for input_id, rule in input_rules.items()
    ):
        raise ValueError(f"Tool operation {operation_id} input-rules must be a string map")
    unknown_rule_inputs = sorted(set(input_rules) - set(inputs))
    if unknown_rule_inputs:
        raise ValueError(
            f"Tool operation {operation_id} has rules for undeclared inputs: "
            f"{', '.join(unknown_rule_inputs)}"
        )
    unsupported_rules = sorted(set(input_rules.values()) - SUPPORTED_INPUT_RULES)
    if unsupported_rules:
        raise ValueError(
            f"Tool operation {operation_id} has unsupported input rules: "
            f"{', '.join(unsupported_rules)}"
        )

    input_values = document.attributes.get("input-values", {})
    if not isinstance(input_values, dict) or any(
        not isinstance(input_id, str)
        or not isinstance(values, list)
        or not values
        or any(not isinstance(value, str) or not value for value in values)
        for input_id, values in input_values.items()
    ):
        raise ValueError(f"Tool operation {operation_id} input-values must map to string arrays")
    unknown_value_inputs = sorted(set(input_values) - set(inputs))
    if unknown_value_inputs:
        raise ValueError(
            f"Tool operation {operation_id} has values for undeclared inputs: "
            f"{', '.join(unknown_value_inputs)}"
        )
    duplicate_value_inputs = sorted(
        input_id for input_id, values in input_values.items() if len(set(values)) != len(values)
    )
    if duplicate_value_inputs:
        raise ValueError(
            f"Tool operation {operation_id} has duplicate allowed values for: "
            f"{', '.join(duplicate_value_inputs)}"
        )

    placeholders = {
        placeholder
        for argument in arguments
        for placeholder in PLACEHOLDER_PATTERN.findall(argument)
    }
    unknown = sorted(placeholders - set(inputs))
    unused = sorted(set(inputs) - placeholders)
    if unknown:
        raise ValueError(
            f"Tool operation {operation_id} has undeclared placeholders: {', '.join(unknown)}"
        )
    if unused:
        raise ValueError(f"Tool operation {operation_id} has unused inputs: {', '.join(unused)}")

    approval_role = optional_string_attribute(document.attributes, "approval-role")
    if approval_role is not None:
        assert_slug(approval_role, "Approval role id")
    result_kind = optional_string_attribute(document.attributes, "result-kind")
    if result_kind is not None:
        assert_slug(result_kind, "Result artifact kind")
    return ToolOperation(
        id=operation_id,
        name=name,
        capability=capability,
        risk=risk,
        arguments=arguments,
        inputs=inputs,
        input_rules=input_rules,
        input_values=input_values,
        approval_role=approval_role,
        result_kind=result_kind,
    )


def validate_operation_inputs(operation: ToolOperation, inputs: dict[str, str]) -> None:
    for input_id, allowed_values in operation.input_values.items():
        value = inputs.get(input_id)
        if value is not None and value not in allowed_values:
            raise ValueError(
                f"Tool operation {operation.id} input {input_id} must be one of: "
                f"{', '.join(allowed_values)}"
            )
    for input_id, rule in operation.input_rules.items():
        value = inputs.get(input_id)
        if value is None:
            continue
        if rule == "conventional-commits/v1.0.0":
            validate_conventional_commit(value)


def validate_tool_adapter_contract(adapter: ToolContract, implemented: ToolContract) -> None:
    if adapter.implements != implemented.id:
        raise ValueError(
            f"Tool adapter {adapter.id} declares {adapter.implements}, not {implemented.id}"
        )
    missing_operations = sorted(set(implemented.operations) - set(adapter.operations))
    if missing_operations:
        raise ValueError(
            f"Tool adapter {adapter.id} is missing operations from {implemented.id}: "
            f"{', '.join(missing_operations)}"
        )
    for operation_id, expected in implemented.operations.items():
        actual = adapter.operations[operation_id]
        if actual.capability != expected.capability:
            raise ValueError(
                f"Tool adapter {adapter.id}/{operation_id} capability must be {expected.capability}"
            )
        if actual.risk != expected.risk:
            raise ValueError(
                f"Tool adapter {adapter.id}/{operation_id} risk must be {expected.risk}"
            )
        missing_inputs = sorted(set(expected.inputs) - set(actual.inputs))
        if missing_inputs:
            raise ValueError(
                f"Tool adapter {adapter.id}/{operation_id} is missing contract inputs: "
                f"{', '.join(missing_inputs)}"
            )
        if actual.result_kind != expected.result_kind:
            raise ValueError(
                f"Tool adapter {adapter.id}/{operation_id} result kind must be "
                f"{expected.result_kind}"
            )


def validate_conventional_commit(message: str) -> None:
    if "\x00" in message:
        raise ValueError("Conventional Commit message must not contain a null byte")
    lines = message.splitlines()
    if not lines or not CONVENTIONAL_COMMIT_HEADER.fullmatch(lines[0]):
        raise ValueError(
            "Commit message must match Conventional Commits 1.0.0: "
            "<type>[optional scope][!]: <description>"
        )
    if len(lines) > 1 and lines[1].strip():
        raise ValueError("Conventional Commit body or footers must begin after a blank line")

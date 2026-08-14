import re
from pathlib import Path
from typing import Any

from agora.filesystem import assert_slug
from agora.markdown import (
    optional_string_attribute,
    read_markdown,
    string_attribute,
    strings_attribute,
)
from agora.model import ACTOR_KINDS, GatePolicy, MethodContract, TransitionRule
from agora.packs import pack_manifest_metadata

TOOL_CAPABILITY_PATTERN = re.compile(r"[a-z][a-z0-9.-]*")
ACTION_PATTERN = re.compile(r"[a-z][a-z0-9.-]*")


def load_method_contract(root: Path) -> MethodContract:
    document = read_markdown(root / "METHOD.md")
    if string_attribute(document.attributes, "schema") != "agora/method/v1":
        raise ValueError("Method Pack schema must be agora/method/v1")

    method_id = string_attribute(document.attributes, "id")
    assert_slug(method_id, "Method id")
    name = string_attribute(document.attributes, "name")
    version, dependencies = pack_manifest_metadata(document.attributes, f"method/{method_id}")
    required_roles = strings_attribute(document.attributes, "required-roles")
    states = strings_attribute(document.attributes, "work-states")
    terminal_state = string_attribute(document.attributes, "terminal-state")
    if not required_roles:
        raise ValueError(f"Method Pack {method_id} must define at least one required role")
    if not states:
        raise ValueError(f"Method Pack {method_id} must define at least one work state")
    if len(set(states)) != len(states):
        raise ValueError(f"Method Pack {method_id} work states must be unique")
    if terminal_state not in states:
        raise ValueError(
            f"Method Pack {method_id} terminal state {terminal_state} is not in work-states"
        )

    missing_roles = [
        role for role in required_roles if not (root / "roles" / f"{role}.md").is_file()
    ]
    if missing_roles:
        raise ValueError(
            f"Method Pack {method_id} is missing role files: {', '.join(missing_roles)}"
        )
    for role in required_roles:
        role_path = root / "roles" / f"{role}.md"
        attributes = read_markdown(role_path).attributes
        if string_attribute(attributes, "schema") != "agora/role/v1":
            raise ValueError(f"Role schema must be agora/role/v1: {role_path}")
        if string_attribute(attributes, "id") != role:
            raise ValueError(f"Role id must match its Method Pack role: {role}")
        required_capabilities = strings_attribute(attributes, "required-capabilities")
        if any(
            not TOOL_CAPABILITY_PATTERN.fullmatch(capability)
            for capability in required_capabilities
        ):
            raise ValueError(f"Role {role} required-capabilities must be a valid string array")
        allowed_kinds = strings_attribute(attributes, "allowed-actor-kinds")
        if not allowed_kinds or any(kind not in ACTOR_KINDS for kind in allowed_kinds):
            raise ValueError(f"Role {role} allowed-actor-kinds contains an unsupported actor kind")
        allowed_actions = strings_attribute(attributes, "allowed-actions")
        if any(not ACTION_PATTERN.fullmatch(action) for action in allowed_actions):
            raise ValueError(f"Role {role} allowed-actions must be a valid string array")
        tool_capabilities = attributes.get("allowed-tool-capabilities", [])
        if not isinstance(tool_capabilities, list) or any(
            not isinstance(item, str) or not TOOL_CAPABILITY_PATTERN.fullmatch(item)
            for item in tool_capabilities
        ):
            raise ValueError(f"Role {role} allowed-tool-capabilities must be a valid string array")

    gates = _load_gates(root)
    for gate in gates.values():
        unknown_approval_roles = [
            role for role in gate.required_approval_roles if role not in required_roles
        ]
        if unknown_approval_roles:
            raise ValueError(
                f"Gate {gate.id} uses unknown approval roles: {', '.join(unknown_approval_roles)}"
            )
    transitions = _load_transitions(
        root,
        method_id=method_id,
        states=states,
        required_roles=required_roles,
        terminal_state=terminal_state,
        gates=gates,
    )
    wip_limits = _load_wip_limits(document.attributes, method_id, states)
    return MethodContract(
        id=method_id,
        name=name,
        version=version,
        dependencies=dependencies,
        required_roles=required_roles,
        work_states=states,
        terminal_state=terminal_state,
        transitions=transitions,
        gates=gates,
        wip_limits=wip_limits,
    )


def _load_gates(root: Path) -> dict[str, GatePolicy]:
    gates = {"completion": GatePolicy(id="completion")}
    gate_root = root / "gates"
    if not gate_root.exists():
        return gates
    for path in sorted(gate_root.glob("*.md")):
        document = read_markdown(path)
        if string_attribute(document.attributes, "schema") != "agora/gate/v1":
            raise ValueError(f"Gate schema must be agora/gate/v1: {path}")
        gate_id = string_attribute(document.attributes, "id")
        assert_slug(gate_id, "Gate id")
        gates[gate_id] = GatePolicy(
            id=gate_id,
            require_all_criteria=_boolean(
                document.attributes, "require-all-criteria", default=True
            ),
            require_required_artifacts=_boolean(
                document.attributes, "require-required-artifacts", default=True
            ),
            require_successful_evidence=_boolean(
                document.attributes, "require-successful-evidence", default=True
            ),
            required_approval_roles=_string_list(
                document.attributes, "required-approval-roles", default=[]
            ),
        )
    return gates


def _load_transitions(
    root: Path,
    *,
    method_id: str,
    states: list[str],
    required_roles: list[str],
    terminal_state: str,
    gates: dict[str, GatePolicy],
) -> list[TransitionRule]:
    transition_root = root / "transitions"
    paths = sorted(transition_root.glob("*.md")) if transition_root.exists() else []
    if not paths:
        if terminal_state != states[-1]:
            raise ValueError(
                f"Legacy Method Pack {method_id} terminal state must be the last work state"
            )
        return [
            TransitionRule(
                source=source,
                target=target,
                roles=[],
                gate="completion" if target == terminal_state else None,
            )
            for source, target in zip(states, states[1:], strict=False)
        ]

    transitions: list[TransitionRule] = []
    seen: set[tuple[str, str]] = set()
    for path in paths:
        document = read_markdown(path)
        if string_attribute(document.attributes, "schema") != "agora/transition/v1":
            raise ValueError(f"Transition schema must be agora/transition/v1: {path}")
        source = string_attribute(document.attributes, "from")
        target = string_attribute(document.attributes, "to")
        roles = strings_attribute(document.attributes, "roles")
        gate = optional_string_attribute(document.attributes, "gate")
        if not roles:
            raise ValueError(f"Transition {source} -> {target} must define at least one role")
        if source not in states or target not in states:
            raise ValueError(
                f"Transition {source} -> {target} uses a state not defined by {method_id}"
            )
        unknown_roles = [role for role in roles if role not in required_roles]
        if unknown_roles:
            raise ValueError(
                f"Transition {source} -> {target} uses unknown roles: {', '.join(unknown_roles)}"
            )
        if gate is not None and gate not in gates:
            raise ValueError(f"Transition {source} -> {target} uses unknown gate: {gate}")
        pair = (source, target)
        if pair in seen:
            raise ValueError(
                f"Duplicate transition in Method Pack {method_id}: {source} -> {target}"
            )
        seen.add(pair)
        transitions.append(TransitionRule(source=source, target=target, roles=roles, gate=gate))

    if any(rule.source == terminal_state for rule in transitions):
        raise ValueError(f"Terminal state {terminal_state} cannot have outgoing transitions")
    reachable = {states[0]}
    while True:
        expanded = reachable | {rule.target for rule in transitions if rule.source in reachable}
        if expanded == reachable:
            break
        reachable = expanded
    unreachable = [state for state in states if state not in reachable]
    if unreachable:
        raise ValueError(
            f"Method Pack {method_id} has unreachable work states: {', '.join(unreachable)}"
        )
    return transitions


def _load_wip_limits(
    attributes: dict[str, Any], method_id: str, states: list[str]
) -> dict[str, int]:
    value = attributes.get("wip-limits", {})
    if not isinstance(value, dict):
        raise ValueError(f"Method Pack {method_id} wip-limits must be an object")
    limits: dict[str, int] = {}
    for state, limit in value.items():
        if state not in states:
            raise ValueError(f"Method Pack {method_id} has a WIP limit for unknown state: {state}")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError(
                f"Method Pack {method_id} WIP limit for {state} must be a positive integer"
            )
        limits[state] = limit
    return limits


def _boolean(attributes: dict[str, Any], key: str, *, default: bool) -> bool:
    value = attributes.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"Expected boolean attribute: {key}")
    return value


def _string_list(attributes: dict[str, Any], key: str, *, default: list[str]) -> list[str]:
    value = attributes.get(key, default)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"Expected string array attribute: {key}")
    return value

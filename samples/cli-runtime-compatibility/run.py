from pathlib import Path

from agora.workspace import AgoraWorkspace


def main() -> None:
    agora = AgoraWorkspace(cwd=Path.cwd())
    adapters = agora.list_tool_adapters(check_runtime=True)

    assert adapters
    for adapter in adapters:
        version = adapter.runtime_version or "not detected"
        if adapter.runtime_compatible is True:
            status = "compatible"
        elif adapter.runtime_compatible is False:
            status = "incompatible"
        else:
            status = "unverified"
        print(f"{adapter.id}: {status}; version={version}; {adapter.runtime_detail}")


if __name__ == "__main__":
    main()

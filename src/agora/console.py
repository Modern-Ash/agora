import os
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, is_dataclass, replace
from types import TracebackType
from typing import Any, TextIO

from agora.model import RunLoopEvent

_DISABLED_VALUES = {"1", "true", "yes", "on"}
_ANSI = {
    "bold": "1",
    "dim": "2",
    "cyan": "36",
    "green": "32",
    "yellow": "33",
    "red": "31",
    "bold_cyan": "1;36",
    "bold_green": "1;32",
    "bold_yellow": "1;33",
    "bold_red": "1;31",
}


@dataclass(frozen=True)
class ActivityContext:
    headline: str
    subject: str
    summary: str
    phase: str
    detail: str
    safety: str = ""
    preflight: tuple[str, ...] = ()
    live_details: tuple[str, ...] = ()
    live_detail_provider: Callable[[], str | None] | None = None


class ConsoleActivity:
    """Render safe governed progress without changing structured stdout."""

    def __init__(
        self,
        stream: TextIO,
        context: ActivityContext | None,
        *,
        interval_seconds: float = 0.12,
    ) -> None:
        self.stream = stream
        self.context = context
        self.interval_seconds = interval_seconds
        self.enabled = context is not None and _supports_progress(stream)
        self._started_at = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._has_rendered = False
        self._rendered_line_count = 0
        self._frame = 0
        self._lock = threading.RLock()

    def __enter__(self) -> "ConsoleActivity":
        if not self.enabled:
            return self
        assert self.context is not None
        self._started_at = time.monotonic()
        for line in self.context.preflight:
            self._write(f"{_fit_terminal_line(line, _terminal_columns(self.stream))}\n")
        if self.context.preflight:
            self._write("\n")
        self._render(0)
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if not self.enabled:
            return False
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 2))
        elapsed = time.monotonic() - self._started_at
        status = "finished" if exc_type is None else "failed"
        self._render_final(status, elapsed)
        return False

    def handle_run_event(self, event: RunLoopEvent) -> None:
        """Render only Agora-owned lifecycle facts, never provider reasoning or raw output."""
        if not self.enabled:
            return
        if event.kind == "step-selected" and event.task is not None:
            task = event.task
            targets = ", ".join(task.target_states) or "governed action"
            self.context = replace(
                self.context,
                phase=f"Step {event.step}/{event.max_steps}: {event.before_state} -> {targets}",
                detail=f"{task.actor} ({task.role}) | authority checked",
            )
            self._emit_event(
                f"AGORA [{event.step}/{event.max_steps}] SELECT  "
                f"{task.actor} ({task.role}) | {event.before_state} -> {targets}"
            )
            return
        if event.kind == "session-finished" and event.session is not None:
            session = event.session
            transition = f"{event.before_state} -> {event.after_state}"
            self.context = replace(
                self.context,
                phase=f"Session {session.status}: {transition}",
                detail=f"{session.id} | exit {session.exit_code}",
            )
            self._emit_event(
                f"AGORA [{event.step}/{event.max_steps}] SESSION "
                f"{session.status} | {transition} | {session.id}"
            )
            return
        if event.kind == "loop-stopped" and event.stop_reason is not None:
            next_action = _next_action_label(event.next_actions or [])
            label = event.stop_reason.replace("-", " ")
            self.context = replace(
                self.context,
                phase=f"Stop: {label}",
                detail=next_action,
            )
            self._emit_event(f"AGORA [stop] {label.upper()} | {next_action}")

    def _animate(self) -> None:
        index = 1
        while not self._stop.wait(self.interval_seconds):
            self._render(index)
            index += 1

    def _render(self, frame: int) -> None:
        with self._lock:
            self._frame = frame
            elapsed = time.monotonic() - self._started_at
            logo = _orbit_frame(frame)
            assert self.context is not None
            lines = [
                f"{logo[0]}  AGORA  {self.context.headline}  [{elapsed:.1f}s]",
                f"{logo[1]}  {self.context.subject}",
                f"{logo[2]}  {self.context.summary}",
                f"{logo[3]}  {self.context.phase}",
                f"{logo[4]}  {self.context.detail}",
            ]
            if self.context.safety:
                lines.append(f"           {self.context.safety}")
            live_detail = self._current_live_detail(frame)
            if live_detail:
                lines.append(f"           Now: {live_detail}")
            self._render_lines(lines)

    def _render_final(self, status: str, elapsed: float) -> None:
        with self._lock:
            logo = _orbit_frame(None)
            assert self.context is not None
            lines = [
                f"{logo[0]}  AGORA [{status}]  {self.context.headline}  ({elapsed:.1f}s)",
                f"{logo[1]}  {self.context.subject}",
                f"{logo[2]}  {self.context.summary}",
                f"{logo[3]}  {self.context.phase}",
                f"{logo[4]}  {self.context.detail}",
            ]
            if self.context.safety:
                lines.append(f"           {self.context.safety}")
            if self.context.live_details or self.context.live_detail_provider is not None:
                outcome = (
                    "Governed session finished; durable result finalized"
                    if status == "finished"
                    else "Governed session failed; durable diagnostics finalized"
                )
                lines.append(f"           Now: {outcome}")
            self._render_lines(lines, finish=True)

    def _current_live_detail(self, frame: int) -> str | None:
        assert self.context is not None
        if self.context.live_detail_provider is not None:
            try:
                provided = self.context.live_detail_provider()
            except (OSError, RuntimeError, ValueError):
                provided = None
            if provided:
                return provided
        if not self.context.live_details:
            return None
        frames_per_detail = max(1, round(1.8 / self.interval_seconds))
        index = (frame // frames_per_detail) % len(self.context.live_details)
        return self.context.live_details[index]

    def _emit_event(self, message: str) -> None:
        with self._lock:
            self._clear_rendered()
            columns = _terminal_columns(self.stream)
            self._write(f"{_fit_terminal_line(message, columns)}\n")
            self._render(self._frame)

    def _clear_rendered(self) -> None:
        if not self._has_rendered:
            return
        move_to_top = (
            f"\r\x1b[{self._rendered_line_count - 1}A" if self._rendered_line_count > 1 else "\r"
        )
        cleared = "\n".join("\x1b[2K" for _ in range(self._rendered_line_count))
        return_to_top = (
            f"\r\x1b[{self._rendered_line_count - 1}A" if self._rendered_line_count > 1 else "\r"
        )
        self._write(move_to_top + cleared + return_to_top)
        self._has_rendered = False
        self._rendered_line_count = 0

    def _render_lines(self, lines: Sequence[str], *, finish: bool = False) -> None:
        columns = _terminal_columns(self.stream)
        fitted = [_fit_terminal_line(line, columns) for line in lines]
        prefix = f"\r\x1b[{self._rendered_line_count - 1}A" if self._has_rendered else "\r"
        rendered = prefix + "\n".join(f"\x1b[2K{line}" for line in fitted)
        if finish:
            rendered += "\n"
        self._write(rendered)
        self._has_rendered = True
        self._rendered_line_count = len(fitted)

    def _write(self, value: str) -> None:
        try:
            self.stream.write(value)
            self.stream.flush()
        except (OSError, ValueError):
            self.enabled = False
            self._stop.set()


class ConsoleResult:
    """Present structured command results for a human terminal."""

    def __init__(self, stream: TextIO) -> None:
        self.stream = stream
        self.color = supports_color(stream)

    def render(self, command: str, value: Any) -> None:
        data = _normalize(value)
        if command == "status" and isinstance(data, dict):
            self._status(data)
        elif command == "doctor" and isinstance(data, (dict, list)):
            self._doctor(data)
        elif command == "validate" and isinstance(data, dict):
            self._validation(data)
        elif command in {"next", "inbox"} and isinstance(data, list):
            self._tasks(command, data)
        elif command == "session diagnose" and isinstance(data, dict):
            self._session_diagnosis(data)
        else:
            self._generic(command, data)
        self.stream.flush()

    def _status(self, data: dict[str, Any]) -> None:
        self._headline("Agora status", ok=True)
        self._section("Project")
        self._rows(
            (
                ("Name", data.get("project")),
                ("Runtime", data.get("integration")),
                ("Method", data.get("default_method")),
                ("Branch", data.get("branch")),
            )
        )
        counts = data.get("counts", {})
        if isinstance(counts, dict):
            visible = [
                (key.replace("-", " ").title(), value) for key, value in counts.items() if value
            ]
            self._section("State")
            self._rows(visible)
        attention = data.get("attention", {})
        pending = (
            [(key.replace("-", " ").title(), values) for key, values in attention.items() if values]
            if isinstance(attention, dict)
            else []
        )
        if pending:
            self._section("Attention")
            for label, values in pending:
                if len(values) == 1:
                    self._check(label, str(values[0]), ok=False)
                    continue
                self._check(label, f"{len(values)} recorded", ok=False)
                for item in values[:3]:
                    print(f"      {self._paint(str(item), 'dim')}", file=self.stream)
                if len(values) > 3:
                    print(
                        f"      {self._paint(f'+{len(values) - 3} more', 'dim')}",
                        file=self.stream,
                    )
        else:
            self._section("Attention")
            self._check("Clear", "No governed work currently needs attention", ok=True)

    def _doctor(self, data: dict[str, Any] | list[Any]) -> None:
        if isinstance(data, dict):
            data = data.get("checks", [])
        checks = [item for item in data if isinstance(item, dict)]
        passed = sum(item.get("ok") is True for item in checks)
        self._headline("Agora doctor", ok=passed == len(checks))
        self._section(f"Checks · {passed}/{len(checks)} passed")
        for item in checks:
            self._check(
                str(item.get("name", "check")).replace("-", " ").title(),
                str(item.get("detail", "")),
                ok=item.get("ok") is True,
            )

    def _validation(self, data: dict[str, Any]) -> None:
        ok = data.get("ok") is True
        issues = data.get("issues", [])
        self._headline("Agora validation", ok=ok)
        self._rows((("Project", data.get("project")), ("Issues", len(issues))))
        checked = data.get("checked", {})
        if isinstance(checked, dict):
            total = sum(value for value in checked.values() if isinstance(value, int))
            self._check("Records", f"{total} durable records checked", ok=True)
        if issues:
            self._section("Issues")
            for item in issues:
                if not isinstance(item, dict):
                    self._check("Issue", str(item), ok=False)
                    continue
                label = str(item.get("code", item.get("severity", "issue")))
                detail = str(item.get("message", item.get("path", "")))
                self._check(label, detail, ok=item.get("severity") != "error")
        else:
            self._check("Validation", "No issues found", ok=True)

    def _tasks(self, command: str, data: list[Any]) -> None:
        title = "Human inbox" if command == "inbox" else "Next governed actions"
        self._headline(title, ok=True)
        if not data:
            self._check("Clear", "No eligible actions found", ok=True)
            return
        for index, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                self._rows(((str(index), item),))
                continue
            actor = item.get("actor") or "unassigned"
            role = item.get("role") or "no role"
            reference = "/".join(
                str(part) for part in (item.get("swarm_id"), item.get("work_id")) if part
            )
            state = item.get("state") or item.get("kind") or "pending"
            targets = item.get("target_states") or []
            print(
                f"\n  {self._paint(str(index) + '.', 'bold_cyan')} "
                f"{self._paint(reference or str(item.get('id', 'action')), 'bold')}",
                file=self.stream,
            )
            self._rows(
                (
                    ("Actor", f"{actor} ({role})"),
                    ("Action", item.get("kind")),
                    ("State", state),
                    (
                        "Transition",
                        " → ".join([str(state), *map(str, targets)]) if targets else None,
                    ),
                )
            )
            blockers = item.get("blockers") or []
            if blockers:
                self._check("Blocked", "; ".join(str(value) for value in blockers), ok=False)

    def _session_diagnosis(self, data: dict[str, Any]) -> None:
        status = str(data.get("status", "unknown"))
        ok = status in {"completed", "recovered"}
        self._headline("Session diagnosis", ok=ok)
        scope = "/".join(str(item) for item in (data.get("swarm_id"), data.get("work_id")) if item)
        self._rows(
            (
                ("Session", data.get("id")),
                ("Status", status),
                ("Actor", data.get("actor")),
                ("Work", scope),
                ("Cause", data.get("termination_reason")),
                (
                    "Output",
                    f"{data.get('output_bytes', 0)} / {data.get('max_output_bytes', 0)} "
                    f"bytes ({data.get('output_percent', 0)}%)",
                ),
            )
        )
        self._section("Assessment")
        self._check(
            "Outcome",
            str(data.get("diagnosis", "No diagnosis available")),
            ok=ok,
        )
        if data.get("recovered_by"):
            self._check("Recovery", str(data["recovered_by"]), ok=True)
        self._section("Next step")
        self._rows((("Command", data.get("recommended_command")),))

    def _generic(self, command: str, data: Any) -> None:
        ok = not (isinstance(data, dict) and data.get("ok") is False)
        self._headline(command.replace("-", " ").title(), ok=ok)
        if isinstance(data, dict):
            self._render_mapping(data)
        elif isinstance(data, list):
            self._render_list(data)
        elif data is None:
            self._check("Completed", "No structured result returned", ok=ok)
        else:
            self._rows((("Result", data),))

    def _render_mapping(self, data: dict[str, Any]) -> None:
        scalars = [(key, value) for key, value in data.items() if _is_scalar(value)]
        if scalars:
            self._rows(((_label(key), _scalar(value)) for key, value in scalars))
        for key, value in data.items():
            if _is_scalar(value):
                continue
            if isinstance(value, list) and all(_is_scalar(item) for item in value):
                self._rows(((_label(key), _scalar_list(value)),))
                continue
            self._section(_label(key))
            if isinstance(value, dict):
                nested_scalars = [
                    (_label(child), _scalar(item))
                    for child, item in value.items()
                    if _is_scalar(item)
                ]
                self._rows(nested_scalars or (("Entries", len(value)),))
                nested = sum(not _is_scalar(item) for item in value.values())
                if nested:
                    self._rows((("Nested records", nested),))
            elif isinstance(value, list):
                self._render_list(value)
            else:
                self._rows((("Value", value),))

    def _render_list(self, values: list[Any]) -> None:
        if not values:
            self._rows((("Items", 0),))
            return
        for index, item in enumerate(values, start=1):
            if not isinstance(item, dict):
                self._rows(((str(index), _scalar(item)),))
                continue
            identity = next(
                (
                    item.get(key)
                    for key in ("title", "name", "id", "reference", "type", "kind")
                    if item.get(key) not in (None, "")
                ),
                f"Item {index}",
            )
            print(
                f"  {self._paint('•', 'cyan')} {self._paint(str(identity), 'bold')}",
                file=self.stream,
            )
            details = [
                (_label(key), _scalar(value))
                for key, value in item.items()
                if key not in {"title", "name", "id", "reference"} and _is_scalar(value)
            ][:5]
            self._rows(details)

    def _headline(self, title: str, *, ok: bool) -> None:
        marker = self._paint("✓" if ok else "!", "bold_green" if ok else "bold_yellow")
        print(f"\n{marker} {self._paint(title, 'bold')}", file=self.stream)

    def _section(self, title: str) -> None:
        print(f"\n{self._paint(title, 'bold_cyan')}", file=self.stream)

    def _rows(self, rows: Sequence[tuple[str, Any]]) -> None:
        materialized = [(str(label), value) for label, value in rows if value is not None]
        width = max((len(label) for label, _ in materialized), default=0)
        for label, value in materialized:
            print(
                f"  {self._paint(f'{label:<{width}}', 'dim')}  {_scalar(value)}",
                file=self.stream,
            )

    def _check(self, label: str, detail: str, *, ok: bool) -> None:
        marker = self._paint("✓" if ok else "!", "green" if ok else "bold_yellow")
        print(f"  {marker} {self._paint(label, 'bold')}  {detail}", file=self.stream)

    def _paint(self, value: str, style: str) -> str:
        if not self.color:
            return value
        return f"\x1b[{_ANSI[style]}m{value}\x1b[0m"


def _next_action_label(actions: Sequence[object]) -> str:
    for action in actions:
        actor = getattr(action, "actor", None)
        role = getattr(action, "role", None)
        if getattr(action, "actor_kind", None) == "human":
            return f"human decision: {actor} ({role})"
    return "no further governed action"


def _supports_progress(stream: TextIO) -> bool:
    disabled = os.environ.get("AGORA_NO_PROGRESS", "").strip().lower()
    if disabled in _DISABLED_VALUES or os.environ.get("TERM", "") == "dumb":
        return False
    try:
        return stream.isatty()
    except (AttributeError, OSError):
        return False


def is_human_terminal(stream: TextIO) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, OSError):
        return False


def supports_color(stream: TextIO) -> bool:
    return (
        is_human_terminal(stream)
        and "NO_COLOR" not in os.environ
        and os.environ.get("TERM", "") != "dumb"
    )


def _normalize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _normalize(child) for key, child in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _normalize(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(child) for child in value]
    return value


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _scalar(value: Any) -> str:
    if value is None:
        return "none"
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return str(value)


def _scalar_list(values: list[Any]) -> str:
    visible = ", ".join(_scalar(value) for value in values[:6])
    remaining = len(values) - 6
    return f"{visible} (+{remaining} more)" if remaining > 0 else visible or "none"


def _label(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").strip().title()


def _orbit_frame(active: int | None) -> tuple[str, str, str, str, str]:
    nodes = [" "] * 8
    if active is None:
        for index in (0, 2, 4, 6):
            nodes[index] = "."
    else:
        nodes[active % 8] = "o"
        nodes[(active - 1) % 8] = "*"
        nodes[(active - 2) % 8] = "."
    return (
        f"    {nodes[0]}    ",
        f" {nodes[7]} /-\\ {nodes[1]} ",
        f"{nodes[6]} | A | {nodes[2]}",
        f" {nodes[5]} \\-/ {nodes[3]} ",
        f"    {nodes[4]}    ",
    )


def _terminal_columns(stream: TextIO) -> int:
    try:
        return max(24, os.get_terminal_size(stream.fileno()).columns)
    except (AttributeError, OSError, ValueError):
        try:
            return max(24, int(os.environ.get("COLUMNS", "80")))
        except ValueError:
            return 80


def _fit_terminal_line(value: str, columns: int) -> str:
    available = max(1, columns - 1)
    if len(value) <= available:
        return value
    if available <= 3:
        return value[:available]
    return f"{value[: available - 3]}..."

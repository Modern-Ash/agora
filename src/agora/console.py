import os
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from types import TracebackType
from typing import TextIO

from agora.model import RunLoopEvent

_DISABLED_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ActivityContext:
    headline: str
    subject: str
    summary: str
    phase: str
    detail: str
    safety: str = ""
    preflight: tuple[str, ...] = ()


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
            self._render_lines(lines, finish=True)

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

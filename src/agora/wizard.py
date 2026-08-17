import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TextIO


@dataclass(frozen=True)
class Choice:
    label: str
    value: str
    detail: str = ""


class Wizard:
    def __init__(
        self,
        input_stream: TextIO,
        output_stream: TextIO,
        *,
        brand: str = "Agora Setup",
    ) -> None:
        self.input = input_stream
        self.output = output_stream
        self.brand = brand
        self.color = _supports_color(output_stream)

    def heading(self, title: str, detail: str | None = None) -> None:
        brand = self._paint(self.brand, "bold_cyan")
        separator = self._paint("|", "dim")
        print(f"\n{brand} {separator} {self._paint(title, 'bold')}", file=self.output)
        if detail:
            print(self._paint(detail, "dim"), file=self.output)

    def note(self, message: str) -> None:
        print(message, file=self.output)

    def success(self, title: str, detail: str | None = None) -> None:
        marker = self._paint("✓", "bold_green")
        print(f"\n{marker} {self._paint(title, 'bold')}", file=self.output)
        if detail:
            print(f"  {self._paint(detail, 'dim')}", file=self.output)

    def warning(self, message: str) -> None:
        print(f"\n{self._paint('!', 'bold_yellow')} {message}", file=self.output)

    def section(self, title: str) -> None:
        print(f"\n{self._paint(title, 'bold_cyan')}", file=self.output)

    def rows(self, rows: Sequence[tuple[str, str]]) -> None:
        width = max((len(label) for label, _ in rows), default=0)
        for label, value in rows:
            painted_label = self._paint(f"{label:<{width}}", "dim")
            print(f"  {painted_label}  {value}", file=self.output)

    def check(self, label: str, detail: str, *, ok: bool = True) -> None:
        marker = self._paint("✓" if ok else "!", "green" if ok else "bold_yellow")
        painted_label = self._paint(label, "bold")
        print(f"  {marker} {painted_label}  {detail}", file=self.output)

    def next_steps(self, commands: Sequence[tuple[str, str]]) -> None:
        self.section("Next steps")
        for index, (command, detail) in enumerate(commands, start=1):
            number = self._paint(f"{index}.", "bold_cyan")
            rendered_command = self._paint(command, "bold")
            print(f"  {number} {rendered_command}", file=self.output)
            print(f"     {self._paint(detail, 'dim')}", file=self.output)

    def text(
        self,
        label: str,
        *,
        default: str | None = None,
        validate: Callable[[str], str | None] | None = None,
    ) -> str:
        while True:
            suffix = f" [{default}]" if default is not None else ""
            value = self._read(f"{label}{suffix}: ").strip()
            if not value and default is not None:
                value = default
            if not value:
                print("  A value is required.", file=self.output)
                continue
            error = validate(value) if validate is not None else None
            if error is None:
                return value
            print(f"  {error}", file=self.output)

    def optional_text(self, label: str, *, default: str | None = None) -> str | None:
        suffix = f" [{default}]" if default is not None else ""
        value = self._read(f"{label}{suffix}: ").strip()
        if value:
            return value
        return default

    def integer(self, label: str, *, default: int, minimum: int = 0) -> int:
        def validate(value: str) -> str | None:
            try:
                parsed = int(value)
            except ValueError:
                return "Enter a whole number."
            return None if parsed >= minimum else f"Enter a value of at least {minimum}."

        return int(self.text(label, default=str(default), validate=validate))

    def choose(
        self,
        label: str,
        choices: Sequence[Choice],
        *,
        default: int = 0,
    ) -> str:
        if not choices:
            raise ValueError("Wizard choices must not be empty")
        if default < 0 or default >= len(choices):
            raise ValueError("Wizard default choice is out of range")
        print(f"{label}:", file=self.output)
        for index, choice in enumerate(choices, start=1):
            marker = " (recommended)" if index - 1 == default else ""
            number = self._paint(f"{index}.", "cyan")
            recommendation = self._paint(marker, "green")
            print(f"  {number} {choice.label}{recommendation}", file=self.output)
            if choice.detail:
                print(f"     {self._paint(choice.detail, 'dim')}", file=self.output)
        while True:
            answer = self._read(f"Select [{default + 1}]: ").strip()
            if not answer:
                return choices[default].value
            if answer.isdigit() and 1 <= int(answer) <= len(choices):
                return choices[int(answer) - 1].value
            by_value = {choice.value.lower(): choice.value for choice in choices}
            if answer.lower() in by_value:
                return by_value[answer.lower()]
            print(f"  Choose a number from 1 to {len(choices)}.", file=self.output)

    def confirm(self, label: str, *, default: bool = True) -> bool:
        suffix = "Y/n" if default else "y/N"
        while True:
            answer = self._read(f"{label} [{suffix}]: ").strip().lower()
            if not answer:
                return default
            if answer in {"y", "yes"}:
                return True
            if answer in {"n", "no"}:
                return False
            print("  Enter yes or no.", file=self.output)

    def review(self, rows: Sequence[tuple[str, str]]) -> None:
        self.heading("Review")
        self.rows(rows)

    def _read(self, prompt: str) -> str:
        self.output.write(self._paint(prompt, "cyan"))
        self.output.flush()
        value = self.input.readline()
        if value == "":
            raise ValueError(f"{self.brand} input ended before the wizard completed")
        return value

    def _paint(self, value: str, style: str) -> str:
        if not self.color:
            return value
        codes = {
            "bold": "1",
            "dim": "2",
            "cyan": "36",
            "green": "32",
            "bold_cyan": "1;36",
            "bold_green": "1;32",
            "bold_yellow": "1;33",
        }
        return f"\x1b[{codes[style]}m{value}\x1b[0m"


def _supports_color(stream: TextIO) -> bool:
    if "NO_COLOR" in os.environ or os.environ.get("TERM", "") == "dumb":
        return False
    try:
        return stream.isatty()
    except (AttributeError, OSError):
        return False

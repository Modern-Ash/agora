"""Provider-neutral issue tracker reconciliation for Agora Core.

Core owns bindings, normalized snapshots, idempotency, and lifecycle consequences.  Provider
adapters only fetch native records and translate them into ``ExternalIssueSnapshot`` values.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from agora.filesystem import assert_slug, atomic_write, filesystem_transaction, write_new
from agora.markdown import (
    MarkdownDocument,
    optional_string_attribute,
    read_markdown,
    render_markdown,
    string_attribute,
    strings_attribute,
)
from agora.model import (
    BindIssueTrackerInput,
    ExternalIssueSnapshot,
    IssueTrackerBindingRecord,
    IssueTrackerSyncEventRecord,
    IssueTrackerSyncResult,
    SyncIssueTrackerInput,
)


class IssueTrackerPort(Protocol):
    """Exact provider boundary consumed by Core reconciliation."""

    @property
    def tracker(self) -> str: ...

    def fetch(self, project: str, external_ids: Sequence[str]) -> list[ExternalIssueSnapshot]: ...


ReopenCallback = Callable[[IssueTrackerBindingRecord, ExternalIssueSnapshot, str], int]


class IssueTrackerService:
    def __init__(
        self,
        root: Path,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.state = self.root / ".agora" / "issue-trackers"
        self._now = now or (lambda: datetime.now(UTC))

    def _timestamp(self) -> str:
        return self._now().astimezone(UTC).isoformat().replace("+00:00", "Z")

    def bind(self, data: BindIssueTrackerInput) -> IssueTrackerBindingRecord:
        assert_slug(data.id, "Issue tracker binding id")
        assert_slug(data.swarm_id, "Swarm id")
        assert_slug(data.work_id, "Work id")
        for value, label in (
            (data.tracker, "Issue tracker"),
            (data.project, "Issue tracker project"),
            (data.external_id, "External issue id"),
            (data.reopen_actor_id, "Reopen actor id"),
        ):
            if not value.strip():
                raise ValueError(f"{label} cannot be empty")
        duplicates = [
            item
            for item in self.list_bindings()
            if item.tracker == data.tracker.strip()
            and item.project == data.project.strip()
            and item.external_id == data.external_id.strip()
        ]
        if duplicates:
            raise ValueError(
                "External issue is already bound to work: "
                f"{duplicates[0].swarm_id}/{duplicates[0].work_id}"
            )
        path = self.state / "bindings" / data.id / "BINDING.md"
        record = IssueTrackerBindingRecord(
            id=data.id,
            swarm_id=data.swarm_id,
            work_id=data.work_id,
            tracker=data.tracker.strip(),
            project=data.project.strip(),
            external_id=data.external_id.strip(),
            reopen_actor_id=data.reopen_actor_id.strip(),
            created_at=self._timestamp(),
            path=str(path),
        )
        write_new(path, _render_binding(record))
        return record

    def list_bindings(
        self, *, tracker: str | None = None, project: str | None = None
    ) -> list[IssueTrackerBindingRecord]:
        records = [
            _load_binding(path) for path in sorted((self.state / "bindings").glob("*/BINDING.md"))
        ]
        return [
            item
            for item in records
            if (tracker is None or item.tracker == tracker)
            and (project is None or item.project == project)
        ]

    def list_events(self) -> list[IssueTrackerSyncEventRecord]:
        records = [_load_event(path) for path in sorted((self.state / "events").glob("*/EVENT.md"))]
        return sorted(records, key=lambda item: (item.created_at, item.id))

    def snapshot_for_binding(self, binding_id: str) -> ExternalIssueSnapshot | None:
        """Return the last normalized provider snapshot without exposing adapter details."""
        assert_slug(binding_id, "Issue tracker binding id")
        return self._load_snapshot(binding_id)

    def sync(
        self,
        data: SyncIssueTrackerInput,
        adapter: IssueTrackerPort,
        *,
        reopen: ReopenCallback,
    ) -> IssueTrackerSyncResult:
        tracker = data.tracker.strip()
        project = data.project.strip()
        if not tracker or not project:
            raise ValueError("Issue tracker and project cannot be empty")
        if adapter.tracker != tracker:
            raise ValueError(
                f"Issue tracker adapter {adapter.tracker} cannot synchronize {tracker}"
            )
        bindings = self.list_bindings(tracker=tracker, project=project)
        if len(bindings) > 100:
            raise ValueError("One issue tracker sync is limited to 100 bound issues")
        snapshots = adapter.fetch(project, [item.external_id for item in bindings])
        by_id = {item.external_id: item for item in snapshots}
        if len(by_id) != len(snapshots):
            raise ValueError("Issue tracker adapter returned duplicate issue ids")
        missing = sorted({item.external_id for item in bindings} - set(by_id))
        if missing:
            raise ValueError("Issue tracker adapter omitted bound issues: " + ", ".join(missing))

        events: list[IssueTrackerSyncEventRecord] = []
        reopened = 0
        unchanged = 0
        for binding in bindings:
            snapshot = by_id[binding.external_id]
            _assert_snapshot_identity(binding, snapshot)
            previous = self._load_snapshot(binding.id)
            change = _snapshot_change(previous, snapshot)
            event_key = (
                f"{tracker}:{project}:{binding.external_id}:"
                f"{snapshot.updated_at}:{snapshot.payload_sha256}"
            )
            revision = None
            if change == "reopened":
                revision = reopen(binding, snapshot, event_key)
                reopened += 1
            if change == "unchanged":
                unchanged += 1
            event = self._persist_snapshot_event(
                binding,
                previous,
                snapshot,
                change,
                event_key,
                revision,
            )
            events.append(event)
        return IssueTrackerSyncResult(
            tracker=tracker,
            project=project,
            bindings=len(bindings),
            changed=len(bindings) - unchanged,
            reopened=reopened,
            unchanged=unchanged,
            events=events,
        )

    def _load_snapshot(self, binding_id: str) -> ExternalIssueSnapshot | None:
        path = self.state / "snapshots" / binding_id / "SNAPSHOT.md"
        return _load_snapshot(path) if path.is_file() else None

    def _persist_snapshot_event(
        self,
        binding: IssueTrackerBindingRecord,
        previous: ExternalIssueSnapshot | None,
        snapshot: ExternalIssueSnapshot,
        change: str,
        event_key: str,
        revision: int | None,
    ) -> IssueTrackerSyncEventRecord:
        digest = hashlib.sha256(event_key.encode("utf-8")).hexdigest()
        event_id = f"event-{digest[:20]}"
        event_path = self.state / "events" / event_id / "EVENT.md"
        if event_path.is_file():
            existing = _load_event(event_path)
            if existing.payload_sha256 != snapshot.payload_sha256:
                raise ValueError("Issue sync event id was reused with a different payload")
            return existing
        event = IssueTrackerSyncEventRecord(
            id=event_id,
            binding_id=binding.id,
            tracker=binding.tracker,
            project=binding.project,
            external_id=binding.external_id,
            previous_state=previous.state if previous is not None else None,
            current_state=snapshot.state,
            change=change,  # type: ignore[arg-type]
            payload_sha256=snapshot.payload_sha256,
            work_revision=revision,
            created_at=self._timestamp(),
            path=str(event_path),
        )
        with filesystem_transaction():
            atomic_write(
                self.state / "snapshots" / binding.id / "SNAPSHOT.md",
                _render_snapshot(snapshot),
            )
            write_new(event_path, _render_event(event))
        return event


def snapshot_payload_sha256(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")
    ).hexdigest()


def _assert_snapshot_identity(
    binding: IssueTrackerBindingRecord, snapshot: ExternalIssueSnapshot
) -> None:
    actual = (snapshot.tracker, snapshot.project, snapshot.external_id)
    expected = (binding.tracker, binding.project, binding.external_id)
    if actual != expected:
        raise ValueError(
            "Issue tracker snapshot identity does not match binding: "
            f"expected {expected}, got {actual}"
        )
    if snapshot.state not in {"open", "closed"}:
        raise ValueError(f"Unsupported normalized issue state: {snapshot.state}")
    if re.fullmatch(r"[0-9a-f]{64}", snapshot.payload_sha256) is None:
        raise ValueError("Issue tracker snapshot requires a lowercase SHA-256")


def _snapshot_change(previous: ExternalIssueSnapshot | None, current: ExternalIssueSnapshot) -> str:
    if previous is None:
        return "created"
    if previous.payload_sha256 == current.payload_sha256:
        return "unchanged"
    if previous.state == "closed" and current.state == "open":
        return "reopened"
    if previous.state == "open" and current.state == "closed":
        return "closed"
    return "updated"


def _render_binding(record: IssueTrackerBindingRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/issue-tracker-binding/v1",
                "id": record.id,
                "swarm": record.swarm_id,
                "work": record.work_id,
                "tracker": record.tracker,
                "project": record.project,
                "external-id": record.external_id,
                "reopen-actor": record.reopen_actor_id,
                "created-at": record.created_at,
            },
            body=(
                f"# Issue binding {record.id}\n\n"
                "This provider-neutral binding connects one external issue to one Agora work item."
            ),
        )
    )


def _load_binding(path: Path) -> IssueTrackerBindingRecord:
    document = read_markdown(path)
    if string_attribute(document.attributes, "schema") != "agora/issue-tracker-binding/v1":
        raise ValueError(f"Unsupported issue tracker binding schema: {path}")
    return IssueTrackerBindingRecord(
        id=string_attribute(document.attributes, "id"),
        swarm_id=string_attribute(document.attributes, "swarm"),
        work_id=string_attribute(document.attributes, "work"),
        tracker=string_attribute(document.attributes, "tracker"),
        project=string_attribute(document.attributes, "project"),
        external_id=string_attribute(document.attributes, "external-id"),
        reopen_actor_id=string_attribute(document.attributes, "reopen-actor"),
        created_at=string_attribute(document.attributes, "created-at"),
        path=str(path),
    )


def _render_snapshot(record: ExternalIssueSnapshot) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/external-issue-snapshot/v1",
                "tracker": record.tracker,
                "project": record.project,
                "external-id": record.external_id,
                "title": record.title,
                "state": record.state,
                "url": record.url,
                "updated-at": record.updated_at,
                "author-subject": record.author_subject,
                "author-display-name": record.author_display_name,
                "labels": record.labels,
                "milestone": record.milestone,
                "comment-count": record.comment_count,
                "payload-sha256": record.payload_sha256,
            },
            body=f"# External issue {record.external_id}\n\nCurrent normalized tracker snapshot.",
        )
    )


def _load_snapshot(path: Path) -> ExternalIssueSnapshot:
    document = read_markdown(path)
    if string_attribute(document.attributes, "schema") != "agora/external-issue-snapshot/v1":
        raise ValueError(f"Unsupported external issue snapshot schema: {path}")
    comment_count = document.attributes.get("comment-count")
    if isinstance(comment_count, bool) or not isinstance(comment_count, int):
        raise ValueError(f"External issue comment count must be an integer: {path}")
    state = string_attribute(document.attributes, "state")
    if state not in {"open", "closed"}:
        raise ValueError(f"Unsupported normalized issue state: {state}")
    return ExternalIssueSnapshot(
        tracker=string_attribute(document.attributes, "tracker"),
        project=string_attribute(document.attributes, "project"),
        external_id=string_attribute(document.attributes, "external-id"),
        title=string_attribute(document.attributes, "title"),
        state=state,  # type: ignore[arg-type]
        url=string_attribute(document.attributes, "url"),
        updated_at=string_attribute(document.attributes, "updated-at"),
        author_subject=optional_string_attribute(document.attributes, "author-subject"),
        author_display_name=optional_string_attribute(document.attributes, "author-display-name"),
        labels=strings_attribute(document.attributes, "labels"),
        milestone=optional_string_attribute(document.attributes, "milestone"),
        comment_count=comment_count,
        payload_sha256=string_attribute(document.attributes, "payload-sha256"),
    )


def _render_event(record: IssueTrackerSyncEventRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/issue-tracker-sync-event/v1",
                "id": record.id,
                "binding": record.binding_id,
                "tracker": record.tracker,
                "project": record.project,
                "external-id": record.external_id,
                "previous-state": record.previous_state,
                "current-state": record.current_state,
                "change": record.change,
                "payload-sha256": record.payload_sha256,
                "work-revision": record.work_revision,
                "created-at": record.created_at,
            },
            body=(
                f"# Issue sync event {record.id}\n\n"
                "This immutable event records one normalized reconciliation result."
            ),
        )
    )


def _load_event(path: Path) -> IssueTrackerSyncEventRecord:
    document = read_markdown(path)
    if string_attribute(document.attributes, "schema") != "agora/issue-tracker-sync-event/v1":
        raise ValueError(f"Unsupported issue tracker sync event schema: {path}")
    previous = optional_string_attribute(document.attributes, "previous-state")
    current = string_attribute(document.attributes, "current-state")
    change = string_attribute(document.attributes, "change")
    if previous not in {None, "open", "closed"} or current not in {"open", "closed"}:
        raise ValueError(f"Unsupported issue tracker event state: {path}")
    if change not in {"created", "updated", "closed", "reopened", "unchanged"}:
        raise ValueError(f"Unsupported issue tracker event change: {path}")
    revision = document.attributes.get("work-revision")
    if revision is not None and (isinstance(revision, bool) or not isinstance(revision, int)):
        raise ValueError(f"Issue tracker work revision must be an integer: {path}")
    return IssueTrackerSyncEventRecord(
        id=string_attribute(document.attributes, "id"),
        binding_id=string_attribute(document.attributes, "binding"),
        tracker=string_attribute(document.attributes, "tracker"),
        project=string_attribute(document.attributes, "project"),
        external_id=string_attribute(document.attributes, "external-id"),
        previous_state=previous,  # type: ignore[arg-type]
        current_state=current,  # type: ignore[arg-type]
        change=change,  # type: ignore[arg-type]
        payload_sha256=string_attribute(document.attributes, "payload-sha256"),
        work_revision=revision,
        created_at=string_attribute(document.attributes, "created-at"),
        path=str(path),
    )

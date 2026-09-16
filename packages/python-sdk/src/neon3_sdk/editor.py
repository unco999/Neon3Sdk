"""Editor document APIs backing the NUI ``code_editor`` component
(``editor-runtime``, v0.2.10+).

The editor domain logic lives in the runtime's pure ``neon-editor-core``
(buffer, rule-table highlighting, undo/redo, completion). This module is the
host-side counterpart: open documents, apply change sets, commit revisions,
and request completions over the wire, mirroring the exact serde shapes of
``neon-editor-runtime``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from .client import NeonClient

#: The only editor language the runtime supports today.
EDITOR_LANGUAGE_NUI_FLOW = "nui_flow"

#: Mirrors ``MAX_CHANGESET_OPS`` in ``neon-editor-runtime``.
MAX_CHANGESET_OPS = 256
#: Mirrors ``MAX_INSERT_BYTES`` in ``neon-editor-runtime``.
MAX_INSERT_BYTES = 64 * 1024


@dataclass(frozen=True)
class EditorPosition:
    """A position in the document (line/column, both in ``char`` units)."""

    line: int = 0
    column: int = 0

    def to_wire(self) -> dict[str, int]:
        return {"line": self.line, "column": self.column}


@dataclass(frozen=True)
class EditorSelection:
    """An ordered selection range (``anchor`` -> ``active``)."""

    anchor: EditorPosition
    active: EditorPosition

    def to_wire(self) -> dict[str, Any]:
        return {"anchor": self.anchor.to_wire(), "active": self.active.to_wire()}

    @staticmethod
    def from_wire(payload: dict[str, Any]) -> "EditorSelection":
        return EditorSelection(
            anchor=EditorPosition(**payload["anchor"]),
            active=EditorPosition(**payload["active"]),
        )


@dataclass(frozen=True)
class EditOp:
    """One edit operation, tagged ``kind: insert | delete`` on the wire."""

    kind: str
    text: str
    line: int | None = None
    column: int | None = None
    end: EditorPosition | None = None
    start: EditorPosition | None = None

    @staticmethod
    def insert(line: int, column: int, end: EditorPosition, text: str) -> "EditOp":
        return EditOp("insert", text, line=line, column=column, end=end)

    @staticmethod
    def delete(start: EditorPosition, end: EditorPosition, text: str) -> "EditOp":
        return EditOp("delete", text, start=start, end=end)

    def to_wire(self) -> dict[str, Any]:
        if self.kind == "insert":
            return {"kind": "insert", "line": self.line, "column": self.column, "end": self.end.to_wire(), "text": self.text}
        if self.kind == "delete":
            return {"kind": "delete", "start": self.start.to_wire(), "end": self.end.to_wire(), "text": self.text}
        raise ValueError(f"invalid edit op kind: {self.kind!r}")


@dataclass(frozen=True)
class ChangeSet:
    """A host-side change set applied on top of ``base_revision``."""

    base_revision: int
    ops: tuple[EditOp, ...]

    def validate(self) -> None:
        """Local pre-flight matching the runtime limits
        (``editor_changeset_invalid`` / ``editor_change_set_overflow``):
        1..=256 ops, each insert at most 64 KiB of UTF-8."""
        if not 1 <= len(self.ops) <= MAX_CHANGESET_OPS:
            raise ValueError(f"change set must contain 1..={MAX_CHANGESET_OPS} ops, got {len(self.ops)}")
        for op in self.ops:
            if op.kind == "insert" and len(op.text.encode("utf-8")) > MAX_INSERT_BYTES:
                raise ValueError(f"single insert exceeds {MAX_INSERT_BYTES} bytes, got {len(op.text.encode('utf-8'))}")

    def to_wire(self) -> dict[str, Any]:
        self.validate()
        return {"base_revision": self.base_revision, "ops": [op.to_wire() for op in self.ops]}


@dataclass(frozen=True)
class EditorChangeKind:
    """Change application mode (``draft`` folds into the pending revision,
    ``commit`` also advances ``committed_revision``)."""

    value: str

    def as_wire(self) -> str:
        return self.value


EDITOR_CHANGE_DRAFT = EditorChangeKind("draft")
EDITOR_CHANGE_COMMIT = EditorChangeKind("commit")


@dataclass(frozen=True)
class CompletionTriggerKind:
    """Completion trigger (``automatic`` / ``invoked`` / ``trigger_character``)."""

    value: str

    def as_wire(self) -> str:
        return self.value


COMPLETION_AUTOMATIC = CompletionTriggerKind("automatic")
COMPLETION_INVOKED = CompletionTriggerKind("invoked")
COMPLETION_TRIGGER_CHARACTER = CompletionTriggerKind("trigger_character")


@dataclass(frozen=True)
class EditorSnapshot:
    """A document snapshot returned by every editor method."""

    document_id: str
    session_id: str
    language: str
    epoch: int
    revision: int
    committed_revision: int
    dirty: bool
    line_count: int
    byte_length: int
    source_hash: str
    source: str
    diagnostics: list[Any] = field(default_factory=list)

    @staticmethod
    def from_wire(payload: dict[str, Any]) -> "EditorSnapshot":
        return EditorSnapshot(
            document_id=payload["document_id"],
            session_id=payload["session_id"],
            language=payload["language"],
            epoch=int(payload["epoch"]),
            revision=int(payload["revision"]),
            committed_revision=int(payload["committed_revision"]),
            dirty=bool(payload["dirty"]),
            line_count=int(payload["line_count"]),
            byte_length=int(payload["byte_length"]),
            source_hash=payload["source_hash"],
            source=payload["source"],
            diagnostics=list(payload.get("diagnostics", [])),
        )


@dataclass(frozen=True)
class CompletionItem:
    """One completion candidate (mirrors ``neon_editor_core::CompletionItem``)."""

    item_id: str
    label: str
    insert_text: str
    replace_start: EditorPosition
    replace_end: EditorPosition
    kind: str
    detail: str
    sort_text: str
    source: str
    commit_characters: tuple[str, ...] = ()

    @staticmethod
    def from_wire(payload: dict[str, Any]) -> "CompletionItem":
        return CompletionItem(
            item_id=payload["item_id"],
            label=payload["label"],
            insert_text=payload["insert_text"],
            replace_start=EditorPosition(**payload["replace_start"]),
            replace_end=EditorPosition(**payload["replace_end"]),
            kind=payload["kind"],
            detail=payload["detail"],
            sort_text=payload["sort_text"],
            source=payload["source"],
            commit_characters=tuple(payload.get("commit_characters", [])),
        )


@dataclass(frozen=True)
class EditorCompletionResult:
    document_id: str
    document_revision: int
    position: EditorPosition
    items: tuple[CompletionItem, ...]

    @staticmethod
    def from_wire(payload: dict[str, Any]) -> "EditorCompletionResult":
        return EditorCompletionResult(
            document_id=payload["document_id"],
            document_revision=int(payload["document_revision"]),
            position=EditorPosition(**payload["position"]),
            items=tuple(CompletionItem.from_wire(item) for item in payload.get("items", [])),
        )


@dataclass(frozen=True)
class EditorOpenResult:
    """Freshly opened documents carry the initial snapshot; re-opening
    returns ``already_open`` without one."""

    state: str
    snapshot: EditorSnapshot | None

    @staticmethod
    def from_wire(payload: dict[str, Any]) -> "EditorOpenResult":
        return EditorOpenResult(
            state=payload["state"],
            snapshot=EditorSnapshot.from_wire(payload["snapshot"]) if payload.get("snapshot") else None,
        )


@dataclass(frozen=True)
class EditorOperationResult:
    state: str
    snapshot: EditorSnapshot
    applied_ops: int
    cursor: EditorPosition | None
    selection: EditorSelection | None

    @staticmethod
    def from_wire(payload: dict[str, Any]) -> "EditorOperationResult":
        return EditorOperationResult(
            state=payload["state"],
            snapshot=EditorSnapshot.from_wire(payload["snapshot"]),
            applied_ops=int(payload["applied_ops"]),
            cursor=EditorPosition(**payload["cursor"]) if payload.get("cursor") else None,
            selection=EditorSelection.from_wire(payload["selection"]) if payload.get("selection") else None,
        )


def _validate_identity(document_id: str, session_id: str) -> None:
    if not document_id or not document_id.strip():
        raise ValueError("document_id must be non-empty")
    if not session_id or not session_id.strip():
        raise ValueError("session_id must be non-empty")


class EditorClient:
    """High-level wrapper for the headless editor document service.

    ``target`` defaults to ``editor-runtime``; override only when the endpoint
    multiplexes services (e.g. the Android host).
    """

    def __init__(self, client: NeonClient, target: str = "editor-runtime") -> None:
        self.client = client
        self.target = target

    def open(
        self,
        document_id: str,
        session_id: str,
        source: str,
        language: str = EDITOR_LANGUAGE_NUI_FLOW,
        *,
        idempotency_key: str | None = None,
    ) -> EditorOpenResult:
        """Open a document (``editor.document.open``). The runtime requires an
        envelope-level idempotency key; one is generated when omitted."""
        _validate_identity(document_id, session_id)
        language = language or EDITOR_LANGUAGE_NUI_FLOW
        if language != EDITOR_LANGUAGE_NUI_FLOW:
            raise ValueError(f"unsupported editor language {language!r}; only {EDITOR_LANGUAGE_NUI_FLOW!r} is supported")
        key = idempotency_key or f"editor:open:{document_id}:{uuid.uuid4()}"
        response = self.client.call(
            self.target,
            "editor.document.open",
            {"document_id": document_id, "session_id": session_id, "language": language, "source": source},
            idempotency_key=key,
        )
        return EditorOpenResult.from_wire(response.result)

    def snapshot(self, document_id: str, session_id: str, epoch: int) -> EditorSnapshot:
        """Fetch the current snapshot (``editor.document.snapshot.get``)."""
        _validate_identity(document_id, session_id)
        response = self.client.call(
            self.target,
            "editor.document.snapshot.get",
            {"document_id": document_id, "session_id": session_id, "epoch": epoch},
        )
        return EditorSnapshot.from_wire(response.result)

    def apply_change(
        self,
        document_id: str,
        session_id: str,
        epoch: int,
        change_set: ChangeSet,
        kind: EditorChangeKind = EDITOR_CHANGE_DRAFT,
        *,
        cursor: EditorPosition | None = None,
        selection: EditorSelection | None = None,
        idempotency_key: str | None = None,
    ) -> EditorOperationResult:
        """Apply a change set (``editor.document.change.apply``). The runtime
        requires an idempotency key; one is generated when omitted.
        ``cursor`` / ``selection`` update the renderer's caret state."""
        _validate_identity(document_id, session_id)
        change_set.validate()
        params: dict[str, Any] = {
            "document_id": document_id,
            "session_id": session_id,
            "epoch": epoch,
            "change_set": change_set.to_wire(),
            "kind": kind.as_wire(),
        }
        if cursor is not None:
            params["cursor"] = cursor.to_wire()
        if selection is not None:
            params["selection"] = selection.to_wire()
        key = idempotency_key or f"editor:apply:{document_id}:{uuid.uuid4()}"
        response = self.client.call(self.target, "editor.document.change.apply", params, idempotency_key=key)
        return EditorOperationResult.from_wire(response.result)

    def commit(self, document_id: str, session_id: str, epoch: int, expected_revision: int) -> EditorSnapshot:
        """Commit the pending revision (``editor.document.change.commit``).
        The envelope carries ``expected_revision``; a stale revision is
        rejected with ``editor_revision_conflict``."""
        _validate_identity(document_id, session_id)
        response = self.client.call(
            self.target,
            "editor.document.change.commit",
            {"document_id": document_id, "session_id": session_id, "epoch": epoch},
            expected_revision=expected_revision,
            idempotency_key=f"editor:commit:{document_id}:{uuid.uuid4()}",
        )
        return EditorSnapshot.from_wire(response.result)

    def completions(
        self,
        document_id: str,
        session_id: str,
        epoch: int,
        document_revision: int,
        position: EditorPosition,
        trigger_kind: CompletionTriggerKind = COMPLETION_AUTOMATIC,
    ) -> EditorCompletionResult:
        """Request completion candidates at ``position``
        (``editor.completion.request``). A stale ``document_revision`` is
        rejected with ``editor_completion_stale``."""
        _validate_identity(document_id, session_id)
        response = self.client.call(
            self.target,
            "editor.completion.request",
            {
                "document_id": document_id,
                "session_id": session_id,
                "epoch": epoch,
                "document_revision": document_revision,
                "position": position.to_wire(),
                "trigger_kind": trigger_kind.as_wire(),
            },
        )
        return EditorCompletionResult.from_wire(response.result)

    def close(self, document_id: str, session_id: str, epoch: int, *, idempotency_key: str | None = None) -> Any:
        """Close a document (``editor.document.close``). The runtime requires
        an idempotency key; one is generated when omitted."""
        _validate_identity(document_id, session_id)
        key = idempotency_key or f"editor:close:{document_id}:{uuid.uuid4()}"
        response = self.client.call(
            self.target,
            "editor.document.close",
            {"document_id": document_id, "session_id": session_id, "epoch": epoch},
            idempotency_key=key,
        )
        return response.result

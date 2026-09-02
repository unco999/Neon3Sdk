"""Public UI flow and semantic event API."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .client import NeonClient
from .models import UiProgramRevisionInfo, UiSnapshot, UiTraceRecord


@dataclass(frozen=True)
class UiProgram:
    surface_id: str
    program_revision: UiProgramRevisionInfo
    input_schema: dict[str, Any]
    submission_result: Any = None
    slots: tuple[str, ...] = field(default=())

    @classmethod
    def from_submission(cls, result: dict[str, Any]) -> "UiProgram":
        schema = result["input_schema"]
        return cls(
            surface_id=result["surface_id"],
            program_revision=UiProgramRevisionInfo.from_wire(result["program_revision"]),
            input_schema=schema,
            submission_result=result,
            slots=tuple(slot["key"] for slot in schema.get("slots", [])),
        )


class UiClient:
    def __init__(self, client: NeonClient, target: str = "ui-runtime") -> None:
        self.client = client
        self.target = target
        self.active: UiProgram | None = None

    def submit_flow(self, source: str, *, idempotency_key: str | None = None) -> UiProgram:
        result = self.client.call(self.target, "ui.flow.submit", {"source": source}, idempotency_key=idempotency_key or f"ui-flow:{uuid.uuid4()}").result
        if not isinstance(result, dict):
            raise ValueError("ui.flow.submit returned an invalid result")
        self.active = UiProgram.from_submission(result)
        return self.active

    def submit_flow_file(self, path: str | Path, **kwargs: Any) -> UiProgram:
        return self.submit_flow(Path(path).read_text(encoding="utf-8"), **kwargs)

    def host_inbound(self, event: dict[str, Any], *, idempotency_key: str | None = None) -> Any:
        return self.client.call(self.target, "ui.host.inbound", event, idempotency_key=idempotency_key or f"ui-host:{uuid.uuid4()}").result

    def apply_input(self, program_revision: dict[str, Any], expected_input_revision: int, changes: list[dict[str, Any]], *, request_id: str | None = None, idempotency_key: str | None = None) -> Any:
        """Publish a typed external input frame to the active UI program."""
        frame = {"program_revision": program_revision, "expected_input_revision": expected_input_revision, "request_id": request_id or str(uuid.uuid4()), "idempotency_key": idempotency_key or f"ui-input:{uuid.uuid4()}", "changes": changes}
        return self.client.call(self.target, "ui.input.frame", frame, request_id=frame["request_id"], idempotency_key=frame["idempotency_key"]).result

    def snapshot(self) -> UiSnapshot:
        """Typed pair of the service debug snapshot and the host input state."""
        service = self.client.call(self.target, "debug.snapshot.get").result
        if not isinstance(service, dict):
            raise ValueError("debug.snapshot.get returned an invalid result")
        host = self.client.call(self.target, "debug.ui.host.snapshot", raise_for_status=False).result
        return UiSnapshot.from_wire(service, host if isinstance(host, dict) else None)

    def traces(self, request_id: str | None = None, event_id: str | None = None) -> tuple[UiTraceRecord, ...]:
        params: dict[str, Any] = {}
        if request_id:
            params["request_id"] = request_id
        if event_id:
            params["event_id"] = event_id
        result = self.client.call(self.target, "debug.trace.query", params).result
        if not isinstance(result, list):
            raise ValueError("debug.trace.query returned an invalid result")
        return tuple(UiTraceRecord.from_wire(record) for record in result if isinstance(record, dict))

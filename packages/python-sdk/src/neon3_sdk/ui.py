"""Public UI flow and semantic event API."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import NeonClient


@dataclass(frozen=True)
class UiProgram:
    surface_id: str
    program_revision: dict[str, Any]
    input_schema: dict[str, Any]
    submission_result: Any


class UiClient:
    def __init__(self, client: NeonClient, target: str = "ui-runtime") -> None:
        self.client = client
        self.target = target
        self.active: UiProgram | None = None

    def submit_flow(self, source: str, *, idempotency_key: str | None = None) -> UiProgram:
        result = self.client.call(self.target, "ui.flow.submit", {"source": source}, idempotency_key=idempotency_key or f"ui-flow:{uuid.uuid4()}").result
        if not isinstance(result, dict):
            raise ValueError("ui.flow.submit returned an invalid result")
        self.active = UiProgram(result["surface_id"], result["program_revision"], result["input_schema"], result)
        return self.active

    def submit_flow_file(self, path: str | Path, **kwargs: Any) -> UiProgram:
        return self.submit_flow(Path(path).read_text(encoding="utf-8"), **kwargs)

    def host_inbound(self, event: dict[str, Any], *, idempotency_key: str | None = None) -> Any:
        return self.client.call(self.target, "ui.host.inbound", event, idempotency_key=idempotency_key or f"ui-host:{uuid.uuid4()}").result

    def apply_input(self, program_revision: dict[str, Any], expected_input_revision: int, changes: list[dict[str, Any]], *, request_id: str | None = None, idempotency_key: str | None = None) -> Any:
        """Publish a typed external input frame to the active UI program."""
        frame = {"program_revision": program_revision, "expected_input_revision": expected_input_revision, "request_id": request_id or str(uuid.uuid4()), "idempotency_key": idempotency_key or f"ui-input:{uuid.uuid4()}", "changes": changes}
        return self.client.call(self.target, "ui.input.frame", frame, request_id=frame["request_id"], idempotency_key=frame["idempotency_key"]).result

    def snapshot(self) -> Any:
        return self.client.call(self.target, "debug.snapshot.get").result

    def traces(self, request_id: str | None = None) -> Any:
        params = {"request_id": request_id} if request_id else {}
        return self.client.call(self.target, "debug.trace.query", params).result

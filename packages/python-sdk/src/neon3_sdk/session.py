"""Revision-aware UI session: automatic program/input revision management.

``UiSession`` owns the active :class:`~neon3_sdk.ui.UiProgram`, the current
:class:`~neon3_sdk.models.RevisionState`, interaction sequencing and
idempotency identity, so business code never hand-writes ``program_revision``,
``input_revision``, ``idempotency_key`` or raw semantic envelopes.

Authoritative field provenance (docs/sdk-wire-contract.md §6.3):

- ``renderer_epoch`` comes only from the ui-runtime ``service.describe``
  response (the host adapter is activated against that epoch).
- ``input_revision`` comes only from runtime-observed results:
  ``ui.host.inbound`` accepted ``result.input_revision``, the external
  ``ui.input.frame`` accepted ``result.input.snapshot.scalar_inputs
  .input_revision``, or a ``debug.ui.host.snapshot`` refresh. The RPC
  ``revision`` envelope field is the *fragment* revision and is never used as
  input revision. When a result carries no input revision (async host
  forwards), the session falls back to ``+1`` and re-synchronizes on the first
  stale rejection via one snapshot refresh.
- ``frame_sequence`` is only ever observed, never invented.

Replays of the same ``event_id`` / ``request_id`` short-circuit on a local
ledger; runtime-side duplicate responses are surfaced as
``status="duplicate"``, not raised.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import RemoteError, StaleRevisionError
from .models import RevisionState
from .ui import UiClient, UiProgram


@dataclass(frozen=True)
class IntentResult:
    """Outcome of one dispatched semantic intent."""

    event_id: str
    status: str  # accepted | rejected | duplicate
    input_revision: int
    result: Any = None
    code: str | None = None
    message: str = ""


def _walk(value: Any, *path: str) -> Any:
    current = value
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _observed_input_revision(method: str, result: Any) -> int | None:
    """Extract the authoritative new input revision from an accepted result.

    ``dispatch``: ``result.input_revision`` (sync host forward) or
    ``result.semantic_intent.accepted_input_revision`` (program-native router).
    ``publish``: ``result.input.snapshot.scalar_inputs.input_revision``.
    """
    if not isinstance(result, dict):
        return None
    if method == "publish":
        observed = _walk(result, "input", "snapshot", "scalar_inputs", "input_revision")
    else:
        observed = result.get("input_revision")
        if not isinstance(observed, int):
            observed = _walk(result, "semantic_intent", "accepted_input_revision")
    return observed if isinstance(observed, int) else None


class UiSession:
    """Holds the program + revision state and mediates all UI mutations."""

    def __init__(self, ui: UiClient) -> None:
        self.ui = ui
        self.program: UiProgram | None = None
        self.renderer_epoch: int | None = None
        self.input_revision = 0
        self.frame_sequence: int | None = None
        self.interaction_sequence = 0
        self._dispatched: dict[str, IntentResult] = {}
        self._published: dict[str, Any] = {}

    # ------------------------------------------------------------------ setup

    def _resolve_renderer_epoch(self, *, refresh: bool = False) -> int:
        epoch = self.ui.capabilities(refresh=refresh).epoch_of(self.ui.target)
        if epoch is None:
            epoch = self.ui.client.health(self.ui.target).epoch
        self.renderer_epoch = epoch
        return epoch

    def mount_flow(self, source: str, *, validate: bool = True, idempotency_key: str | None = None) -> UiProgram:
        """Submit a Flow, adopt it as the active program, and re-synchronize.

        A fresh program activates a fresh host adapter, so the session resets
        its local revision bookkeeping and then reads authoritative state via
        ``refresh()``.
        """
        program = self.ui.submit_flow(source, idempotency_key=idempotency_key, validate=validate)
        return self.adopt(program)

    def adopt(self, program: UiProgram, *, synchronize: bool = True) -> UiProgram:
        """Adopt an already-submitted program, resetting and re-synchronizing.

        Used by ``mount_flow`` and by hosts (NeonApp) that submit through a
        shared client and hand the program to the session. ``synchronize=False``
        skips the runtime refresh for offline/fixture adoption where no
        authoritative host snapshot exists yet.
        """
        self.program = program
        self.ui.active = program
        self.input_revision = 0
        self.frame_sequence = None
        self.interaction_sequence = 0
        self._dispatched.clear()
        self._published.clear()
        if synchronize:
            self._resolve_renderer_epoch(refresh=True)
            self.refresh()
        return program

    def mount_flow_file(self, path: str | Path, **kwargs: Any) -> UiProgram:
        return self.mount_flow(Path(path).read_text(encoding="utf-8"), **kwargs)

    # ------------------------------------------------------------- properties

    @property
    def revision_state(self) -> RevisionState:
        if self.program is None:
            raise RuntimeError("UiSession has no mounted program; call mount_flow first")
        return RevisionState(
            program_revision=self.program.program_revision.revision,
            input_revision=self.input_revision,
            renderer_epoch=self.renderer_epoch or 0,
            frame_sequence=self.frame_sequence,
        )

    @property
    def program_revision_wire(self) -> dict[str, Any]:
        if self.program is None:
            raise RuntimeError("UiSession has no mounted program; call mount_flow first")
        return self.program.program_revision.to_wire()

    # --------------------------------------------------------------- refresh

    def refresh(self) -> RevisionState:
        """Re-read authoritative revision state from the runtime host snapshot."""
        host = self.ui.client.call(self.ui.target, "debug.ui.host.snapshot", raise_for_status=False)
        if host.status == "accepted" and isinstance(host.result, dict):
            observed = _walk(host.result, "scalar_inputs", "input_revision")
            if isinstance(observed, int):
                self.input_revision = observed
        # Keep the renderer epoch fresh: a restarted service bumps it.
        self._resolve_renderer_epoch(refresh=True)
        return self.revision_state

    # -------------------------------------------------------------- dispatch

    def build_intent_event(
        self,
        intent: str,
        payload: dict[str, Any] | None = None,
        *,
        source_node_key: str = "sdk",
        kind: str = "activate",
        event_id: str | None = None,
        requested_value: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Assemble a canonical ``UiProgramSemanticEvent`` with live revisions.

        Exposed for diagnostics and Stage 008 probes; ``dispatch_intent`` is
        the normal entry point.
        """
        if self.program is None:
            raise RuntimeError("UiSession has no mounted program; call mount_flow first")
        resolved_id = event_id or str(uuid.uuid4())
        self.interaction_sequence += 1
        event: dict[str, Any] = {
            "event_id": resolved_id,
            "kind": kind,
            "intent": intent,
            "source_node_key": source_node_key,
            "payload": payload or {},
            "program_revision": self.program_revision_wire,
            "input_revision": self.input_revision,
            "request_id": resolved_id,
            "idempotency_key": f"intent:{resolved_id}",
            "interaction": {
                "interaction_id": resolved_id,
                "sequence": self.interaction_sequence,
                "renderer_epoch": self._resolve_renderer_epoch(),
            },
        }
        if requested_value is not None:
            event["requested_value"] = requested_value
        return event

    def dispatch_intent(
        self,
        intent: str,
        payload: dict[str, Any] | None = None,
        *,
        source_node_key: str = "sdk",
        kind: str = "activate",
        event_id: str | None = None,
        requested_value: dict[str, Any] | None = None,
    ) -> IntentResult:
        """Send one semantic intent with automatic revision and identity.

        Behavior:

        - Local replay of the same ``event_id`` returns the recorded result
          (``status="duplicate"``) without touching the runtime.
        - A stale rejection refreshes the session once, then raises
          :class:`StaleRevisionError` with ``refreshed=True``.
        - A runtime-level duplicate result is surfaced as
          ``status="duplicate"`` with ``code="duplicate_event"``.
        - Other rejections propagate as :class:`RemoteError` with the frozen
          ``sdk_code`` available on the instance.
        """
        resolved_id = event_id or str(uuid.uuid4())
        cached = self._dispatched.get(resolved_id)
        if cached is not None:
            return IntentResult(
                event_id=resolved_id,
                status="duplicate",
                input_revision=self.input_revision,
                result=cached.result,
                code="duplicate_event",
                message="replayed from session ledger",
            )

        event = self.build_intent_event(
            intent,
            payload,
            source_node_key=source_node_key,
            kind=kind,
            event_id=resolved_id,
            requested_value=requested_value,
        )
        response = self.ui.client.call(
            self.ui.target,
            "ui.host.inbound",
            {"kind": "semantic_intent", "event": event},
            request_id=event["request_id"],
            idempotency_key=event["idempotency_key"],
            raise_for_status=False,
        )
        if response.status != "accepted":
            error = response.error or {}
            remote = RemoteError(response.request_id, response.status, error)
            if remote.sdk_code == "stale_revision":
                previous = self.input_revision
                self.refresh()
                raise StaleRevisionError(
                    f"intent dispatch rejected as stale: {remote.message}",
                    expected=previous,
                    actual=self.input_revision,
                    refreshed=True,
                    runtime_code=remote.code,
                )
            raise remote

        result_payload = response.result
        status = "accepted"
        code: str | None = None
        message = ""
        inner = result_payload.get("semantic_intent") if isinstance(result_payload, dict) else None
        if isinstance(inner, dict) and inner.get("status") in {"accepted", "rejected", "duplicate"}:
            # Program-native semantic event result envelope.
            status = str(inner["status"])
            code = inner.get("code") or None
            message = str(inner.get("message", ""))
            accepted = inner.get("accepted_input_revision")
            if isinstance(accepted, int) and accepted > self.input_revision:
                self.input_revision = accepted
        observed = _observed_input_revision("dispatch", result_payload)
        if observed is not None and observed > self.input_revision:
            self.input_revision = observed
        elif observed is None and status == "accepted":
            # Async host forward ack: the publication applies later; assume the
            # single step and let the first stale rejection re-synchronize.
            self.input_revision += 1
        result = IntentResult(
            event_id=resolved_id,
            status=status,
            input_revision=self.input_revision,
            result=result_payload,
            code=code or ("duplicate_event" if status == "duplicate" else None),
            message=message,
        )
        self._dispatched[resolved_id] = result
        return result

    # --------------------------------------------------------------- publish

    def publish(self, scalar_changes: list[dict[str, Any]], *, request_id: str | None = None) -> Any:
        """Apply an external scalar input frame with automatic revision.

        Builds ``ui.input.frame`` params (closed ``UiInputFrame`` schema — grid
        windows travel inside host publications, not external frames). An
        accepted frame advances ``input_revision`` to the observed value, or
        by one when the runtime does not echo it. A stale rejection refreshes
        once and retries with the current revision; a second stale rejection
        raises :class:`StaleRevisionError`. Replays of the same ``request_id``
        return the recorded result without re-applying.
        """
        if self.program is None:
            raise RuntimeError("UiSession has no mounted program; call mount_flow first")
        frame_id = request_id or str(uuid.uuid4())
        if frame_id in self._published:
            return self._published[frame_id]

        def build_frame(expected_revision: int) -> dict[str, Any]:
            return {
                "program_revision": self.program_revision_wire,
                "expected_input_revision": expected_revision,
                "request_id": frame_id,
                "idempotency_key": f"input:{frame_id}",
                "changes": scalar_changes,
            }

        attempt = build_frame(self.input_revision)
        response = self.ui.client.call(
            self.ui.target,
            "ui.input.frame",
            attempt,
            request_id=frame_id,
            idempotency_key=attempt["idempotency_key"],
            raise_for_status=False,
        )
        if response.status != "accepted":
            error = response.error or {}
            remote = RemoteError(response.request_id, response.status, error)
            if remote.sdk_code != "stale_revision":
                raise remote
            previous = self.input_revision
            self.refresh()
            retry = build_frame(self.input_revision)
            response = self.ui.client.call(
                self.ui.target,
                "ui.input.frame",
                retry,
                request_id=frame_id,
                idempotency_key=retry["idempotency_key"],
                raise_for_status=False,
            )
            if response.status != "accepted":
                second_error = response.error or {}
                self.refresh()
                raise StaleRevisionError(
                    f"publication still rejected after one refresh: {second_error.get('message', '')}",
                    expected=previous,
                    actual=self.input_revision,
                    refreshed=True,
                    runtime_code=str(second_error.get("code", "")),
                )

        observed = _observed_input_revision("publish", response.result)
        if observed is not None and observed > self.input_revision:
            self.input_revision = observed
        else:
            self.input_revision += 1
        self._published[frame_id] = response.result
        return response.result

    def flush(self) -> RevisionState:
        """Observe the current session revision state (post batched changes)."""
        return self.revision_state

    # --------------------------------------------------------- advanced raw

    def raw_host_inbound(self, inbound: dict[str, Any], *, idempotency_key: str | None = None) -> Any:
        """**Advanced.** Forward an unmanaged host inbound envelope.

        The session does not track revisions for raw calls; callers own every
        identity and revision field.
        """
        return self.ui.host_inbound(inbound, idempotency_key=idempotency_key)

    def raw_apply_input(self, frame: dict[str, Any], *, request_id: str | None = None, idempotency_key: str | None = None) -> Any:
        """**Advanced.** Send a fully-specified ``ui.input.frame`` envelope."""
        return self.ui.client.call(
            self.ui.target,
            "ui.input.frame",
            frame,
            request_id=request_id or frame.get("request_id"),
            idempotency_key=idempotency_key or frame.get("idempotency_key"),
        ).result

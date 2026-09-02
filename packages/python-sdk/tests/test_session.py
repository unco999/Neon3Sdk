"""Stage 003 revision-aware UiSession tests against an in-memory fake runtime.

The fake mirrors the frozen wire contract: accepted ``ui.input.frame`` echoes
the new input revision under ``result.input.snapshot...``, host inbound echoes
it under ``result.input_revision``, a stale frame is rejected with
``ui_program_stale_input_revision`` and exposes the current revision via a
host-snapshot refresh, and duplicate event ids are surfaced as duplicate
results.
"""

from __future__ import annotations

import unittest

from neon3_sdk.errors import RemoteError, StaleRevisionError
from neon3_sdk.models import RpcResponse, UiProgramRevisionInfo
from neon3_sdk.session import UiSession
from neon3_sdk.ui import UiProgram


class FakeRuntime:
    """Minimal authoritative host: single program, monotonic input revision."""

    def __init__(self) -> None:
        self.epoch = 4
        self.program_revision = {"program_id": "demo", "revision": 1, "schema_version": 1, "capabilities": []}
        self.input_revision = 0
        self.seen_idempotency: dict[str, dict] = {}
        self.frame_requests: list[int] = []
        self.host_requests: list[int] = []
        self.applied_event_ids: set[str] = set()
        self.publish_stuck = False

    def describe(self, target: str):
        class _D:
            service = target
            epoch = self.epoch
            capabilities: tuple = ()
        return _D()

    def health(self, target: str):
        class _H:
            epoch = self.epoch
            status = "healthy"
        return _H()

    def call(self, target, method, params=None, *, request_id=None, idempotency_key=None, raise_for_status=True):
        params = params or {}
        if method == "debug.ui.host.snapshot":
            snapshot = {"scalar_inputs": {"input_revision": self.input_revision, "program_revision": self.program_revision, "values": {}, "changed_slots": []}, "grid_inputs": []}
            return self._response(request_id, "accepted", result=snapshot)
        if method == "ui.input.frame":
            return self._apply_frame(params, request_id, idempotency_key)
        if method == "ui.host.inbound":
            return self._inbound(params, request_id, idempotency_key)
        raise AssertionError(f"unexpected method {method}")

    def _apply_frame(self, frame, request_id, idempotency_key):
        self.frame_requests.append(frame["expected_input_revision"])
        if idempotency_key in self.seen_idempotency:
            return self._response(request_id, **self.seen_idempotency[idempotency_key])
        if self.publish_stuck or frame["expected_input_revision"] != self.input_revision:
            return self._rejected(request_id, "ui_program_stale_input_revision", "input revision is stale")
        self.input_revision += 1
        result = {"input": {"snapshot": {"scalar_inputs": {"input_revision": self.input_revision}}}}
        self.seen_idempotency[idempotency_key] = {"status": "accepted", "revision": self.input_revision, "result": result}
        return self._response(request_id, "accepted", revision=self.input_revision, result=result)

    def _inbound(self, inbound, request_id, idempotency_key):
        event = inbound["event"]
        self.host_requests.append(event["input_revision"])
        event_id = event["event_id"]
        if event_id in self.applied_event_ids:
            return self._response(request_id, "accepted", revision=self.input_revision, result={"semantic_intent": {"status": "duplicate", "event_id": event_id, "accepted_input_revision": self.input_revision, "message": "seen"}})
        if idempotency_key in self.seen_idempotency:
            return self._response(request_id, **self.seen_idempotency[idempotency_key])
        if event["input_revision"] != self.input_revision:
            return self._rejected(request_id, "ui_host_stale_semantic_intent", "semantic intent revision is stale")
        self.input_revision += 1
        self.applied_event_ids.add(event_id)
        result = {"input_revision": self.input_revision, "semantic_intent": {"status": "accepted", "event_id": event_id, "message": "ok", "accepted_input_revision": self.input_revision}}
        self.seen_idempotency[idempotency_key] = {"status": "accepted", "revision": self.input_revision, "result": result}
        return self._response(request_id, "accepted", revision=self.input_revision, result=result)

    def _response(self, request_id, status, *, revision=None, result=None, error=None):
        return RpcResponse(request_id or "req", status, revision, result, None, error)

    def _rejected(self, request_id, code, message):
        return self._response(request_id, "rejected", revision=self.input_revision, error={"code": code, "message": message})


class FakeUi:
    """An object shaped like the UiClient dependencies UiSession relies on."""

    target = "ui-runtime"

    def __init__(self, runtime: FakeRuntime) -> None:
        self.client = runtime
        self.active: UiProgram | None = None
        self._caps = None

    def capabilities(self, *, refresh: bool = False):
        from neon3_sdk.capabilities import CapabilitySet
        if self._caps is None or refresh:
            self._caps = CapabilitySet(services=("ui-runtime",), capabilities=frozenset(), epochs=(self.client.epoch,))
        return self._caps

    def host_inbound(self, event, *, idempotency_key=None):
        return self.client.call(self.target, "ui.host.inbound", event, idempotency_key=idempotency_key).result


def _mounted_session(runtime: FakeRuntime) -> UiSession:
    ui = FakeUi(runtime)
    session = UiSession(ui)
    session.program = UiProgram(
        surface_id="surface.demo",
        program_revision=UiProgramRevisionInfo(program_id="demo", revision=1, schema_version=1, capabilities=()),
        input_schema={"schema_id": "demo", "version": 1, "slots": [], "layout_hash": "x"},
        submission_result=None,
    )
    return session


class UiSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = FakeRuntime()
        self.session = _mounted_session(self.runtime)

    def test_input_revision_strictly_increases_over_100_dispatches(self) -> None:
        revisions = [self.session.dispatch_intent("demo.ping", source_node_key="row").input_revision for _ in range(100)]
        self.assertEqual(revisions, list(range(1, 101)))
        self.assertEqual(self.session.input_revision, 100)

    def test_publish_advances_revision_to_observed_value(self) -> None:
        self.session.publish([{"key": "count", "value": {"kind": "i32", "value": 1}}])
        self.assertEqual(self.session.input_revision, 1)
        self.session.publish([{"key": "count", "value": {"kind": "i32", "value": 2}}])
        self.assertEqual(self.session.input_revision, 2)

    def test_duplicate_event_id_does_not_reapply(self) -> None:
        before = self.session.dispatch_intent("demo.save", source_node_key="row", event_id="evt-fixed")
        after = self.session.dispatch_intent("demo.save", source_node_key="row", event_id="evt-fixed")
        self.assertEqual(before.status, "accepted")
        self.assertEqual(after.status, "duplicate")
        self.assertEqual(self.session.input_revision, 1)
        self.assertEqual(self.runtime.input_revision, 1)

    def test_duplicate_publish_returns_ledger_without_reapplying(self) -> None:
        self.session.publish([{"key": "a", "value": {"kind": "i32", "value": 1}}], request_id="req-pub")
        self.session.publish([{"key": "a", "value": {"kind": "i32", "value": 2}}], request_id="req-pub")
        self.assertEqual(self.session.input_revision, 1)
        self.assertEqual(len(self.runtime.frame_requests), 1)

    def test_runtime_level_duplicate_is_surfaced_not_raised(self) -> None:
        self.session.dispatch_intent("demo.x", event_id="evt-dup", source_node_key="row")
        self.session._dispatched.clear()  # simulate a fresh session over a warm runtime
        result = self.session.dispatch_intent("demo.x", event_id="evt-dup", source_node_key="row")
        self.assertEqual(result.status, "duplicate")
        self.assertEqual(result.code, "duplicate_event")

    def test_stale_publish_refreshes_once_then_succeeds(self) -> None:
        self.runtime.input_revision = 3  # advanced out of band
        self.session.input_revision = 0
        self.session.publish([{"key": "a", "value": {"kind": "i32", "value": 1}}], request_id="req-stale")
        self.assertEqual(self.session.input_revision, 4)

    def test_persistent_stale_raises_typed_error(self) -> None:
        self.runtime.publish_stuck = True
        with self.assertRaises(StaleRevisionError) as caught:
            self.session.publish([{"key": "a", "value": {"kind": "i32", "value": 1}}], request_id="req-stuck")
        self.assertTrue(caught.exception.refreshed)
        self.assertEqual(caught.exception.runtime_code, "ui_program_stale_input_revision")

    def test_stale_dispatch_distinguishes_unknown_target(self) -> None:
        self.runtime._inbound = lambda inbound, request_id, idempotency_key: self.runtime._rejected(  # type: ignore[method-assign]
            request_id, "ui_host_invalid_drag_drop", "drop key is not declared")
        with self.assertRaises(RemoteError) as caught:
            self.session.dispatch_intent("demo.drop", event_id="evt-t", source_node_key="row")
        self.assertEqual(caught.exception.sdk_code, "unknown_target")

    def test_stale_dispatch_refreshes_and_raises_with_refresh_flag(self) -> None:
        self.runtime.input_revision = 7  # session will send 0 -> stale, refresh reads 7
        self.session.input_revision = 0
        with self.assertRaises(StaleRevisionError) as caught:
            self.session.dispatch_intent("demo.ping", event_id="evt-s1", source_node_key="row")
        self.assertTrue(caught.exception.refreshed)
        self.assertEqual(self.session.input_revision, 7)

    def test_build_intent_event_embeds_revision_and_epoch(self) -> None:
        event = self.session.build_intent_event("demo.ping", {"k": {"kind": "i32", "value": 1}}, source_node_key="row")
        self.assertEqual(event["program_revision"]["program_id"], "demo")
        self.assertEqual(event["input_revision"], 0)
        self.assertEqual(event["interaction"]["renderer_epoch"], self.runtime.epoch)
        self.assertTrue(event["idempotency_key"].startswith("intent:"))


if __name__ == "__main__":
    unittest.main()

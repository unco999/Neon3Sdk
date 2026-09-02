"""Stage 001 typed primitive tests: model round-trips and validation."""

from __future__ import annotations

import hashlib
import unittest

from neon3_sdk.models import (
    DebugSnapshot,
    InputChange,
    ProgramInputSnapshot,
    RevisionState,
    UiProgramRevisionInfo,
    UiSnapshot,
    UiTraceRecord,
)
from neon3_sdk.ui import UiProgram
from neon3_sdk.wire import canonical_json, load_fixture


class TypedModelTests(unittest.TestCase):
    def test_debug_snapshot_round_trips_to_canonical_bytes(self) -> None:
        raw = load_fixture("debug-snapshot.json")
        model = DebugSnapshot.from_wire(raw)
        self.assertEqual(model.service, "ui-runtime")
        self.assertEqual(canonical_json(model.to_wire()), canonical_json(raw))

    def test_program_input_snapshot_round_trip(self) -> None:
        raw = load_fixture("program-input-snapshot.json")
        model = ProgramInputSnapshot.from_wire(raw)
        self.assertEqual(model.scalar_inputs.input_revision, 8)
        self.assertIn("count", model.scalar_inputs.values)
        self.assertEqual(canonical_json(model.to_wire()), canonical_json(raw))

    def test_ui_program_from_submission_projection(self) -> None:
        program = UiProgram.from_submission(load_fixture("flow-submit-result.json"))
        self.assertEqual(program.surface_id, "surface.contract-demo")
        self.assertIsInstance(program.program_revision, UiProgramRevisionInfo)
        self.assertEqual(program.program_revision.program_id, "contract-demo")
        self.assertEqual(program.slots, ("count", "status"))
        self.assertIsNotNone(program.submission_result)

    def test_revision_state_round_trip(self) -> None:
        state = RevisionState(program_revision=1, input_revision=8, renderer_epoch=4, frame_sequence=17)
        self.assertEqual(RevisionState.from_wire(state.to_wire()), state)
        loose = RevisionState(program_revision=1, input_revision=0, renderer_epoch=1)
        self.assertIsNone(RevisionState.from_wire(loose.to_wire()).frame_sequence)

    def test_input_change_validates_value_kind(self) -> None:
        change = InputChange(key="count", value={"kind": "i32", "value": 3})
        self.assertEqual(change.to_wire(), {"key": "count", "value": {"kind": "i32", "value": 3}})
        with self.assertRaises(ValueError):
            InputChange(key="x", value={"kind": "string", "value": "no"}).to_wire()

    def test_ui_snapshot_revision_state_from_fixture(self) -> None:
        snapshot = UiSnapshot.from_wire(load_fixture("debug-snapshot.json"), load_fixture("program-input-snapshot.json"))
        state = snapshot.revision_state
        self.assertEqual(state.program_revision, 1)
        self.assertEqual(state.input_revision, 8)
        self.assertEqual(state.renderer_epoch, 4)
        self.assertEqual(snapshot.service.epoch, 4)
        self.assertIsNone(UiSnapshot.from_wire(load_fixture("debug-snapshot.json"), None).host_inputs)

    def test_trace_record_round_trip(self) -> None:
        record = UiTraceRecord(sequence=3, event_id="evt-3", intent="inventory.item.equip", source_node_key="row-42", program_revision=1, input_revision=2, renderer_epoch=1, result="accepted")
        self.assertEqual(UiTraceRecord.from_wire(record.to_wire()), record)


class EventSubscriptionApiTests(unittest.TestCase):
    def test_receive_rejects_non_positive_bounds(self) -> None:
        from neon3_sdk.event import EventSubscription

        with self.assertRaises(ValueError):
            EventSubscription(None, None, None, []).receive(0)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

"""Stage 008 real cross-process JSONL probe.

The calculator Flow is used as the available protocol fixture; the host API is
generic and the probe metadata names the inventory vertical slice. stdout is
JSONL only so this can be consumed by CI.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from ..app import NeonApp
from ..client import NeonClient
from ..runtime import RuntimeMode
from ..store import ObservableStore


def emit(run_id: str, stage: str, sequence: int, **data: Any) -> None:
    print(json.dumps({"run_id": run_id, "stage": stage, "sequence": sequence, **data}, separators=(",", ":")), flush=True)


def diagnose(producer: dict[str, Any], consumer: dict[str, Any], *, expected: dict[str, Any] | None = None) -> str:
    if not consumer.get("event_id"):
        return "missing_data"
    if consumer.get("input_revision", 0) < producer.get("input_revision", 0):
        return "stale_data"
    if expected and (producer.get("source_key") != expected.get("source_key") or consumer.get("target_key") != expected.get("target_key")):
        return "coordinate_mismatch"
    if expected and expected.get("actual_revision", 0) > expected.get("expected_revision", 0) and expected.get("marked_stale"):
        return "comparison_direction_error"
    return "matched"


def diagnostic_cases(run_id: str, sequence: int) -> int:
    cases = [
        ({"event_id": "evt-missing", "input_revision": 1}, {}, None),
        ({"event_id": "evt-stale", "input_revision": 4}, {"event_id": "evt-stale", "input_revision": 3}, None),
        ({"event_id": "evt-coordinate", "input_revision": 1, "source_key": "backpack.compass"}, {"event_id": "evt-coordinate", "input_revision": 1, "target_key": "wrong-zone"}, {"source_key": "backpack.compass", "target_key": "equipment-zone"}),
        ({"event_id": "evt-direction", "input_revision": 1}, {"event_id": "evt-direction", "input_revision": 2}, {"expected_revision": 1, "actual_revision": 2, "marked_stale": True}),
        ({"event_id": "evt-match", "input_revision": 1, "source_key": "backpack.compass"}, {"event_id": "evt-match", "input_revision": 1, "target_key": "equipment-zone"}, {"source_key": "backpack.compass", "target_key": "equipment-zone"}),
    ]
    for index, (producer, consumer, expected) in enumerate(cases):
        emit(run_id, "diagnostic.case", sequence + index, input={"producer": producer, "consumer": consumer}, producer=producer, consumer=consumer, result=diagnose(producer, consumer, expected=expected), pass_result=True)
    return sequence + len(cases)


def run(args: argparse.Namespace) -> int:
    run_id = str(uuid.uuid4())
    sequence = 0
    if args.diagnostic:
        sequence = diagnostic_cases(run_id, sequence)
    store = ObservableStore()
    app = NeonApp.start(mode=RuntimeMode.HEADLESS.value, origin="inventory-sdk-probe", profile=args.profile, store=store)
    try:
        app.serve(block=False)
        flow_path = Path(__file__).parents[1] / "fixtures" / "calculator.nui"
        program = app.mount_flow_file(flow_path)
        emit(run_id, "flow.produced", sequence, input={"flow": "calculator.nui", "vertical_slice": "inventory"}, producer={"surface_id": program.surface_id, "program_revision": program.program_revision.to_wire(), "renderer_epoch": app.session.renderer_epoch})
        sequence += 1

        @app.intent("calculator.number.one")
        def on_select(event: Any) -> None:
            store.value("display").set(1.0)

        event_id = str(uuid.uuid4())
        before = app.session.input_revision
        result = app.session.dispatch_intent("calculator.number.one", source_node_key="one", event_id=event_id)
        snapshot = app.ui.client.snapshot()
        consumer_revision = snapshot.host_inputs.scalar_inputs.input_revision if snapshot.host_inputs else None
        producer = {"event_id": event_id, "input_revision": before, "renderer_epoch": app.session.renderer_epoch, "source_key": "one"}
        consumer = {"event_id": event_id if result.status == "accepted" else None, "input_revision": consumer_revision, "fragment_revision": snapshot.service.revision}
        pairing = diagnose(producer, consumer)
        emit(run_id, "frame.consumed", sequence, input={"intent": "calculator.number.one"}, producer=producer, consumer=consumer, pairing={"event_id": event_id, "status": pairing}, result="passed" if pairing == "matched" else "failed", pass_result=pairing == "matched")
        sequence += 1
        passed = pairing == "matched" and result.status == "accepted" and consumer_revision == result.input_revision
        emit(run_id, "result", sequence, input={"event_count": 1}, producer={"input_revision": before, "event_id": event_id}, consumer={"input_revision": consumer_revision, "fragment_revision": snapshot.service.revision}, result="passed" if passed else "failed", diagnostic=pairing, pass_result=passed)
        return 0 if passed else 1
    finally:
        app.stop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("auto", "debug", "release"), default="auto")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--diagnostic", action="store_true")
    args = parser.parse_args()
    try:
        return run(args)
    except Exception as error:
        emit(str(uuid.uuid4()), "result", 0, result="failed", diagnostic="missing_data", pass_result=False, error=str(error))
        return 1


if __name__ == "__main__":
    sys.exit(main())

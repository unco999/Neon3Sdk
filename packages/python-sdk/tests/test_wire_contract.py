"""Stage 000 cross-language wire contract tests.

Parses every canonical fixture in ``docs/fixtures/wire``, validates the
frozen field sets, and pins the sha256 of canonical JSON output. The Node
suite pins the identical digest table, so a serializer drift on either side
fails both languages.
"""

from __future__ import annotations

import hashlib
import unittest

from neon3_sdk.wire import (
    CORE_ERROR_CODES,
    canonical_json,
    fixture_path,
    load_fixture,
    require_fields,
)

# digest -> canonical sha256, frozen with docs/sdk-wire-contract.md §3
CANONICAL_DIGESTS = {
    "debug-snapshot.json": "8cf8cfac8f2981f68f2a44b0097571a03d9b63c2946bc00144bdb9a4149deccd",
    "flow-submit-result.json": "63e30e58a6d53b22ab565706e7c41a3ff641f5918fe6591eadb7796f1c55dcef",
    "inbound-drag-drop.json": "18b19b05dfcb726d4856458a4a782fa50570e20e61e48cb190e223cf83f4f893",
    "inbound-semantic-intent.json": "57b6e53caa05b46c5f56a12040e0777649bca60fdad7fd1ba7df1064c8defd93",
    "input-frame.json": "ec7e0df1e0baad82b542aef91aeb44ed79f0d90b2082558f0852c0605983b737",
    "program-input-snapshot.json": "b7f9f5b40b43d1e499828758c6447d9424adbae892c65cfef0f1b18d874a81ec",
    "publication.json": "34ac4cbd83faca6f0fe9c68fe394414f36cd831abecde86a56d3559e2bcbeed3",
    "rpc-response-rejected-stale.json": "96484207781ec91ab23ae2101bbc8c85b4356775ab961547f390c89073936e48",
    "service-describe.json": "22526dd9bd3d4367af31e59f48c9772a9bf6e1af3e7b5ee9e9623008fbecabd9",
}


class WireContractFixtureTests(unittest.TestCase):
    def test_every_fixture_has_a_pinned_digest(self) -> None:
        from pathlib import Path

        names = sorted(p.name for p in Path(fixture_path("__probe__")).parent.glob("*.json"))
        self.assertEqual(names, sorted(CANONICAL_DIGESTS))

    def test_canonical_digests_match_frozen_table(self) -> None:
        for name, digest in CANONICAL_DIGESTS.items():
            with self.subTest(fixture=name):
                value = load_fixture(name)
                actual = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
                self.assertEqual(actual, digest)

    def test_rpc_envelope_is_closed(self) -> None:
        response = require_fields(
            load_fixture("rpc-response-rejected-stale.json"),
            ("request_id", "status", "revision", "result", "snapshot", "error"),
            (),
            "RpcResponse",
        )
        self.assertEqual(response["status"], "rejected")
        self.assertEqual(response["error"]["code"], "ui_program_stale_input_revision")

    def test_semantic_intent_event_fields(self) -> None:
        inbound = require_fields(load_fixture("inbound-semantic-intent.json"), ("kind", "event"), (), "UiHostInbound")
        self.assertEqual(inbound["kind"], "semantic_intent")
        event = require_fields(
            inbound["event"],
            (
                "event_id", "kind", "intent", "source_node_key", "payload",
                "program_revision", "input_revision", "request_id", "idempotency_key", "interaction",
            ),
            ("requested_value",),
            "UiProgramSemanticEvent",
        )
        self.assertEqual(event["kind"], "activate")
        require_fields(event["interaction"], ("interaction_id", "sequence", "renderer_epoch"), (), "UiSemanticInteractionMetadata")
        for key, value in event["payload"].items():
            self.assertIn(value["kind"], {"bool", "i32", "u32", "f32", "enum", "text_handle", "asset_handle"}, key)

    def test_drag_drop_inbound_fields(self) -> None:
        inbound = require_fields(load_fixture("inbound-drag-drop.json"), ("kind", "event", "active_fragment"), (), "UiHostInbound")
        self.assertEqual(inbound["kind"], "drag_drop")
        event = require_fields(
            inbound["event"],
            (
                "event_id", "drag_key", "drop_key", "intent", "payload",
                "program_revision", "input_revision", "request_id", "idempotency_key", "interaction",
            ),
            (),
            "UiProgramDragDropEvent",
        )
        payload = require_fields(event["payload"], ("source_key", "target_key", "placement"), ("presentation_template_key",), "UiDragDropPayload")
        self.assertIn(payload["placement"], {"into", "before", "after"})
        fragment = require_fields(inbound["active_fragment"], ("fragment", "root", "effects"), (), "UiHostFragmentContext")
        require_fields(fragment["fragment"], ("id", "revision"), (), "UiFragmentRevision")

    def test_input_frame_and_publication_fields(self) -> None:
        frame = require_fields(
            load_fixture("input-frame.json"),
            ("program_revision", "expected_input_revision", "request_id", "idempotency_key", "changes"),
            (),
            "UiInputFrame",
        )
        for change in frame["changes"]:
            require_fields(change, ("key", "value"), (), "UiInputChange")
        publication = require_fields(load_fixture("publication.json"), ("scalar_frame", "grid_inputs"), ("presentation_update",), "UiHostPublication")
        self.assertIn("presentation_update", publication)
        self.assertIsNone(publication["presentation_update"])
        for grid in publication["grid_inputs"]:
            require_fields(grid, ("source_key", "frame"), (), "UiDataGridInputFrame")
            grid_frame = require_fields(grid["frame"], ("list_revision", "total_rows", "first_row", "window_rows", "expected_program_revision"), (), "UiDataGridFrame")
            for row in grid_frame["window_rows"]:
                require_fields(row, ("stable_row_key", "cells"), (), "UiDataGridWindowRow")

    def test_snapshot_and_describe_shapes(self) -> None:
        snapshot = require_fields(
            load_fixture("debug-snapshot.json"),
            ("service", "epoch", "revision", "health", "capabilities", "active_jobs"),
            (),
            "DebugSnapshot",
        )
        self.assertEqual(snapshot["service"], "ui-runtime")
        describe = require_fields(
            load_fixture("service-describe.json"),
            ("service", "protocol_version", "endpoint", "epoch", "capabilities"),
            (),
            "ServiceDescription",
        )
        self.assertEqual(describe["protocol_version"], {"major": 1, "minor": 0})
        host_snapshot = require_fields(
            load_fixture("program-input-snapshot.json"),
            ("scalar_inputs", "grid_inputs"),
            (),
            "UiProgramInputSnapshot",
        )
        require_fields(host_snapshot["scalar_inputs"], ("program_revision", "input_revision", "values", "changed_slots"), (), "UiResolvedInputs")

    def test_flow_submit_result_shape(self) -> None:
        result = require_fields(load_fixture("flow-submit-result.json"), ("surface_id", "program_revision", "input_schema"), (), "ui.flow.submit result")
        require_fields(result["program_revision"], ("program_id", "revision", "schema_version", "capabilities"), (), "UiProgramRevision")
        schema = require_fields(result["input_schema"], ("schema_id", "version", "slots", "layout_hash"), ("grid_slots", "flow_name", "emit_event_keys"), "UiInputSchema")
        for slot in schema["slots"]:
            require_fields(
                slot,
                ("key", "kind", "default_value", "update_class", "semantic_label", "packing"),
                (),
                "UiInputSlot",
            )

    def test_core_error_codes_are_frozen(self) -> None:
        self.assertEqual(
            CORE_ERROR_CODES,
            ("stale_revision", "unknown_target", "unsupported_intent", "capability_unavailable", "duplicate_event", "invalid_publication"),
        )


if __name__ == "__main__":
    unittest.main()

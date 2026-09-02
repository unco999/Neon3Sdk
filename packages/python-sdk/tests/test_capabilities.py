"""Stage 002 capability negotiation and typed error tests."""

from __future__ import annotations

import unittest

from neon3_sdk.capabilities import (
    CapabilitySet,
    required_capabilities_for_flow,
    scan_flow,
    validate_flow_source,
)
from neon3_sdk.errors import (
    CapabilityError,
    FlowValidationError,
    RemoteError,
    normalize_error_code,
)
from neon3_sdk.models import ServiceDescription

CALCULATOR_FLOW = """version 1
surface calculator column w 560 h 420 gap 12 pad 20 align stretch fill #20252B
flow calculator
input display f32 default 0
  panel display-panel column h 108 pad 14 gap 8 align stretch fill #303740 line #596675
    text title value "Hello"
    button one w 112 h 52 value "1" event calculator.number.one
"""

DATA_GRID_FLOW = """version 1
surface grid column w 600 h 400
flow grid-demo
grid_input rows capacity 16 key item_key
  data_grid list h 320 source rows columns name:text
"""


def full_ui_capabilities() -> CapabilitySet:
    # Mirrors the frozen ui-runtime capability list from the wire contract §5.1.
    return CapabilitySet.from_descriptions([
        ServiceDescription(
            service="ui-runtime",
            protocol_version={"major": 1, "minor": 0},
            endpoint="headless://ui-runtime",
            epoch=4,
            capabilities=(
                "ui.static_fragment.submit.v1", "ui.fragment.submit.v1", "ui.image.upload.v1",
                "ui.nine_slice.v1", "ui.semantic_input.v1", "ui.intent_dispatch.v1",
                "ui.surface.machine.v1", "ui.ai.terrain.panel.v1", "ui.text_input.commit.v1",
                "ui.program.input.v1", "ui.input.repeat.v1", "ui.data_grid.window.v1",
                "ui.host.pointer_event.v1", "ui.state.animation.v1", "ui.numeric.animation.v1",
                "debug.interaction.v1",
            ),
        ),
        ServiceDescription(
            service="wgpu-runtime",
            protocol_version={"major": 1, "minor": 0},
            endpoint="headless://wgpu-runtime",
            epoch=4,
            capabilities=("wgpu.ui.fragment.v1", "wgpu.render.diagnostics"),
        ),
    ])


class CapabilitySetTests(unittest.TestCase):
    def test_missing_and_require(self) -> None:
        caps = CapabilitySet(services=("ui-runtime",), capabilities=frozenset({"ui.program.v1"}))
        self.assertEqual(caps.missing("ui.program.v1", "ui.data_grid.window.v1"), ("ui.data_grid.window.v1",))
        with self.assertRaises(CapabilityError) as caught:
            caps.require("ui.data_grid.window.v1", service="ui-runtime")
        self.assertEqual(caught.exception.missing, ("ui.data_grid.window.v1",))
        self.assertEqual(caught.exception.code, "capability_unavailable")
        self.assertFalse(caught.exception.retryable)

    def test_union(self) -> None:
        a = CapabilitySet(services=("a",), capabilities=frozenset({"x"}))
        b = CapabilitySet(services=("b",), capabilities=frozenset({"y"}))
        merged = a.union(b)
        self.assertEqual(merged.capabilities, frozenset({"x", "y"}))
        self.assertEqual(merged.services, ("a", "b"))

    def test_flow_requirements(self) -> None:
        self.assertEqual(required_capabilities_for_flow(CALCULATOR_FLOW), ("ui.intent_dispatch.v1", "ui.semantic_input.v1"))
        self.assertIn("ui.data_grid.window.v1", required_capabilities_for_flow(DATA_GRID_FLOW))

    def test_scan_records_positions(self) -> None:
        infos = scan_flow(DATA_GRID_FLOW)
        grid = next(info for info in infos if info.component == "data_grid")
        self.assertEqual(grid.key, "list")
        self.assertGreaterEqual(grid.line, 1)
        self.assertGreaterEqual(grid.column, 1)

    def test_validate_accepts_with_full_capabilities(self) -> None:
        required = validate_flow_source(DATA_GRID_FLOW, full_ui_capabilities())
        self.assertIn("ui.data_grid.window.v1", required)

    def test_validate_fails_before_collection_when_grid_capability_missing(self) -> None:
        stripped = CapabilitySet(services=("ui-runtime",), capabilities=frozenset({"ui.program.v1"}))
        with self.assertRaises(CapabilityError) as caught:
            validate_flow_source(DATA_GRID_FLOW, stripped)
        self.assertIn("ui.data_grid.window.v1", caught.exception.missing)

    def test_unknown_component_reports_location(self) -> None:
        bad = "version 1\nsurface demo\n  watnot key w 10 h 10\n"
        with self.assertRaises(FlowValidationError) as caught:
            validate_flow_source(bad)
        self.assertEqual(caught.exception.line, 3)
        self.assertEqual(caught.exception.code_runtime, "nui_flow_unknown_component")


class ErrorCodeMappingTests(unittest.TestCase):
    def test_runtime_codes_map_to_frozen_sdk_codes(self) -> None:
        cases = {
            "ui_program_stale_input_revision": ("stale_revision", True),
            "ui_host_stale_semantic_intent": ("stale_revision", True),
            "ui_host_stale_drag_drop": ("stale_revision", True),
            "ui_host_renderer_epoch_mismatch": ("stale_revision", True),
            "ui_host_invalid_drag_drop": ("unknown_target", False),
            "ui_host_invalid_publication": ("invalid_publication", False),
            "ui_flow_submit_failed": ("invalid_program", False),
        }
        for runtime_code, expected in cases.items():
            with self.subTest(code=runtime_code):
                self.assertEqual(normalize_error_code(runtime_code), expected)

    def test_unknown_codes_pass_through(self) -> None:
        self.assertEqual(normalize_error_code("some_future_code"), ("some_future_code", False))

    def test_remote_error_exposes_normalized_fields(self) -> None:
        error = RemoteError("req-1", "rejected", {"code": "ui_program_stale_input_revision", "message": "stale", "details": {"expected": 3, "actual": 4}})
        self.assertEqual(error.code, "ui_program_stale_input_revision")
        self.assertEqual(error.sdk_code, "stale_revision")
        self.assertEqual(error.message, "stale")
        self.assertTrue(error.retryable)
        self.assertEqual(error.details["expected"], 3)

    def test_remote_error_defaults_when_envelope_empty(self) -> None:
        error = RemoteError("req-2", "failed", None)
        self.assertEqual(error.code, "unknown_remote_error")
        self.assertEqual(error.sdk_code, "unknown_remote_error")
        self.assertFalse(error.retryable)


if __name__ == "__main__":
    unittest.main()

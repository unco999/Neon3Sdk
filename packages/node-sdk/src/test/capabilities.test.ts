/**
 * Stage 002 capability negotiation and typed error tests.
 *
 * The inline Flow strings are byte-identical to the Python suite in
 * `packages/python-sdk/tests/test_capabilities.py`, so both languages must
 * derive the same required-capability sets from them.
 */

import assert from "node:assert/strict";
import test from "node:test";
import {
  CapabilitySet,
  capabilityOwner,
  requiredCapabilitiesForFlow,
  scanFlow,
  validateFlowSource,
  KNOWN_FLOW_COMPONENTS,
} from "../capabilities.js";
import {
  CapabilityError,
  ERROR_CODES,
  FlowValidationError,
  RemoteError,
  normalizeErrorCode,
} from "../errors.js";
import { ServiceDescription } from "../protocol.js";

const CALCULATOR_FLOW = `version 1
surface calculator column w 560 h 420 gap 12 pad 20 align stretch fill #20252B
flow calculator
input display f32 default 0
  panel display-panel column h 108 pad 14 gap 8 align stretch fill #303740 line #596675
    text title value "Hello"
    button one w 112 h 52 value "1" event calculator.number.one
`;

const DATA_GRID_FLOW = `version 1
surface grid column w 600 h 400
flow grid-demo
grid_input rows capacity 16 key item_key
  data_grid list h 320 source rows columns name:text
`;

function fullUiCapabilities(): CapabilitySet {
  // Mirrors the frozen ui-runtime capability list from the wire contract §5.1.
  return CapabilitySet.fromDescriptions([
    {
      service: "ui-runtime",
      protocol_version: { major: 1, minor: 0 },
      endpoint: "headless://ui-runtime",
      epoch: 4,
      capabilities: [
        "ui.static_fragment.submit.v1", "ui.fragment.submit.v1", "ui.image.upload.v1",
        "ui.nine_slice.v1", "ui.semantic_input.v1", "ui.intent_dispatch.v1",
        "ui.surface.machine.v1", "ui.ai.terrain.panel.v1", "ui.text_input.commit.v1",
        "ui.program.input.v1", "ui.input.repeat.v1", "ui.data_grid.window.v1",
        "ui.host.pointer_event.v1", "ui.state.animation.v1", "ui.numeric.animation.v1",
        "debug.interaction.v1",
      ],
    } as ServiceDescription,
    {
      service: "wgpu-runtime",
      protocol_version: { major: 1, minor: 0 },
      endpoint: "headless://wgpu-runtime",
      epoch: 4,
      capabilities: ["wgpu.ui.fragment.v1", "wgpu.render.diagnostics"],
    } as ServiceDescription,
  ]);
}

test("CapabilitySet missing/require/union", () => {
  const caps = CapabilitySet.of(["ui.program.v1"], "ui-runtime");
  assert.deepEqual(caps.missing("ui.program.v1", "ui.data_grid.window.v1"), ["ui.data_grid.window.v1"]);
  assert.throws(() => caps.require("ui.data_grid.window.v1"), CapabilityError);
  try {
    caps.require("ui.data_grid.window.v1");
  } catch (error) {
    assert.ok(error instanceof CapabilityError);
    assert.equal(error.code, ERROR_CODES.CAPABILITY_UNAVAILABLE);
    assert.equal(error.retryable, false);
  }
  const merged = CapabilitySet.of(["x"], "a").union(CapabilitySet.of(["y"], "b"));
  assert.deepEqual([...merged.capabilities].sort(), ["x", "y"]);
});

test("flow capability requirements match the Python suite", () => {
  assert.deepEqual(requiredCapabilitiesForFlow(CALCULATOR_FLOW), ["ui.intent_dispatch.v1", "ui.semantic_input.v1"]);
  assert.deepEqual(requiredCapabilitiesForFlow(DATA_GRID_FLOW), ["ui.data_grid.window.v1"]);
});

test("capability owner split", () => {
  assert.equal(capabilityOwner("ui.data_grid.window.v1"), "ui-runtime");
  assert.equal(capabilityOwner("ui.canvas.points_lines.v1"), "wgpu-runtime");
  assert.equal(capabilityOwner("wgpu.ui.hit_target.v1"), "wgpu-runtime");
});

test("scanFlow records component position", () => {
  const grid = scanFlow(DATA_GRID_FLOW).find((info) => info.component === "data_grid");
  assert.ok(grid);
  assert.equal(grid.key, "list");
  assert.ok(grid.line >= 1);
  assert.ok(grid.column >= 1);
});

test("validateFlowSource accepts with full capabilities", () => {
  const required = validateFlowSource(DATA_GRID_FLOW, fullUiCapabilities(), "ui-runtime");
  assert.ok(required.includes("ui.data_grid.window.v1"));
});

test("validateFlowSource fails before collection when grid capability missing", () => {
  const stripped = CapabilitySet.of(["ui.program.v1"], "ui-runtime");
  assert.throws(
    () => validateFlowSource(DATA_GRID_FLOW, stripped, "ui-runtime"),
    (error) => error instanceof CapabilityError && error.missing.includes("ui.data_grid.window.v1"),
  );
});

test("canvas capability is not gated by a ui-runtime-only check", () => {
  const canvasFlow = `version 1\nsurface demo\ncanvas paint w 100 h 100\n`;
  const uiOnly = CapabilitySet.of(["ui.program.v1"], "ui-runtime");
  // Required set still reports the renderer capability...
  assert.deepEqual(requiredCapabilitiesForFlow(canvasFlow), ["ui.canvas.points_lines.v1"]);
  // ...but a ui-runtime validation does not fail on it.
  assert.deepEqual(validateFlowSource(canvasFlow, uiOnly, "ui-runtime"), ["ui.canvas.points_lines.v1"]);
});

test("unknown component reports a location", () => {
  const bad = "version 1\nsurface demo\n  watnot key w 10 h 10\n";
  assert.throws(
    () => validateFlowSource(bad, null, "ui-runtime"),
    (error) => error instanceof FlowValidationError && error.line === 3 && error.flowCode === "nui_flow_unknown_component",
  );
});

test("runtime codes map to frozen SDK codes identically to Python", () => {
  const cases: Array<[string, [string, boolean]]> = [
    ["ui_program_stale_input_revision", ["stale_revision", true]],
    ["ui_host_stale_semantic_intent", ["stale_revision", true]],
    ["ui_host_stale_drag_drop", ["stale_revision", true]],
    ["ui_host_renderer_epoch_mismatch", ["stale_revision", true]],
    ["ui_host_invalid_drag_drop", ["unknown_target", false]],
    ["ui_host_invalid_publication", ["invalid_publication", false]],
    ["ui_flow_submit_failed", ["invalid_program", false]],
  ];
  for (const [runtimeCode, expected] of cases) {
    assert.deepEqual([normalizeErrorCode(runtimeCode).sdkCode, normalizeErrorCode(runtimeCode).retryable], expected, runtimeCode);
  }
  assert.equal(normalizeErrorCode("some_future_code").sdkCode, "some_future_code");
});

test("RemoteError exposes code, message, details, retryable", () => {
  const error = new RemoteError("req-1", "rejected", { code: "ui_program_stale_input_revision", message: "stale", details: { expected: 3, actual: 4 } });
  assert.equal(error.code, "ui_program_stale_input_revision");
  assert.equal(error.sdkCode, "stale_revision");
  assert.equal(error.retryable, true);
  assert.equal(error.details.expected, 3);
  const empty = new RemoteError("req-2", "failed", null);
  assert.equal(empty.code, "unknown_remote_error");
  assert.equal(empty.retryable, false);
});

test("closed vocabulary is present", () => {
  assert.ok(KNOWN_FLOW_COMPONENTS.has("data_grid"));
  assert.ok(KNOWN_FLOW_COMPONENTS.has("canvas"));
});

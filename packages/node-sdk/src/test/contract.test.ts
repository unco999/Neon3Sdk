/**
 * Stage 000 cross-language wire contract tests.
 *
 * Digest table must stay byte-identical with the Python suite in
 * `packages/python-sdk/tests/test_wire_contract.py`; the shared source of
 * truth is `docs/sdk-wire-contract.md` §3.
 */

import assert from "node:assert/strict";
import test from "node:test";
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { CORE_ERROR_CODES, canonicalDigest, fixtureRoot, loadFixture, requireFields, asObject } from "../wire.js";

const CANONICAL_DIGESTS: Record<string, string> = {
  "debug-snapshot.json": "8cf8cfac8f2981f68f2a44b0097571a03d9b63c2946bc00144bdb9a4149deccd",
  "flow-submit-result.json": "63e30e58a6d53b22ab565706e7c41a3ff641f5918fe6591eadb7796f1c55dcef",
  "inbound-drag-drop.json": "18b19b05dfcb726d4856458a4a782fa50570e20e61e48cb190e223cf83f4f893",
  "inbound-semantic-intent.json": "57b6e53caa05b46c5f56a12040e0777649bca60fdad7fd1ba7df1064c8defd93",
  "input-frame.json": "ec7e0df1e0baad82b542aef91aeb44ed79f0d90b2082558f0852c0605983b737",
  "program-input-snapshot.json": "b7f9f5b40b43d1e499828758c6447d9424adbae892c65cfef0f1b18d874a81ec",
  "publication.json": "34ac4cbd83faca6f0fe9c68fe394414f36cd831abecde86a56d3559e2bcbeed3",
  "rpc-response-rejected-stale.json": "96484207781ec91ab23ae2101bbc8c85b4356775ab961547f390c89073936e48",
  "service-describe.json": "22526dd9bd3d4367af31e59f48c9772a9bf6e1af3e7b5ee9e9623008fbecabd9",
};

test("every fixture on disk has a pinned digest", () => {
  const names = readdirSync(fixtureRoot()).filter((name) => name.endsWith(".json")).sort();
  assert.deepEqual(names, Object.keys(CANONICAL_DIGESTS).sort());
});

test("canonical digests match the frozen table", () => {
  for (const [name, digest] of Object.entries(CANONICAL_DIGESTS)) {
    assert.equal(canonicalDigest(loadFixture(name)), digest, name);
  }
});

test("rpc envelope is closed", () => {
  const response = requireFields(loadFixture("rpc-response-rejected-stale.json"), ["request_id", "status", "revision", "result", "snapshot", "error"], [], "RpcResponse");
  assert.equal(response.status, "rejected");
  assert.equal(asObject(response.error, "error").code, "ui_program_stale_input_revision");
});

test("semantic intent event fields", () => {
  const inbound = requireFields(loadFixture("inbound-semantic-intent.json"), ["kind", "event"], [], "UiHostInbound");
  assert.equal(inbound.kind, "semantic_intent");
  const event = requireFields(
    inbound.event,
    ["event_id", "kind", "intent", "source_node_key", "payload", "program_revision", "input_revision", "request_id", "idempotency_key", "interaction"],
    ["requested_value"],
    "UiProgramSemanticEvent",
  );
  assert.equal(event.kind, "activate");
  requireFields(event.interaction, ["interaction_id", "sequence", "renderer_epoch"], [], "UiSemanticInteractionMetadata");
  const payload = asObject(event.payload, "payload");
  for (const key of Object.keys(payload)) {
    assert.ok(["bool", "i32", "u32", "f32", "enum", "text_handle", "asset_handle"].includes(asObject(payload[key], key).kind as string));
  }
});

test("drag drop inbound fields", () => {
  const inbound = requireFields(loadFixture("inbound-drag-drop.json"), ["kind", "event", "active_fragment"], [], "UiHostInbound");
  assert.equal(inbound.kind, "drag_drop");
  const event = requireFields(
    inbound.event,
    ["event_id", "drag_key", "drop_key", "intent", "payload", "program_revision", "input_revision", "request_id", "idempotency_key", "interaction"],
    [],
    "UiProgramDragDropEvent",
  );
  const payload = requireFields(event.payload, ["source_key", "target_key", "placement"], ["presentation_template_key"], "UiDragDropPayload");
  assert.ok(["into", "before", "after"].includes(payload.placement as string));
  const fragment = requireFields(inbound.active_fragment, ["fragment", "root", "effects"], [], "UiHostFragmentContext");
  requireFields(fragment.fragment, ["id", "revision"], [], "UiFragmentRevision");
});

test("input frame and publication fields", () => {
  const frame = requireFields(loadFixture("input-frame.json"), ["program_revision", "expected_input_revision", "request_id", "idempotency_key", "changes"], [], "UiInputFrame");
  for (const change of frame.changes as unknown[]) requireFields(change, ["key", "value"], [], "UiInputChange");
  const publication = requireFields(loadFixture("publication.json"), ["scalar_frame", "grid_inputs"], ["presentation_update"], "UiHostPublication");
  assert.ok("presentation_update" in publication);
  assert.equal(publication.presentation_update, null);
  for (const grid of publication.grid_inputs as unknown[]) {
    const record = requireFields(grid, ["source_key", "frame"], [], "UiDataGridInputFrame");
    const gridFrame = requireFields(record.frame, ["list_revision", "total_rows", "first_row", "window_rows", "expected_program_revision"], [], "UiDataGridFrame");
    for (const row of gridFrame.window_rows as unknown[]) requireFields(row, ["stable_row_key", "cells"], [], "UiDataGridWindowRow");
  }
});

test("snapshot and describe shapes", () => {
  const snapshot = requireFields(loadFixture("debug-snapshot.json"), ["service", "epoch", "revision", "health", "capabilities", "active_jobs"], [], "DebugSnapshot");
  assert.equal(snapshot.service, "ui-runtime");
  const describe = requireFields(loadFixture("service-describe.json"), ["service", "protocol_version", "endpoint", "epoch", "capabilities"], [], "ServiceDescription");
  assert.deepEqual(describe.protocol_version, { major: 1, minor: 0 });
  const hostSnapshot = requireFields(loadFixture("program-input-snapshot.json"), ["scalar_inputs", "grid_inputs"], [], "UiProgramInputSnapshot");
  requireFields(hostSnapshot.scalar_inputs, ["program_revision", "input_revision", "values", "changed_slots"], [], "UiResolvedInputs");
});

test("flow submit result shape", () => {
  const result = requireFields(loadFixture("flow-submit-result.json"), ["surface_id", "program_revision", "input_schema"], [], "ui.flow.submit result");
  requireFields(result.program_revision, ["program_id", "revision", "schema_version", "capabilities"], [], "UiProgramRevision");
  const schema = requireFields(result.input_schema, ["schema_id", "version", "slots", "layout_hash"], ["grid_slots", "flow_name", "emit_event_keys"], "UiInputSchema");
  for (const slot of schema.slots as unknown[]) {
    requireFields(slot, ["key", "kind", "default_value", "update_class", "semantic_label", "packing"], [], "UiInputSlot");
  }
});

test("core error codes are frozen", () => {
  assert.deepEqual([...CORE_ERROR_CODES], ["stale_revision", "unknown_target", "unsupported_intent", "capability_unavailable", "duplicate_event", "invalid_publication"]);
});

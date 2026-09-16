/**
 * Editor document API contract tests (editor-runtime, v0.2.10+).
 *
 * Unit-level: wire shapes, local validation, and envelope construction via a
 * stubbed client. Integration (skipped unless NEON3_EDITOR_INTEGRATION=1 and
 * an editor-runtime endpoint is provided) exercises the live service.
 */
import assert from "node:assert/strict";
import test from "node:test";
import {
  ChangeSet,
  EditOp,
  EditorClient,
  EditorOpenResult,
  EditorOperationResult,
  EditorSnapshot,
  EDITOR_LANGUAGE_NUI_FLOW,
  MAX_CHANGESET_OPS,
  MAX_INSERT_BYTES,
  editDelete,
  editInsert,
  validateChangeSet,
} from "../editor.js";
import { eventName, method, service } from "../constants.js";
import { NeonClient } from "../client.js";

test("edit op wire shape matches the runtime serde tagging", () => {
  const insert = editInsert(3, 7, { line: 3, column: 12 }, "hello");
  assert.deepEqual(insert, { kind: "insert", line: 3, column: 7, end: { line: 3, column: 12 }, text: "hello" });
  const del = editDelete({ line: 3, column: 7 }, { line: 3, column: 12 }, "hello");
  assert.deepEqual(del, { kind: "delete", start: { line: 3, column: 7 }, end: { line: 3, column: 12 }, text: "hello" });
});

test("change set validation matches the runtime limits", () => {
  assert.throws(() => validateChangeSet({ base_revision: 0, ops: [] }));
  const overflow: EditOp[] = [];
  for (let i = 0; i <= MAX_CHANGESET_OPS; i++) overflow.push(editInsert(i, 0, { line: 0, column: 1 }, "x"));
  assert.throws(() => validateChangeSet({ base_revision: 0, ops: overflow }));
  const big = "x".repeat(MAX_INSERT_BYTES + 1);
  assert.throws(() => validateChangeSet({ base_revision: 0, ops: [editInsert(0, 0, { line: 0, column: 1 }, big)] }));
  validateChangeSet({ base_revision: 4, ops: [editInsert(0, 0, { line: 0, column: 1 }, "x")] });
});

test("wire constants are stable", () => {
  assert.equal(service.EDITOR_RUNTIME, "editor-runtime");
  assert.equal(method.EDITOR_DOCUMENT_OPEN, "editor.document.open");
  assert.equal(method.EDITOR_DOCUMENT_SNAPSHOT_GET, "editor.document.snapshot.get");
  assert.equal(method.EDITOR_DOCUMENT_CHANGE_APPLY, "editor.document.change.apply");
  assert.equal(method.EDITOR_DOCUMENT_CHANGE_COMMIT, "editor.document.change.commit");
  assert.equal(method.EDITOR_COMPLETION_REQUEST, "editor.completion.request");
  assert.equal(method.EDITOR_DOCUMENT_CLOSE, "editor.document.close");
  assert.equal(method.WGPU_SHADER_REGISTER, "wgpu.shader.register");
  assert.equal(method.WGPU_SHADER_STATE, "wgpu.shader.state");
  assert.equal(eventName.DOCUMENT_COMMIT, "document_commit");
  assert.equal(EDITOR_LANGUAGE_NUI_FLOW, "nui_flow");
});

/** Captures envelopes and answers a canned result, no socket involved. */
function stubClient(result: unknown): { envelopes: Array<{ target: string; method: string; params: unknown; options: unknown }>; client: NeonClient } {
  const envelopes: Array<{ target: string; method: string; params: unknown; options: unknown }> = [];
  const client = {
    call: async (target: string, meth: string, params: unknown, options: unknown = {}) => {
      envelopes.push({ target, method: meth, params, options });
      return { request_id: "r", status: "accepted", revision: null, result, snapshot: null, error: null };
    },
  } as unknown as NeonClient;
  return { envelopes, client };
}

const SNAPSHOT: EditorSnapshot = {
  document_id: "doc-1", session_id: "sess-1", language: "nui_flow", epoch: 2,
  revision: 9, committed_revision: 8, dirty: true, line_count: 12, byte_length: 340,
  source_hash: "abc", source: "flow", diagnostics: [],
};

test("open sends the mutating envelope with an idempotency key", async () => {
  const { envelopes, client } = stubClient({ state: "opened", snapshot: SNAPSHOT });
  const editor = new EditorClient(client);
  const opened: EditorOpenResult = await editor.open("doc-1", "sess-1", "flow");
  assert.equal(opened.state, "opened");
  assert.equal(envelopes.length, 1);
  assert.equal(envelopes[0].target, "editor-runtime");
  assert.equal(envelopes[0].method, "editor.document.open");
  const params = envelopes[0].params as Record<string, unknown>;
  assert.equal(params.language, "nui_flow");
  assert.equal(params.source, "flow");
  const options = envelopes[0].options as { idempotencyKey: string };
  assert.match(options.idempotencyKey, /^editor:open:doc-1:/);
  await assert.rejects(() => editor.open("doc-1", "sess-1", "flow", "typescript" as never), /unsupported editor language/);
  await assert.rejects(() => editor.open("", "sess-1", "flow"), /document_id must be non-empty/);
});

test("apply change sends cursor/selection and validates first", async () => {
  const operation: EditorOperationResult = {
    state: "draft", snapshot: SNAPSHOT, applied_ops: 2,
    cursor: { line: 1, column: 1 }, selection: { anchor: { line: 0, column: 0 }, active: { line: 1, column: 1 } },
  };
  const { envelopes, client } = stubClient(operation);
  const editor = new EditorClient(client);
  const changeSet: ChangeSet = { base_revision: 4, ops: [editInsert(0, 0, { line: 0, column: 1 }, "x")] };
  const result = await editor.applyChange("doc-1", "sess-1", 2, changeSet, "draft", {
    cursor: { line: 1, column: 1 },
    selection: { anchor: { line: 0, column: 0 }, active: { line: 1, column: 1 } },
  });
  assert.equal(result.applied_ops, 2);
  const params = envelopes[0].params as Record<string, unknown>;
  assert.deepEqual(params.change_set, changeSet);
  assert.deepEqual(params.cursor, { line: 1, column: 1 });
  assert.equal(params.kind, "draft");
  await assert.rejects(() => editor.applyChange("doc-1", "sess-1", 2, { base_revision: 0, ops: [] }, "draft"), /1..=256 ops/);
});

test("commit carries expected_revision on the envelope", async () => {
  const { envelopes, client } = stubClient(SNAPSHOT);
  const editor = new EditorClient(client);
  await editor.commit("doc-1", "sess-1", 2, 9);
  const options = envelopes[0].options as { expectedRevision: number; idempotencyKey: string };
  assert.equal(options.expectedRevision, 9);
  assert.match(options.idempotencyKey, /^editor:commit:doc-1:/);
});

test("completions and close use the read/mutating split correctly", async () => {
  const { envelopes, client } = stubClient({
    document_id: "doc-1", document_revision: 9, position: { line: 0, column: 3 },
    items: [{ item_id: "k1", label: "machine", insert_text: "machine", replace_start: { line: 0, column: 0 }, replace_end: { line: 0, column: 3 }, kind: "keyword", detail: "", sort_text: "0machine", source: "grammar", commit_characters: [" "] }],
  });
  const editor = new EditorClient(client);
  const result = await editor.completions("doc-1", "sess-1", 2, 9, { line: 0, column: 3 }, "invoked");
  assert.equal(result.items[0].label, "machine");
  const completionOptions = envelopes[0].options as Record<string, unknown>;
  assert.equal(completionOptions.idempotencyKey, undefined);
  await editor.close("doc-1", "sess-1", 2);
  const closeOptions = envelopes[1].options as { idempotencyKey: string };
  assert.match(closeOptions.idempotencyKey, /^editor:close:doc-1:/);
});

test("integration against a live editor-runtime (opt-in)", { skip: process.env.NEON3_EDITOR_INTEGRATION !== "1" }, async () => {
  const endpoint = process.env.NEON3_EDITOR_ENDPOINT ?? "127.0.0.1:39104";
  const client = new NeonClient(endpoint, { origin: "neon3-editor-test" });
  const editor = new EditorClient(client);
  const opened = await editor.open(`doc-${Date.now()}`, "sess-1", "flow demo\n");
  assert.equal(opened.state, "opened");
  const epoch = opened.snapshot!.epoch;
  const documentId = opened.snapshot!.document_id;
  const revision = opened.snapshot!.revision;
  const changeSet: ChangeSet = { base_revision: revision, ops: [editInsert(0, 9, { line: 0, column: 10 }, "!")] };
  const applied = await editor.applyChange(documentId, "sess-1", epoch, changeSet, "commit");
  assert.equal(applied.applied_ops, 1);
  const snapshot = await editor.snapshot(documentId, "sess-1", epoch);
  assert.ok(snapshot.source.endsWith("!"));
  const completions = await editor.completions(documentId, "sess-1", epoch, snapshot.revision, { line: 0, column: 0 });
  assert.ok(Array.isArray(completions.items));
  await editor.close(documentId, "sess-1", epoch);
});

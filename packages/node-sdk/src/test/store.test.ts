/**
 * Stage 004 typed store and publication tests.
 *
 * Mirrors packages/python-sdk/tests/test_store.py. The store-wire digest is
 * asserted identical in both suites so a diff-algorithm or serialization
 * drift on either side fails the pair.
 */

import assert from "node:assert/strict";
import test from "node:test";
import { createHash } from "node:crypto";
import { CollectionStore, ObservableStore, typedValue } from "../store.js";
import { InvalidPublicationError } from "../errors.js";
import { canonicalJson } from "../wire.js";

const PROGRAM_REVISION = { program_id: "demo", revision: 1, schema_version: 1, capabilities: [] };

const item = (key: string, n: number, label = "") => ({ key, n, label: label || `item-${key}` });
const cells = (_collection: CollectionStore, entry: any) => ({ label: { value: { kind: "enum", value: entry.label }, display: { id: 1, generation: 1 } } });

test("typedValue maps JS types to wire kinds", () => {
  assert.deepEqual(typedValue(true), { kind: "bool", value: true });
  assert.deepEqual(typedValue(7), { kind: "i32", value: 7 });
  assert.deepEqual(typedValue(2.5), { kind: "f32", value: 2.5 });
  assert.deepEqual(typedValue("ready"), { kind: "enum", value: "ready" });
  assert.deepEqual(typedValue([1, 2]), { kind: "vec2", value: [1, 2] });
  assert.deepEqual(typedValue({ kind: "u32", value: 4 }), { kind: "u32", value: 4 });
});

test("typedValue rejects out-of-vocabulary values", () => {
  assert.throws(() => typedValue(NaN), InvalidPublicationError);
  assert.throws(() => typedValue(""), InvalidPublicationError);
  assert.throws(() => typedValue(new Map()), InvalidPublicationError);
});

test("scalar set marks dirty once", () => {
  const store = new ObservableStore();
  const scalar = store.value("count");
  scalar.set(1);
  assert.equal(scalar.isDirty(), true);
  assert.deepEqual(store.changedScalars(), [{ key: "count", value: { kind: "i32", value: 1 } }]);
  store.markApplied();
  assert.deepEqual(store.changedScalars(), []);
  assert.equal(store.domain_revision, 1);
});

test("selection lane publishes an enum slot", () => {
  const store = new ObservableStore();
  const collection = store.collection("items");
  collection.setKeyOf((entry: any) => entry.key);
  collection.replace([item("a", 1), item("b", 2)]);
  const selection = store.selection("items");
  selection.set("a");
  const publication = store.buildPublication(PROGRAM_REVISION as any, 3, "r-sel", { selectionSlots: { items: "selected_key" } });
  assert.deepEqual(publication.scalar_frame.changes, [{ key: "selected_key", value: { kind: "enum", value: "a" } }]);
  assert.equal(publication.scalar_frame.expected_input_revision, 3);
});

function fresh(): { store: ObservableStore; collection: CollectionStore } {
  const store = new ObservableStore();
  const collection = store.collection("items");
  collection.setKeyOf((entry: any) => entry.key);
  collection.replace([item("a", 1), item("b", 2), item("c", 3)]);
  store.markApplied();
  return { store, collection };
}

const publishedRows = (store: ObservableStore, options: any = {}): string[] => {
  const publication = store.buildPublication(PROGRAM_REVISION as any, 0, "req", { cellsOf: cells, ...options });
  if (!publication.grid_inputs.length) return [];
  return (publication.grid_inputs[0].frame as any).window_rows.map((row: any) => row.stable_row_key);
};

test("scalar update emits only that row", () => {
  const { store, collection } = fresh();
  collection.update("c", item("c", 99));
  assert.deepEqual(publishedRows(store), ["c"]);
});

test("add/move/remove republish the bounded window", () => {
  const { store, collection } = fresh();
  collection.add("d", item("d", 4));
  assert.deepEqual(publishedRows(store), ["a", "b", "c", "d"]);
  collection.markApplied();
  collection.move("a", 2);
  assert.deepEqual(publishedRows(store), ["b", "c", "a", "d"]);
  collection.markApplied();
  collection.remove("b");
  assert.deepEqual(publishedRows(store), ["c", "a", "d"]);
});

test("one update of a thousand items emits a single row", () => {
  const store = new ObservableStore();
  const collection = store.collection("items");
  collection.setKeyOf((entry: any) => entry.key);
  collection.replace(Array.from({ length: 1000 }, (_, index) => item(`k${index}`, index)));
  store.markApplied();
  collection.update("k42", item("k42", 500));
  const publication = store.buildPublication(PROGRAM_REVISION as any, 0, "big", { cellsOf: cells });
  const rows = (publication.grid_inputs[0].frame as any).window_rows;
  assert.deepEqual(rows.map((row: any) => row.stable_row_key), ["k42"]);
  assert.equal(rows.length, 1);
  assert.equal((publication.grid_inputs[0].frame as any).total_rows, 1000);
  assert.deepEqual(publication.scalar_frame.changes, []);
});

test("structural change respects window cap", () => {
  const { store, collection } = fresh();
  collection.add("d", item("d", 4));
  assert.deepEqual(publishedRows(store, { windowRows: 2 }), ["a", "b"]);
});

test("mixed transaction collapses into one publication", async () => {
  const store = new ObservableStore();
  const collection = store.collection("items");
  collection.setKeyOf((entry: any) => entry.key);
  collection.replace([item("a", 1)]);
  store.markApplied();
  await store.transaction((self) => {
    collection.add("b", item("b", 2));
    self.value("count").set(2);
    self.selection("items").set("b");
  });
  const publication = store.buildPublication(PROGRAM_REVISION as any, 0, "txn", { cellsOf: cells, selectionSlots: { items: "selected" } });
  assert.deepEqual(publication.scalar_frame.changes.map((change) => change.key), ["count", "selected"]);
  assert.deepEqual((publication.grid_inputs[0].frame as any).window_rows.map((row: any) => row.stable_row_key), ["a", "b"]);
});

test("aborted transaction leaves no half publication", async () => {
  const store = new ObservableStore();
  store.value("count").set(1);
  const collection = store.collection("items");
  collection.setKeyOf((entry: any) => entry.key);
  collection.replace([item("a", 1)]);
  store.markApplied();
  await assert.rejects(
    () => store.transaction((self) => {
      self.value("count").set(99);
      collection.remove("a");
      self.selection("items").set("ghost");
      throw new Error("domain rule rejected");
    }),
    /domain rule rejected/,
  );
  assert.deepEqual(store.value("count").current, { kind: "i32", value: 1 });
  assert.equal(store.value("count").isDirty(), false);
  assert.deepEqual(collection.keys(), ["a"]);
  assert.equal(collection.hasPendingChanges(), false);
  assert.equal(store.hasPendingChanges(), false);
  const publication = store.buildPublication(PROGRAM_REVISION as any, 0, "post-abort", { cellsOf: cells });
  assert.deepEqual(publication.scalar_frame.changes, []);
  assert.deepEqual(publication.grid_inputs, []);
});

test("rejection keeps local pending state", () => {
  const store = new ObservableStore();
  store.value("count").set(1);
  const before = store.domain_revision;
  store.rejectPending();
  assert.equal(store.value("count").isDirty(), true);
  assert.equal(store.domain_revision, before);
  store.markApplied();
  assert.equal(store.value("count").isDirty(), false);
});

test("store wire round-trips and matches the pinned cross-language digest", () => {
  const store = new ObservableStore({ status: "ready", count: 3 });
  store.collection("items").setKeyOf((entry: any) => entry.key);
  store.collection("items").replace([item("a", 1), item("b", 2)]);
  store.selection("items").set("a");
  const wire = store.toWire();
  const restored = ObservableStore.fromWire(wire);
  assert.equal(restored.domain_revision, (wire as any).domain_revision);
  assert.deepEqual(restored.collection("items").keys(), ["a", "b"]);
  assert.deepEqual(restored.value("status").current, { kind: "enum", value: "ready" });
  assert.equal(restored.selection("items").get(), "a");
  const digest = createHash("sha256").update(Buffer.from(canonicalJson(wire as any), "utf8")).digest("hex");
  assert.equal(digest, "3f790bd056eb8e06d80e9d50709cea97520277f456df46ed1d9866671a240f6e");
});

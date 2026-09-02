/**
 * Stage 006 collection/grid binding tests.
 *
 * Mirrors packages/python-sdk/tests/test_components.py. Mutations publish only
 * necessary grid changes through the binding's cellsOf adapter; selection and
 * drag payload always carry the stable business key rather than visual
 * coordinates; long lists page deterministically; and the missing-capability
 * path falls back cleanly (list mode keeps the binding usable while paging
 * throws, reject mode fails early).
 */

import assert from "node:assert/strict";
import test from "node:test";
import { CapabilitySet } from "../capabilities.js";
import { CapabilityError } from "../errors.js";
import { CollectionBinder, CollectionBinding, DragSpec, DropSpec } from "../components.js";
import { ObservableStore } from "../store.js";

const gridCapabilities = (...extra: string[]) => CapabilitySet.of([
  "ui.data_grid.window.v1", ...extra,
], "ui-runtime");
const emptyCapabilities = () => CapabilitySet.of(["ui.program.v1"], "ui-runtime");

const item = (key: string, name: string) => ({ key, name });
const columns = (entry: any) => ({ name: { value: { kind: "enum", value: entry.name }, display: { id: 1, generation: 1 } } });

function storeWith(items: any[]): ObservableStore {
  const store = new ObservableStore();
  const collection = store.collection("items");
  collection.setKeyOf((entry: any) => entry.key);
  collection.replace(items);
  store.markApplied();
  return store;
}

test("node keys use stable business keys, not index", () => {
  const store = storeWith([item("a", "Alpha"), item("b", "Beta")]);
  const binding = new CollectionBinder(gridCapabilities()).bind("backpack", store.collection("items"), { columns });
  assert.equal(binding.stableNodeKey(item("b", "Beta")), "backpack:b");
  assert.equal(binding.keyForNode("backpack:b"), "b");
  assert.equal(binding.keyForNode("elsewhere:b"), null);
  store.collection("items").move("a", 1);
  assert.equal(binding.stableNodeKey(item("b", "Beta")), "backpack:b");
});

test("drag and selection payloads carry stable keys", () => {
  const store = storeWith([item("gem-1", "Gem")]);
  const selection = store.selection("items");
  const binding = new CollectionBinder(gridCapabilities()).bind("backpack", store.collection("items"), {
    columns,
    selection,
    drag: new DragSpec({ intent: "domain.item.move", payloadFor: (entry: any) => ({ item_id: entry.key, kind: "gem" }) }),
  });
  selection.set("gem-1");
  assert.equal(binding.selectedKey(), "gem-1");
  const [, payloadFor, kindFor] = binding.dragSourceSpec();
  const entry = store.collection("items").get("gem-1");
  assert.deepEqual(payloadFor(entry), { item_id: "gem-1", kind: "gem", source_node_key: "backpack:gem-1", intent: "domain.item.move" });
  assert.equal(kindFor(entry), "gem");
});

test("default drag payload and kind", () => {
  const store = storeWith([item("a", "Alpha")]);
  const binding = new CollectionBinder(gridCapabilities()).bind("grid", store.collection("items"), { columns, drag: new DragSpec("domain.item.move") });
  const [, payloadFor, kindFor] = binding.dragSourceSpec();
  const entry = store.collection("items").get("a");
  assert.deepEqual(payloadFor(entry), { item_key: "a", kind: "grid", source_node_key: "grid:a", intent: "domain.item.move" });
  assert.equal(kindFor(entry), "grid");
});

test("single update publishes only that row via cellsOf", () => {
  const store = storeWith(Array.from({ length: 500 }, (_, index) => item(`k${index}`, `N${index}`)));
  const binding = new CollectionBinder(gridCapabilities()).bind("backpack", store.collection("items"), { columns });
  store.collection("items").update("k42", item("k42", "Changed"));
  const publication = store.buildPublication({ program_id: "demo", revision: 1, schema_version: 1, capabilities: [] } as any, 0, "pub", { cellsOf: binding.cellsOf() });
  const rows = (publication.grid_inputs[0].frame as any).window_rows;
  assert.deepEqual(rows.map((row: any) => row.stable_row_key), ["k42"]);
});

test("cellsOf produces typed display cells", () => {
  const store = storeWith([item("a", "Alpha")]);
  const binding = new CollectionBinder(gridCapabilities()).bind("backpack", store.collection("items"), { columns });
  store.collection("items").update("a", item("a", "Changed"));
  const publication = store.buildPublication({ program_id: "demo", revision: 1, schema_version: 1, capabilities: [] } as any, 0, "pub", { cellsOf: binding.cellsOf() });
  const row = (publication.grid_inputs[0].frame as any).window_rows[0];
  assert.deepEqual(row.cells.name.value, { kind: "enum", value: "Changed" });
  assert.deepEqual(row.cells.name.display, { id: 1, generation: 1 });
});

test("window slice is deterministic and bounded", () => {
  const store = storeWith(Array.from({ length: 100 }, (_, index) => item(`k${index}`, `N${index}`)));
  const binding = new CollectionBinder(gridCapabilities()).bind("list", store.collection("items"), { columns });
  const first = binding.page(10, 25);
  const again = binding.page(10, 25);
  assert.deepEqual(first.rows.map((row) => row.stable_row_key), Array.from({ length: 25 }, (_, index) => `k${index + 10}`));
  assert.equal(first.first_row, 10);
  assert.equal(first.total_rows, 100);
  assert.deepEqual(again.rows, first.rows);
  const tail = binding.page(90, 50);
  assert.deepEqual(tail.rows.map((row) => row.stable_row_key), Array.from({ length: 10 }, (_, index) => `k${index + 90}`));
  assert.throws(() => binding.page(-1, 10), /first_row/);
  assert.throws(() => binding.page(0, 0), /maxRows/);
});

test("list fallback keeps binding usable and gates paging", () => {
  const store = storeWith([item("a", "Alpha")]);
  const binding = new CollectionBinder(emptyCapabilities(), { fallback: "list" }).bind("list", store.collection("items"), { columns });
  assert.equal(binding.windowed, false);
  assert.throws(() => binding.page(0, 10), CapabilityError);
});

test("reject fallback fails before use", () => {
  const store = storeWith([item("a", "Alpha")]);
  assert.throws(() => new CollectionBinder(emptyCapabilities(), { fallback: "reject" }).bind("list", store.collection("items"), { columns }), CapabilityError);
});

test("unknown fallback is rejected", () => {
  assert.throws(() => new CollectionBinder(gridCapabilities(), { fallback: "magic" as "list" }), /list.*reject/);
});

test("presentation state derivation", () => {
  const store = new ObservableStore();
  const collection = store.collection("items");
  collection.setKeyOf((entry: any) => entry.key);
  const loading = store.value("loading");
  const error = store.value("error");
  const binding = new CollectionBinding("list", collection, { columns, loading, error });
  assert.equal(binding.presentationState(), "empty");
  collection.replace([item("a", "A")]);
  assert.equal(binding.presentationState(), "ready");
  loading.set(true);
  assert.equal(binding.presentationState(), "loading");
  error.set(true);
  assert.equal(binding.presentationState(), "error");
});

test("drop spec registration shape", () => {
  const store = storeWith([item("a", "Alpha")]);
  const binding = new CollectionBinder(gridCapabilities()).bind("grid", store.collection("items"), {
    columns,
    drop: new DropSpec("domain.item.place", ["gem"]),
  });
  assert.deepEqual(binding.dropTargetSpec(), ["grid", "domain.item.place", ["gem"]]);
});

test("binding without drop returns null; empty node key rejected", () => {
  const store = storeWith([item("a", "Alpha")]);
  assert.equal(new CollectionBinder(gridCapabilities()).bind("grid", store.collection("items"), { columns }).dropTargetSpec(), null);
  assert.throws(() => new CollectionBinder(gridCapabilities()).bind("", store.collection("items"), { columns }), /node_key/);
});

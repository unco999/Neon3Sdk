/**
 * Stage 005 intent routing and drag/drop tests.
 *
 * Mirrors packages/python-sdk/tests/test_routing.py. The acceptance intent
 * table (equip/craft/discard/select/move) lives only in these fixtures — a
 * validation case, not SDK public API. A rejected or unroutable drop must not
 * mutate domain state.
 */

import assert from "node:assert/strict";
import test from "node:test";
import { DropRejectedError, UnknownTargetError, UnsupportedIntentError } from "../errors.js";
import { DropEvent, IntentEvent } from "../protocol.js";
import { IntentRouter } from "../routing.js";

function dropInbound(sourceKey: string, targetKey: string, options: { intent?: string; sequence?: number; epoch?: number } = {}) {
  const event: Record<string, unknown> = {
    event_id: `evt-${sourceKey}-${targetKey}`,
    drag_key: sourceKey,
    drop_key: targetKey,
    payload: { source_key: sourceKey, target_key: targetKey, placement: "into" },
    interaction: { sequence: options.sequence ?? 1, renderer_epoch: options.epoch ?? 1 },
  };
  if (options.intent) event.intent = options.intent;
  return { kind: "drag_drop", event };
}

function inventoryFixture() {
  const router = new IntentRouter();
  const items: Record<string, any> = {
    "backpack-compass": { id: "compass", kind: "accessory", slot: "trinket" },
    "backpack-potion": { id: "potion", kind: "consumable", count: 3 },
    "backpack-gem": { id: "gem", kind: "material" },
  };
  router.setCatalogMap(items);
  const payload = (item: any) => ({ item_id: item.id, kind: item.kind });
  const kindOf = (item: any) => item.kind;
  for (const key of Object.keys(items)) router.dragSource(key, { payload, kindOf });
  router.dropTarget("equipment-zone", "inventory.item.equip", ["accessory"]);
  router.dropTarget("crafting-zone", "inventory.item.craft", ["material", "consumable"]);
  router.dropTarget("discard-zone", "inventory.item.discard");

  const state: Record<string, string | null> = { equipped: null, crafted: null, discarded: null };
  router.on("inventory.item.equip", (event) => { state.equipped = (event as DropEvent).payload.item_id as string; });
  router.on("inventory.item.craft", (event) => { state.crafted = (event as DropEvent).payload.item_id as string; });
  router.on("inventory.item.discard", (event) => { state.discarded = (event as DropEvent).payload.item_id as string; });
  return { router, state };
}

test("exact, prefix and default matching", async () => {
  const router = new IntentRouter();
  const calls: string[] = [];
  router.on("app.save", (e) => calls.push(`exact:${e.intent}`));
  router.on("app.*", (e) => calls.push(`prefix:${e.intent}`));
  router.default((e) => calls.push(`default:${e.intent}`));
  await router.dispatch(new IntentEvent("1", "app.save", "n"));
  await router.dispatch(new IntentEvent("2", "app.open", "n"));
  await router.dispatch(new IntentEvent("3", "other", "n"));
  assert.deepEqual(calls, ["exact:app.save", "prefix:app.open", "default:other"]);
});

test("unknown intent raises a structured error", async () => {
  const router = new IntentRouter();
  router.on("known", () => undefined);
  await assert.rejects(
    () => router.dispatch(new IntentEvent("1", "missing", "n")),
    (error) => error instanceof UnsupportedIntentError && error.intent === "missing" && error.code === "unsupported_intent",
  );
});

test("async handler is awaited", async () => {
  const router = new IntentRouter();
  const seen: Record<string, unknown> = {};
  router.on("slow.task", async (event) => { seen.intent = event.intent; return "publication-marker"; });
  const result = await router.dispatch(new IntentEvent("1", "slow.task", "n"));
  assert.equal(seen.intent, "slow.task");
  assert.equal(result, "publication-marker");
});

test("three drops trigger their intents", async () => {
  const { router, state } = inventoryFixture();
  await router.dispatch(dropInbound("backpack-compass", "equipment-zone"));
  await router.dispatch(dropInbound("backpack-gem", "crafting-zone"));
  await router.dispatch(dropInbound("backpack-potion", "discard-zone"));
  assert.deepEqual(state, { equipped: "compass", crafted: "gem", discarded: "potion" });
});

test("drop carries the resolved business payload", async () => {
  const { router } = inventoryFixture();
  const resolved = router.resolveInbound(dropInbound("backpack-compass", "equipment-zone")) as DropEvent;
  assert.ok(resolved instanceof DropEvent);
  assert.deepEqual(resolved.payload, { item_id: "compass", kind: "accessory" });
  assert.equal(resolved.source_key, "backpack-compass");
  assert.equal(resolved.target_key, "equipment-zone");
  assert.equal(resolved.placement, "into");
  assert.equal(resolved.frame_sequence, 1);
  assert.equal(resolved.generation, 1);
});

test("target rejection leaves state untouched", async () => {
  const { router, state } = inventoryFixture();
  await assert.rejects(
    () => router.dispatch(dropInbound("backpack-gem", "equipment-zone")),
    (error) => error instanceof DropRejectedError && error.code === "drop_rejected" && String(error.details.accepted) === "accessory",
  );
  assert.equal(state.equipped, null);
});

test("missing source or target is unknown_target, not rejection", async () => {
  const { router } = inventoryFixture();
  await assert.rejects(() => router.dispatch(dropInbound("backpack-compass", "ghost-zone")), UnknownTargetError);
  await assert.rejects(() => router.dispatch(dropInbound("ghost-item", "equipment-zone")), UnknownTargetError);
});

test("accepts-omitted target accepts any kind", async () => {
  const { router } = inventoryFixture();
  await router.dispatch(dropInbound("backpack-gem", "discard-zone"));
});

test("semantic intent envelope resolves to an IntentEvent", () => {
  const router = new IntentRouter();
  const resolved = router.resolveInbound({ kind: "semantic_intent", event: {
    event_id: "e", intent: "inventory.item.select", source_node_key: "row-1",
    payload: { item_id: { kind: "enum", value: "compass" } }, input_revision: 4,
    program_revision: { revision: 1 }, interaction: { interaction_id: "e", sequence: 2, renderer_epoch: 1 },
  } }) as IntentEvent;
  assert.ok(resolved instanceof IntentEvent);
  assert.equal(resolved.input_revision, 4);
  assert.equal((resolved.payload.item_id as any).value, "compass");
});

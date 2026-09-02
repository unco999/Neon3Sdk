import assert from "node:assert/strict";
import test from "node:test";
import * as sdk from "@neon3/sdk";

test("published package export exposes application API", () => {
  assert.equal(typeof sdk.NeonApp, "function");
  assert.equal(typeof sdk.ObservableStore, "function");
  assert.equal(typeof sdk.RuntimeSession, "function");
});

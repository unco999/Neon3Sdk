import assert from "node:assert/strict";
import test from "node:test";
import { NeonApp } from "../app.js";
import { ObservableStore } from "../store.js";

test("offline NeonApp routes a generic intent through one store transaction", async () => {
  const store = new ObservableStore({ selected: null });
  const app = NeonApp.offline({ client: {} as any, store });
  app.session.program = {
    surface_id: "surface.demo",
    program_revision: { program_id: "demo", revision: 1, schema_version: 1, capabilities: [] },
    input_schema: {},
    submissionResult: null,
  };
  app.intent("domain.select")((event: any) => store.value("selected").set(event.payload.key));
  const [outcome] = await app.runOnce([{ kind: "semantic_intent", event: { event_id: "evt-1", request_id: "evt-1", intent: "domain.select", source_node_key: "row", payload: { key: "alpha" }, input_revision: 0, program_revision: app.session.program.program_revision, interaction: { interaction_id: "evt-1", sequence: 1, renderer_epoch: 1 } } }]);
  assert.equal(outcome.response.status, "accepted");
  assert.deepEqual(store.value("selected").get(), { kind: "enum", value: "alpha" });
  assert.equal(app.session.inputRevision, 1);
  assert.equal(store.hasPendingChanges(), false);
});

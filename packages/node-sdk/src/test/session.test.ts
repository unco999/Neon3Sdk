/**
 * Stage 003 revision-aware UiSession tests against an in-memory fake runtime.
 *
 * Mirrors `packages/python-sdk/tests/test_session.py`: accepted external
 * frames echo the new input revision under `result.input.snapshot...`, host
 * inbound echoes it under `result.input_revision`, stale requests are
 * rejected with the frozen runtime codes, and duplicate event ids surface as
 * duplicate results.
 */

import assert from "node:assert/strict";
import test from "node:test";
import { RemoteError, StaleRevisionError } from "../errors.js";
import { RpcResponse, ServiceDescription, ServiceHealth } from "../protocol.js";
import { UiSession } from "../session.js";
import { UiClient, UiProgram } from "../ui.js";

class FakeRuntime {
  epoch = 4;
  inputRevision = 0;
  publishStuck = false;
  unknownTarget = false;
  frameRequests: number[] = [];
  hostRequests: number[] = [];
  private readonly seen = new Map<string, RpcResponse<unknown>>();
  private readonly appliedEventIds = new Set<string>();

  describe(): Promise<ServiceDescription> {
    return Promise.resolve({ service: "ui-runtime", protocol_version: { major: 1, minor: 0 }, endpoint: "headless://ui-runtime", epoch: this.epoch, capabilities: [] });
  }

  health(): Promise<ServiceHealth> {
    return Promise.resolve({ service: "ui-runtime", status: "healthy", epoch: this.epoch });
  }

  async call<T>(target: string, method: string, params: Record<string, unknown> = {}, options: { requestId?: string; idempotencyKey?: string } = {}): Promise<RpcResponse<T>> {
    const requestId = options.requestId ?? "req";
    if (method === "debug.ui.host.snapshot") {
      return this.response(requestId, "accepted", { result: { scalar_inputs: { input_revision: this.inputRevision, program_revision: null, values: {}, changed_slots: [] }, grid_inputs: [] } }) as RpcResponse<T>;
    }
    if (method === "ui.input.frame") return this.applyFrame(params, requestId, options.idempotencyKey ?? "") as RpcResponse<T>;
    if (method === "ui.host.inbound") return this.inbound(params, requestId, options.idempotencyKey ?? "") as RpcResponse<T>;
    throw new Error(`unexpected method ${method}`);
  }

  private applyFrame(frame: Record<string, unknown>, requestId: string, idempotencyKey: string): RpcResponse<unknown> {
    this.frameRequests.push(frame.expected_input_revision as number);
    const cached = this.seen.get(idempotencyKey);
    if (cached) return { ...cached, request_id: requestId };
    if (this.publishStuck || (frame.expected_input_revision as number) !== this.inputRevision) {
      return this.response(requestId, "rejected", { revision: this.inputRevision, error: { code: "ui_program_stale_input_revision", message: "input revision is stale" } });
    }
    this.inputRevision += 1;
    const result = { input: { snapshot: { scalar_inputs: { input_revision: this.inputRevision } } } };
    this.seen.set(idempotencyKey, this.response(requestId, "accepted", { revision: this.inputRevision, result }));
    return this.response(requestId, "accepted", { revision: this.inputRevision, result });
  }

  private inbound(inbound: Record<string, unknown>, requestId: string, idempotencyKey: string): RpcResponse<unknown> {
    const event = (inbound.event ?? {}) as Record<string, unknown>;
    this.hostRequests.push(event.input_revision as number);
    const eventId = event.event_id as string;
    if (this.unknownTarget) {
      return this.response(requestId, "rejected", { revision: this.inputRevision, error: { code: "ui_host_invalid_drag_drop", message: "drop key is not declared" } });
    }
    if (this.appliedEventIds.has(eventId)) {
      return this.response(requestId, "accepted", { revision: this.inputRevision, result: { semantic_intent: { status: "duplicate", event_id: eventId, accepted_input_revision: this.inputRevision, message: "seen" } } });
    }
    const cached = this.seen.get(idempotencyKey);
    if (cached) return { ...cached, request_id: requestId };
    if ((event.input_revision as number) !== this.inputRevision) {
      return this.response(requestId, "rejected", { revision: this.inputRevision, error: { code: "ui_host_stale_semantic_intent", message: "semantic intent revision is stale" } });
    }
    this.inputRevision += 1;
    this.appliedEventIds.add(eventId);
    const result = { input_revision: this.inputRevision, semantic_intent: { status: "accepted", event_id: eventId, message: "ok", accepted_input_revision: this.inputRevision } };
    this.seen.set(idempotencyKey, this.response(requestId, "accepted", { revision: this.inputRevision, result }));
    return this.response(requestId, "accepted", { revision: this.inputRevision, result });
  }

  private response(request_id: string, status: "accepted" | "rejected", extra: Partial<RpcResponse<unknown>> = {}): RpcResponse<unknown> {
    return { request_id, status, revision: extra.revision ?? null, result: extra.result ?? null, snapshot: null, error: extra.error ?? null };
  }
}

function mountedSession(runtime: FakeRuntime): UiSession {
  const ui = new UiClient(runtime as never);
  const session = new UiSession(ui);
  session.program = {
    surface_id: "surface.demo",
    program_revision: { program_id: "demo", revision: 1, schema_version: 1, capabilities: [] },
    input_schema: {},
    submissionResult: null,
  } as UiProgram;
  return session;
}

test("input revision strictly increases over 100 dispatches", async () => {
  const session = mountedSession(new FakeRuntime());
  const revisions: number[] = [];
  for (let index = 0; index < 100; index += 1) {
    const result = await session.dispatchIntent("demo.ping", {}, { sourceNodeKey: "row" });
    assert.equal(result.status, "accepted");
    revisions.push(result.input_revision);
  }
  assert.deepEqual(revisions, Array.from({ length: 100 }, (_, index) => index + 1));
  assert.equal(session.inputRevision, 100);
});

test("publish advances revision to the observed value", async () => {
  const session = mountedSession(new FakeRuntime());
  await session.publish([{ key: "count", value: { kind: "i32", value: 1 } }]);
  assert.equal(session.inputRevision, 1);
  await session.publish([{ key: "count", value: { kind: "i32", value: 2 } }]);
  assert.equal(session.inputRevision, 2);
});

test("duplicate event id does not reapply", async () => {
  const runtime = new FakeRuntime();
  const session = mountedSession(runtime);
  const before = await session.dispatchIntent("demo.save", {}, { sourceNodeKey: "row", eventId: "evt-fixed" });
  const after = await session.dispatchIntent("demo.save", {}, { sourceNodeKey: "row", eventId: "evt-fixed" });
  assert.equal(before.status, "accepted");
  assert.equal(after.status, "duplicate");
  assert.equal(session.inputRevision, 1);
  assert.equal(runtime.inputRevision, 1);
});

test("duplicate publish returns ledger without reapplying", async () => {
  const runtime = new FakeRuntime();
  const session = mountedSession(runtime);
  await session.publish([{ key: "a", value: { kind: "i32", value: 1 } }], { requestId: "req-pub" });
  await session.publish([{ key: "a", value: { kind: "i32", value: 2 } }], { requestId: "req-pub" });
  assert.equal(session.inputRevision, 1);
  assert.equal(runtime.frameRequests.length, 1);
});

test("runtime-level duplicate is surfaced not raised", async () => {
  const runtime = new FakeRuntime();
  const session = mountedSession(runtime);
  await session.dispatchIntent("demo.x", {}, { eventId: "evt-dup", sourceNodeKey: "row" });
  const fresh = mountedSession(runtime);
  const result = await fresh.dispatchIntent("demo.x", {}, { eventId: "evt-dup", sourceNodeKey: "row" });
  assert.equal(result.status, "duplicate");
  assert.equal(result.code, "duplicate_event");
});

test("stale publish refreshes once then succeeds", async () => {
  const runtime = new FakeRuntime();
  const session = mountedSession(runtime);
  runtime.inputRevision = 3;
  session.inputRevision = 0;
  await session.publish([{ key: "a", value: { kind: "i32", value: 1 } }], { requestId: "req-stale" });
  assert.equal(session.inputRevision, 4);
});

test("persistent stale raises typed error", async () => {
  const runtime = new FakeRuntime();
  const session = mountedSession(runtime);
  runtime.publishStuck = true;
  await assert.rejects(
    () => session.publish([{ key: "a", value: { kind: "i32", value: 1 } }], { requestId: "req-stuck" }),
    (error) => error instanceof StaleRevisionError && error.details.refreshed === true && error.details.runtime_code === "ui_program_stale_input_revision",
  );
});

test("stale dispatch distinguishes unknown target", async () => {
  const runtime = new FakeRuntime();
  runtime.unknownTarget = true;
  const session = mountedSession(runtime);
  await assert.rejects(
    () => session.dispatchIntent("demo.drop", {}, { eventId: "evt-t", sourceNodeKey: "row" }),
    (error) => error instanceof RemoteError && error.sdkCode === "unknown_target",
  );
});

test("stale dispatch refreshes and raises with refresh flag", async () => {
  const runtime = new FakeRuntime();
  const session = mountedSession(runtime);
  runtime.inputRevision = 7;
  session.inputRevision = 0;
  await assert.rejects(
    () => session.dispatchIntent("demo.ping", {}, { eventId: "evt-s1", sourceNodeKey: "row" }),
    (error) => error instanceof StaleRevisionError && error.details.refreshed === true,
  );
  assert.equal(session.inputRevision, 7);
});

test("buildIntentEvent embeds revision and epoch", async () => {
  const session = mountedSession(new FakeRuntime());
  const event = await session.buildIntentEvent("demo.ping", { k: { kind: "i32", value: 1 } }, { sourceNodeKey: "row" });
  assert.equal(event.program_revision.program_id, "demo");
  assert.equal(event.input_revision, 0);
  assert.equal(event.interaction.renderer_epoch, 4);
  assert.ok(event.idempotency_key.startsWith("intent:"));
});

/**
 * Stage 001 typed primitive tests: envelope parsing and typed wire helpers.
 */

import assert from "node:assert/strict";
import test from "node:test";
import { parseRpcResponse, ProtocolShapeError } from "../protocol.js";
import { NeonClient } from "../client.js";
import { PointerEvent } from "../render.js";
import { keyEventToWire } from "../input.js";
import { EventSubscription } from "../event.js";
import { TransportError } from "../errors.js";

test("parseRpcResponse accepts the canonical rejected envelope", () => {
  const response = parseRpcResponse({
    request_id: "req-0001",
    status: "rejected",
    revision: null,
    result: null,
    snapshot: null,
    error: { code: "ui_program_stale_input_revision", message: "stale" },
  });
  assert.equal(response.status, "rejected");
  assert.equal(response.error?.code, "ui_program_stale_input_revision");
});

test("parseRpcResponse rejects missing, extra, or malformed keys", () => {
  assert.throws(() => parseRpcResponse({ request_id: "r", status: "accepted" }), ProtocolShapeError);
  assert.throws(() => parseRpcResponse({ request_id: "r", status: "accepted", revision: null, result: null, snapshot: null, error: null, extra: 1 }), ProtocolShapeError);
  assert.throws(() => parseRpcResponse({ request_id: 1, status: "accepted", revision: null, result: null, snapshot: null, error: null }), ProtocolShapeError);
  assert.throws(() => parseRpcResponse({ request_id: "r", status: "maybe", revision: null, result: null, snapshot: null, error: null }), ProtocolShapeError);
});

test("pointer event serializes the canonical wire shape", () => {
  const event = new PointerEvent("down", "surface.demo", [10, 20], 1, 2, 3, 4, "primary");
  const wire = event.toWire();
  assert.equal(wire.event_type, "down");
  assert.equal(wire.delta_mode, "pixel");
  assert.deepEqual(wire.buttons, ["primary"]);
  assert.equal(wire.frame_sequence, 4);
  assert.throws(() => new PointerEvent("swipe", "surface.demo", [0, 0], 1, 1, 1, 1).toWire(), /invalid pointer event type/);
});

test("keyboard event wire validation", () => {
  assert.deepEqual(keyEventToWire({ key: "a", action: "down" }), { key: "a", action: "down", modifiers: [], repeat: false });
  assert.throws(() => keyEventToWire({ key: "a", action: "hold" as "down" }), /down or up/);
});

test("client rejects malformed endpoints and frame bounds", () => {
  assert.throws(() => new NeonClient("example.com:39102"), /loopback/);
  assert.throws(() => new NeonClient("127.0.0.1:0"), /between 1 and 65535/);
  assert.throws(() => new NeonClient("127.0.0.1:notaport"), /host:port/);
  assert.throws(() => new NeonClient("127.0.0.1:70000"), /between 1 and 65535/);
  assert.throws(() => new NeonClient("127.0.0.1:39102", { timeoutMs: 0 }), /timeoutMs must be positive/);
  assert.throws(() => new NeonClient("127.0.0.1:39102", { maxFrameSize: -1 }), /maxFrameSize must be a positive integer/);
});

test("bounded receive validates its event cap and honors timeout", async () => {
  const socket = { destroy() {} } as never;
  const blockingReader = {
    next(timeoutMs?: number) {
      return new Promise<never>((_, reject) => {
        if (timeoutMs !== undefined) setTimeout(() => reject(new TransportError("event recv timeout")), timeoutMs);
      });
    },
  } as never;
  const subscription = new EventSubscription(socket, blockingReader, [], 10);
  await assert.rejects(() => subscription.receive(0), TypeError);
  assert.deepEqual(await subscription.receive(1, 5), []);

  const readyReader = { next: () => Promise.resolve({ kind: "delivery", event: { name: "demo", payload: {} } }) } as never;
  const flowing = new EventSubscription(socket, readyReader, [], 10);
  const events = await flowing.receive(2);
  assert.equal(events.length, 2);
});

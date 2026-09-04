/**
 * Android transport contract tests.
 *
 * Unit tests never touch adb. The integration test (marked with
 * NEON3_ANDROID_INTEGRATION=1) runs against the real Android host and covers
 * the whole lifecycle in one case: start (adb forward + health wait),
 * service.health/describe, and clean shutdown. It skips otherwise so plain
 * `npm test` never hangs on adb.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { ANDROID_HOST_ENDPOINT, ANDROID_HOST_PORT, AndroidSession } from "../android.js";
import { NeonClient } from "../client.js";

const INTEGRATION = process.env.NEON3_ANDROID_INTEGRATION === "1";

test("endpoint defaults are loopback and the Android host port", () => {
  assert.equal(ANDROID_HOST_ENDPOINT, "127.0.0.1:43100");
  assert.equal(ANDROID_HOST_PORT, 43100);
});

test("NeonClient rejects non-loopback unless allowNonLoopback is set", () => {
  assert.throws(() => new NeonClient("192.168.1.50:43100"), /loopback/);
  const client = new NeonClient("192.168.1.50:43100", { allowNonLoopback: true });
  assert.equal(client.host, "192.168.1.50");
  assert.equal(client.port, 43100);
});

test("full Android session lifecycle against the real host", { skip: !INTEGRATION }, async (t) => {
  const session = new AndroidSession({ timeoutMs: 20000 });
  const handle = await session.start();
  t.diagnostic(`connected to ${handle.device} at ${handle.endpoint} (forward=${handle.useForward})`);
  assert.ok(handle.endpoint.length > 0);
  const client = new NeonClient(handle.endpoint, { origin: "android-contract-test", kind: "cli", allowNonLoopback: true });
  const health = await client.health("wgpu-runtime");
  assert.equal(health.status, "healthy");
  const describe = await client.describe("wgpu-runtime");
  assert.ok(describe.epoch > 0);
  await session.stop();
  t.diagnostic("host shut down cleanly and adb forward removed");
});
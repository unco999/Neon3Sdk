import assert from "node:assert/strict";
import net from "node:net";
import test from "node:test";
import { NeonClient } from "../index.js";

test("Node client uses Neon3 big-endian framed RPC", async () => {
  const server = net.createServer((socket) => {
    let buffer = Buffer.alloc(0);
    socket.on("data", (chunk) => {
      buffer = Buffer.concat([buffer, chunk]);
      if (buffer.length < 4 || buffer.length < buffer.readUInt32BE(0) + 4) return;
      const request = JSON.parse(buffer.subarray(4).toString("utf8"));
      const body = Buffer.from(JSON.stringify({ request_id: request.request_id, status: "accepted", revision: null, result: { service: "test", status: "healthy", epoch: 1 }, snapshot: null, error: null }));
      const frame = Buffer.alloc(4 + body.length);
      frame.writeUInt32BE(body.length, 0);
      body.copy(frame, 4);
      socket.end(frame);
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", () => resolve()));
  const address = server.address();
  assert.ok(address && typeof address !== "string");
  const health = await new NeonClient(`127.0.0.1:${address.port}`).health("test");
  assert.equal(health.status, "healthy");
  await new Promise<void>((resolve) => server.close(() => resolve()));
});

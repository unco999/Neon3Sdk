import { NeonClient, RenderClient, RuntimeConfig, RuntimeSession, UiClient } from "../index.js";

const external = process.env.NEON_EXTERNAL === "1";
const config = { ...(process.env.NEON_ROOT ? { neonRoot: process.env.NEON_ROOT } : {}), mode: (external ? "external_surface" : "headless") as RuntimeConfig["mode"] } satisfies RuntimeConfig;
const session = new RuntimeSession(config);
await session.start();
try {
  const ui = new UiClient(new NeonClient("127.0.0.1:39102", { origin: "neon3-node-api-probe" }));
  const renderer = new RenderClient(new NeonClient("127.0.0.1:39103", { origin: "neon3-node-api-probe", kind: external ? "external_host" : "cli" }));
  const description = await renderer.client.describe("wgpu-runtime");
  console.log(JSON.stringify({ stage: "describe", status: "passed", service: description.service, capabilities: description.capabilities }));
  console.log(JSON.stringify({ stage: "diagnostics", status: "passed", value: await renderer.diagnostics() }));
  if (external) {
    const surface = await renderer.openSurface({ sessionId: "node-probe-session", surfaceId: "node-probe-surface", kind: "screen_ui", width: 320, height: 180, targets: [{ targetId: "node-probe-color", kind: "color", format: "rgba8unorm" }] });
    console.log(JSON.stringify({ stage: "surface.open", status: "passed", descriptor: surface.descriptor }));
    console.log(JSON.stringify({ stage: "surface.acquire", status: "passed", handles: await surface.acquire() }));
    console.log(JSON.stringify({ stage: "surface.frame", status: "passed", frame: await surface.frame() }));
  }
  console.log(JSON.stringify({ stage: "ui.snapshot", status: "passed", value: await ui.snapshot() }));
  console.log(JSON.stringify({ stage: "result", status: "passed" }));
} finally {
  await session.stop();
}

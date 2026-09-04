/**
 * Shared surface texture + PNG save contract test (Windows GPU).
 *
 * Spawns the Neon3 headless external GPU server (DX12, no window), opens a
 * shared surface through the public SDK API, saves the surface texture to a
 * PNG file, and verifies the artifact. Skips cleanly when the runtime binary
 * is unavailable or the host has no DX12 adapter, so non-GPU CI stays green.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { NeonClient } from "../client.js";
import { RenderClient } from "../render.js";

const ENDPOINT = "127.0.0.1:43113";
const PORT = 43113;

function neonRuntimeBin(): string | null {
  const override = process.env.NEON3_RUNTIME_BIN;
  if (override) return override;
  const candidates = [
    join(process.cwd(), "..", "..", "..", "..", "Neon3", "target", "debug", "neon-wgpu-runtime.exe"),
    join(process.env.LOCALAPPDATA ?? "", "Neon3Sdk", "runtime", "latest", "neon-wgpu-runtime.exe"),
  ];
  return candidates.find((candidate) => existsSync(candidate)) ?? null;
}

test("SDK opens a shared surface and saves its texture as PNG", { skip: process.platform !== "win32" || !process.env.NEON3_SURFACE_PNG_INTEGRATION }, async (t) => {
  const bin = neonRuntimeBin();
  if (!bin || !existsSync(bin)) {
    t.skip(`runtime binary not found (NEON_ROOT?); skipped surface PNG integration`);
    return;
  }
  const server = spawn(bin, ["--headless-external-server", `${ENDPOINT}`], { stdio: "ignore", windowsHide: true });
  const dir = join(tmpdir(), "neon3-surface-png-test");
  mkdirSync(dir, { recursive: true });
  const pngPath = join(dir, "surface.png");
  let client: NeonClient | null = null;
  try {
    // Wait for the server to accept connections.
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline) {
      try {
        client = new NeonClient(ENDPOINT, { origin: "surface-png-test", kind: "cli", timeoutMs: 1000 });
        const health = await client.health("wgpu-runtime");
        if (health.status === "healthy") break;
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 200));
      }
    }
    assert.ok(client, "headless external server did not become healthy in time");
    // The health probe client uses a short timeout; the surface workflow needs
    // longer for DX12 shared-resource creation, so use a fresh client here.
    client = new NeonClient(ENDPOINT, { origin: "surface-png-test", kind: "cli", timeoutMs: 8000 });
    const renderer = new RenderClient(client, "wgpu-runtime");

    const flow = await client.call("wgpu-runtime", "ui.flow.submit", { source: "version 1\nsurface example revision 1\nsurface root\n" });
    assert.equal(flow.status, "accepted");

    const surface = await renderer.openSurface({
      sessionId: "test-session",
      surfaceId: "example",
      kind: "screen_ui",
      width: 320,
      height: 200,
      bufferCount: 2,
    });
    assert.ok(surface.generation >= 0);

    // Give the render loop a moment to complete at least one frame.
    await new Promise((resolve) => setTimeout(resolve, 1200));

    const capture = (await surface.savePng(pngPath)) as { artifact_path?: string; frame_sequence?: number } | null;
    assert.ok(capture && typeof capture.artifact_path === "string");
    assert.ok(existsSync(pngPath), "PNG artifact must exist on disk");
    const bytes = readFileSync(pngPath);
    const header = bytes.subarray(0, 8);
    assert.deepEqual([...header], [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], "artifact must be a valid PNG");
    t.diagnostic(`saved ${capture.artifact_path} (${bytes.length} bytes, frame ${capture.frame_sequence})`);
  } finally {
    try {
      if (client) await client.call("wgpu-runtime", "service.shutdown", {}, { raiseForStatus: false });
    } catch { /* ignore */ }
    server.kill();
    try { rmSync(dir, { recursive: true, force: true }); } catch { /* ignore */ }
  }
});
/**
 * Custom-shader package contract test.
 *
 * - Unit: `shaderSourceDigest` matches the FNV-1a 64-bit runtime fingerprint.
 * - Integration (skipped unless NEON3_SHADER_INTEGRATION=1 and a runtime
 *   binary exists): boots the headless external GPU server, registers a small
 *   WGSL package through the public SDK API, and reads it back with
 *   `shaderState`.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { NeonClient } from "../client.js";
import { RenderClient, ShaderPackage, shaderSourceDigest } from "../render.js";

const ENDPOINT = "127.0.0.1:43114";

test("shaderSourceDigest matches the FNV-1a 64-bit runtime fingerprint", () => {
  // Standard FNV-1a 64-bit: offset basis 0xcbf29ce484222325, prime 0x100000001b3.
  assert.equal(shaderSourceDigest(new TextEncoder().encode("A")), "af63fc4c860222ec");
  assert.equal(
    shaderSourceDigest(new TextEncoder().encode("@fragment fn material() {}")),
    shaderSourceDigest(new TextEncoder().encode("@fragment fn material() {}")),
  );
  assert.notEqual(
    shaderSourceDigest(new TextEncoder().encode("a")),
    shaderSourceDigest(new TextEncoder().encode("b")),
  );
});

function neonRuntimeBin(): string | null {
  const override = process.env.NEON3_RUNTIME_BIN;
  if (override) return override;
  const candidates = [
    join(process.cwd(), "..", "..", "..", "..", "Neon3", "target", "debug", "neon-wgpu-runtime.exe"),
    join(process.env.LOCALAPPDATA ?? "", "Neon3Sdk", "runtime", "latest", "neon-wgpu-runtime.exe"),
  ];
  return candidates.find((candidate) => existsSync(candidate)) ?? null;
}

test("SDK registers a shader package and reads it back", { skip: !process.env.NEON3_SHADER_INTEGRATION }, async (t) => {
  const bin = neonRuntimeBin();
  if (!bin || !existsSync(bin)) {
    t.skip("runtime binary not found; skipped shader integration");
    return;
  }
  const server = spawn(bin, ["--headless-external-server", ENDPOINT], { stdio: "ignore", windowsHide: true });
  try {
    const deadline = Date.now() + 15000;
    let client: NeonClient | null = null;
    while (Date.now() < deadline) {
      try {
        client = new NeonClient(ENDPOINT, { kind: "app_host" });
        const health = await client.health("wgpu-runtime");
        if (health.status === "healthy") break;
      } catch {
        // Server still starting.
      }
      await new Promise((resolve) => setTimeout(resolve, 150));
    }
    assert.ok(client, "headless server must become healthy");
    const source = new TextEncoder().encode(
      "@fragment fn material() -> @location(0) vec4<f32> { return vec4(0.0); }",
    );
    const pkg: ShaderPackage = {
      package_id: "pulse-glow",
      version: 1,
      source_digest: shaderSourceDigest(source),
      source_bytes: Array.from(source),
      entry_point: "material",
      fallback: "standard_ui",
      parameters: [],
    };
    const render = new RenderClient(client);
    const registered = (await render.registerShader(pkg)) as { status: string };
    assert.equal(registered.status, "registered");
    const state = (await render.shaderState()) as { count: number; packages: Array<{ package_id: string; source_digest: string }> };
    assert.equal(state.count, 1);
    assert.equal(state.packages[0].package_id, "pulse-glow");
    assert.equal(state.packages[0].source_digest, pkg.source_digest);
  } finally {
    server.kill();
  }
});
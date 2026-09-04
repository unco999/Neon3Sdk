/**
 * Android transport for the Neon3 Node SDK.
 *
 * The Neon3 Android Host runs inside an APK foreground service on
 * 127.0.0.1:43100 (headless, no window). This session locates the device,
 * establishes `adb forward` (or direct device IP), waits for the headless
 * host health, and shuts it down cleanly on stop. The wire contract and
 * target semantics are identical to the desktop runtime; only the bootstrap
 * differs.
 */
import { execFile } from "node:child_process";
import { join } from "node:path";
import { access, constants } from "node:fs/promises";
import { NeonClient } from "./client.js";

export const ANDROID_HOST_ENDPOINT = "127.0.0.1:43100";
export const ANDROID_HOST_PORT = 43100;

export interface AndroidConfig {
  /** adb executable. Defaults to ANDROID_HOME/platform-tools/adb or PATH. */
  adb?: string;
  /** Device serial (e.g. emulator-5554). Defaults to the first connected device. */
  device?: string;
  /** Use `adb forward tcp:43100 tcp:43100`. Default true (loopback endpoint). */
  useForward?: boolean;
  /** Direct device IP when not using adb forward. Requires allowNonLoopback. */
  host?: string;
  /** Host port when not using adb forward. Default 43100. */
  port?: number;
  /** Wait budget for the headless host to become healthy. Default 15000ms. */
  timeoutMs?: number;
}

export interface AndroidSessionHandle {
  /** Loopback endpoint after adb forward, or device host:port for direct. */
  endpoint: string;
  device: string;
  useForward: boolean;
}

async function resolveAdb(config: AndroidConfig): Promise<string> {
  if (config.adb) return config.adb;
  const sdkRoot = process.env.ANDROID_HOME ?? process.env.ANDROID_SDK_ROOT;
  if (sdkRoot) {
    const candidate = join(sdkRoot, "platform-tools", process.platform === "win32" ? "adb.exe" : "adb");
    try { await access(candidate, constants.X_OK); return candidate; } catch { /* fall through */ }
  }
  return "adb";
}

function runAdb(adb: string, args: string[], timeoutMs: number): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(adb, args, { timeout: timeoutMs, windowsHide: true }, (error, stdout, stderr) => {
      if (error) reject(new Error(`adb ${args.join(" ")} failed: ${(stderr || error.message).trim()}`));
      else resolve(stdout);
    });
  });
}

export class AndroidSession {
  readonly config: AndroidConfig;
  /** Resolved endpoint after start(): loopback after adb forward, or device host:port for direct. */
  endpoint = "";
  private adb = "adb";
  private device = "";
  private forwardActive = false;
  private stopped = false;

  constructor(config: AndroidConfig = {}) {
    this.config = config;
  }

  /** Locate the device, establish the endpoint, and wait for host health. */
  async start(): Promise<AndroidSessionHandle> {
    this.adb = await resolveAdb(this.config);
    const useForward = this.config.useForward ?? true;
    let endpoint: string;
    if (!useForward && this.config.host) {
      this.device = this.config.device ?? this.config.host;
      endpoint = `${this.config.host}:${this.config.port ?? ANDROID_HOST_PORT}`;
    } else {
      this.device = await this.resolveDevice();
      if (this.config.device && this.device !== this.config.device) {
        throw new Error(`adb device ${this.config.device} is not connected`);
      }
      await runAdb(this.adb, ["-s", this.device, "forward", `tcp:${ANDROID_HOST_PORT}`, `tcp:${ANDROID_HOST_PORT}`], 15000);
      this.forwardActive = true;
      endpoint = ANDROID_HOST_ENDPOINT;
    }
    await this.waitHealthy(endpoint);
    this.endpoint = endpoint;
    return { endpoint, device: this.device, useForward };
  }

  /** Stop the host cleanly (service.shutdown) and remove adb forward. */
  async stop(): Promise<void> {
    if (this.stopped) return;
    this.stopped = true;
    try {
      const client = new NeonClient(ANDROID_HOST_ENDPOINT, { origin: "neon3-node-android", kind: "cli", timeoutMs: 3000, allowNonLoopback: true });
      await client.call("wgpu-runtime", "service.shutdown", {}, { raiseForStatus: false });
    } catch { /* host may already be gone */ }
    if (this.forwardActive) {
      try { await runAdb(this.adb, ["-s", this.device, "forward", "--remove", `tcp:${ANDROID_HOST_PORT}`], 10000); } catch { /* ignore */ }
      this.forwardActive = false;
    }
  }

  private async resolveDevice(): Promise<string> {
    const output = await runAdb(this.adb, ["devices"], 10000);
    const lines = output.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    const devices = lines
      .slice(1)
      .filter((line) => !line.endsWith("offline") && !line.endsWith("unauthorized"))
      .map((line) => line.split(/\s+/)[0])
      .filter(Boolean);
    if (this.config.device) {
      if (!devices.includes(this.config.device)) throw new Error(`adb device ${this.config.device} is not connected`);
      return this.config.device;
    }
    if (devices.length === 0) throw new Error("no adb devices found; start an emulator or connect a device");
    return devices[0];
  }

  private async waitHealthy(endpoint: string): Promise<void> {
    const timeoutMs = this.config.timeoutMs ?? 15000;
    const deadline = Date.now() + timeoutMs;
    let lastError: unknown = null;
    while (Date.now() < deadline) {
      try {
        const client = new NeonClient(endpoint, { origin: "neon3-node-android", kind: "cli", timeoutMs: 1000, allowNonLoopback: true });
        const health = await client.health("wgpu-runtime");
        if (health.status === "healthy") return;
      } catch (error) { lastError = error; }
      await new Promise((resolve) => setTimeout(resolve, 150));
    }
    throw new Error(`Timed out waiting for Neon3 Android host at ${endpoint}: ${String(lastError)}`);
  }
}
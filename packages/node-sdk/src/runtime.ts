import { spawn, ChildProcess, execFile } from "node:child_process";
import { access, mkdir, unlink, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { homedir } from "node:os";
import { ProxyAgent } from "undici";
import { NeonClient } from "./client.js";

export const NEON3_RUNTIME_VERSION = "v0.2.1";
const NEON3_RUNTIME_REPOSITORY = "unco999/Neon3-CiJian";
const NEON3_RUNTIME_ASSET = `neon3-runtime-windows-x86_64-${NEON3_RUNTIME_VERSION}.zip`;

export type RuntimeMode = "windowed" | "headless" | "external_surface";
export type RuntimeProfile = "auto" | "debug" | "release";
export interface RuntimeConfig { neonRoot?: string; mode?: RuntimeMode; profile?: RuntimeProfile; eventd?: string; ui?: string; wgpu?: string; domain?: string; timeoutMs?: number; }

export class RuntimeSession {
  private processes: ChildProcess[] = [];
  readonly config: Required<RuntimeConfig>;
  private executableDir = "";
  private selectedProfile: Exclude<RuntimeProfile, "auto"> = "debug";
  constructor(config: RuntimeConfig) {
    this.config = { neonRoot: defaultNeonRoot(), mode: "windowed", profile: (process.env.NEON_PROFILE as RuntimeProfile | undefined) ?? "auto", eventd: "127.0.0.1:39101", ui: "127.0.0.1:39102", wgpu: "127.0.0.1:39103", domain: "127.0.0.1:39104", timeoutMs: 15000, ...config };
  }
  get activeProfile(): Exclude<RuntimeProfile, "auto"> { return this.selectedProfile; }
  async start(): Promise<void> {
    this.executableDir = await this.findExecutableDir();
    const specs: Array<[string, string, string[]]> = [
      ["eventd", join(this.executableDir, "neon-eventd.exe"), ["--server", this.config.eventd, "1"]],
      ["wgpu", join(this.executableDir, "neon-wgpu-runtime.exe"), this.wgpuArgs()],
      ["ui", join(this.executableDir, "neon-ui-runtime.exe"), ["--forward-server", this.config.ui, this.config.wgpu, this.config.domain, "--eventd", this.config.eventd]],
    ];
    try {
      for (const [name, executable, args] of specs) { await access(executable); this.processes.push(spawn(executable, args, { cwd: this.config.neonRoot, stdio: "ignore", windowsHide: false })); void name; }
      await this.waitReady();
    } catch (error) { await this.stop(); throw error; }
  }
  private wgpuArgs(): string[] { return this.config.mode === "headless" ? ["--headless-server", this.config.wgpu] : ["--window-server", this.config.wgpu, this.config.ui, "--eventd", this.config.eventd]; }
  private async findExecutableDir(): Promise<string> {
    const requested = this.config.profile;
    const profiles: Array<Exclude<RuntimeProfile, "auto">> = requested === "auto" ? ["release", "debug"] : [requested];
    for (const profile of profiles) {
      const directory = join(this.config.neonRoot, "target", profile);
      try {
        await Promise.all(["neon-eventd.exe", "neon-wgpu-runtime.exe", "neon-ui-runtime.exe"].map((name) => access(join(directory, name))));
        this.selectedProfile = profile;
        return directory;
      } catch {
        // Try the next profile so a source checkout remains convenient in development.
      }
    }
    if ((requested === "auto" || requested === "release") && !process.env.NEON_ROOT && this.config.neonRoot === defaultNeonRoot()) {
      const downloadedRoot = await this.ensureDownloadedRuntime();
      this.selectedProfile = "release";
      return join(downloadedRoot, "target", "release");
    }
    throw new Error(`Neon3 runtime binaries not found under ${this.config.neonRoot}/target (${profiles.join(", ")})`);
  }
  private async ensureDownloadedRuntime(): Promise<string> {
    const cacheRoot = join(process.env.LOCALAPPDATA ?? join(homedir(), "AppData", "Local"), "Neon3Sdk", "runtime", NEON3_RUNTIME_VERSION);
    const binaries = ["neon-eventd.exe", "neon-wgpu-runtime.exe", "neon-ui-runtime.exe"];
    try { await Promise.all(binaries.map(name => access(join(cacheRoot, "target", "release", name)))); return cacheRoot; } catch { /* download below */ }
    await mkdir(cacheRoot, { recursive: true });
    const archive = join(cacheRoot, `${NEON3_RUNTIME_ASSET}.download`);
    const url = `https://github.com/${NEON3_RUNTIME_REPOSITORY}/releases/download/${NEON3_RUNTIME_VERSION}/${NEON3_RUNTIME_ASSET}`;
    const downloadTimeoutMs = Math.max(this.config.timeoutMs, 180000);
    await download(url, archive, downloadTimeoutMs);
    await new Promise<void>((resolve, reject) => execFile("tar", ["-xf", archive, "-C", cacheRoot], { timeout: downloadTimeoutMs }, error => error ? reject(error) : resolve()));
    await unlink(archive).catch(() => undefined);
    await Promise.all(binaries.map(name => access(join(cacheRoot, "target", "release", name))));
    return cacheRoot;
  }
  private async waitReady(): Promise<void> {
    const deadline = Date.now() + this.config.timeoutMs;
    for (const [target, endpoint] of [["eventd", this.config.eventd], ["wgpu-runtime", this.config.wgpu], ["ui-runtime", this.config.ui]] as const) {
      while (Date.now() < deadline) {
        try {
          if ((await new NeonClient(endpoint, { timeoutMs: 500 }).health(target)).status === "healthy") break;
        } catch {}
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      if (Date.now() >= deadline) throw new Error(`Timed out waiting for ${target} on ${endpoint}`);
    }
  }
  async stop(): Promise<void> { for (const process of this.processes.reverse()) { if (!process.killed) process.kill(); } this.processes = []; }
}

function defaultNeonRoot(): string {
  if (process.env.NEON_ROOT) return process.env.NEON_ROOT;
  return join(process.env.LOCALAPPDATA ?? join(homedir(), "AppData", "Local"), "Neon3Sdk", "runtime", NEON3_RUNTIME_VERSION);
}

async function download(url: string, destination: string, timeoutMs: number): Promise<void> {
  const proxy = process.env.HTTPS_PROXY ?? process.env.HTTP_PROXY ?? process.env.https_proxy ?? process.env.http_proxy;
  const response = await fetch(url, {
    signal: AbortSignal.timeout(timeoutMs),
    redirect: "follow",
    ...(proxy ? { dispatcher: new ProxyAgent(proxy) } : {}),
  } as RequestInit);
  if (!response.ok) throw new Error(`Neon3 runtime download failed: HTTP ${response.status}`);
  await writeFile(destination, Buffer.from(await response.arrayBuffer()));
}

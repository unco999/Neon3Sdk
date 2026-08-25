import { spawn, ChildProcess } from "node:child_process";
import { access } from "node:fs/promises";
import { NeonClient } from "./client.js";

export type RuntimeMode = "windowed" | "headless" | "external_surface";
export interface RuntimeConfig { neonRoot: string; mode?: RuntimeMode; eventd?: string; ui?: string; wgpu?: string; domain?: string; timeoutMs?: number; }

export class RuntimeSession {
  private processes: ChildProcess[] = [];
  readonly config: Required<RuntimeConfig>;
  constructor(config: RuntimeConfig) { this.config = { mode: "windowed", eventd: "127.0.0.1:39101", ui: "127.0.0.1:39102", wgpu: "127.0.0.1:39103", domain: "127.0.0.1:39104", timeoutMs: 15000, ...config }; }
  async start(): Promise<void> {
    const debug = `${this.config.neonRoot}/target/debug`;
    const specs: Array<[string, string, string[]]> = [
      ["eventd", `${debug}/neon-eventd.exe`, ["--server", this.config.eventd, "1"]],
      ["wgpu", `${debug}/neon-wgpu-runtime.exe`, this.wgpuArgs()],
      ["ui", `${debug}/neon-ui-runtime.exe`, ["--forward-server", this.config.ui, this.config.wgpu, this.config.domain, "--eventd", this.config.eventd]],
    ];
    try {
      for (const [name, executable, args] of specs) { await access(executable); this.processes.push(spawn(executable, args, { cwd: this.config.neonRoot, stdio: "ignore", windowsHide: false })); void name; }
      await this.waitReady();
    } catch (error) { await this.stop(); throw error; }
  }
  private wgpuArgs(): string[] { return this.config.mode === "headless" ? ["--headless-server", this.config.wgpu] : ["--window-server", this.config.wgpu, this.config.ui]; }
  private async waitReady(): Promise<void> { const deadline = Date.now() + this.config.timeoutMs; for (const [target, endpoint] of [["eventd", this.config.eventd], ["wgpu-runtime", this.config.wgpu], ["ui-runtime", this.config.ui]] as const) { while (Date.now() < deadline) { try { if ((await new NeonClient(endpoint, { timeoutMs: 500 }).health(target)).status === "healthy") break; } catch {} await new Promise((resolve) => setTimeout(resolve, 100)); } } }
  async stop(): Promise<void> { for (const process of this.processes.reverse()) { if (!process.killed) process.kill(); } this.processes = []; }
}

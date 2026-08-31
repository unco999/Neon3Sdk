import { NeonClient, RuntimeSession } from "../index.js";

const root = process.env.NEON_ROOT;
const profile = (process.env.NEON_PROFILE as "auto" | "debug" | "release" | undefined) ?? "auto";
const runtime = new RuntimeSession({ ...(root ? { neonRoot: root } : {}), profile, mode: "headless", timeoutMs: 15000 });
const callbacks: Array<Record<string, unknown>> = [];
const emit = (event: Record<string, unknown>) => { callbacks.push(event); console.log(JSON.stringify(event)); };

try {
  emit({ stage: "input", root, profile, mode: "headless", sequence: 0 });
  await runtime.start();
  emit({ stage: "runtime", status: "started", selected_profile: runtime.activeProfile, sequence: 1 });
  for (const [sequence, [target, endpoint]] of [
    [2, ["eventd", runtime.config.eventd]],
    [3, ["wgpu-runtime", runtime.config.wgpu]],
    [4, ["ui-runtime", runtime.config.ui]],
  ] as const) {
    const health = await new NeonClient(endpoint, { timeoutMs: 1000 }).health(target);
    emit({ stage: "health", target, endpoint, sequence, status: health.status });
    if (health.status !== "healthy") throw new Error(`${target} reported ${health.status}`);
  }
  emit({ stage: "result", status: "passed", sequence: 5, callbacks: callbacks.length + 1 });
} catch (error) {
  emit({ stage: "result", status: "failed", sequence: 5, error: error instanceof Error ? error.message : String(error) });
  process.exitCode = 1;
} finally {
  await runtime.stop();
}

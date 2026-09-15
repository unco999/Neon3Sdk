/**
 * Structured logging for the Neon3 SDK.
 *
 * Usage:
 * ```ts
 * import { configure, getLogger } from "@neon3/sdk/log";
 * configure("debug");
 * const log = getLogger("rpc");
 * ```
 *
 * Honors the `NEON3_LOG_LEVEL` env var (debug/info/warn/error) on first call.
 */

let configured = false;
type Level = "debug" | "info" | "warn" | "error";
let level: Level = "warn";

const ORDER: Record<Level, number> = { debug: 10, info: 20, warn: 30, error: 40 };

export function configure(l: Level | string = "warn"): void {
  if (configured) return;
  level = (l as Level) in ORDER ? (l as Level) : "warn";
  const env = (process.env.NEON3_LOG_LEVEL as string | undefined)?.toLowerCase();
  if (env && env in ORDER) level = env as Level;
  configured = true;
}

export function getLogger(name = ""): {
  debug: (msg: string, ...args: unknown[]) => void;
  info: (msg: string, ...args: unknown[]) => void;
  warn: (msg: string, ...args: unknown[]) => void;
  error: (msg: string, ...args: unknown[]) => void;
} {
  if (!configured) configure();
  const prefix = name ? `neon3/${name}` : "neon3";
  const emit = (lvl: Level, msg: string, args: unknown[]) => {
    if (ORDER[lvl] < ORDER[level]) return;
    const ts = new Date().toISOString();
    // eslint-disable-next-line no-console
    console.error(`${ts} ${lvl.toUpperCase().padEnd(5)} ${prefix}: ${msg}`, ...args);
  };
  return {
    debug: (m, ...a) => emit("debug", m, a),
    info: (m, ...a) => emit("info", m, a),
    warn: (m, ...a) => emit("warn", m, a),
    error: (m, ...a) => emit("error", m, a),
  };
}

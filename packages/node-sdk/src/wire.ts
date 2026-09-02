/**
 * Stage 000 cross-language wire contract helpers.
 *
 * Canonical JSON here must stay byte-identical with the Python helper in
 * `packages/python-sdk/src/neon3_sdk/wire.py`: keys sorted at every depth,
 * no insignificant whitespace, UTF-8 (non-ASCII preserved).
 */

import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const FIXTURE_DIR_ENV = "NEON3_WIRE_FIXTURES";

export const CORE_ERROR_CODES = [
  "stale_revision",
  "unknown_target",
  "unsupported_intent",
  "capability_unavailable",
  "duplicate_event",
  "invalid_publication",
] as const;

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

function sortDeep(value: JsonValue): JsonValue {
  if (Array.isArray(value)) return value.map(sortDeep);
  if (value !== null && typeof value === "object") {
    const out: { [key: string]: JsonValue } = {};
    for (const key of Object.keys(value).sort()) out[key] = sortDeep(value[key] as JsonValue);
    return out;
  }
  return value;
}

export function canonicalJson(value: JsonValue): string {
  return JSON.stringify(sortDeep(value));
}

export function canonicalDigest(value: JsonValue): string {
  return createHash("sha256").update(Buffer.from(canonicalJson(value), "utf8")).digest("hex");
}

function candidateRoots(): string[] {
  const roots: string[] = [];
  const override = process.env[FIXTURE_DIR_ENV];
  if (override) roots.push(override);
  let dir = dirname(fileURLToPath(import.meta.url));
  for (;;) {
    roots.push(join(dir, "docs", "fixtures", "wire"));
    const parent = resolve(dir, "..");
    if (parent === dir) break;
    dir = parent;
  }
  return roots;
}

export function fixtureRoot(): string {
  for (const candidate of candidateRoots()) {
    if (existsSync(candidate)) return candidate;
  }
  throw new Error(`neon3 wire fixtures directory not found; set ${FIXTURE_DIR_ENV}`);
}

export function loadFixture(name: string): JsonValue {
  return JSON.parse(readFileSync(join(fixtureRoot(), name), "utf8")) as JsonValue;
}

export function requireFields(value: unknown, required: readonly string[], optional: readonly string[], label: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label}: expected an object`);
  const keys = new Set(Object.keys(value as object));
  const missing = required.filter((key) => !keys.has(key));
  const unexpected = [...keys].filter((key) => !required.includes(key) && !optional.includes(key));
  if (missing.length || unexpected.length) {
    throw new Error(`${label}: missing=${missing.sort()} unexpected=${unexpected.sort()}`);
  }
  return value as Record<string, unknown>;
}

export function asObject(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label}: expected an object`);
  return value as Record<string, unknown>;
}

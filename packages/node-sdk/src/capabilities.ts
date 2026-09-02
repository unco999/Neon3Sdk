/**
 * Capability negotiation for the Neon3 SDK (docs/sdk-wire-contract.md §5).
 *
 * Mirrors `neon3_sdk/capabilities.py`. `CapabilitySet` is the cross-language
 * view of what a connected runtime advertises; Flow constructs map to the
 * capabilities they need so `UiClient.validateFlow` can fail *before*
 * submission with a typed `CapabilityError`. Static checks mirror the
 * runtime's closed node vocabulary and line grammar (nui_flow.rs).
 */

import { CapabilityError, FlowValidationError } from "./errors.js";
import { ServiceDescription } from "./protocol.js";

export const FLOW_CAPABILITY_REQUIREMENTS: Record<string, string[]> = {
  data_grid: ["ui.data_grid.window.v1"],
  canvas: ["ui.canvas.points_lines.v1"],
  image: ["ui.image.upload.v1"],
  input: ["ui.text_input.commit.v1"],
  motion: ["ui.state.animation.v1"],
  transition: ["ui.state.animation.v1"],
  drag: ["ui.semantic_input.v1", "ui.intent_dispatch.v1"],
  drop: ["ui.semantic_input.v1", "ui.intent_dispatch.v1"],
};

export const SEMANTIC_EVENT_CAPABILITIES = ["ui.semantic_input.v1", "ui.intent_dispatch.v1"];

// Closed node vocabulary from neon-ui-runtime nui_flow.rs::parse_node.
export const KNOWN_FLOW_COMPONENTS: ReadonlySet<string> = new Set([
  "surface", "panel", "scroll", "overlay", "branch", "repeat", "template",
  "data_grid", "tooltip", "modal", "dialog", "text", "button", "input",
  "checkbox", "radio_button", "slider", "drag_value", "combo", "dropdown",
  "tabs", "selectable", "list_box", "scrollbar", "progress_bar", "image",
  "render", "canvas", "world",
]);

const DECLARATION_HEADS = new Set(["drag", "drop", "motion", "transition"]);
const STATE_MACHINE_HEADS = new Set(["machine", "sync", "on", "state"]);
const DIRECTIVE_HEADS = new Set([
  "version", "flow", "budget", "input", "grid_input", "resource",
  "text_registry", "surface_bind", "camera", "style", "binding", "resource_bind",
]);
const ACCEPTED_HEADS: ReadonlySet<string> = new Set([
  ...KNOWN_FLOW_COMPONENTS, ...DECLARATION_HEADS, ...STATE_MACHINE_HEADS, ...DIRECTIVE_HEADS,
  "text", "resource_bind", "binding", "style",
]);

const KEY_RE = /^[A-Za-z0-9._-]+$/;

// Capabilities advertised only by the renderer process. A UI-session client
// cannot describe them, so Flow validation gates on them only when the target
// service is wgpu-runtime.
export const RENDERER_ONLY_CAPABILITIES: ReadonlySet<string> = new Set(["ui.canvas.points_lines.v1"]);

/** Return the service that advertises `capability` in the base runtime. */
export function capabilityOwner(capability: string): string {
  return RENDERER_ONLY_CAPABILITIES.has(capability) || capability.startsWith("wgpu.") ? "wgpu-runtime" : "ui-runtime";
}

export interface FlowComponentInfo {
  component: string;
  line: number;
  column: number;
  key: string | null;
}

interface ContentLine {
  raw: string;
  number: number;
  indent: number;
  tokens: string[];
}

export class CapabilitySet {
  private constructor(
    readonly services: readonly string[],
    readonly capabilities: ReadonlySet<string>,
    readonly epochs: readonly number[],
  ) {}

  static fromDescriptions(descriptions: Iterable<ServiceDescription>): CapabilitySet {
    const services: string[] = [];
    const capabilities = new Set<string>();
    const epochs: number[] = [];
    for (const description of descriptions) {
      services.push(description.service);
      for (const capability of description.capabilities) capabilities.add(capability);
      epochs.push(description.epoch);
    }
    return new CapabilitySet(services, capabilities, epochs);
  }

  static of(capabilities: Iterable<string>, service = ""): CapabilitySet {
    return new CapabilitySet(service ? [service] : [], new Set(capabilities), []);
  }

  has(capability: string): boolean { return this.capabilities.has(capability); }

  missing(...capabilities: string[]): string[] { return capabilities.filter((name) => !this.capabilities.has(name)); }

  require(...capabilities: string[]): this {
    const gaps = this.missing(...capabilities);
    if (gaps.length) throw new CapabilityError(gaps);
    return this;
  }

  requireService(service: string, ...capabilities: string[]): this {
    const gaps = this.missing(...capabilities);
    if (gaps.length) throw new CapabilityError(gaps, { service });
    return this;
  }

  union(other: CapabilitySet): CapabilitySet {
    const services = [...this.services, ...other.services.filter((name) => !this.services.includes(name))];
    const capabilities = new Set([...this.capabilities, ...other.capabilities]);
    return new CapabilitySet(services, capabilities, [...this.epochs, ...other.epochs]);
  }
}

function contentLines(source: string): ContentLine[] {
  const lines: ContentLine[] = [];
  const rawLines = source.split(/\r?\n/);
  for (let index = 0; index < rawLines.length; index += 1) {
    const raw = rawLines[index];
    const stripped = raw.trim();
    if (!stripped || stripped.startsWith("#")) continue;
    const indent = raw.length - raw.trimStart().length;
    lines.push({ raw, number: index + 1, indent, tokens: stripped.split(/\s+/) });
  }
  return lines;
}

function nodeComponent(line: ContentLine): string | null {
  const head = line.tokens[0] ?? "";
  if (head === "world") return line.tokens[1] === "panel" && line.tokens.length >= 3 ? "panel" : null;
  if (DECLARATION_HEADS.has(head)) return head;
  if (head === "data_grid" || head === "canvas" || head === "image") return head;
  if (head === "input") return line.indent > 0 ? "input" : null;
  if (KNOWN_FLOW_COMPONENTS.has(head)) return head;
  return null;
}

function nodeKey(line: ContentLine): string | null {
  const head = line.tokens[0] ?? "";
  const rawKey = head === "world" ? line.tokens[2] : line.tokens[1];
  return rawKey && KEY_RE.test(rawKey) ? rawKey : null;
}

export function scanFlow(source: string): FlowComponentInfo[] {
  const found: FlowComponentInfo[] = [];
  for (const line of contentLines(source)) {
    const head = line.tokens[0];
    const column = line.raw.indexOf(head) + 1;
    const component = nodeComponent(line);
    if (component !== null) {
      found.push({ component, line: line.number, column, key: nodeKey(line) });
    }
    const stripped = ` ${line.raw.trim()} `;
    if (stripped.includes(" event ") || stripped.includes(" emit ")) {
      found.push({ component: "event", line: line.number, column, key: null });
    }
  }
  return found;
}

export function requiredCapabilitiesForFlow(source: string): string[] {
  const needed = new Set<string>();
  for (const info of scanFlow(source)) {
    if (info.component === "event") for (const capability of SEMANTIC_EVENT_CAPABILITIES) needed.add(capability);
    for (const capability of FLOW_CAPABILITY_REQUIREMENTS[info.component] ?? []) needed.add(capability);
  }
  return [...needed].sort();
}

export function validateFlowSource(source: string, capabilities: CapabilitySet | null = null, service = "ui-runtime"): string[] {
  const required = requiredCapabilitiesForFlow(source);
  if (capabilities) {
    const gated = required.filter((name) => capabilityOwner(name) === service);
    const gaps = capabilities.missing(...gated);
    if (gaps.length) throw new CapabilityError(gaps, { service });
  }
  for (const line of contentLines(source)) {
    const head = line.tokens[0];
    if (head.startsWith("@") || ACCEPTED_HEADS.has(head)) continue;
    throw new FlowValidationError(`component is outside the closed Flow vocabulary: ${head}`, {
      line: line.number,
      column: line.raw.indexOf(head) + 1,
      flowCode: "nui_flow_unknown_component",
    });
  }
  return required;
}

/** Minimal shape needed to query a runtime; satisfied by NeonClient. */
export interface DescribeTarget {
  describe(target: string): Promise<ServiceDescription>;
}

export async function describeCapabilities(client: DescribeTarget, targets: readonly string[] = ["ui-runtime", "wgpu-runtime"]): Promise<CapabilitySet> {
  const descriptions: ServiceDescription[] = [];
  for (const target of targets) descriptions.push(await client.describe(target));
  return CapabilitySet.fromDescriptions(descriptions);
}

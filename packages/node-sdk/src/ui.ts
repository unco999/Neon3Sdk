import { readFile } from "node:fs/promises";
import { NeonClient } from "./client.js";
import { CapabilitySet, describeCapabilities, validateFlowSource } from "./capabilities.js";
import {
  DebugSnapshot,
  HostFragmentContext,
  InputChange,
  ProgramInputSnapshot,
  SemanticIntentEvent,
  DragDropEvent,
  UiInputFrame,
  UiProgramRevision,
  UiSnapshot,
  UiTraceRecord,
} from "./protocol.js";

/**
 * Active program view. `program_revision` keeps the canonical snake_case wire
 * shape; `submissionResult` carries the untouched `ui.flow.submit` result so
 * advanced callers can inspect runtime fields the SDK does not model yet.
 */
export interface UiProgram {
  surface_id: string;
  program_revision: UiProgramRevision;
  input_schema: Record<string, unknown>;
  submissionResult: unknown;
}

export type HostInbound =
  | { kind: "semantic_intent"; event: SemanticIntentEvent }
  | { kind: "drag_drop"; event: DragDropEvent; active_fragment: HostFragmentContext };

export interface FlowSubmissionResult {
  surface_id: string;
  program_revision: UiProgramRevision;
  input_schema: Record<string, unknown>;
}

export interface UiCallOptions {
  idempotencyKey?: string;
  requestId?: string;
}

function parseUiProgram(result: FlowSubmissionResult): UiProgram {
  return {
    surface_id: result.surface_id,
    program_revision: result.program_revision,
    input_schema: result.input_schema,
    submissionResult: result,
  };
}

export class UiClient {
  active: UiProgram | null = null;
  private capabilitiesPromise: Promise<CapabilitySet> | null = null;
  private sessionPromise: Promise<import("./session.js").UiSession> | null = null;

  /** Lazily-created revision-aware UiSession, mirroring `app.ui.session`. */
  get session(): Promise<import("./session.js").UiSession> {
    if (!this.sessionPromise) {
      this.sessionPromise = import("./session.js").then(({ UiSession }) => new UiSession(this));
    }
    return this.sessionPromise;
  }

  constructor(readonly client: NeonClient, readonly target = "ui-runtime") {}

  /** Advertised runtime capabilities for this UI session target, cached. */
  capabilities(options: { refresh?: boolean } = {}): Promise<CapabilitySet> {
    if (!this.capabilitiesPromise || options.refresh) {
      this.capabilitiesPromise = describeCapabilities(this.client, [this.target]);
    }
    return this.capabilitiesPromise;
  }

  /** Fail before any submission when the runtime lacks a capability. */
  async requireCapabilities(...capabilities: string[]): Promise<CapabilitySet> {
    const set = await this.capabilities();
    return set.require(...capabilities);
  }

  /**
   * Statically validate a Flow against the closed vocabulary and the
   * connected runtime's advertised capabilities. Returns the capabilities
   * the Flow requires; throws CapabilityError / FlowValidationError.
   */
  async validateFlow(source: string, options: { require?: string[] } = {}): Promise<string[]> {
    if (options.require?.length) await this.requireCapabilities(...options.require);
    return validateFlowSource(source, await this.capabilities(), this.target);
  }

  async submitFlow(source: string, options: UiCallOptions & { validate?: boolean } = {}): Promise<UiProgram> {
    if (options.validate ?? true) await this.validateFlow(source);
    const response = await this.client.call<FlowSubmissionResult>(this.target, "ui.flow.submit", { source }, { idempotencyKey: options.idempotencyKey ?? `ui-flow:${crypto.randomUUID()}` });
    const result = response.result;
    if (!result || typeof result.surface_id !== "string" || !result.program_revision || !result.input_schema) {
      throw new Error("ui.flow.submit returned an invalid program envelope");
    }
    this.active = parseUiProgram(result);
    return this.active;
  }

  async submitFlowFile(path: string, options?: UiCallOptions): Promise<UiProgram> {
    return this.submitFlow(await readFile(path, "utf8"), options);
  }

  async applyInput(frame: Omit<UiInputFrame, "request_id" | "idempotency_key"> & Partial<Pick<UiInputFrame, "request_id" | "idempotency_key">>, options: UiCallOptions = {}): Promise<unknown> {
    const requestId = frame.request_id ?? options.requestId ?? crypto.randomUUID();
    const idempotencyKey = frame.idempotency_key ?? options.idempotencyKey ?? `ui-input:${requestId}`;
    const body: UiInputFrame = { ...frame, request_id: requestId, idempotency_key: idempotencyKey } as UiInputFrame;
    return (await this.client.call(this.target, "ui.input.frame", body, { requestId, idempotencyKey })).result;
  }

  async hostInbound(event: HostInbound, options: UiCallOptions = {}): Promise<unknown> {
    return (await this.client.call(this.target, "ui.host.inbound", event, { idempotencyKey: options.idempotencyKey ?? `ui-host:${crypto.randomUUID()}`, requestId: options.requestId })).result;
  }

  async snapshot(): Promise<UiSnapshot> {
    const service = (await this.client.call<DebugSnapshot>(this.target, "debug.snapshot.get")).result;
    if (!service || typeof service !== "object") throw new Error("debug.snapshot.get returned an invalid result");
    const hostResponse = await this.client.call<ProgramInputSnapshot>(this.target, "debug.ui.host.snapshot", {}, { raiseForStatus: false });
    const host = hostResponse.status === "accepted" && hostResponse.result && typeof hostResponse.result === "object" ? hostResponse.result : null;
    return { service, host_inputs: host };
  }

  async traces(filter: { requestId?: string; eventId?: string } = {}): Promise<UiTraceRecord[]> {
    const params: Record<string, string> = {};
    if (filter.requestId) params.request_id = filter.requestId;
    if (filter.eventId) params.event_id = filter.eventId;
    const result = (await this.client.call<UiTraceRecord[]>(this.target, "debug.trace.query", params)).result;
    if (!Array.isArray(result)) throw new Error("debug.trace.query returned an invalid result");
    return result;
  }

  async hostInputSnapshot(): Promise<ProgramInputSnapshot | null> {
    const response = await this.client.call<ProgramInputSnapshot>(this.target, "debug.ui.host.snapshot", {}, { raiseForStatus: false });
    return response.status === "accepted" && response.result && typeof response.result === "object" ? response.result : null;
  }

  /**
   * Bind a keyed collection store to a template/grid node, gated on
   * `ui.data_grid.window.v1`. Mirrors `UiClient.collection()` in Python.
   */
  async collection(
    nodeKey: string,
    source: import("./store.js").CollectionStore,
    options: Omit<import("./components.js").CollectionBindingOptions, "windowed"> & { fallback?: "list" | "reject" },
  ): Promise<import("./components.js").CollectionBinding> {
    const { CollectionBinder } = await import("./components.js");
    const { fallback = "list", ...bindingOptions } = options;
    const binder = new CollectionBinder(await this.capabilities(), { fallback });
    return binder.bind(nodeKey, source, bindingOptions);
  }
}

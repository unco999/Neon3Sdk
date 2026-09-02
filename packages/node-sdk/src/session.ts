/**
 * Revision-aware UI session: automatic program/input revision management.
 *
 * `UiSession` owns the active program, the current revision state,
 * interaction sequencing and idempotency identity, so business code never
 * hand-writes `program_revision`, `input_revision`, `idempotency_key` or raw
 * semantic envelopes. Mirrors `neon3_sdk/session.py`.
 *
 * Field provenance (docs/sdk-wire-contract.md §6.3): renderer epoch from
 * `service.describe`; input revision from accepted results
 * (`result.input_revision` for host inbound, `result.input.snapshot...` for
 * external frames) or a host-snapshot refresh; the RPC `revision` envelope
 * field is the fragment revision and is never treated as input revision.
 */

import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { RemoteError, StaleRevisionError } from "./errors.js";
import {
  InputChange,
  RevisionState,
  SemanticIntentEvent,
  UiProgramRevision,
} from "./protocol.js";
import { HostInbound, UiClient, UiProgram } from "./ui.js";

export interface IntentResult {
  event_id: string;
  status: "accepted" | "rejected" | "duplicate";
  input_revision: number;
  result: unknown;
  code?: string | null;
  message: string;
}

function walk(value: unknown, ...path: string[]): unknown {
  let current: unknown = value;
  for (const key of path) {
    if (current === null || typeof current !== "object" || Array.isArray(current) || !(key in (current as Record<string, unknown>))) return null;
    current = (current as Record<string, unknown>)[key];
  }
  return current;
}

function observedInputRevision(method: "dispatch" | "publish", result: unknown): number | null {
  if (result === null || typeof result !== "object") return null;
  if (method === "publish") {
    const revision = walk(result, "input", "snapshot", "scalar_inputs", "input_revision");
    return typeof revision === "number" ? revision : null;
  }
  const direct = (result as Record<string, unknown>).input_revision;
  if (typeof direct === "number") return direct;
  const accepted = walk(result, "semantic_intent", "accepted_input_revision");
  return typeof accepted === "number" ? accepted : null;
}

export class UiSession {
  program: UiProgram | null = null;
  rendererEpoch: number | null = null;
  inputRevision = 0;
  frameSequence: number | null = null;
  interactionSequence = 0;
  private readonly dispatched = new Map<string, IntentResult>();
  private readonly published = new Map<string, unknown>();

  constructor(readonly ui: UiClient) {}

  private async resolveRendererEpoch(options: { refresh?: boolean } = {}): Promise<number> {
    const capabilities = await this.ui.capabilities({ refresh: options.refresh });
    const epoch = capabilities.epochOf(this.ui.target) ?? (await this.ui.client.health(this.ui.target)).epoch;
    this.rendererEpoch = epoch;
    return epoch;
  }

  /** Submit a Flow, adopt it as the active program, and re-synchronize. */
  async mountFlow(source: string, options: { validate?: boolean; idempotencyKey?: string } = {}): Promise<UiProgram> {
    const program = await this.ui.submitFlow(source, { ...options, validate: options.validate ?? true });
    return this.adopt(program);
  }

  async mountFlowFile(path: string, options?: { validate?: boolean; idempotencyKey?: string }): Promise<UiProgram> {
    return this.mountFlow(await readFile(path, "utf8"), options);
  }

  /** Adopt an already-submitted program and reset session revisions. */
  adopt(program: UiProgram): UiProgram {
    this.program = program;
    this.inputRevision = 0;
    this.frameSequence = null;
    this.interactionSequence = 0;
    this.dispatched.clear();
    this.published.clear();
    return program;
  }

  get revisionState(): RevisionState {
    if (!this.program) throw new Error("UiSession has no mounted program; call mountFlow first");
    return {
      program_revision: this.program.program_revision.revision,
      input_revision: this.inputRevision,
      renderer_epoch: this.rendererEpoch ?? 0,
      frame_sequence: this.frameSequence,
    };
  }

  get programRevisionWire(): UiProgramRevision {
    if (!this.program) throw new Error("UiSession has no mounted program; call mountFlow first");
    return this.program.program_revision;
  }

  /** Re-read authoritative revision state from the runtime host snapshot. */
  async refresh(): Promise<RevisionState> {
    const host = await this.ui.hostInputSnapshot();
    if (host) {
      const revision = host.scalar_inputs.input_revision;
      if (typeof revision === "number") this.inputRevision = revision;
    }
    await this.resolveRendererEpoch({ refresh: true });
    return this.revisionState;
  }

  /** Assemble a canonical semantic event with live revisions (for probes). */
  async buildIntentEvent(
    intent: string,
    payload: SemanticIntentEvent["payload"] = {},
    options: { sourceNodeKey?: string; kind?: SemanticIntentEvent["kind"]; eventId?: string; requestedValue?: SemanticIntentEvent["requested_value"] } = {},
  ): Promise<SemanticIntentEvent> {
    if (!this.program) throw new Error("UiSession has no mounted program; call mountFlow first");
    const eventId = options.eventId ?? randomUUID();
    this.interactionSequence += 1;
    const event: SemanticIntentEvent = {
      event_id: eventId,
      kind: options.kind ?? "activate",
      intent,
      source_node_key: options.sourceNodeKey ?? "sdk",
      payload,
      program_revision: this.programRevisionWire,
      input_revision: this.inputRevision,
      request_id: eventId,
      idempotency_key: `intent:${eventId}`,
      interaction: {
        interaction_id: eventId,
        sequence: this.interactionSequence,
        renderer_epoch: await this.resolveRendererEpoch(),
      },
    };
    if (options.requestedValue) event.requested_value = options.requestedValue;
    return event;
  }

  /**
   * Send one semantic intent with automatic revision and identity.
   *
   * Local replay of the same `event_id` returns the recorded result. A stale
   * rejection refreshes once then raises StaleRevisionError (refreshed=true).
   * A runtime duplicate is surfaced as status="duplicate", never thrown.
   */
  async dispatchIntent(
    intent: string,
    payload: SemanticIntentEvent["payload"] = {},
    options: { sourceNodeKey?: string; kind?: SemanticIntentEvent["kind"]; eventId?: string; requestedValue?: SemanticIntentEvent["requested_value"] } = {},
  ): Promise<IntentResult> {
    const eventId = options.eventId ?? randomUUID();
    const cached = this.dispatched.get(eventId);
    if (cached) {
      return { event_id: eventId, status: "duplicate", input_revision: this.inputRevision, result: cached.result, code: "duplicate_event", message: "replayed from session ledger" };
    }
    const event = await this.buildIntentEvent(intent, payload, { ...options, eventId });
    const response = await this.ui.client.call(this.ui.target, "ui.host.inbound", { kind: "semantic_intent", event } satisfies Extract<HostInbound, { kind: "semantic_intent" }>, { requestId: event.request_id, idempotencyKey: event.idempotency_key, raiseForStatus: false });
    if (response.status !== "accepted") {
      const remote = new RemoteError(response.request_id, response.status, response.error);
      if (remote.sdkCode === "stale_revision") {
        const previous = this.inputRevision;
        await this.refresh();
        throw new StaleRevisionError(`intent dispatch rejected as stale: ${remote.message}`, { expected: previous, actual: this.inputRevision, refreshed: true, runtime_code: remote.code });
      }
      throw remote;
    }
    const resultPayload = response.result as Record<string, unknown> | null;
    let status: IntentResult["status"] = "accepted";
    let code: string | null | undefined;
    let message = "";
    const inner = resultPayload?.semantic_intent as Record<string, unknown> | undefined;
    if (inner && (inner.status === "accepted" || inner.status === "rejected" || inner.status === "duplicate")) {
      status = inner.status as IntentResult["status"];
      code = (inner.code as string | null) ?? null;
      message = String(inner.message ?? "");
      const accepted = inner.accepted_input_revision;
      if (typeof accepted === "number" && accepted > this.inputRevision) this.inputRevision = accepted;
    }
    const observed = observedInputRevision("dispatch", resultPayload);
    if (observed !== null && observed > this.inputRevision) {
      this.inputRevision = observed;
    } else if (observed === null && status === "accepted") {
      this.inputRevision += 1;
    }
    const result: IntentResult = {
      event_id: eventId,
      status,
      input_revision: this.inputRevision,
      result: resultPayload,
      code: code ?? (status === "duplicate" ? "duplicate_event" : null),
      message,
    };
    this.dispatched.set(eventId, result);
    return result;
  }

  /** Apply an external scalar input frame with automatic revision management. */
  async publish(scalarChanges: InputChange[], options: { requestId?: string } = {}): Promise<unknown> {
    if (!this.program) throw new Error("UiSession has no mounted program; call mountFlow first");
    const frameId = options.requestId ?? randomUUID();
    if (this.published.has(frameId)) return this.published.get(frameId);
    const buildFrame = (expectedRevision: number) => ({
      program_revision: this.programRevisionWire,
      expected_input_revision: expectedRevision,
      request_id: frameId,
      idempotency_key: `input:${frameId}`,
      changes: scalarChanges,
    });
    let response = await this.ui.client.call(this.ui.target, "ui.input.frame", buildFrame(this.inputRevision), { requestId: frameId, idempotencyKey: `input:${frameId}`, raiseForStatus: false });
    if (response.status !== "accepted") {
      const remote = new RemoteError(response.request_id, response.status, response.error);
      if (remote.sdkCode !== "stale_revision") throw remote;
      const previous = this.inputRevision;
      await this.refresh();
      response = await this.ui.client.call(this.ui.target, "ui.input.frame", buildFrame(this.inputRevision), { requestId: frameId, idempotencyKey: `input:${frameId}`, raiseForStatus: false });
      if (response.status !== "accepted") {
        const secondError = (response.error ?? {}) as Record<string, unknown>;
        await this.refresh();
        throw new StaleRevisionError(`publication still rejected after one refresh: ${String(secondError.message ?? "")}`, {
          expected: previous,
          actual: this.inputRevision,
          refreshed: true,
          runtime_code: String(secondError.code ?? ""),
        });
      }
    }
    const observed = observedInputRevision("publish", response.result);
    if (observed !== null && observed > this.inputRevision) this.inputRevision = observed;
    else this.inputRevision += 1;
    this.published.set(frameId, response.result);
    return response.result;
  }

  /** Observe the current session revision state after batched changes. */
  flush(): RevisionState {
    return this.revisionState;
  }

  /** **Advanced.** Forward an unmanaged host inbound envelope. */
  async rawHostInbound(inbound: HostInbound, options: { idempotencyKey?: string } = {}): Promise<unknown> {
    return this.ui.hostInbound(inbound, options);
  }

  /** **Advanced.** Send a fully-specified `ui.input.frame` envelope. */
  async rawApplyInput(frame: Record<string, unknown>): Promise<unknown> {
    return (await this.ui.client.call(this.ui.target, "ui.input.frame", frame, {
      requestId: frame.request_id as string | undefined,
      idempotencyKey: frame.idempotency_key as string | undefined,
    })).result;
  }
}

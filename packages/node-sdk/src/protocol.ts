export const RPC_PROTOCOL = "neon3.rpc" as const;
export const PROTOCOL_VERSION = { major: 1, minor: 0 } as const;
export const EVENT_PROTOCOL = "neon3.event" as const;

export type RpcStatus = "accepted" | "rejected" | "failed";

export interface RpcResponse<T = unknown> {
  request_id: string;
  status: RpcStatus;
  revision: number | null;
  result: T | null;
  snapshot: unknown | null;
  error: Record<string, unknown> | null;
}

/** Validates the six-key closed RPC envelope (docs/sdk-wire-contract.md §1.3). */
export function parseRpcResponse<T>(value: unknown): RpcResponse<T> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new ProtocolShapeError("response must be a JSON object");
  }
  const record = value as Record<string, unknown>;
  const required = ["request_id", "status", "revision", "result", "snapshot", "error"];
  const keys = Object.keys(record);
  const missing = required.filter((key) => !(key in record));
  const unexpected = keys.filter((key) => !required.includes(key));
  if (missing.length || unexpected.length) {
    throw new ProtocolShapeError(`invalid RpcResponse fields: missing=${missing.sort()} unexpected=${unexpected.sort()}`);
  }
  if (typeof record.request_id !== "string") throw new ProtocolShapeError("request_id must be a string");
  if (!["accepted", "rejected", "failed"].includes(String(record.status))) throw new ProtocolShapeError(`invalid status: ${String(record.status)}`);
  if (record.revision !== null && !Number.isInteger(record.revision)) throw new ProtocolShapeError("revision must be an integer or null");
  if (record.error !== null && (typeof record.error !== "object" || Array.isArray(record.error))) throw new ProtocolShapeError("error must be an object or null");
  return record as unknown as RpcResponse<T>;
}

export class ProtocolShapeError extends Error {}

export interface ServiceDescription {
  service: string;
  protocol_version: { major: number; minor: number };
  endpoint: string;
  epoch: number;
  capabilities: string[];
}

export interface ServiceHealth {
  service: string;
  status: "healthy" | "degraded" | "unhealthy";
  epoch: number;
}

export interface ClientIdentity {
  kind: string;
  instance_id: string;
  pid: number;
  origin: string;
}

export interface EventEnvelope {
  protocol: string;
  version: { major: number; minor: number };
  event_id: string;
  name: string;
  schema_version: number;
  epoch: number;
  sequence: number;
  timestamp_unix_ms: number;
  publisher: ClientIdentity;
  payload: unknown;
}

/* ------------------------------------------------------------------ */
/* UI domain models (wire field names, see docs/sdk-wire-contract.md) */
/* ------------------------------------------------------------------ */

export type InputValueKind =
  | "bool" | "i32" | "u32" | "f32" | "vec2" | "vec4" | "color"
  | "enum" | "text_handle" | "asset_handle" | "canvas_data";

export interface InputValue {
  kind: InputValueKind;
  [key: string]: unknown;
}

export interface TextHandle {
  id: number;
  generation: number;
}

export type SemanticPayloadKind = "bool" | "i32" | "u32" | "f32" | "enum" | "text_handle" | "asset_handle";

export interface SemanticPayloadValue {
  kind: SemanticPayloadKind;
  [key: string]: unknown;
}

export interface ProgramCapability {
  name: string;
  version: number;
  owner: "ui_runtime" | "wgpu_runtime" | "shared_contract";
  status: "experimental" | "supported" | "deprecated";
}

export interface UiProgramRevision {
  program_id: string;
  revision: number;
  schema_version: number;
  capabilities: ProgramCapability[];
}

export interface InputPacking {
  alignment: number;
  lanes: number;
  offset: number;
  representation: "bool32" | "i32" | "u32" | "f32" | "vec2_f32" | "vec4_f32" | "handle_uvec2";
}

export interface InputSlot {
  key: string;
  kind: Record<string, unknown>;
  default_value: InputValue;
  update_class: "static_at_program_activation" | "reliable_external" | "local_presentation" | "text_registry_reference";
  semantic_label: string;
  packing: InputPacking;
}

export interface UiInputSchema {
  schema_id: string;
  version: number;
  slots: InputSlot[];
  grid_slots?: Array<Record<string, unknown>>;
  layout_hash: string;
  flow_name?: string;
  emit_event_keys?: string[];
}

export interface InputChange {
  key: string;
  value: InputValue;
}

export interface UiInputFrame {
  program_revision: UiProgramRevision;
  expected_input_revision: number;
  request_id: string;
  idempotency_key: string;
  changes: InputChange[];
}

export interface ResolvedInputValue {
  value: InputValue;
  source: "default" | "reliable_external" | "local_presentation" | "text_registry_reference";
  last_update_revision: number;
}

export interface ResolvedInputs {
  program_revision: UiProgramRevision;
  input_revision: number;
  values: Record<string, ResolvedInputValue>;
  changed_slots: string[];
}

export interface ProgramInputSnapshot {
  scalar_inputs: ResolvedInputs;
  grid_inputs: Array<Record<string, unknown>>;
}

export interface DebugSnapshot {
  service: string;
  epoch: number;
  revision: number;
  health: "healthy" | "degraded" | "unhealthy";
  capabilities: string[];
  active_jobs: string[];
}

export interface SemanticInteractionMetadata {
  interaction_id: string;
  sequence: number;
  renderer_epoch: number;
}

export type SemanticEventKind =
  | "activate" | "value_tentative" | "value_commit"
  | "selection_changed" | "text_edit_commit" | "interaction_cancel";

export interface SemanticIntentEvent {
  event_id: string;
  kind: SemanticEventKind;
  intent: string;
  source_node_key: string;
  payload: Record<string, SemanticPayloadValue>;
  program_revision: UiProgramRevision;
  input_revision: number;
  request_id: string;
  idempotency_key: string;
  requested_value?: SemanticPayloadValue;
  interaction: SemanticInteractionMetadata;
}

export interface DragDropPayload {
  source_key: string;
  target_key: string;
  placement: "into" | "before" | "after";
  presentation_template_key?: string | null;
}

export interface DragDropEvent {
  event_id: string;
  drag_key: string;
  drop_key: string;
  intent: string;
  payload: DragDropPayload;
  program_revision: UiProgramRevision;
  input_revision: number;
  request_id: string;
  idempotency_key: string;
  interaction: SemanticInteractionMetadata;
}

export interface FragmentRevision {
  id: string;
  revision: number;
}

export interface UiBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface UiNode {
  node_id: string;
  kind: string;
  bounds: UiBounds;
  visible: boolean;
  enabled: boolean;
  text_key?: string | null;
  children: UiNode[];
  [key: string]: unknown;
}

export interface HostFragmentContext {
  fragment: FragmentRevision;
  root: UiNode;
  effects: Array<Record<string, unknown>>;
}

export interface SemanticEventResult {
  event_id: string;
  status: "accepted" | "rejected" | "duplicate";
  code?: string | null;
  accepted_input_revision?: number | null;
  message: string;
}

export interface UiTraceRecord {
  sequence: number;
  event_id: string;
  intent: string;
  source_node_key: string;
  program_revision: number;
  input_revision: number;
  renderer_epoch: number;
  result: "accepted" | "rejected" | "duplicate";
}

export interface RevisionState {
  program_revision: number;
  input_revision: number;
  renderer_epoch: number;
  frame_sequence: number | null;
}

export interface UiSnapshot {
  service: DebugSnapshot;
  host_inputs: ProgramInputSnapshot | null;
}

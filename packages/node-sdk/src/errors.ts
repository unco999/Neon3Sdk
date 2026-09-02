/**
 * Stable SDK error types with frozen cross-language error codes.
 *
 * The semantic codes are defined in `docs/sdk-wire-contract.md` §6 and must
 * stay identical to `neon3_sdk/errors.py` (RUNTIME_CODE_MAP). Both SDKs map
 * the same runtime code to the same SDK code.
 */

export const ERROR_CODES = {
  STALE_REVISION: "stale_revision",
  UNKNOWN_TARGET: "unknown_target",
  UNSUPPORTED_INTENT: "unsupported_intent",
  CAPABILITY_UNAVAILABLE: "capability_unavailable",
  DUPLICATE_EVENT: "duplicate_event",
  INVALID_PUBLICATION: "invalid_publication",
  INVALID_PROGRAM: "invalid_program",
  // drop_rejected is an SDK routing outcome, not part of the frozen 6-code
  // core contract asserted across languages in Stage 000.
  DROP_REJECTED: "drop_rejected",
} as const;

export type SdkErrorCode = (typeof ERROR_CODES)[keyof typeof ERROR_CODES] | string;

type RuntimeCodeEntry = { code: SdkErrorCode; retryable: boolean };

/** runtime code -> { SDK code, retryable }. Unmapped codes pass through. */
export const RUNTIME_CODE_MAP: Record<string, RuntimeCodeEntry> = {
  ui_program_stale_input_revision: { code: ERROR_CODES.STALE_REVISION, retryable: true },
  ui_host_stale_semantic_intent: { code: ERROR_CODES.STALE_REVISION, retryable: true },
  ui_host_stale_drag_drop: { code: ERROR_CODES.STALE_REVISION, retryable: true },
  ui_host_renderer_epoch_mismatch: { code: ERROR_CODES.STALE_REVISION, retryable: true },
  ui_host_invalid_drag_drop: { code: ERROR_CODES.UNKNOWN_TARGET, retryable: false },
  ui_host_invalid_semantic_intent: { code: ERROR_CODES.UNKNOWN_TARGET, retryable: false },
  ui_host_invalid_publication: { code: ERROR_CODES.INVALID_PUBLICATION, retryable: false },
  ui_flow_submit_failed: { code: ERROR_CODES.INVALID_PROGRAM, retryable: false },
  ui_program_invalid_input_schema: { code: ERROR_CODES.INVALID_PROGRAM, retryable: false },
  ui_program_duplicate_input_key: { code: ERROR_CODES.INVALID_PROGRAM, retryable: false },
  ui_program_invalid_default: { code: ERROR_CODES.INVALID_PROGRAM, retryable: false },
  ui_program_invalid_input_snapshot: { code: ERROR_CODES.INVALID_PROGRAM, retryable: false },
  nui_flow_invalid_node: { code: ERROR_CODES.INVALID_PROGRAM, retryable: false },
  nui_flow_unknown_component: { code: ERROR_CODES.INVALID_PROGRAM, retryable: false },
  nui_flow_invalid_key: { code: ERROR_CODES.INVALID_PROGRAM, retryable: false },
};

const TARGET_DIAGNOSTIC_HINTS = ["is not declared", "unknown target", "no such node"];

/** Map a runtime error code onto the frozen SDK code + retryability. */
export function normalizeErrorCode(runtimeCode: string, message = ""): { sdkCode: SdkErrorCode; retryable: boolean } {
  const entry = RUNTIME_CODE_MAP[runtimeCode];
  if (!entry) return { sdkCode: runtimeCode, retryable: false };
  let sdkCode = entry.code;
  if (runtimeCode === "ui_host_invalid_semantic_intent" && !TARGET_DIAGNOSTIC_HINTS.some((hint) => message.toLowerCase().includes(hint))) {
    sdkCode = ERROR_CODES.INVALID_PUBLICATION;
  }
  return { sdkCode, retryable: entry.retryable };
}

export interface NeonErrorDetails {
  [key: string]: unknown;
}

export class NeonError extends Error {
  code: SdkErrorCode = "neon_error";
  retryable = false;
  readonly details: NeonErrorDetails;
  constructor(message = "", details: NeonErrorDetails = {}) {
    super(message);
    this.details = details;
  }
}

export class TransportError extends NeonError {
  override code = "transport_error";
  override retryable = true;
}

export class ProtocolError extends NeonError {
  override code = "protocol_error";
  override retryable = false;
}

/**
 * A Neon3 service rejected or failed an RPC request. `sdkCode` is the frozen
 * cross-language code; `code` keeps the raw runtime code for diagnostics.
 */
export class RemoteError extends NeonError {
  readonly sdkCode: SdkErrorCode;
  constructor(
    readonly requestId: string,
    readonly status: string,
    readonly error: Record<string, unknown> | null,
  ) {
    const raw = String(error?.code ?? "unknown_remote_error");
    const message = String(error?.message ?? "The service returned no error message.");
    const normalized = normalizeErrorCode(raw, message);
    super(`${raw}: ${message} (request_id=${requestId}, status=${status})`, {
      ...(((error?.details as NeonErrorDetails) ?? {})),
      runtime_code: raw,
      status,
    });
    this.code = raw;
    this.sdkCode = normalized.sdkCode;
    this.retryable = normalized.retryable;
  }
}

export class CapabilityError extends NeonError {
  override code = ERROR_CODES.CAPABILITY_UNAVAILABLE;
  override retryable = false;
  readonly missing: string[];
  constructor(missing: Iterable<string>, options: { service?: string; message?: string } = {}) {
    const list = [...missing];
    super(options.message ?? `runtime is missing required capabilities: ${list.join(", ")}`, { missing: list, service: options.service ?? "" });
    this.missing = list;
  }
}

export class StaleRevisionError extends NeonError {
  override code = ERROR_CODES.STALE_REVISION;
  override retryable = true;
  constructor(message = "revision is stale", details: NeonErrorDetails = {}) {
    super(message, details);
  }
}

export class UnknownTargetError extends NeonError {
  override code = ERROR_CODES.UNKNOWN_TARGET;
  override retryable = false;
  readonly key: string;
  constructor(key: string, kind = "node", message = "") {
    super(message || `${kind} key is not declared by the active program: ${key}`, { key, kind });
    this.key = key;
  }
}

export class UnsupportedIntentError extends NeonError {
  override code = ERROR_CODES.UNSUPPORTED_INTENT;
  override retryable = false;
  readonly intent: string;
  constructor(intent: string, message = "") {
    super(message || `no handler is registered for intent: ${intent}`, { intent });
    this.intent = intent;
  }
}

/**
 * A drop target declined the payload by its `accepts` contract. Distinct from
 * UnknownTargetError: the target exists but rejects this drag's type, so
 * domain state must not change.
 */
export class DropRejectedError extends NeonError {
  override code = ERROR_CODES.DROP_REJECTED;
  override retryable = false;
  readonly sourceKey: string;
  readonly targetKey: string;
  constructor(message = "drop target rejected the payload", details: { sourceKey?: string; targetKey?: string; accepted?: string[] } = {}) {
    super(message, { source_key: details.sourceKey ?? "", target_key: details.targetKey ?? "", accepted: details.accepted ?? [] });
    this.sourceKey = details.sourceKey ?? "";
    this.targetKey = details.targetKey ?? "";
  }
}

export class DuplicateEventError extends NeonError {
  override code = ERROR_CODES.DUPLICATE_EVENT;
  override retryable = false;
  readonly eventId: string;
  constructor(eventId: string, message = "") {
    super(message || `duplicate event replay: ${eventId}`, { event_id: eventId });
    this.eventId = eventId;
  }
}

export class InvalidPublicationError extends NeonError {
  override code = ERROR_CODES.INVALID_PUBLICATION;
  override retryable = false;
  constructor(message = "publication is not valid for the active program", details: NeonErrorDetails = {}) {
    super(message, details);
  }
}

export class FlowValidationError extends NeonError {
  override code = ERROR_CODES.INVALID_PROGRAM;
  override retryable = false;
  readonly line: number | null;
  readonly column: number | null;
  readonly flowCode: string;
  readonly missingCapabilities: string[];
  constructor(
    message: string,
    options: { line?: number | null; column?: number | null; flowCode?: string; missingCapabilities?: string[] } = {},
  ) {
    const line = options.line ?? null;
    const column = options.column ?? null;
    const location = line !== null ? ` (line ${line}, column ${column ?? 1})` : "";
    super(`${message}${location}`, {
      line,
      column,
      flow_code: options.flowCode ?? "nui_flow_invalid",
      missing: options.missingCapabilities ?? [],
    });
    this.line = line;
    this.column = column;
    this.flowCode = options.flowCode ?? "nui_flow_invalid";
    this.missingCapabilities = options.missingCapabilities ?? [];
  }
}

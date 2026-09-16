/**
 * Editor document APIs backing the NUI `code_editor` component
 * (`editor-runtime`, v0.2.10+).
 *
 * The editor domain logic lives in the runtime's pure `neon-editor-core`
 * (buffer, rule-table highlighting, undo/redo, completion). This module is
 * the host-side counterpart: open documents, apply change sets, commit
 * revisions, and request completions over the wire, mirroring the exact serde
 * shapes of `neon-editor-runtime`.
 */
import { randomUUID } from "node:crypto";
import { NeonClient } from "./client.js";
import { ProtocolError } from "./errors.js";
import { method as rpcMethod, service } from "./constants.js";

/** The only editor language the runtime supports today. */
export const EDITOR_LANGUAGE_NUI_FLOW = "nui_flow";

/** Mirrors `MAX_CHANGESET_OPS` in `neon-editor-runtime`. */
export const MAX_CHANGESET_OPS = 256;
/** Mirrors `MAX_INSERT_BYTES` in `neon-editor-runtime`. */
export const MAX_INSERT_BYTES = 64 * 1024;

/** A position in the document (line/column, both in `char` units). */
export interface EditorPosition {
  line: number;
  column: number;
}

/** An ordered selection range (`anchor` -> `active`). */
export interface EditorSelection {
  anchor: EditorPosition;
  active: EditorPosition;
}

/** One edit operation. `kind` tags the wire JSON: `"insert" | "delete"`. */
export type EditOp =
  | { kind: "insert"; line: number; column: number; end: EditorPosition; text: string }
  | { kind: "delete"; start: EditorPosition; end: EditorPosition; text: string };

export function editInsert(line: number, column: number, end: EditorPosition, text: string): EditOp {
  return { kind: "insert", line, column, end, text };
}

export function editDelete(start: EditorPosition, end: EditorPosition, text: string): EditOp {
  return { kind: "delete", start, end, text };
}

/** A host-side change set applied on top of `base_revision`. */
export interface ChangeSet {
  /** Document revision the ops apply on top of. */
  base_revision: number;
  ops: EditOp[];
}

/**
 * Local pre-flight matching the runtime limits (`editor_changeset_invalid` /
 * `editor_change_set_overflow`): 1..=256 ops, each insert at most 64 KiB of
 * UTF-8. Throws on violation.
 */
export function validateChangeSet(changeSet: ChangeSet): void {
  if (changeSet.ops.length < 1 || changeSet.ops.length > MAX_CHANGESET_OPS) {
    throw new Error(`change set must contain 1..=${MAX_CHANGESET_OPS} ops, got ${changeSet.ops.length}`);
  }
  for (const op of changeSet.ops) {
    if (op.kind === "insert") {
      const bytes = Buffer.byteLength(op.text, "utf8");
      if (bytes > MAX_INSERT_BYTES) {
        throw new Error(`single insert exceeds ${MAX_INSERT_BYTES} bytes, got ${bytes}`);
      }
    }
  }
}

/** Change application mode: `"draft"` or `"commit"`. */
export type EditorChangeKind = "draft" | "commit";

/** Completion trigger: `"automatic" | "invoked" | "trigger_character"`. */
export type CompletionTriggerKind = "automatic" | "invoked" | "trigger_character";

/** A document snapshot returned by every editor method. */
export interface EditorSnapshot {
  document_id: string;
  session_id: string;
  language: string;
  epoch: number;
  revision: number;
  committed_revision: number;
  dirty: boolean;
  line_count: number;
  byte_length: number;
  source_hash: string;
  source: string;
  diagnostics?: unknown[];
}

/** One completion candidate (mirrors `neon_editor_core::CompletionItem`). */
export interface CompletionItem {
  item_id: string;
  label: string;
  insert_text: string;
  replace_start: EditorPosition;
  replace_end: EditorPosition;
  kind: string;
  detail: string;
  sort_text: string;
  source: string;
  commit_characters?: string[];
}

/** Result of `editor.completion.request`. */
export interface EditorCompletionResult {
  document_id: string;
  document_revision: number;
  position: EditorPosition;
  items: CompletionItem[];
}

/** Result of `editor.document.open`: freshly opened documents carry the
 * initial snapshot; re-opening returns `"already_open"` without one. */
export interface EditorOpenResult {
  state: "opened" | "already_open";
  snapshot?: EditorSnapshot;
}

/** Result of `editor.document.change.apply`. */
export interface EditorOperationResult {
  state: string;
  snapshot: EditorSnapshot;
  applied_ops: number;
  cursor?: EditorPosition | null;
  selection?: EditorSelection | null;
}

export interface EditorCallOptions {
  /** Envelope-level idempotency key (required by mutating editor methods);
   * generated when omitted. */
  idempotencyKey?: string;
}

function validateIdentity(documentId: string, sessionId: string): void {
  if (!documentId || !documentId.trim()) throw new Error("document_id must be non-empty");
  if (!sessionId || !sessionId.trim()) throw new Error("session_id must be non-empty");
}

/** Unwraps an accepted result; the editor methods always answer objects. */
function required<T>(method: string, result: T | null): T {
  if (result === null || typeof result !== "object") {
    throw new ProtocolError(`${method} returned a non-object result`);
  }
  return result;
}

/**
 * High-level wrapper for the headless editor document service. `target`
 * defaults to `editor-runtime`; override only when the endpoint multiplexes
 * services (e.g. the Android host).
 */
export class EditorClient {
  constructor(readonly client: NeonClient, readonly target: string = service.EDITOR_RUNTIME) {}

  /** Open a document (`editor.document.open`). */
  async open(
    documentId: string,
    sessionId: string,
    source: string,
    language: string = EDITOR_LANGUAGE_NUI_FLOW,
    options: EditorCallOptions = {},
  ): Promise<EditorOpenResult> {
    validateIdentity(documentId, sessionId);
    if (language !== EDITOR_LANGUAGE_NUI_FLOW) {
      throw new Error(`unsupported editor language ${JSON.stringify(language)}; only ${JSON.stringify(EDITOR_LANGUAGE_NUI_FLOW)} is supported`);
    }
    const response = await this.client.call<EditorOpenResult>(this.target, rpcMethod.EDITOR_DOCUMENT_OPEN, {
      document_id: documentId,
      session_id: sessionId,
      language,
      source,
    }, { idempotencyKey: options.idempotencyKey ?? `editor:open:${documentId}:${randomUUID()}` });
    return required(rpcMethod.EDITOR_DOCUMENT_OPEN, response.result);
  }

  /** Fetch the current snapshot (`editor.document.snapshot.get`). */
  async snapshot(documentId: string, sessionId: string, epoch: number): Promise<EditorSnapshot> {
    validateIdentity(documentId, sessionId);
    const response = await this.client.call<EditorSnapshot>(this.target, rpcMethod.EDITOR_DOCUMENT_SNAPSHOT_GET, {
      document_id: documentId,
      session_id: sessionId,
      epoch,
    });
    return required(rpcMethod.EDITOR_DOCUMENT_SNAPSHOT_GET, response.result);
  }

  /**
   * Apply a change set (`editor.document.change.apply`). `cursor` /
   * `selection` update the renderer's caret state.
   */
  async applyChange(
    documentId: string,
    sessionId: string,
    epoch: number,
    changeSet: ChangeSet,
    kind: EditorChangeKind = "draft",
    options: {
      cursor?: EditorPosition;
      selection?: EditorSelection;
      idempotencyKey?: string;
    } = {},
  ): Promise<EditorOperationResult> {
    validateIdentity(documentId, sessionId);
    validateChangeSet(changeSet);
    const params: Record<string, unknown> = {
      document_id: documentId,
      session_id: sessionId,
      epoch,
      change_set: changeSet,
      kind,
    };
    if (options.cursor) params.cursor = options.cursor;
    if (options.selection) params.selection = options.selection;
    const response = await this.client.call<EditorOperationResult>(this.target, rpcMethod.EDITOR_DOCUMENT_CHANGE_APPLY, params, {
      idempotencyKey: options.idempotencyKey ?? `editor:apply:${documentId}:${randomUUID()}`,
    });
    return required(rpcMethod.EDITOR_DOCUMENT_CHANGE_APPLY, response.result);
  }

  /**
   * Commit the pending revision (`editor.document.change.commit`). The
   * envelope carries `expected_revision`; a stale revision is rejected with
   * `editor_revision_conflict`.
   */
  async commit(documentId: string, sessionId: string, epoch: number, expectedRevision: number): Promise<EditorSnapshot> {
    validateIdentity(documentId, sessionId);
    const response = await this.client.call<EditorSnapshot>(this.target, rpcMethod.EDITOR_DOCUMENT_CHANGE_COMMIT, {
      document_id: documentId,
      session_id: sessionId,
      epoch,
    }, {
      expectedRevision,
      idempotencyKey: `editor:commit:${documentId}:${randomUUID()}`,
    });
    return required(rpcMethod.EDITOR_DOCUMENT_CHANGE_COMMIT, response.result);
  }

  /**
   * Request completion candidates at `position`
   * (`editor.completion.request`). A stale `document_revision` is rejected
   * with `editor_completion_stale`.
   */
  async completions(
    documentId: string,
    sessionId: string,
    epoch: number,
    documentRevision: number,
    position: EditorPosition,
    triggerKind: CompletionTriggerKind = "automatic",
  ): Promise<EditorCompletionResult> {
    validateIdentity(documentId, sessionId);
    const response = await this.client.call<EditorCompletionResult>(this.target, rpcMethod.EDITOR_COMPLETION_REQUEST, {
      document_id: documentId,
      session_id: sessionId,
      epoch,
      document_revision: documentRevision,
      position,
      trigger_kind: triggerKind,
    });
    return required(rpcMethod.EDITOR_COMPLETION_REQUEST, response.result);
  }

  /** Close a document (`editor.document.close`). Returns
   * `{"state": "closed", "document_id": ...}`. */
  async close(documentId: string, sessionId: string, epoch: number, options: EditorCallOptions = {}): Promise<{ state: string; document_id: string }> {
    validateIdentity(documentId, sessionId);
    const response = await this.client.call<{ state: string; document_id: string }>(this.target, rpcMethod.EDITOR_DOCUMENT_CLOSE, {
      document_id: documentId,
      session_id: sessionId,
      epoch,
    }, { idempotencyKey: options.idempotencyKey ?? `editor:close:${documentId}:${randomUUID()}` });
    return required(rpcMethod.EDITOR_DOCUMENT_CLOSE, response.result);
  }
}

/**
 * Canonical wire constants and enums for the Neon3 protocol.
 *
 * Every service name, RPC method, event name, and animation action that used
 * to be a bare string literal now lives here. Import these and your IDE will
 * autocomplete; a typo becomes a compile error, not a runtime
 * `unsupported_method`.
 *
 * ```ts
 * import { service, method, eventName, AnimationAction } from "@neon3/sdk";
 * client.call(service.WGPU_RUNTIME, method.WGPU_UI_SET_VIEW_EXTRAS, {...});
 * client.call(service.WGPU_RUNTIME, AnimationAction.PAUSE.method(), {...});
 * ```
 */

/** Service target names (the `target` field of every RPC envelope). */
export const service = {
  /** Event bus. Default endpoint 127.0.0.1:39101. */
  EVENTD: "eventd",
  /** UI runtime. Default endpoint 127.0.0.1:39102. */
  UI_RUNTIME: "ui-runtime",
  /** WGPU renderer. Default endpoint 127.0.0.1:39103. */
  WGPU_RUNTIME: "wgpu-runtime",
  /** Headless editor document service backing the NUI `code_editor`
   * component (v0.2.10+). Serves the `editor.document.v1`,
   * `editor.changeset.v1`, and `editor.completion.v1` capabilities. */
  EDITOR_RUNTIME: "editor-runtime",
} as const;

/** RPC method names. */
export const method = {
  // service lifecycle
  SERVICE_HEALTH: "service.health",
  SERVICE_DESCRIBE: "service.describe",
  SERVICE_SHUTDOWN: "service.shutdown",

  // ui-runtime
  UI_FLOW_SUBMIT: "ui.flow.submit",
  UI_HOST_INBOUND: "ui.host.inbound",
  UI_INPUT_FRAME: "ui.input.frame",
  UI_HOST_POINTER_EVENT: "ui.host.pointer_event",

  // debug
  DEBUG_SNAPSHOT_GET: "debug.snapshot.get",
  DEBUG_UI_HOST_SNAPSHOT: "debug.ui.host.snapshot",

  // wgpu-runtime: surfaces
  RENDER_SURFACE_OPEN: "render.surface.open",
  RENDER_SURFACE_ACQUIRE: "render.surface.acquire",
  RENDER_SURFACE_FRAME: "render.surface.frame",
  RENDER_SURFACE_CAPTURE_PNG: "render.surface.capture_png",

  // wgpu-runtime: diagnostics
  WGPU_RENDER_DIAGNOSTICS: "wgpu.render.diagnostics",
  WGPU_RENDER_GRAPH_SNAPSHOT: "wgpu.render.graph.snapshot",

  // v0.2.7 shader extras
  WGPU_UI_SET_VIEW_EXTRAS: "wgpu.ui.set_view_extras",

  // v0.2.10 animation
  WGPU_UI_ANIMATION_PREFIX: "wgpu.ui.animation.",

  // wgpu-runtime: custom text material packages
  WGPU_SHADER_REGISTER: "wgpu.shader.register",
  WGPU_SHADER_STATE: "wgpu.shader.state",

  // editor-runtime: code_editor document service (v0.2.10+)
  EDITOR_DOCUMENT_OPEN: "editor.document.open",
  EDITOR_DOCUMENT_SNAPSHOT_GET: "editor.document.snapshot.get",
  EDITOR_DOCUMENT_CHANGE_APPLY: "editor.document.change.apply",
  EDITOR_DOCUMENT_CHANGE_COMMIT: "editor.document.change.commit",
  EDITOR_COMPLETION_REQUEST: "editor.completion.request",
  EDITOR_DOCUMENT_CLOSE: "editor.document.close",
} as const;

/** Event names published on eventd. */
export const eventName = {
  /** GPU→CPU event from WGSL `emit_shader_event` (v0.2.7). */
  SHADER_EVENT: "shader.event",
  /** File-drop acceptance. */
  UI_FILE_DROP_ACCEPTED: "ui.file_drop.accepted",
  /** Blank-area click (v0.2.9). */
  UI_CLICK_BLANK: "ui.click_blank",
  /** Semantic event kind emitted when a NUI `code_editor` node commits its
   * document (v0.2.10+). Arrives over `ui.host.inbound` with the full
   * document text in the `text.value` payload; the node's `event` clause
   * names the intent action (e.g. `editor.commit`). */
  DOCUMENT_COMMIT: "document_commit",
} as const;

/** Animation control action (v0.2.10). */
export const AnimationAction = {
  Pause: "pause",
  Resume: "resume",
  Seek: "seek",
  Cancel: "cancel",
} as const;

export type AnimationAction = (typeof AnimationAction)[keyof typeof AnimationAction];

/** Helper: full RPC method `wgpu.ui.animation.<action>`. */
export function animationMethod(action: AnimationAction): string {
  return `${method.WGPU_UI_ANIMATION_PREFIX}${action}`;
}

//! Canonical wire constants and enums for the Neon3 protocol.
//!
//! Every service name, RPC method, event name, and animation action that used
//! to be a bare string literal in call sites now lives here. Import these and
//! your IDE will autocomplete; a typo becomes a compile error, not a runtime
//! `unsupported_method`.
//!
//! Snake_case on the wire is preserved: the Rust identifiers are
//! CamelCase variants of the snake_case strings.

/// Service target names (the `target` field of every RPC envelope).
pub mod service {
    /// Event bus. Default endpoint 127.0.0.1:39101.
    pub const EVENTD: &str = "eventd";
    /// UI runtime. Default endpoint 127.0.0.1:39102.
    pub const UI_RUNTIME: &str = "ui-runtime";
    /// WGPU renderer. Default endpoint 127.0.0.1:39103.
    pub const WGPU_RUNTIME: &str = "wgpu-runtime";
    /// Headless editor document service backing the NUI `code_editor`
    /// component (v0.2.10+). Serves the `editor.document.v1`,
    /// `editor.changeset.v1`, and `editor.completion.v1` capabilities.
    pub const EDITOR_RUNTIME: &str = "editor-runtime";
}

/// RPC method names, grouped by the service that answers them.
pub mod method {
    // --- service lifecycle ---
    pub const SERVICE_HEALTH: &str = "service.health";
    pub const SERVICE_DESCRIBE: &str = "service.describe";
    pub const SERVICE_SHUTDOWN: &str = "service.shutdown";

    // --- ui-runtime ---
    pub const UI_FLOW_COMPILE: &str = "ui.flow.compile";
    pub const UI_FLOW_SUBMIT: &str = "ui.flow.submit";
    pub const UI_FLOW_PATCH: &str = "ui.flow.patch";
    pub const UI_HOST_INBOUND: &str = "ui.host.inbound";
    pub const UI_INPUT_FRAME: &str = "ui.input.frame";
    pub const UI_HOST_POINTER_EVENT: &str = "ui.host.pointer_event";

    // --- debug ---
    pub const DEBUG_SNAPSHOT_GET: &str = "debug.snapshot.get";
    pub const DEBUG_UI_HOST_SNAPSHOT: &str = "debug.ui.host.snapshot";

    // --- wgpu-runtime: surfaces ---
    pub const RENDER_SURFACE_OPEN: &str = "render.surface.open";
    pub const RENDER_SURFACE_ACQUIRE: &str = "render.surface.acquire";
    pub const RENDER_SURFACE_FRAME: &str = "render.surface.frame";
    pub const RENDER_SURFACE_CAPTURE_PNG: &str = "render.surface.capture_png";

    // --- wgpu-runtime: diagnostics ---
    pub const WGPU_RENDER_DIAGNOSTICS: &str = "wgpu.render.diagnostics";
    pub const WGPU_RENDER_GRAPH_SNAPSHOT: &str = "wgpu.render.graph.snapshot";

    // --- wgpu-runtime: v0.2.7 shader extras ---
    pub const WGPU_UI_SET_VIEW_EXTRAS: &str = "wgpu.ui.set_view_extras";

    // --- wgpu-runtime: v0.2.10 animation timeline control ---
    pub const WGPU_UI_ANIMATION_PREFIX: &str = "wgpu.ui.animation.";

    // --- wgpu-runtime: custom text material packages ---
    pub const WGPU_SHADER_REGISTER: &str = "wgpu.shader.register";
    pub const WGPU_SHADER_STATE: &str = "wgpu.shader.state";

    // --- editor-runtime: code_editor document service (v0.2.10+) ---
    pub const EDITOR_DOCUMENT_OPEN: &str = "editor.document.open";
    pub const EDITOR_DOCUMENT_SNAPSHOT_GET: &str = "editor.document.snapshot.get";
    pub const EDITOR_DOCUMENT_CHANGE_APPLY: &str = "editor.document.change.apply";
    pub const EDITOR_DOCUMENT_CHANGE_COMMIT: &str = "editor.document.change.commit";
    pub const EDITOR_COMPLETION_REQUEST: &str = "editor.completion.request";
    pub const EDITOR_DOCUMENT_CLOSE: &str = "editor.document.close";

    // --- editor-runtime: LSP introspection (v0.2.12+) ---
    pub const EDITOR_LSP_DIAGNOSTICS: &str = "editor.lsp.diagnostics";
    pub const EDITOR_LSP_HOVER: &str = "editor.lsp.hover";
    pub const EDITOR_LSP_DEFINITION: &str = "editor.lsp.definition";
    pub const EDITOR_LSP_REFERENCES: &str = "editor.lsp.references";
    pub const EDITOR_LSP_SYMBOLS: &str = "editor.lsp.symbols";
    pub const EDITOR_LSP_SIGNATURE_HELP: &str = "editor.lsp.signature_help";
    pub const EDITOR_LSP_CONFIGURE: &str = "editor.lsp.configure";
    pub const EDITOR_LANGUAGE_CAPABILITIES: &str = "editor.language.capabilities";
}

/// Event names published on eventd.
pub mod event_name {
    /// GPU→CPU event emitted by WGSL `emit_shader_event(event_id, payload)`.
    /// v0.2.7. Payload: `{event_id: u32, payload: [f32; 4]}`.
    pub const SHADER_EVENT: &str = "shader.event";
    /// File-drop acceptance. Payload is `UiFileDropPayload`.
    pub const UI_FILE_DROP_ACCEPTED: &str = "ui.file_drop.accepted";
    /// Blank-area click (v0.2.9). Carries vec2 coordinates in the semantic
    /// intent payload; used for outside-click dismissal.
    pub const UI_CLICK_BLANK: &str = "ui.click_blank";
    /// Semantic event kind emitted when a NUI `code_editor` node commits its
    /// document (v0.2.10+). Arrives over `ui.host.inbound` with the full
    /// document text in the `text.value` payload; the node's `event` clause
    /// names the intent action (e.g. `editor.commit`).
    pub const DOCUMENT_COMMIT: &str = "document_commit";
}

/// Rendered surface kind (NUI `kind` field).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SurfaceKind {
    ScreenUi,
    WorldUi,
}

impl SurfaceKind {
    /// Wire string: `"screen_ui"` / `"world_ui"`.
    pub fn as_wire(self) -> &'static str {
        match self {
            Self::ScreenUi => "screen_ui",
            Self::WorldUi => "world_ui",
        }
    }
}

/// Animation control action (v0.2.10). Maps to `wgpu.ui.animation.<action>`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AnimationAction {
    Pause,
    Resume,
    Seek,
    Cancel,
}

impl AnimationAction {
    /// Wire suffix: `"pause"` / `"resume"` / `"seek"` / `"cancel"`.
    pub fn as_wire(self) -> &'static str {
        match self {
            Self::Pause => "pause",
            Self::Resume => "resume",
            Self::Seek => "seek",
            Self::Cancel => "cancel",
        }
    }

    /// Full RPC method: `wgpu.ui.animation.<action>`.
    pub fn method(self) -> String {
        format!("{}{}", method::WGPU_UI_ANIMATION_PREFIX, self.as_wire())
    }
}

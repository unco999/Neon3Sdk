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
}

/// RPC method names, grouped by the service that answers them.
pub mod method {
    // --- service lifecycle ---
    pub const SERVICE_HEALTH: &str = "service.health";
    pub const SERVICE_DESCRIBE: &str = "service.describe";
    pub const SERVICE_SHUTDOWN: &str = "service.shutdown";

    // --- ui-runtime ---
    pub const UI_FLOW_SUBMIT: &str = "ui.flow.submit";
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

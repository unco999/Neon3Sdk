//! Rendering, camera, external-surface, and pointer APIs.

use crate::client::NeonClient;
use crate::constants::{method as m, AnimationAction};
use crate::wire::RpcFailure;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SurfaceKind {
    ScreenUi,
    WorldUi,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct SurfaceSize {
    pub width: u32,
    pub height: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SurfaceOpen {
    pub session_id: String,
    pub surface_id: String,
    pub kind: SurfaceKind,
    pub size: SurfaceSize,
    #[serde(default = "default_format")]
    pub format: String,
    #[serde(default)]
    pub color_space: String,
    #[serde(default)]
    pub depth: bool,
    #[serde(default = "default_buffer_count")]
    pub buffer_count: u32,
}

fn default_format() -> String {
    "rgba8unorm".into()
}
fn default_buffer_count() -> u32 {
    1
}

/// A descriptor-backed shared surface. Native handles are never interpreted
/// by this SDK; `RenderClient::save_surface_png` asks the runtime to read
/// back and write a PNG.
#[derive(Debug, Clone)]
pub struct ExternalSurface {
    pub surface_id: String,
    pub descriptor: Value,
}

impl ExternalSurface {
    pub fn generation(&self) -> i64 {
        self.descriptor.get("generation").and_then(Value::as_i64).unwrap_or(-1)
    }
}

/// High-level wrapper for the WGPU runtime control-plane contract.
#[derive(Debug)]
pub struct RenderClient {
    client: NeonClient,
    pub target: String,
}

impl RenderClient {
    pub fn new(client: NeonClient, target: &str) -> Self {
        Self { client, target: target.into() }
    }

    pub fn diagnostics(&mut self) -> Result<Value, String> {
        let response = self.client.call(&self.target, "wgpu.render.diagnostics", json!({}))?;
        response.ok().map_err(|f: RpcFailure| f.to_string())
    }

    pub fn graph_snapshot(&mut self) -> Result<Value, String> {
        let response = self.client.call(&self.target, "wgpu.render.graph.snapshot", json!({}))?;
        response.ok().map_err(|f: RpcFailure| f.to_string())
    }

    pub fn open_surface(&mut self, open: &SurfaceOpen) -> Result<ExternalSurface, String> {
        if open.kind == SurfaceKind::WorldUi {
            return Err("world-ui surfaces require placement (not yet supported in the Rust SDK)".into());
        }
        if !(1..=3).contains(&open.buffer_count) {
            return Err("buffer_count must be between 1 and 3".into());
        }
        let params = json!({
            "session_id": open.session_id,
            "surface_id": open.surface_id,
            "kind": match open.kind { SurfaceKind::ScreenUi => "screen_ui", SurfaceKind::WorldUi => "world_ui" },
            "size": {"width": open.size.width, "height": open.size.height},
            "format": open.format,
            "color_space": open.color_space,
            "depth": open.depth,
            "buffer_count": open.buffer_count,
        });
        let response = self.client.call(&self.target, "render.surface.open", params)?;
        let result = response.ok().map_err(|f: RpcFailure| f.to_string())?;
        if !result.is_object() {
            return Err("render.surface.open returned a non-object result".into());
        }
        Ok(ExternalSurface {
            surface_id: open.surface_id.clone(),
            descriptor: result,
        })
    }

    /// Save the latest completed frame of a shared surface to a PNG file.
    pub fn save_surface_png(&mut self, surface: &ExternalSurface, path: &str) -> Result<Value, String> {
        let response = self.client.call(
            &self.target,
            "render.surface.capture_png",
            json!({"surface_id": surface.surface_id, "path": path}),
        )?;
        response.ok().map_err(|f: RpcFailure| f.to_string())
    }

    /// Acquire ring buffers for a consuming process (Windows host path).
    pub fn acquire_surface(&mut self, surface: &ExternalSurface, pid: u32) -> Result<Value, String> {
        let response = self.client.call(
            &self.target,
            "render.surface.acquire",
            json!({"surface_id": surface.surface_id, "pid": pid}),
        )?;
        response.ok().map_err(|f: RpcFailure| f.to_string())
    }

    /// Request a clean runtime shutdown.
    pub fn shutdown(&mut self) -> Result<Value, String> {
        let response = self.client.call(&self.target, "service.shutdown", json!({}))?;
        response.ok().map_err(|f: RpcFailure| f.to_string())
    }

    /// Upload 10 groups of `vec4<f32>` to the shader's `view.extras[0..9]`
    /// uniform (`wgpu.ui.set_view_extras`, v0.2.7).
    ///
    /// `extras` may have 1..=10 rows; missing rows are zero-padded to 10.
    /// Values outside the finite range are rejected locally before any RPC.
    pub fn set_view_extras(&mut self, extras: &[[f32; 4]]) -> Result<Value, String> {
        if extras.is_empty() || extras.len() > 10 {
            return Err(format!("extras must have 1..=10 rows, got {}", extras.len()));
        }
        for row in extras.iter() {
            for v in row.iter() {
                if !v.is_finite() {
                    return Err("view extras must contain only finite f32 values".into());
                }
            }
        }
        let mut padded: Vec<Vec<f32>> = extras.iter().map(|r| r.to_vec()).collect();
        while padded.len() < 10 {
            padded.push(vec![0.0; 4]);
        }
        let response = self.client.call(
            &self.target,
            m::WGPU_UI_SET_VIEW_EXTRAS,
            json!({ "extras": padded }),
        )?;
        response.ok().map_err(|f: RpcFailure| f.to_string())
    }

    /// Pause a renderer-owned animation timeline
    /// (`wgpu.ui.animation.pause`, v0.2.10). Requires the windowed renderer;
    /// headless surfaces return `backend_not_available`.
    pub fn animation_pause(&mut self, node_path: &str) -> Result<Value, String> {
        self.animation_control(AnimationAction::Pause, node_path, None)
    }

    /// Resume a paused animation timeline (`wgpu.ui.animation.resume`).
    pub fn animation_resume(&mut self, node_path: &str) -> Result<Value, String> {
        self.animation_control(AnimationAction::Resume, node_path, None)
    }

    /// Cancel an animation timeline (`wgpu.ui.animation.cancel`).
    pub fn animation_cancel(&mut self, node_path: &str) -> Result<Value, String> {
        self.animation_control(AnimationAction::Cancel, node_path, None)
    }

    /// Seek an animation timeline to `progress` in `[0.0, 1.0]`
    /// (`wgpu.ui.animation.seek`). Out-of-range progress is rejected locally.
    pub fn animation_seek(&mut self, node_path: &str, progress: f32) -> Result<Value, String> {
        if !(0.0..=1.0).contains(&progress) || !progress.is_finite() {
            return Err(format!("animation progress must be finite in [0, 1], got {progress}"));
        }
        self.animation_control(AnimationAction::Seek, node_path, Some(progress))
    }

    fn animation_control(
        &mut self,
        action: AnimationAction,
        node_path: &str,
        progress: Option<f32>,
    ) -> Result<Value, String> {
        if node_path.trim().is_empty() {
            return Err("node_path must be non-empty".into());
        }
        let mut params = serde_json::Map::new();
        params.insert("node_path".into(), json!(node_path));
        if let Some(p) = progress {
            params.insert("progress".into(), json!(p));
        }
        // The runtime rejects animation control without an envelope-level
        // idempotency key (see neon-wgpu-runtime v0.2.10 lib.rs).
        let idempotency_key = format!("anim:{node_path}:{}:{}", action.as_wire(), uuid::Uuid::new_v4());
        let response = self.client.call_with_idempotency(
            &self.target,
            &action.method(),
            Value::Object(params),
            Some(idempotency_key),
        )?;
        response.ok().map_err(|f: RpcFailure| f.to_string())
    }
}

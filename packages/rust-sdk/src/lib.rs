//! Neon3 Rust SDK.
//!
//! Talks the same `neon3.rpc` wire contract as the Python and Node SDKs over
//! loopback TCP (4-byte big-endian length prefix + UTF-8 JSON). Use it against
//! the desktop runtime, the headless GPU server, or the Android host endpoint.

pub mod android;
pub mod client;
pub mod constants;
pub mod editor;
pub mod error;
pub mod event;
pub mod facade;
pub mod render;
pub mod session;
pub mod wire;

pub use android::{ANDROID_HOST_ENDPOINT, ANDROID_HOST_PORT, AndroidConfig, AndroidSession, AndroidSessionHandle};
pub use client::{ClientOptions, NeonClient};
pub use editor::{
    ChangeSet, CompletionItem, CompletionTriggerKind, EditorChangeKind, EditorClient, EditorCompletionResult,
    EditorLspDiagnostic, EditorLspDiagnosticsResult, EditorLspLocation, EditorLspLocationsResult,
    EditorLspPositionRequest, EditorLspRange, EditorLspRawResult, EditorLspRef, EditorLspSymbol,
    EditorLspSymbolsResult, EditorOpenResult, EditorOperationResult, EditorPosition, EditorSelection,
    EditorSnapshot, EditOp, EDITOR_LANGUAGES, EDITOR_LANGUAGE_CPP, EDITOR_LANGUAGE_NUI_FLOW,
    EDITOR_LANGUAGE_RUST, EDITOR_LANGUAGE_TYPESCRIPT, MAX_CHANGESET_OPS, MAX_INSERT_BYTES, LspPosition,
};
pub use event::{EventClient, EventEnvelope, EventSubscription, ShaderEvent};
pub use render::{ExternalSurface, RenderClient, ShaderPackage, ShaderParameter, SurfaceKind, SurfaceOpen, SurfaceSize, shader_source_digest};
pub use session::{IntentResult, PatchOp, PublishResult, UiProgram, UiProgramRevision, UiSession, UiTarget, mount_flow_file, patch_flow_ops};
pub use wire::{ClientIdentity, RpcError, RpcFailure, RpcRequest, RpcResponse, Version};

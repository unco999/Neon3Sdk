//! Neon3 Rust SDK.
//!
//! Talks the same `neon3.rpc` wire contract as the Python and Node SDKs over
//! loopback TCP (4-byte big-endian length prefix + UTF-8 JSON). Use it against
//! the desktop runtime, the headless GPU server, or the Android host endpoint.

pub mod android;
pub mod client;
pub mod render;
pub mod session;
pub mod wire;

pub use android::{ANDROID_HOST_ENDPOINT, ANDROID_HOST_PORT, AndroidConfig, AndroidSession, AndroidSessionHandle};
pub use client::{ClientOptions, NeonClient};
pub use render::{ExternalSurface, RenderClient, SurfaceKind, SurfaceOpen, SurfaceSize};
pub use session::{IntentResult, PublishResult, UiProgram, UiProgramRevision, UiSession, UiTarget};
pub use wire::{ClientIdentity, RpcError, RpcFailure, RpcRequest, RpcResponse, Version};

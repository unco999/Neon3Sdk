//! Typed error hierarchy for the Neon3 Rust SDK.
//!
//! Mirrors the Python `neon3_sdk.errors` and Node `@neon3/sdk/errors`
//! hierarchy:
//!
//! ```text
//! NeonError
//! ├── Transport(String)       — TCP / timeout / frame transport failure
//! ├── Protocol(String)        — peer violated framing / envelope contract
//! ├── Remote { code, ... }    — runtime rejected the RPC
//! ├── CapabilityMissing(...)  — runtime doesn't advertise a required cap
//! └── InvalidArgument(...)    — caller passed a bad parameter
//! ```
//!
//! Existing code still returns `Result<T, String>`; new code should prefer
//! `Result<T, NeonError>`. `From<String>` is provided so call sites can
//! gradually migrate without a big-bang refactor.

use std::fmt;

#[derive(Debug)]
pub enum NeonError {
    /// A loopback connection, timeout, or frame transport failure. Retryable.
    Transport(String),

    /// The peer violated the RPC framing or envelope contract. Not retryable.
    Protocol(String),

    /// A Neon3 service rejected or failed an RPC request.
    Remote {
        /// Raw runtime error code (e.g. `stale_revision`).
        code: String,
        /// Human-readable message from the runtime.
        message: String,
        /// RPC request id for tracing.
        request_id: String,
        /// Whether retrying the same RPC is likely to help.
        retryable: bool,
    },

    /// A required runtime capability is not advertised.
    CapabilityMissing {
        missing: Vec<String>,
        service: String,
    },

    /// The caller passed an invalid argument (bad node_path, progress out of
    /// range, etc.). Not retryable.
    InvalidArgument(String),
}

impl NeonError {
    pub fn transport(msg: impl Into<String>) -> Self {
        Self::Transport(msg.into())
    }

    pub fn protocol(msg: impl Into<String>) -> Self {
        Self::Protocol(msg.into())
    }

    pub fn invalid_arg(msg: impl Into<String>) -> Self {
        Self::InvalidArgument(msg.into())
    }

    pub fn is_retryable(&self) -> bool {
        match self {
            Self::Transport(_) => true,
            Self::Remote { retryable, .. } => *retryable,
            _ => false,
        }
    }

    pub fn code(&self) -> &str {
        match self {
            Self::Transport(_) => "transport_error",
            Self::Protocol(_) => "protocol_error",
            Self::Remote { code, .. } => code,
            Self::CapabilityMissing { .. } => "capability_unavailable",
            Self::InvalidArgument(_) => "invalid_argument",
        }
    }
}

impl fmt::Display for NeonError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Transport(msg) => write!(f, "transport error: {msg}"),
            Self::Protocol(msg) => write!(f, "protocol error: {msg}"),
            Self::Remote { code, message, request_id, .. } => {
                write!(f, "{code}: {message} (request_id={request_id})")
            }
            Self::CapabilityMissing { missing, service } => {
                write!(f, "missing capabilities on {service}: {}", missing.join(", "))
            }
            Self::InvalidArgument(msg) => write!(f, "invalid argument: {msg}"),
        }
    }
}

impl std::error::Error for NeonError {}

/// Allow gradual migration: a bare String error becomes InvalidArgument.
impl From<String> for NeonError {
    fn from(s: String) -> Self {
        Self::InvalidArgument(s)
    }
}

impl From<&str> for NeonError {
    fn from(s: &str) -> Self {
        Self::InvalidArgument(s.to_string())
    }
}

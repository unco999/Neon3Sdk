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
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Source location attached to a NUI Flow compiler diagnostic.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct NuiFlowDiagnosticSpan {
    pub line: u32,
    pub column: u32,
    pub end_line: u32,
    pub end_column: u32,
}

/// One typed diagnostic emitted by the NUI Flow parse or compile stage.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NuiFlowDiagnostic {
    pub stage: String,
    pub code: String,
    pub severity: String,
    pub message: String,
    #[serde(default)]
    pub span: Option<NuiFlowDiagnosticSpan>,
}

/// Complete `NuiFlowCompileReport` returned by `ui.flow.compile` and carried
/// in `error.details` for rejected `ui.flow.submit` requests.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NuiFlowCompileReport {
    pub schema_version: u32,
    pub status: String,
    #[serde(default)]
    pub source_id: String,
    #[serde(default)]
    pub surface_id: Option<String>,
    #[serde(default)]
    pub program_revision: Option<u64>,
    #[serde(default)]
    pub node_count: Option<u64>,
    #[serde(default)]
    pub binding_count: Option<u64>,
    #[serde(default)]
    pub event_count: Option<u64>,
    #[serde(default)]
    pub layout_hash: Option<String>,
    #[serde(default)]
    pub diagnostics: Vec<NuiFlowDiagnostic>,
}

impl NuiFlowCompileReport {
    pub fn is_valid(&self) -> bool {
        self.status == "valid"
    }

    pub fn has_stage(&self, stage: &str) -> bool {
        self.diagnostics.iter().any(|diagnostic| diagnostic.stage == stage)
    }
}

/// A rejected NUI Flow compile gate with its complete typed report.
#[derive(Debug, Clone)]
pub struct NuiFlowCompileError {
    /// Stable top-level runtime code: `nui_flow_parse` or `nui_flow_compile`.
    pub code: String,
    pub message: String,
    pub status: String,
    pub request_id: String,
    pub current_revision: Option<u64>,
    pub object_id: Option<String>,
    pub report: NuiFlowCompileReport,
    /// The original `error.details` value, retained for forward-compatible
    /// fields that this SDK version does not model yet.
    pub details: Value,
}

impl NuiFlowCompileError {
    pub fn from_rpc_failure(failure: &crate::wire::RpcFailure) -> Result<Self, String> {
        let details = failure
            .details
            .clone()
            .ok_or_else(|| format!("{} response is missing error.details", failure.code))?;
        let report: NuiFlowCompileReport = serde_json::from_value(details.clone())
            .map_err(|e| format!("decode {} error.details: {e}", failure.code))?;
        Ok(Self {
            code: failure.code.clone(),
            message: failure.message.clone(),
            status: failure.status.clone(),
            request_id: failure.request_id.clone(),
            current_revision: failure.current_revision,
            object_id: failure.object_id.clone(),
            report,
            details,
        })
    }
}

impl fmt::Display for NuiFlowCompileError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {} (request_id={})", self.code, self.message, self.request_id)
    }
}

impl std::error::Error for NuiFlowCompileError {}

/// Errors returned by the structured NUI Flow compile/submit APIs.
#[derive(Debug, Clone)]
pub enum NuiFlowError {
    Transport(String),
    Protocol(String),
    /// A non-Flow remote failure, such as a downstream activation error.
    Remote(crate::wire::RpcFailure),
    Compile(NuiFlowCompileError),
    Decode(String),
}

impl NuiFlowError {
    pub fn from_rpc_failure(failure: crate::wire::RpcFailure) -> Self {
        if matches!(failure.code.as_str(), "nui_flow_parse" | "nui_flow_compile") {
            match NuiFlowCompileError::from_rpc_failure(&failure) {
                Ok(error) => Self::Compile(error),
                Err(message) => Self::Protocol(message),
            }
        } else {
            Self::Remote(failure)
        }
    }
}

impl fmt::Display for NuiFlowError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Transport(message) => write!(f, "transport error: {message}"),
            Self::Protocol(message) => write!(f, "protocol error: {message}"),
            Self::Remote(failure) => failure.fmt(f),
            Self::Compile(error) => error.fmt(f),
            Self::Decode(message) => write!(f, "decode error: {message}"),
        }
    }
}

impl std::error::Error for NuiFlowError {}

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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::wire::RpcFailure;
    use serde_json::json;

    fn report_json(status: &str) -> Value {
        json!({
            "schema_version": 1,
            "status": status,
            "source_id": "nui-flow",
            "surface_id": "surface.probe",
            "program_revision": 1,
            "node_count": 2,
            "binding_count": 0,
            "event_count": 0,
            "layout_hash": "fnv1a64-test",
            "diagnostics": [{
                "stage": "parse",
                "code": "nui_flow_unquoted_text",
                "severity": "error",
                "message": "literal text must be a single quoted token",
                "span": {"line": 4, "column": 1, "end_line": 4, "end_column": 1}
            }]
        })
    }

    #[test]
    fn compile_report_decodes_and_exposes_stage() {
        let report: NuiFlowCompileReport = serde_json::from_value(report_json("invalid")).unwrap();
        assert!(!report.is_valid());
        assert!(report.has_stage("parse"));
        assert_eq!(report.diagnostics[0].code, "nui_flow_unquoted_text");
        assert_eq!(report.diagnostics[0].span.unwrap().line, 4);
    }

    #[test]
    fn compile_error_keeps_typed_report_and_rpc_metadata() {
        let failure = RpcFailure {
            code: "nui_flow_parse".into(),
            message: "literal text must be a single quoted token".into(),
            status: "rejected".into(),
            request_id: "req-1".into(),
            revision: None,
            current_revision: Some(0),
            object_id: None,
            details: Some(report_json("invalid")),
        };
        let error = NuiFlowError::from_rpc_failure(failure);
        let NuiFlowError::Compile(error) = error else { panic!("expected compile error") };
        assert_eq!(error.code, "nui_flow_parse");
        assert_eq!(error.current_revision, Some(0));
        assert_eq!(error.report.diagnostics[0].stage, "parse");
        assert_eq!(error.details["source_id"], "nui-flow");
    }
}

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

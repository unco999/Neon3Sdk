//! Neon3 `neon3.rpc` wire contract: framing and envelope types.
//!
//! Every request/response/event frame is a 4-byte big-endian length prefix
//! followed by UTF-8 JSON. RPC requests cap at 128 MiB, event frames at
//! 64 KiB. Field names are canonical snake_case; a missing envelope field is
//! a `ProtocolError`. This module is transport-agnostic (loopback TCP,
//! adb forward, or future named pipes all use the same frames).

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::io::{self, Read, Write};

pub const PROTOCOL_NAME: &str = "neon3.rpc";
pub const PROTOCOL_VERSION: Version = Version { major: 1, minor: 0 };
pub const MAX_RPC_FRAME: usize = 128 * 1024 * 1024;
pub const MAX_EVENT_FRAME: usize = 64 * 1024;

/// Protocol version. Serialized as an object `{"major": 1, "minor": 0}`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Version {
    pub major: u32,
    pub minor: u32,
}

/// Client identity sent with every request.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClientIdentity {
    pub kind: String,
    pub instance_id: String,
    pub pid: u32,
    pub origin: String,
}

impl ClientIdentity {
    pub fn cli(origin: &str) -> Self {
        Self {
            kind: "cli".into(),
            instance_id: uuid::Uuid::new_v4().to_string(),
            pid: std::process::id(),
            origin: origin.into(),
        }
    }

    pub fn external_host(origin: &str) -> Self {
        Self {
            kind: "external_host".into(),
            instance_id: uuid::Uuid::new_v4().to_string(),
            pid: std::process::id(),
            origin: origin.into(),
        }
    }
}

/// A single `neon3.rpc` request envelope.
#[derive(Debug, Clone, Serialize)]
pub struct RpcRequest {
    pub protocol: &'static str,
    pub version: Version,
    pub request_id: String,
    pub client: ClientIdentity,
    pub target: String,
    pub method: String,
    pub params: Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub expected_revision: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub idempotency_key: Option<String>,
}

impl RpcRequest {
    pub fn new(target: &str, method: &str, params: Value, client: ClientIdentity) -> Self {
        Self {
            protocol: PROTOCOL_NAME,
            version: PROTOCOL_VERSION,
            request_id: uuid::Uuid::new_v4().to_string(),
            client,
            target: target.into(),
            method: method.into(),
            params,
            expected_revision: None,
            idempotency_key: None,
        }
    }
}

/// Error object inside a rejected/failed response.
#[derive(Debug, Clone, Deserialize)]
pub struct RpcError {
    pub code: String,
    pub message: String,
    #[serde(default)]
    pub current_revision: Option<u64>,
    #[serde(default)]
    pub object_id: Option<String>,
}

/// A `neon3.rpc` response envelope.
#[derive(Debug, Clone, Deserialize)]
pub struct RpcResponse {
    pub request_id: String,
    pub status: String,
    #[serde(default)]
    pub revision: Option<u64>,
    #[serde(default)]
    pub result: Option<Value>,
    #[serde(default)]
    pub snapshot: Option<Value>,
    #[serde(default)]
    pub error: Option<RpcError>,
}

impl RpcResponse {
    /// True when the runtime accepted the request.
    pub fn is_accepted(&self) -> bool {
        self.status == "accepted"
    }

    /// Result value, or the stable error code when rejected/failed.
    pub fn ok(self) -> Result<Value, RpcFailure> {
        if self.is_accepted() {
            Ok(self.result.unwrap_or(Value::Null))
        } else {
            Err(RpcFailure {
                code: self.error.as_ref().map(|e| e.code.clone()).unwrap_or_else(|| self.status.clone()),
                message: self.error.as_ref().map(|e| e.message.clone()).unwrap_or_default(),
                status: self.status,
                request_id: self.request_id,
                revision: self.revision,
            })
        }
    }
}

/// Machine-readable failure carried by a rejected/failed response.
#[derive(Debug, Clone)]
pub struct RpcFailure {
    pub code: String,
    pub message: String,
    pub status: String,
    pub request_id: String,
    pub revision: Option<u64>,
}

impl std::fmt::Display for RpcFailure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{} ({}): {} [request {}]", self.status, self.code, self.message, self.request_id)
    }
}

impl std::error::Error for RpcFailure {}

/// Serializes a frame and writes `4-byte BE length + UTF-8 JSON`.
pub fn write_frame<W: Write>(writer: &mut W, value: &Value) -> io::Result<()> {
    let bytes = serde_json::to_vec(value).map_err(io::Error::other)?;
    let len = bytes.len() as u32;
    writer.write_all(&len.to_be_bytes())?;
    writer.write_all(&bytes)
}

/// Reads `4-byte BE length + UTF-8 JSON` from the stream.
pub fn read_frame<R: Read>(reader: &mut R, max: usize) -> io::Result<Value> {
    let mut header = [0u8; 4];
    reader.read_exact(&mut header)?;
    let len = u32::from_be_bytes(header) as usize;
    if len > max {
        return Err(io::Error::new(io::ErrorKind::InvalidData, format!("frame too large: {len} > {max}")));
    }
    let mut bytes = vec![0u8; len];
    reader.read_exact(&mut bytes)?;
    serde_json::from_slice(&bytes).map_err(io::Error::other)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn frame_round_trip() {
        let value = serde_json::json!({"protocol": "neon3.rpc", "version": {"major": 1, "minor": 0}});
        let mut buf = Vec::new();
        write_frame(&mut buf, &value).unwrap();
        let json_len = serde_json::to_vec(&value).unwrap().len() as u32;
        assert_eq!(u32::from_be_bytes([buf[0], buf[1], buf[2], buf[3]]), json_len);
        assert_eq!(&buf[..4], &json_len.to_be_bytes());
        let parsed = read_frame(&mut &buf[..], MAX_RPC_FRAME).unwrap();
        assert_eq!(parsed["protocol"], "neon3.rpc");
        assert_eq!(parsed["version"]["major"], 1);
    }

    #[test]
    fn frame_too_large_rejected() {
        let value = serde_json::json!({"x": "y".repeat(100)});
        let mut buf = Vec::new();
        write_frame(&mut buf, &value).unwrap();
        assert!(read_frame(&mut &buf[..], 10).is_err());
    }

    #[test]
    fn response_ok_accepts_and_fails() {
        let accepted: RpcResponse = serde_json::from_value(serde_json::json!({
            "request_id": "r1", "status": "accepted", "revision": 3, "result": {"state": "healthy"}, "snapshot": null, "error": null
        })).unwrap();
        assert!(accepted.is_accepted());
        assert_eq!(accepted.ok().unwrap()["state"], "healthy");

        let rejected: RpcResponse = serde_json::from_value(serde_json::json!({
            "request_id": "r2", "status": "rejected", "revision": 7, "result": null, "snapshot": null,
            "error": {"code": "revision_conflict", "message": "stale"}
        })).unwrap();
        let failure = rejected.ok().unwrap_err();
        assert_eq!(failure.code, "revision_conflict");
        assert_eq!(failure.revision, Some(7));
    }
}

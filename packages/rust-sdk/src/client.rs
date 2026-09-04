//! `NeonClient`: framed RPC over loopback TCP (or any resolved endpoint).
//!
//! The default security posture is loopback-only: `127.x`, `localhost`, and
//! `::1`. Android transport connects through `adb forward` (loopback), so it
//! does not need to relax this. Set `allow_non_loopback = true` only when
//! connecting to a device IP directly.

use crate::wire::{
    ClientIdentity, RpcRequest, RpcResponse, read_frame, write_frame,
};
use serde_json::{Value, json};
use std::io::{BufReader, BufWriter, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::time::Duration;

#[derive(Debug, Clone)]
pub struct ClientOptions {
    pub origin: String,
    pub kind: String,
    pub timeout: Duration,
    pub max_frame_size: usize,
    pub allow_non_loopback: bool,
}

impl Default for ClientOptions {
    fn default() -> Self {
        Self {
            origin: "neon3-rust-sdk".into(),
            kind: "cli".into(),
            timeout: Duration::from_secs(5),
            max_frame_size: 128 * 1024 * 1024,
            allow_non_loopback: false,
        }
    }
}

/// A framed RPC client against one Neon3 endpoint.
pub struct NeonClient {
    reader: BufReader<TcpStream>,
    writer: BufWriter<TcpStream>,
    options: ClientOptions,
    endpoint: String,
}

impl std::fmt::Debug for NeonClient {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("NeonClient").field("endpoint", &self.endpoint).finish()
    }
}

fn is_loopback_host(host: &str) -> bool {
    host == "localhost" || host.starts_with("127.") || host == "::1"
}

impl NeonClient {
    /// Resolve the endpoint and enforce the loopback policy.
    pub fn connect(endpoint: &str, options: Option<ClientOptions>) -> Result<Self, String> {
        let options = options.unwrap_or_default();
        let mut sockets = endpoint.to_socket_addrs().map_err(|e| format!("resolve {endpoint}: {e}"))?;
        let addr = sockets.next().ok_or_else(|| format!("resolve {endpoint}: no addresses"))?;
        let host = addr.ip().to_string();
        if !options.allow_non_loopback && !is_loopback_host(&host) {
            return Err(format!("endpoint must be loopback (got {host}); use allow_non_loopback only for direct device IPs"));
        }
        let stream = TcpStream::connect_timeout(&addr, options.timeout)
            .map_err(|e| format!("connect {endpoint}: {e}"))?;
        stream.set_read_timeout(Some(options.timeout)).map_err(|e| format!("set read timeout: {e}"))?;
        stream.set_write_timeout(Some(options.timeout)).map_err(|e| format!("set write timeout: {e}"))?;
        Ok(Self {
            reader: BufReader::new(stream.try_clone().map_err(|e| e.to_string())?),
            writer: BufWriter::new(stream),
            options,
            endpoint: endpoint.to_string(),
        })
    }

    pub fn endpoint(&self) -> &str {
        &self.endpoint
    }

    fn identity(&self) -> ClientIdentity {
        ClientIdentity {
            kind: self.options.kind.clone(),
            instance_id: uuid::Uuid::new_v4().to_string(),
            pid: std::process::id(),
            origin: self.options.origin.clone(),
        }
    }

    /// Perform one framed RPC and return the parsed response envelope.
    pub fn call(&mut self, target: &str, method: &str, params: Value) -> Result<RpcResponse, String> {
        let request = RpcRequest::new(target, method, params, self.identity());
        write_frame(&mut self.writer, &serde_json::to_value(&request).map_err(|e| e.to_string())?)
            .map_err(|e| format!("write request: {e}"))?;
        self.writer.flush().map_err(|e| format!("flush request: {e}"))?;
        let frame = read_frame(&mut self.reader, self.options.max_frame_size)
            .map_err(|e| format!("read response: {e}"))?;
        let response: RpcResponse = serde_json::from_value(frame)
            .map_err(|e| format!("parse response: {e}"))?;
        if response.request_id != request.request_id {
            return Err(format!(
                "response request_id mismatch: expected {} got {}",
                request.request_id, response.request_id
            ));
        }
        Ok(response)
    }

    /// Convenience: health probe.
    pub fn health(&mut self, target: &str) -> Result<Value, String> {
        let response = self.call(target, "service.health", json!({}))?;
        response.ok().map_err(|f| f.to_string())
    }

    /// Convenience: service describe.
    pub fn describe(&mut self, target: &str) -> Result<Value, String> {
        let response = self.call(target, "service.describe", json!({}))?;
        response.ok().map_err(|f| f.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loopback_policy_rejects_public_host() {
        let err = NeonClient::connect("8.8.8.8:39103", None).unwrap_err();
        assert!(err.contains("loopback"), "unexpected: {err}");
    }

    #[test]
    fn loopback_policy_allows_localhost() {
        // No server at this port, but the policy check must pass and the
        // connect attempt may still fail; here we only assert the error is a
        // connection error, not a policy error.
        let err = NeonClient::connect("127.0.0.1:59999", None).unwrap_err();
        assert!(!err.contains("loopback"), "unexpected: {err}");
    }
}

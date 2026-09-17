use std::io::{BufReader, BufWriter, Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::time::Duration;

/// Client connection options.
#[derive(Clone, Debug)]
pub struct ClientOptions {
    pub timeout: Duration,
    pub max_frame_size: u32,
    pub kind: String,
    pub origin: String,
    pub allow_non_loopback: bool,
}

impl Default for ClientOptions {
    fn default() -> Self {
        Self {
            timeout: Duration::from_secs(30),
            max_frame_size: 128 * 1024 * 1024,
            kind: "cli".into(),
            origin: "unknown".into(),
            allow_non_loopback: false,
        }
    }
}

fn is_loopback_host(host: &str) -> bool {
    host == "localhost" || host.starts_with("127.") || host == "::1"
}

/// A framed RPC client against one Neon3 endpoint.
/// Each call opens a fresh TCP connection (server is one-request-per-connection).
pub struct NeonClient {
    options: ClientOptions,
    endpoint: String,
}

impl std::fmt::Debug for NeonClient {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("NeonClient").field("endpoint", &self.endpoint).finish()
    }
}

impl NeonClient {
    pub fn connect(endpoint: &str, options: Option<ClientOptions>) -> Result<Self, String> {
        let options = options.unwrap_or_default();
        let mut sockets = endpoint.to_socket_addrs().map_err(|e| format!("resolve {endpoint}: {e}"))?;
        let addr = sockets.next().ok_or_else(|| format!("resolve {endpoint}: no addresses"))?;
        let host = addr.ip().to_string();
        if !options.allow_non_loopback && !is_loopback_host(&host) {
            return Err(format!("endpoint must be loopback (got {host})"));
        }
        // Verify connectivity now
        let probe = TcpStream::connect_timeout(&addr, options.timeout)
            .map_err(|e| format!("connect {endpoint}: {e}"))?;
        drop(probe);
        Ok(Self { options, endpoint: endpoint.to_string() })
    }

    pub fn endpoint(&self) -> &str { &self.endpoint }

    fn identity(&self) -> ClientIdentity {
        ClientIdentity {
            kind: self.options.kind.clone(),
            instance_id: uuid::Uuid::new_v4().to_string(),
            pid: std::process::id(),
            origin: self.options.origin.clone(),
        }
    }

    fn dial(&self) -> Result<TcpStream, String> {
        let mut sockets = self.endpoint.to_socket_addrs().map_err(|e| format!("resolve: {e}"))?;
        let addr = sockets.next().ok_or_else(|| "no addr".to_string())?;
        let stream = TcpStream::connect_timeout(&addr, self.options.timeout)
            .map_err(|e| format!("connect: {e}"))?;
        stream.set_read_timeout(Some(self.options.timeout)).map_err(|e| format!("read timeout: {e}"))?;
        stream.set_write_timeout(Some(self.options.timeout)).map_err(|e| format!("write timeout: {e}"))?;
        Ok(stream)
    }

    pub fn call(&mut self, target: &str, method: &str, params: serde_json::Value) -> Result<RpcResponse, String> {
        self.call_with_idempotency(target, method, params, None)
    }

    pub fn call_with_idempotency(
        &mut self,
        target: &str,
        method: &str,
        params: serde_json::Value,
        idempotency_key: Option<String>,
    ) -> Result<RpcResponse, String> {
        self.call_full(target, method, params, idempotency_key, None)
    }

    pub(crate) fn call_full(
        &mut self,
        target: &str,
        method: &str,
        params: serde_json::Value,
        idempotency_key: Option<String>,
        expected_revision: Option<u64>,
    ) -> Result<RpcResponse, String> {
        let stream = self.dial()?;
        let mut writer = BufWriter::new(&stream);
        let mut reader = BufReader::new(&stream);

        let mut request = RpcRequest::new(target, method, params, self.identity());
        request.idempotency_key = idempotency_key;
        request.expected_revision = expected_revision;

        write_frame(&mut writer, &serde_json::to_value(&request).map_err(|e| e.to_string())?)
            .map_err(|e| format!("write: {e}"))?;
        writer.flush().map_err(|e| format!("flush: {e}"))?;

        let frame = read_frame(&mut reader, self.options.max_frame_size)
            .map_err(|e| format!("read response: {e}"))?;
        let response: RpcResponse = serde_json::from_value(frame).map_err(|e| format!("parse: {e}"))?;
        if response.request_id != request.request_id {
            return Err(format!("request_id mismatch"));
        }
        Ok(response)
    }

    pub fn health(&mut self, target: &str) -> Result<serde_json::Value, String> {
        let response = self.call(target, "service.health", serde_json::json!({}))?;
        response.ok().map_err(|f: RpcFailure| f.to_string())
    }
}

fn write_frame<W: Write>(w: &mut BufWriter<W>, value: &serde_json::Value) -> Result<(), String> {
    let bytes = serde_json::to_vec(value).map_err(|e| e.to_string())?;
    let len = bytes.len() as u32;
    w.write_all(&len.to_be_bytes()).map_err(|e| e.to_string())?;
    w.write_all(&bytes).map_err(|e| e.to_string())?;
    Ok(())
}

fn read_frame<R: Read>(r: &mut BufReader<R>, max: u32) -> Result<serde_json::Value, String> {
    let mut header = [0u8; 4];
    r.read_exact(&mut header).map_err(|e| e.to_string())?;
    let len = u32::from_be_bytes(header);
    if len > max {
        return Err(format!("frame too large: {len} > {max}"));
    }
    let mut buf = vec![0u8; len as usize];
    r.read_exact(&mut buf).map_err(|e| e.to_string())?;
    serde_json::from_slice(&buf).map_err(|e| e.to_string())
}

// Re-export types needed
pub use crate::wire::{ClientIdentity, RpcError, RpcFailure, RpcRequest, RpcResponse, Version};

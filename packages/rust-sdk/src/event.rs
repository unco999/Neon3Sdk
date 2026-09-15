//! `neon3.event` v1.0 client: long-lived subscription to eventd.
//!
//! Subscribe by event name (or name prefix), then read typed deliveries.
//! The canonical use case is listening for `shader.event` (v0.2.7), whose
//! payload is `{event_id: u32, payload: [f32; 4]}`.

use crate::wire::{ClientIdentity, MAX_EVENT_FRAME, read_frame, write_frame};
use serde::Deserialize;
use serde_json::{Value, json};
use std::io::{BufReader, BufWriter, Write};
use std::net::TcpStream;
use std::time::Duration;

const EVENT_PROTOCOL: &str = "neon3.event";

/// One delivery envelope from eventd. Only the fields callers care about
/// are decoded; the rest pass through as raw JSON.
#[derive(Debug, Clone, Deserialize)]
pub struct EventEnvelope {
    pub name: String,
    #[serde(default)]
    pub schema_version: u32,
    #[serde(default)]
    pub epoch: u64,
    #[serde(default)]
    pub sequence: u64,
    #[serde(default)]
    pub payload: Value,
}

/// A shader event emitted by WGSL `emit_shader_event(event_id, payload)`
/// (v0.2.7). `event_id` is a caller-chosen u32 (typically an FNV-1a hash);
/// `payload` is the 4-component vec4 the shader passed in.
#[derive(Debug, Clone, Copy)]
pub struct ShaderEvent {
    pub event_id: u32,
    pub payload: [f32; 4],
}

impl ShaderEvent {
    /// Parse from a `shader.event` delivery payload.
    pub fn from_payload(payload: &Value) -> Result<Self, String> {
        let event_id = payload
            .get("event_id")
            .and_then(Value::as_u64)
            .ok_or_else(|| "shader.event payload missing u32 event_id".to_string())?;
        let payload_arr = payload
            .get("payload")
            .and_then(Value::as_array)
            .ok_or_else(|| "shader.event payload missing vec4 array".to_string())?;
        if payload_arr.len() != 4 {
            return Err(format!("shader.event payload must have 4 components, got {}", payload_arr.len()));
        }
        let mut v = [0.0f32; 4];
        for (i, cell) in payload_arr.iter().enumerate() {
            v[i] = cell
                .as_f64()
                .ok_or_else(|| format!("shader.event payload[{i}] is not a number"))?
                as f32;
        }
        Ok(Self { event_id: event_id as u32, payload: v })
    }
}

/// A live subscription: one TCP connection to eventd, one filter.
pub struct EventSubscription {
    reader: BufReader<TcpStream>,
    writer: BufWriter<TcpStream>,
}

impl EventSubscription {
    /// Read the next delivery frame, optionally bounded by `timeout`.
    /// Returns `Err` on connection close or a malformed frame; a timeout
    /// surfaces as `Err("event recv timeout")`.
    pub fn recv(&mut self, timeout: Option<Duration>) -> Result<EventEnvelope, String> {
        let stream = self.reader.get_ref();
        stream
            .set_read_timeout(timeout)
            .map_err(|e| format!("set read timeout: {e}"))?;
        let frame = read_frame(&mut self.reader, MAX_EVENT_FRAME)
            .map_err(|e| format!("read delivery: {e}"))?;
        if frame.get("kind").and_then(Value::as_str) != Some("delivery") {
            return Err(format!("expected delivery frame, got {}", frame));
        }
        let event = frame
            .get("event")
            .ok_or_else(|| "delivery frame missing event".to_string())?;
        let envelope: EventEnvelope = serde_json::from_value(event.clone())
            .map_err(|e| format!("parse event envelope: {e}"))?;
        Ok(envelope)
    }

    /// Yield shader events as they arrive, filtering by the envelope name.
    /// Use `recv()` for non-shader events.
    pub fn shader_events(&mut self) -> Result<ShaderEvent, String> {
        loop {
            let envelope = self.recv(None)?;
            if envelope.name == "shader.event" {
                return ShaderEvent::from_payload(&envelope.payload);
            }
        }
    }
}

/// Connect to eventd and open named subscriptions.
pub struct EventClient {
    endpoint: String,
    instance_id: String,
    origin: String,
    timeout: Duration,
}

impl EventClient {
    pub fn new(endpoint: impl Into<String>) -> Self {
        Self {
            endpoint: endpoint.into(),
            instance_id: uuid::Uuid::new_v4().to_string(),
            origin: "neon3-rust-sdk".into(),
            timeout: Duration::from_secs(5),
        }
    }

    pub fn with_origin(mut self, origin: impl Into<String>) -> Self {
        self.origin = origin.into();
        self
    }

    /// Open a subscription filtered by exact event name.
    pub fn subscribe(&self, name: &str) -> Result<EventSubscription, String> {
        let stream = TcpStream::connect(&self.endpoint)
            .map_err(|e| format!("connect eventd {}: {e}", self.endpoint))?;
        stream
            .set_read_timeout(Some(self.timeout))
            .map_err(|e| format!("set read timeout: {e}"))?;
        stream
            .set_write_timeout(Some(self.timeout))
            .map_err(|e| format!("set write timeout: {e}"))?;

        let mut writer = BufWriter::new(stream.try_clone().map_err(|e| e.to_string())?);
        let reader = BufReader::new(stream);

        let subscribe = json!({
            "kind": "subscribe",
            "protocol": EVENT_PROTOCOL,
            "version": {"major": 1, "minor": 0},
            "request_id": format!("sub-{}", self.instance_id),
            "client": ClientIdentity {
                kind: "external_host".into(),
                instance_id: self.instance_id.clone(),
                pid: std::process::id(),
                origin: self.origin.clone(),
            },
            "filters": [{ "name": name, "name_prefix": Value::Null, "publisher_kinds": Value::Null }],
            "replay_from_sequence": Value::Null,
            "max_rate_hz": Value::Null,
        });
        write_frame(&mut writer, &subscribe).map_err(|e| format!("write subscribe: {e}"))?;
        writer.flush().map_err(|e| format!("flush subscribe: {e}"))?;

        let mut reader = reader;
        let ack = read_frame(&mut reader, MAX_EVENT_FRAME)
            .map_err(|e| format!("read ack: {e}"))?;
        if ack.get("kind").and_then(Value::as_str) != Some("ack")
            || ack.get("status").and_then(Value::as_str) != Some("accepted")
        {
            return Err(format!("event subscription rejected: {ack}"));
        }

        Ok(EventSubscription { reader, writer })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shader_event_parses_payload() {
        let payload = json!({
            "event_id": 0x5F3759DFu64,
            "payload": [0.1f64, 0.2, 0.3, 0.4]
        });
        let ev = ShaderEvent::from_payload(&payload).unwrap();
        assert_eq!(ev.event_id, 0x5F3759DF);
        assert_eq!(ev.payload[0], 0.1);
        assert_eq!(ev.payload[3], 0.4);
    }

    #[test]
    fn shader_event_rejects_wrong_length() {
        let payload = json!({ "event_id": 1u64, "payload": [0.1, 0.2] });
        assert!(ShaderEvent::from_payload(&payload).is_err());
    }
}

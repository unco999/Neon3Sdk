//! `UiSession`: the revision-aware UI session contract used by the Python
//! and Node SDKs. Handles `ui.flow.submit`, `ui.host.inbound`, and
//! `ui.input.frame` with strict input-revision bookkeeping.

use crate::client::NeonClient;
use crate::wire::{RpcFailure, RpcResponse};
use serde::Deserialize;
use serde_json::{Value, json};

#[derive(Debug, Clone, Deserialize)]
pub struct UiProgramRevision {
    pub program_id: String,
    pub revision: u64,
    pub schema_version: u16,
    #[serde(default)]
    pub capabilities: Vec<Value>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct UiProgram {
    pub surface_id: String,
    pub program_revision: UiProgramRevision,
    #[serde(default)]
    pub input_schema: Value,
}

/// The target service: desktop ui-runtime or the single Android endpoint
/// (which answers `ui.*` on `wgpu-runtime`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UiTarget {
    UiRuntime,
    WgpuRuntime,
}

impl UiTarget {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::UiRuntime => "ui-runtime",
            Self::WgpuRuntime => "wgpu-runtime",
        }
    }
}

#[derive(Debug, Clone)]
pub struct UiSession {
    pub input_revision: u64,
    pub program: Option<UiProgram>,
    target: UiTarget,
}

impl UiSession {
    pub fn new(target: UiTarget) -> Self {
        Self { input_revision: 0, program: None, target }
    }

    /// Compile and mount a NUI Flow source on the host.
    pub fn mount_flow(
        &mut self,
        client: &mut NeonClient,
        source: &str,
    ) -> Result<UiProgram, String> {
        let response = client.call(
            self.target.as_str(),
            "ui.flow.submit",
            json!({"source": source}),
        )?;
        let result = response.ok().map_err(|f: RpcFailure| f.to_string())?;
        let program: UiProgram = serde_json::from_value(result)
            .map_err(|e| format!("parse ui.flow.submit result: {e}"))?;
        self.program = Some(program.clone());
        Ok(program)
    }

    /// Dispatch a semantic intent to the host (`ui.host.inbound`).
    pub fn dispatch_intent(
        &mut self,
        client: &mut NeonClient,
        intent: &str,
        payload: Value,
    ) -> Result<IntentResult, String> {
        let event = json!({
            "event_id": format!("intent-{}", uuid::Uuid::new_v4()),
            "kind": "activate",
            "intent": intent,
            "source_node_key": "rust-sdk",
            "payload": payload,
            "program_revision": self.program.as_ref().map(|p| {
                json!({"program_id": p.program_revision.program_id, "revision": p.program_revision.revision})
            }).unwrap_or(Value::Null),
            "input_revision": self.input_revision,
            "request_id": uuid::Uuid::new_v4().to_string(),
            "idempotency_key": format!("intent:{}", uuid::Uuid::new_v4()),
            "interaction": null,
        });
        let response = client.call(
            self.target.as_str(),
            "ui.host.inbound",
            json!({"kind": "semantic_intent", "event": event}),
        )?;
        let status = response.status.clone();
        let result = response.ok().map_err(|f: RpcFailure| f.to_string())?;
        let accepted_revision = result
            .get("semantic_intent")
            .and_then(|inner| inner.get("accepted_input_revision"))
            .and_then(Value::as_u64)
            .unwrap_or(self.input_revision + 1);
        self.input_revision = accepted_revision;
        Ok(IntentResult {
            status,
            input_revision: accepted_revision,
            result,
        })
    }

    /// Publish external scalar inputs (`ui.input.frame`).
    pub fn publish(
        &mut self,
        client: &mut NeonClient,
        changes: &[Value],
    ) -> Result<PublishResult, String> {
        let response = client.call(
            self.target.as_str(),
            "ui.input.frame",
            json!({
                "program_revision": self.program.as_ref().map(|p| {
                    json!({"program_id": p.program_revision.program_id, "revision": p.program_revision.revision})
                }).unwrap_or(Value::Null),
                "expected_input_revision": self.input_revision,
                "request_id": uuid::Uuid::new_v4().to_string(),
                "idempotency_key": format!("frame:{}", uuid::Uuid::new_v4()),
                "changes": changes,
            }),
        )?;
        if response.status == "rejected"
            && response.error.as_ref().map(|e| e.code.as_str()) == Some("ui_program_stale_input_revision")
        {
            // Stale: refresh the host input revision and retry once.
            let snapshot = client.call(
                self.target.as_str(),
                "debug.ui.host.snapshot",
                json!({}),
            )?;
            if let Ok(value) = snapshot.ok() {
                if let Some(rev) = value.pointer("/scalar_inputs/input_revision").and_then(Value::as_u64) {
                    self.input_revision = rev;
                }
            }
            return self.publish(client, changes);
        }
        let status = response.status.clone();
        let result = response.ok().map_err(|f: RpcFailure| f.to_string())?;
        let accepted = result
            .get("accepted_input_revision")
            .and_then(Value::as_u64)
            .unwrap_or(self.input_revision + 1);
        self.input_revision = accepted;
        Ok(PublishResult { status, input_revision: accepted, result })
    }
}

#[derive(Debug, Clone)]
pub struct IntentResult {
    pub status: String,
    pub input_revision: u64,
    pub result: Value,
}

#[derive(Debug, Clone)]
pub struct PublishResult {
    pub status: String,
    pub input_revision: u64,
    pub result: Value,
}

/// Convenience: run the standard session flow against a client.
pub fn mount_flow_file(client: &mut NeonClient, source: &str) -> Result<UiProgram, String> {
    UiSession::new(UiTarget::UiRuntime).mount_flow(client, source)
}

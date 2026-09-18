//! `UiSession`: the revision-aware UI session contract used by the Python
//! and Node SDKs. Handles `ui.flow.submit`, `ui.host.inbound`, and
//! `ui.input.frame` with strict input-revision bookkeeping.

use crate::client::NeonClient;
use crate::constants::method as m;
use crate::error::{NuiFlowCompileReport, NuiFlowError};
use crate::wire::RpcFailure;
use crate::ui_patch::UiPatch;
use crate::tree::TreeIntent;
use crate::diff::DiffIntent;
use crate::conversation::ConversationIntent;
use crate::approval::ApprovalIntent;
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

    /// Run the public NUI Flow compile gate without activating the program.
    ///
    /// Parse/compile failures return `NuiFlowError::Compile`, whose `report`
    /// contains the exact structured diagnostics from `error.details`.
    pub fn compile_flow(
        &mut self,
        client: &mut NeonClient,
        source: &str,
    ) -> Result<NuiFlowCompileReport, NuiFlowError> {
        let response = client
            .call(self.target.as_str(), m::UI_FLOW_COMPILE, json!({"source": source}))
            .map_err(NuiFlowError::Transport)?;
        let result = response
            .ok()
            .map_err(NuiFlowError::from_rpc_failure)?;
        serde_json::from_value(result)
            .map_err(|e| NuiFlowError::Decode(format!("decode {} result: {e}", m::UI_FLOW_COMPILE)))
    }

    /// Compile and mount a NUI Flow source, preserving structured diagnostics.
    pub fn mount_flow_checked(
        &mut self,
        client: &mut NeonClient,
        source: &str,
    ) -> Result<UiProgram, NuiFlowError> {
        let idem = format!("flow-mount:{}", uuid::Uuid::new_v4());
        let response = client
            .call_with_idempotency(
                self.target.as_str(),
                m::UI_FLOW_SUBMIT,
                json!({"source": source}),
                Some(idem),
            )
            .map_err(NuiFlowError::Transport)?;
        let result = response
            .ok()
            .map_err(NuiFlowError::from_rpc_failure)?;
        let program: UiProgram = serde_json::from_value(result)
            .map_err(|e| NuiFlowError::Decode(format!("parse {} result: {e}", m::UI_FLOW_SUBMIT)))?;
        self.program = Some(program.clone());
        Ok(program)
    }

    /// Compile and mount a NUI Flow source on the host.
    ///
    /// This legacy entry point keeps its `String` error signature. New code
    /// should use `mount_flow_checked` to inspect `NuiFlowCompileError.report`.
    pub fn mount_flow(
        &mut self,
        client: &mut NeonClient,
        source: &str,
    ) -> Result<UiProgram, String> {
        self.mount_flow_checked(client, source)
            .map_err(|error| error.to_string())
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
            m::UI_HOST_INBOUND,
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
            m::UI_INPUT_FRAME,
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
                m::DEBUG_UI_HOST_SNAPSHOT,
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

    /// Apply the formal versioned patch contract without rebuilding Flow.
    pub fn patch(&mut self, client: &mut NeonClient, patch: &UiPatch) -> Result<Value, String> {
        patch.validate()?;
        let response = client.call_with_idempotency(
            self.target.as_str(),
            m::UI_FLOW_PATCH,
            serde_json::to_value(patch).map_err(|e| format!("encode ui patch: {e}"))?,
            Some(format!("ui-patch:{}:{}", patch.surface_id, uuid::Uuid::new_v4())),
        )?;
        response.ok().map_err(|f: RpcFailure| f.to_string())
    }

    /// Send a revisioned TreeView intent through the existing semantic event
    /// channel. The renderer never becomes the authority for tree state.
    pub fn dispatch_tree_intent(&mut self, client: &mut NeonClient, intent: &TreeIntent) -> Result<IntentResult, String> {
        self.dispatch_intent(client, intent.name(), intent.payload())
    }

    /// Send a patch-review intent through the semantic event channel.
    pub fn dispatch_diff_intent(&mut self, client: &mut NeonClient, intent: &DiffIntent) -> Result<IntentResult, String> {
        self.dispatch_intent(client, intent.name(), intent.payload())
    }

    /// Send a conversation action through the semantic event channel.
    pub fn dispatch_conversation_intent(&mut self, client: &mut NeonClient, intent: &ConversationIntent) -> Result<IntentResult, String> {
        self.dispatch_intent(client, intent.name(), intent.payload())
    }

    /// Send a tool approval or execution action through semantic intents.
    pub fn dispatch_approval_intent(&mut self, client: &mut NeonClient, intent: &ApprovalIntent) -> Result<IntentResult, String> {
        self.dispatch_intent(client, intent.name(), intent.payload())
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

/// One patch operation.
#[derive(serde::Serialize)]
pub struct PatchOp {
    pub kind: &'static str,
    pub path: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub property: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub value: Option<String>,
}

/// Apply an incremental patch to the currently mounted flow.
/// Faster than full remount: skips text parsing.
/// revision: current IR revision (starts at 1, increments per patch).
pub fn patch_flow_ops(
    client: &mut NeonClient,
    revision: u64,
    ops: &[PatchOp],
) -> Result<Value, String> {
    let idem = format!("flow-patch:{}", uuid::Uuid::new_v4());
    let response = client.call_with_idempotency(
        "ui-runtime",
        "ui.flow.patch",
        json!({ "revision": revision, "operations": ops }),
        Some(idem),
    )?;
    let result = response.ok().map_err(|f: RpcFailure| f.to_string())?;
    Ok(result)
}

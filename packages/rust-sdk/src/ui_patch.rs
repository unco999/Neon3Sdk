//! Versioned UI patch and workbench state contracts.
//!
//! These types deliberately contain no renderer details. They are the SDK
//! boundary for updating a persistent UI shell without rebuilding the whole
//! NUI Flow program.

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// A stable semantic node in a mounted UI shell.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct UiNode {
    pub node_path: String,
    pub kind: String,
    #[serde(default, skip_serializing_if = "serde_json::Map::is_empty")]
    pub properties: serde_json::Map<String, Value>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub children: Vec<UiNode>,
}

impl UiNode {
    pub fn new(node_path: impl Into<String>, kind: impl Into<String>) -> Self {
        Self { node_path: node_path.into(), kind: kind.into(), properties: serde_json::Map::new(), children: Vec::new() }
    }

    pub fn property(mut self, name: impl Into<String>, value: Value) -> Self {
        self.properties.insert(name.into(), value);
        self
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TransitionSpec {
    pub name: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub duration_ms: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub easing: Option<String>,
}

/// Formal versioned patch contract. `base_revision` is the revision the
/// producer read; the runtime must reject a stale patch rather than guessing.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct UiPatch {
    pub surface_id: String,
    pub base_revision: u64,
    pub operations: Vec<UiPatchOp>,
}

impl UiPatch {
    pub fn new(surface_id: impl Into<String>, base_revision: u64) -> Self {
        Self { surface_id: surface_id.into(), base_revision, operations: Vec::new() }
    }

    pub fn push(mut self, operation: UiPatchOp) -> Self {
        self.operations.push(operation);
        self
    }

    pub fn validate(&self) -> Result<(), String> {
        if self.surface_id.trim().is_empty() { return Err("surface_id must be non-empty".into()); }
        if self.operations.is_empty() { return Err("patch must contain at least one operation".into()); }
        for operation in &self.operations {
            operation.validate()?;
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case")]
pub enum UiPatchOp {
    SetProperty { node_path: String, property: String, value: Value },
    InsertNode { parent_path: String, index: usize, node: UiNode },
    RemoveNode { node_path: String },
    ReplaceChildren { parent_path: String, children: Vec<UiNode> },
    MoveNode { node_path: String, parent_path: String, index: usize },
    StartTransition { node_path: String, transition: TransitionSpec },
    SetInput { key: String, value: Value },
}

impl UiPatchOp {
    fn validate(&self) -> Result<(), String> {
        let path = match self {
            Self::SetProperty { node_path, .. } | Self::RemoveNode { node_path }
            | Self::MoveNode { node_path, .. } | Self::StartTransition { node_path, .. } => node_path,
            Self::InsertNode { parent_path, .. } | Self::ReplaceChildren { parent_path, .. } => parent_path,
            Self::SetInput { key, .. } => key,
        };
        if path.trim().is_empty() { return Err("patch operation path/key must be non-empty".into()); }
        Ok(())
    }
}

/// The stable route names used by the Agents shell.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ActiveView { Chat, Settings, Changes, Approvals }

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AgentWorkbenchState {
    pub revision: u64,
    pub active_view: ActiveView,
    pub session_id: String,
    pub pending_turn: bool,
    #[serde(default)]
    pub messages: Vec<Value>,
    #[serde(default)]
    pub tool_calls: Vec<Value>,
    #[serde(default)]
    pub approvals: Vec<Value>,
    #[serde(default)]
    pub changes: Vec<Value>,
    #[serde(default)]
    pub settings: serde_json::Map<String, Value>,
}

impl AgentWorkbenchState {
    pub fn new(session_id: impl Into<String>) -> Self {
        Self { revision: 0, active_view: ActiveView::Chat, session_id: session_id.into(), pending_turn: false,
            messages: Vec::new(), tool_calls: Vec::new(), approvals: Vec::new(), changes: Vec::new(), settings: serde_json::Map::new() }
    }

    /// Reduce one host event and return a patch against the previous state.
    pub fn reduce(&mut self, event: WorkbenchEvent) -> UiPatch {
        let base_revision = self.revision;
        let mut patch = UiPatch::new("agents", base_revision);
        match event {
            WorkbenchEvent::SetView(view) => {
                self.active_view = view;
                patch = patch.push(UiPatchOp::SetInput { key: "active_view".into(), value: serde_json::to_value(view).unwrap() });
            }
            WorkbenchEvent::SetPendingTurn(value) => {
                self.pending_turn = value;
                patch = patch.push(UiPatchOp::SetProperty { node_path: "AgentsRoot/ViewHost/ChatView/TaskStatus".into(), property: "pending".into(), value: Value::Bool(value) });
            }
            WorkbenchEvent::AppendMessage(message) => {
                let index = self.messages.len();
                self.messages.push(message.clone());
                patch = patch.push(UiPatchOp::InsertNode { parent_path: "AgentsRoot/ViewHost/ChatView/Transcript".into(), index,
                    node: UiNode::new(format!("AgentsRoot/ViewHost/ChatView/Transcript/{index}"), "message").property("data", message) });
            }
            WorkbenchEvent::SetSetting { key, value } => {
                self.settings.insert(key.clone(), value.clone());
                patch = patch.push(UiPatchOp::SetProperty { node_path: "AgentsRoot/ViewHost/SettingsView".into(), property: key, value });
            }
        }
        self.revision += 1;
        patch
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum WorkbenchEvent { SetView(ActiveView), SetPendingTurn(bool), AppendMessage(Value), SetSetting { key: String, value: Value } }

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn formal_patch_wire_shape_and_validation() {
        let patch = UiPatch::new("agents", 4).push(UiPatchOp::SetInput { key: "active_view".into(), value: json!("settings") });
        patch.validate().unwrap();
        assert_eq!(serde_json::to_value(patch).unwrap(), json!({"surface_id":"agents","base_revision":4,"operations":[{"op":"set_input","key":"active_view","value":"settings"}]}));
    }

    #[test]
    fn reducer_preserves_state_and_emits_local_operations() {
        let mut state = AgentWorkbenchState::new("session-1");
        let patch = state.reduce(WorkbenchEvent::SetView(ActiveView::Settings));
        assert_eq!(patch.base_revision, 0);
        assert_eq!(state.revision, 1);
        assert_eq!(state.active_view, ActiveView::Settings);
        assert_eq!(patch.operations.len(), 1);
    }
}

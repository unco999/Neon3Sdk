//! Revisioned bounded tree data contract for IDE/project views.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashSet;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TreeNodeState {
    Loaded,
    Loading,
    Error,
    PermissionDenied,
    Unloaded,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TreeNode {
    pub node_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub parent_id: Option<String>,
    pub kind: String,
    pub label: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub icon_key: Option<String>,
    pub has_children: bool,
    pub expanded: bool,
    pub state: TreeNodeState,
    pub selected: bool,
    #[serde(default)]
    pub payload: Value,
}

impl TreeNode {
    pub fn new(node_id: impl Into<String>, kind: impl Into<String>, label: impl Into<String>) -> Self {
        Self { node_id: node_id.into(), parent_id: None, kind: kind.into(), label: label.into(), icon_key: None,
            has_children: false, expanded: false, state: TreeNodeState::Loaded, selected: false, payload: Value::Null }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct TreeWindow {
    pub offset: u32,
    pub limit: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub total: Option<u32>,
}

impl TreeWindow {
    pub fn new(offset: u32, limit: u32) -> Self { Self { offset, limit, total: None } }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TreeFrame {
    pub tree_id: String,
    pub tree_revision: u64,
    pub epoch: u64,
    pub window: TreeWindow,
    pub nodes: Vec<TreeNode>,
    #[serde(default)]
    pub selected_node_ids: Vec<String>,
}

impl TreeFrame {
    pub fn validate(&self) -> Result<(), String> {
        if self.tree_id.trim().is_empty() { return Err("tree_id must be non-empty".into()); }
        if self.window.limit == 0 { return Err("tree window limit must be greater than zero".into()); }
        if self.nodes.len() > self.window.limit as usize { return Err("tree frame exceeds window limit".into()); }
        let ids: HashSet<&str> = self.nodes.iter().map(|node| node.node_id.as_str()).collect();
        if ids.len() != self.nodes.len() { return Err("tree node IDs must be unique".into()); }
        for node in &self.nodes {
            if node.node_id.trim().is_empty() { return Err("tree node_id must be non-empty".into()); }
            if let Some(parent_id) = &node.parent_id {
                if parent_id == &node.node_id { return Err("tree node cannot parent itself".into()); }
                // A parent may be outside a bounded window, but an in-window
                // parent must never be duplicated or point at itself.
                if ids.contains(parent_id.as_str()) && parent_id == &node.node_id { return Err("invalid tree parent".into()); }
            }
        }
        if self.selected_node_ids.iter().any(|id| !ids.contains(id.as_str())) {
            return Err("selected node is outside the bounded frame".into());
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum TreeIntent {
    Expand { tree_id: String, tree_revision: u64, epoch: u64, node_id: String },
    Select { tree_id: String, tree_revision: u64, epoch: u64, node_id: String, additive: bool },
    Rename { tree_id: String, tree_revision: u64, epoch: u64, node_id: String, label: String },
    Create { tree_id: String, tree_revision: u64, epoch: u64, parent_id: Option<String>, kind: String, label: String },
    Delete { tree_id: String, tree_revision: u64, epoch: u64, node_id: String },
}

impl TreeIntent {
    pub fn name(&self) -> &'static str {
        match self { Self::Expand { .. } => "tree.expand", Self::Select { .. } => "tree.select", Self::Rename { .. } => "tree.rename", Self::Create { .. } => "tree.create", Self::Delete { .. } => "tree.delete" }
    }

    pub fn payload(&self) -> Value {
        match self {
            Self::Expand { tree_id, tree_revision, epoch, node_id } => serde_json::json!({"tree_id":tree_id,"tree_revision":tree_revision,"epoch":epoch,"node_id":node_id}),
            Self::Select { tree_id, tree_revision, epoch, node_id, additive } => serde_json::json!({"tree_id":tree_id,"tree_revision":tree_revision,"epoch":epoch,"node_id":node_id,"additive":additive}),
            Self::Rename { tree_id, tree_revision, epoch, node_id, label } => serde_json::json!({"tree_id":tree_id,"tree_revision":tree_revision,"epoch":epoch,"node_id":node_id,"label":label}),
            Self::Create { tree_id, tree_revision, epoch, parent_id, kind, label } => serde_json::json!({"tree_id":tree_id,"tree_revision":tree_revision,"epoch":epoch,"parent_id":parent_id,"kind":kind,"label":label}),
            Self::Delete { tree_id, tree_revision, epoch, node_id } => serde_json::json!({"tree_id":tree_id,"tree_revision":tree_revision,"epoch":epoch,"node_id":node_id}),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bounded_frame_rejects_duplicate_and_out_of_window_selection() {
        let mut frame = TreeFrame { tree_id: "files".into(), tree_revision: 3, epoch: 2, window: TreeWindow::new(0, 2), nodes: vec![TreeNode::new("a", "file", "a")], selected_node_ids: vec!["missing".into()] };
        assert!(frame.validate().is_err());
        frame.selected_node_ids = vec!["a".into()];
        assert!(frame.validate().is_ok());
    }

    #[test]
    fn intent_keeps_domain_revision_and_stable_id() {
        let intent = TreeIntent::Expand { tree_id: "files".into(), tree_revision: 9, epoch: 4, node_id: "src".into() };
        assert_eq!(intent.name(), "tree.expand");
        assert_eq!(intent.payload()["node_id"], "src");
        assert_eq!(intent.payload()["tree_revision"], 9);
    }
}

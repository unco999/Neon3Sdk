//! Editor document APIs backing the NUI `code_editor` component
//! (`editor-runtime`, v0.2.10+).
//!
//! The editor domain logic lives in the runtime's pure `neon-editor-core`
//! (buffer, rule-table highlighting, undo/redo, completion). This module is
//! the host-side counterpart: open documents, apply change sets, commit
//! revisions, and request completions over the wire, mirroring the exact
//! serde shapes of `neon-editor-runtime`.

use crate::client::NeonClient;
use crate::constants::{method as m, service};
use crate::wire::RpcFailure;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

/// The only editor language the runtime supports today.
pub const EDITOR_LANGUAGE_NUI_FLOW: &str = "nui_flow";

/// Mirrors `MAX_CHANGESET_OPS` in `neon-editor-runtime`.
pub const MAX_CHANGESET_OPS: usize = 256;
/// Mirrors `MAX_INSERT_BYTES` in `neon-editor-runtime`.
pub const MAX_INSERT_BYTES: usize = 64 * 1024;

/// A position in the document (line/column, both in `char` units).
/// Mirrors `neon_editor_core::buffer::Position`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct EditorPosition {
    pub line: u32,
    pub column: u32,
}

impl EditorPosition {
    pub const START: EditorPosition = EditorPosition { line: 0, column: 0 };

    pub fn new(line: u32, column: u32) -> Self {
        Self { line, column }
    }
}

/// An ordered selection range. Mirrors `neon-editor-runtime::EditorSelection`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct EditorSelection {
    pub anchor: EditorPosition,
    pub active: EditorPosition,
}

impl EditorSelection {
    pub fn between(anchor: EditorPosition, active: EditorPosition) -> Self {
        Self { anchor, active }
    }
}

/// One edit operation. Mirrors `neon_editor_core::edits::EditOp` exactly:
/// the JSON is tagged with `"kind": "insert" | "delete"`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum EditOp {
    Insert {
        line: u32,
        column: u32,
        /// Position just past the inserted text (a newline insert ends on the
        /// next line, so this cannot be derived from `column + text.len()`).
        end: EditorPosition,
        text: String,
    },
    Delete {
        start: EditorPosition,
        end: EditorPosition,
        /// Deleted text, kept for undo.
        text: String,
    },
}

impl EditOp {
    pub fn insert(line: u32, column: u32, end: EditorPosition, text: impl Into<String>) -> Self {
        Self::Insert { line, column, end, text: text.into() }
    }

    pub fn delete(start: EditorPosition, end: EditorPosition, text: impl Into<String>) -> Self {
        Self::Delete { start, end, text: text.into() }
    }
}

/// A host-side change set. Mirrors `neon_editor_core::edits::ChangeSet`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChangeSet {
    /// Document revision the ops apply on top of.
    pub base_revision: u64,
    pub ops: Vec<EditOp>,
}

impl ChangeSet {
    pub fn new(base_revision: u64, ops: Vec<EditOp>) -> Self {
        Self { base_revision, ops }
    }

    /// Local pre-flight matching the runtime limits (`editor_changeset_invalid`
    /// / `editor_change_set_overflow`): 1..=256 ops, each insert at most
    /// 64 KiB of UTF-8.
    pub fn validate(&self) -> Result<(), String> {
        if self.ops.is_empty() || self.ops.len() > MAX_CHANGESET_OPS {
            return Err(format!("change set must contain 1..={MAX_CHANGESET_OPS} ops, got {}", self.ops.len()));
        }
        for op in &self.ops {
            if let EditOp::Insert { text, .. } = op {
                if text.len() > MAX_INSERT_BYTES {
                    return Err(format!("single insert exceeds {MAX_INSERT_BYTES} bytes, got {}", text.len()));
                }
            }
        }
        Ok(())
    }

    pub fn to_wire(&self) -> Value {
        serde_json::to_value(self).unwrap_or(Value::Null)
    }
}

/// Change application mode: `"draft"` folds into the pending revision,
/// `"commit"` also advances `committed_revision`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EditorChangeKind {
    Draft,
    Commit,
}

impl EditorChangeKind {
    /// Wire string: `"draft"` / `"commit"`.
    pub fn as_wire(self) -> &'static str {
        match self {
            Self::Draft => "draft",
            Self::Commit => "commit",
        }
    }
}

/// Completion trigger. Mirrors the runtime's `trigger_kind` strings.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CompletionTriggerKind {
    Automatic,
    Invoked,
    TriggerCharacter,
}

impl CompletionTriggerKind {
    /// Wire string: `"automatic"` / `"invoked"` / `"trigger_character"`.
    pub fn as_wire(self) -> &'static str {
        match self {
            Self::Automatic => "automatic",
            Self::Invoked => "invoked",
            Self::TriggerCharacter => "trigger_character",
        }
    }
}

/// A document snapshot returned by every editor method.
#[derive(Debug, Clone, Deserialize)]
pub struct EditorSnapshot {
    pub document_id: String,
    pub session_id: String,
    pub language: String,
    pub epoch: u64,
    pub revision: u64,
    pub committed_revision: u64,
    pub dirty: bool,
    pub line_count: u32,
    pub byte_length: u64,
    pub source_hash: String,
    pub source: String,
    #[serde(default)]
    pub diagnostics: Vec<Value>,
}

/// One completion candidate. Mirrors `neon_editor_core::CompletionItem`.
#[derive(Debug, Clone, Deserialize)]
pub struct CompletionItem {
    pub item_id: String,
    pub label: String,
    pub insert_text: String,
    pub replace_start: EditorPosition,
    pub replace_end: EditorPosition,
    pub kind: String,
    pub detail: String,
    pub sort_text: String,
    pub source: String,
    #[serde(default)]
    pub commit_characters: Vec<char>,
}

/// Result of `editor.completion.request`.
#[derive(Debug, Clone, Deserialize)]
pub struct EditorCompletionResult {
    pub document_id: String,
    pub document_revision: u64,
    pub position: EditorPosition,
    pub items: Vec<CompletionItem>,
}

/// Result of `editor.document.open`: freshly opened documents carry the
/// initial snapshot; re-opening returns `already_open` without one.
#[derive(Debug, Clone, Deserialize)]
pub struct EditorOpenResult {
    pub state: String,
    #[serde(default)]
    pub snapshot: Option<EditorSnapshot>,
}

/// Result of `editor.document.change.apply`.
#[derive(Debug, Clone, Deserialize)]
pub struct EditorOperationResult {
    pub state: String,
    pub snapshot: EditorSnapshot,
    pub applied_ops: usize,
    #[serde(default)]
    pub cursor: Option<EditorPosition>,
    #[serde(default)]
    pub selection: Option<EditorSelection>,
}

/// High-level wrapper for the headless editor document service.
#[derive(Debug)]
pub struct EditorClient {
    client: NeonClient,
    pub target: String,
}

impl EditorClient {
    /// `target` defaults to `editor-runtime`; override only when the endpoint
    /// multiplexes services (e.g. the Android host).
    pub fn new(client: NeonClient, target: &str) -> Self {
        Self { client, target: target.into() }
    }

    pub fn with_default_target(client: NeonClient) -> Self {
        Self::new(client, service::EDITOR_RUNTIME)
    }

    fn ok(&mut self, method: &str, params: Value) -> Result<Value, String> {
        self.client
            .call(&self.target, method, params)
            .and_then(|r| r.ok().map_err(|f: RpcFailure| f.to_string()))
    }

    fn ok_mutating(
        &mut self,
        method: &str,
        params: Value,
        idempotency_key: Option<String>,
    ) -> Result<Value, String> {
        let key = idempotency_key.unwrap_or_else(|| format!("editor:{method}:{}", uuid::Uuid::new_v4()));
        self.client
            .call_with_idempotency(&self.target, method, params, Some(key))
            .and_then(|r| r.ok().map_err(|f: RpcFailure| f.to_string()))
    }

    /// Open a document (`editor.document.open`). The runtime requires an
    /// envelope-level idempotency key; one is generated when omitted.
    pub fn open(
        &mut self,
        document_id: &str,
        session_id: &str,
        source: &str,
        language: &str,
        idempotency_key: Option<String>,
    ) -> Result<EditorOpenResult, String> {
        validate_identity(document_id, session_id)?;
        let language = if language.trim().is_empty() { EDITOR_LANGUAGE_NUI_FLOW } else { language };
        if language != EDITOR_LANGUAGE_NUI_FLOW {
            return Err(format!("unsupported editor language {language:?}; only {EDITOR_LANGUAGE_NUI_FLOW:?} is supported"));
        }
        let result = self.ok_mutating(
            m::EDITOR_DOCUMENT_OPEN,
            json!({
                "document_id": document_id,
                "session_id": session_id,
                "language": language,
                "source": source,
            }),
            idempotency_key,
        )?;
        serde_json::from_value(result).map_err(|e| format!("decode editor.document.open result: {e}"))
    }

    /// Fetch the current snapshot (`editor.document.snapshot.get`).
    pub fn snapshot(&mut self, document_id: &str, session_id: &str, epoch: u64) -> Result<EditorSnapshot, String> {
        validate_identity(document_id, session_id)?;
        let result = self.ok(
            m::EDITOR_DOCUMENT_SNAPSHOT_GET,
            json!({ "document_id": document_id, "session_id": session_id, "epoch": epoch }),
        )?;
        decode_snapshot(result, "editor.document.snapshot.get")
    }

    /// Apply a change set (`editor.document.change.apply`). The runtime
    /// requires an idempotency key; one is generated when omitted.
    /// `cursor` / `selection` update the renderer's caret state.
    #[allow(clippy::too_many_arguments)]
    pub fn apply_change(
        &mut self,
        document_id: &str,
        session_id: &str,
        epoch: u64,
        change_set: &ChangeSet,
        kind: EditorChangeKind,
        cursor: Option<EditorPosition>,
        selection: Option<EditorSelection>,
        idempotency_key: Option<String>,
    ) -> Result<EditorOperationResult, String> {
        validate_identity(document_id, session_id)?;
        change_set.validate()?;
        let mut params = json!({
            "document_id": document_id,
            "session_id": session_id,
            "epoch": epoch,
            "change_set": change_set.to_wire(),
            "kind": kind.as_wire(),
        });
        if let Some(cursor) = cursor {
            params["cursor"] = json!(cursor);
        }
        if let Some(selection) = selection {
            params["selection"] = json!(selection);
        }
        let result = self.ok_mutating(m::EDITOR_DOCUMENT_CHANGE_APPLY, params, idempotency_key)?;
        serde_json::from_value(result).map_err(|e| format!("decode editor.document.change.apply result: {e}"))
    }

    /// Commit the pending revision (`editor.document.change.commit`). The
    /// envelope carries `expected_revision`; a stale revision is rejected
    /// with `editor_revision_conflict` carrying the current revision.
    pub fn commit(
        &mut self,
        document_id: &str,
        session_id: &str,
        epoch: u64,
        expected_revision: u64,
    ) -> Result<EditorSnapshot, String> {
        validate_identity(document_id, session_id)?;
        let result = self
            .client
            .call_full(
                &self.target,
                m::EDITOR_DOCUMENT_CHANGE_COMMIT,
                json!({ "document_id": document_id, "session_id": session_id, "epoch": epoch }),
                Some(format!("editor:commit:{}:{}", document_id, uuid::Uuid::new_v4())),
                Some(expected_revision),
            )
            .and_then(|r| r.ok().map_err(|f: RpcFailure| f.to_string()))?;
        decode_snapshot(result, "editor.document.change.commit")
    }

    /// Request completion candidates at `position`
    /// (`editor.completion.request`). A stale `document_revision` is rejected
    /// with `editor_completion_stale`.
    pub fn completions(
        &mut self,
        document_id: &str,
        session_id: &str,
        epoch: u64,
        document_revision: u64,
        position: EditorPosition,
        trigger_kind: CompletionTriggerKind,
    ) -> Result<EditorCompletionResult, String> {
        validate_identity(document_id, session_id)?;
        let result = self.ok(
            m::EDITOR_COMPLETION_REQUEST,
            json!({
                "document_id": document_id,
                "session_id": session_id,
                "epoch": epoch,
                "document_revision": document_revision,
                "position": position,
                "trigger_kind": trigger_kind.as_wire(),
            }),
        )?;
        serde_json::from_value(result).map_err(|e| format!("decode editor.completion.request result: {e}"))
    }

    /// Close a document (`editor.document.close`). The runtime requires an
    /// idempotency key; one is generated when omitted. Returns
    /// `{"state": "closed", "document_id": ...}`.
    pub fn close(
        &mut self,
        document_id: &str,
        session_id: &str,
        epoch: u64,
        idempotency_key: Option<String>,
    ) -> Result<Value, String> {
        validate_identity(document_id, session_id)?;
        self.ok_mutating(
            m::EDITOR_DOCUMENT_CLOSE,
            json!({ "document_id": document_id, "session_id": session_id, "epoch": epoch }),
            idempotency_key,
        )
    }
}

fn validate_identity(document_id: &str, session_id: &str) -> Result<(), String> {
    if document_id.trim().is_empty() {
        return Err("document_id must be non-empty".into());
    }
    if session_id.trim().is_empty() {
        return Err("session_id must be non-empty".into());
    }
    Ok(())
}

fn decode_snapshot(result: Value, method: &str) -> Result<EditorSnapshot, String> {
    serde_json::from_value(result).map_err(|e| format!("decode {method} result: {e}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn edit_op_wire_shape_matches_runtime_serde() {
        let insert = EditOp::insert(3, 7, EditorPosition::new(3, 12), "hello");
        assert_eq!(
            serde_json::to_value(&insert).unwrap(),
            json!({"kind": "insert", "line": 3, "column": 7, "end": {"line": 3, "column": 12}, "text": "hello"})
        );
        let delete = EditOp::delete(EditorPosition::new(3, 7), EditorPosition::new(3, 12), "hello");
        assert_eq!(
            serde_json::to_value(&delete).unwrap(),
            json!({"kind": "delete", "start": {"line": 3, "column": 7}, "end": {"line": 3, "column": 12}, "text": "hello"})
        );
    }

    #[test]
    fn change_set_round_trip_and_validation() {
        let change_set = ChangeSet::new(4, vec![EditOp::insert(0, 0, EditorPosition::new(0, 1), "x")]);
        assert!(change_set.validate().is_ok());
        let wire = serde_json::to_value(&change_set).unwrap();
        assert_eq!(wire["base_revision"], 4);
        let parsed: ChangeSet = serde_json::from_value(wire).unwrap();
        assert_eq!(parsed, change_set);
        assert!(ChangeSet::new(0, vec![]).validate().is_err());
        assert!(ChangeSet::new(0, (0..257).map(|i| EditOp::insert(i as u32, 0, EditorPosition::START, "x")).collect()).validate().is_err());
        let big = "x".repeat(MAX_INSERT_BYTES + 1);
        assert!(ChangeSet::new(0, vec![EditOp::insert(0, 0, EditorPosition::START, big)]).validate().is_err());
    }

    #[test]
    fn wire_constants_and_enums_are_stable() {
        assert_eq!(service::EDITOR_RUNTIME, "editor-runtime");
        assert_eq!(m::EDITOR_DOCUMENT_OPEN, "editor.document.open");
        assert_eq!(m::EDITOR_DOCUMENT_SNAPSHOT_GET, "editor.document.snapshot.get");
        assert_eq!(m::EDITOR_DOCUMENT_CHANGE_APPLY, "editor.document.change.apply");
        assert_eq!(m::EDITOR_DOCUMENT_CHANGE_COMMIT, "editor.document.change.commit");
        assert_eq!(m::EDITOR_COMPLETION_REQUEST, "editor.completion.request");
        assert_eq!(m::EDITOR_DOCUMENT_CLOSE, "editor.document.close");
        assert_eq!(EditorChangeKind::Draft.as_wire(), "draft");
        assert_eq!(EditorChangeKind::Commit.as_wire(), "commit");
        assert_eq!(CompletionTriggerKind::Automatic.as_wire(), "automatic");
        assert_eq!(CompletionTriggerKind::Invoked.as_wire(), "invoked");
        assert_eq!(CompletionTriggerKind::TriggerCharacter.as_wire(), "trigger_character");
    }

    #[test]
    fn snapshot_decode_accepts_runtime_shape() {
        let snapshot: EditorSnapshot = serde_json::from_value(json!({
            "document_id": "doc-1", "session_id": "sess-1", "language": "nui_flow",
            "epoch": 2, "revision": 9, "committed_revision": 8, "dirty": true,
            "line_count": 12, "byte_length": 340, "source_hash": "abc", "source": "flow",
            "diagnostics": []
        }))
        .unwrap();
        assert_eq!(snapshot.revision, 9);
        assert!(snapshot.dirty);
    }

    #[test]
    fn completion_decode_accepts_runtime_shape() {
        let result: EditorCompletionResult = serde_json::from_value(json!({
            "document_id": "doc-1", "document_revision": 9,
            "position": {"line": 0, "column": 3},
            "items": [{
                "item_id": "k1", "label": "machine", "insert_text": "machine",
                "replace_start": {"line": 0, "column": 0}, "replace_end": {"line": 0, "column": 3},
                "kind": "keyword", "detail": "NUI keyword", "sort_text": "0machine",
                "source": "grammar", "commit_characters": [" ", "\n"]
            }]
        }))
        .unwrap();
        assert_eq!(result.items.len(), 1);
        assert_eq!(result.items[0].commit_characters, vec![' ', '\n']);
    }

    #[test]
    fn open_result_decodes_both_states() {
        let already: EditorOpenResult = serde_json::from_value(json!({"state": "already_open"})).unwrap();
        assert_eq!(already.state, "already_open");
        assert!(already.snapshot.is_none());
    }
}

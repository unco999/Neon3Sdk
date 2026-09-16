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
/// TypeScript / TSX documents (tree-sitter tokenize + LSP when available).
pub const EDITOR_LANGUAGE_TYPESCRIPT: &str = "typescript";
/// Rust documents (tree-sitter tokenize + LSP when available).
pub const EDITOR_LANGUAGE_RUST: &str = "rust";
/// C / C++ documents (tree-sitter tokenize + LSP when available).
pub const EDITOR_LANGUAGE_CPP: &str = "cpp";

/// Every language the editor runtime accepts.
pub const EDITOR_LANGUAGES: [&str; 4] = [
    EDITOR_LANGUAGE_NUI_FLOW,
    EDITOR_LANGUAGE_TYPESCRIPT,
    EDITOR_LANGUAGE_RUST,
    EDITOR_LANGUAGE_CPP,
];

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

/// One LSP diagnostic pushed by the language server. Severity follows LSP:
/// 1 = Error, 2 = Warning, 3 = Information, 4 = Hint.
#[derive(Debug, Clone, Deserialize)]
pub struct EditorLspDiagnostic {
    pub range: EditorLspRange,
    #[serde(default)]
    pub severity: Option<u8>,
    #[serde(default)]
    pub code: Option<String>,
    #[serde(default)]
    pub source: Option<String>,
    pub message: String,
}

/// Zero-based LSP range (start inclusive, end exclusive).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct EditorLspRange {
    pub start: LspPosition,
    pub end: LspPosition,
}

/// Zero-based LSP position (`character` is in UTF-16 code units).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct LspPosition {
    pub line: u32,
    pub character: u32,
}

/// A jump target (`editor.lsp.definition` / `references`).
#[derive(Debug, Clone, Deserialize)]
pub struct EditorLspLocation {
    pub uri: String,
    pub range: EditorLspRange,
}

/// One entry of `editor.lsp.symbols` (nested).
#[derive(Debug, Clone, Deserialize)]
pub struct EditorLspSymbol {
    pub name: String,
    /// LSP SymbolKind integer (12 = Function, 13 = Variable, ...).
    pub kind: u32,
    #[serde(default)]
    pub detail: Option<String>,
    pub range: EditorLspRange,
    pub selection_range: EditorLspRange,
    #[serde(default)]
    pub children: Vec<EditorLspSymbol>,
}

/// Result of `editor.lsp.diagnostics`.
#[derive(Debug, Clone, Deserialize)]
pub struct EditorLspDiagnosticsResult {
    pub document_id: String,
    pub document_revision: u64,
    pub diagnostics: Vec<EditorLspDiagnostic>,
    #[serde(default)]
    pub server_unavailable: Option<String>,
}

/// Result of `editor.lsp.definition` / `editor.lsp.references`.
#[derive(Debug, Clone, Deserialize)]
pub struct EditorLspLocationsResult {
    pub document_id: String,
    pub document_revision: u64,
    pub locations: Vec<EditorLspLocation>,
}

/// Result of `editor.lsp.symbols`.
#[derive(Debug, Clone, Deserialize)]
pub struct EditorLspSymbolsResult {
    pub document_id: String,
    pub document_revision: u64,
    pub symbols: Vec<EditorLspSymbol>,
}

/// Result of `editor.lsp.hover` / `editor.lsp.signature_help`: the raw LSP
/// payload (contents structure varies by server).
#[derive(Debug, Clone, Deserialize)]
pub struct EditorLspRawResult {
    pub document_id: String,
    pub document_revision: u64,
    pub result: Value,
}

/// Request wire shape for `editor.language.capabilities`.
#[derive(Debug, Clone, Serialize)]
pub struct EditorLanguageRef {
    pub language: String,
}

/// Request wire shape for `editor.lsp.diagnostics` / `editor.lsp.symbols`.
/// Mirrors `neon-editor-runtime::EditorLspRef`.
#[derive(Debug, Clone, Serialize)]
pub struct EditorLspRef {
    pub document_id: String,
    pub session_id: String,
    pub epoch: u64,
    pub document_revision: u64,
}

/// Request wire shape for `editor.lsp.configure`: merge fields over the
/// current server launch config for a language. Mirrors
/// `neon-editor-runtime::EditorLspConfigure`.
#[derive(Debug, Clone, Serialize)]
pub struct EditorLspConfigure {
    pub language: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub command: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub args: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub env: Option<std::collections::HashMap<String, String>>,
}

impl EditorLspConfigure {
    pub fn new(language: impl Into<String>) -> Self {
        Self {
            language: language.into(),
            command: None,
            args: None,
            env: None,
        }
    }

    pub fn command(mut self, command: impl Into<String>) -> Self {
        self.command = Some(command.into());
        self
    }

    pub fn args(mut self, args: Vec<String>) -> Self {
        self.args = Some(args);
        self
    }

    pub fn env(mut self, env: std::collections::HashMap<String, String>) -> Self {
        self.env = Some(env);
        self
    }
}

/// Result of `editor.lsp.configure`.
#[derive(Debug, Clone, Deserialize)]
pub struct EditorLspConfigureResult {
    pub language: String,
    pub state: String,
}

/// The active LSP server launch config reported by
/// `editor.language.capabilities`.
#[derive(Debug, Clone, Deserialize)]
pub struct EditorLspServerInfo {
    pub command: String,
    #[serde(default)]
    pub args: Vec<String>,
    #[serde(default)]
    pub env: std::collections::HashMap<String, String>,
}

/// Result of `editor.language.capabilities`.
#[derive(Debug, Clone, Deserialize)]
pub struct EditorLanguageCapabilitiesResult {
    pub language: String,
    pub syntax_highlight: bool,
    #[serde(default)]
    pub lsp_server: Option<EditorLspServerInfo>,
}

/// Request wire shape for position-scoped LSP methods.
/// Mirrors `neon-editor-runtime::EditorLspPosition`.
#[derive(Debug, Clone, Serialize)]
pub struct EditorLspPositionRequest {
    pub document_id: String,
    pub session_id: String,
    pub epoch: u64,
    pub document_revision: u64,
    pub position: EditorPosition,
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
        if !EDITOR_LANGUAGES.contains(&language) {
            return Err(format!(
                "unsupported editor language {language:?}; supported: {:?}",
                EDITOR_LANGUAGES
            ));
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

    /// Latest published diagnostics (`editor.lsp.diagnostics`). When the
    /// language server binary is missing, `server_unavailable` carries the
    /// reason and the document stays fully editable with tree-sitter
    /// highlighting.
    pub fn lsp_diagnostics(
        &mut self,
        document_id: &str,
        session_id: &str,
        epoch: u64,
        document_revision: u64,
    ) -> Result<EditorLspDiagnosticsResult, String> {
        validate_identity(document_id, session_id)?;
        let result = self.ok(
            m::EDITOR_LSP_DIAGNOSTICS,
            serde_json::to_value(EditorLspRef {
                document_id: document_id.into(),
                session_id: session_id.into(),
                epoch,
                document_revision,
            })
            .map_err(|e| e.to_string())?,
        )?;
        serde_json::from_value(result).map_err(|e| format!("decode {} result: {e}", m::EDITOR_LSP_DIAGNOSTICS))
    }

    /// Hover information at `position` (`editor.lsp.hover`). The raw LSP
    /// payload is returned; `result: null` when the server is unavailable.
    pub fn lsp_hover(
        &mut self,
        document_id: &str,
        session_id: &str,
        epoch: u64,
        document_revision: u64,
        position: EditorPosition,
    ) -> Result<EditorLspRawResult, String> {
        self.lsp_position_call(
            m::EDITOR_LSP_HOVER,
            document_id,
            session_id,
            epoch,
            document_revision,
            position,
        )
    }

    /// Jump-to-definition targets at `position` (`editor.lsp.definition`).
    pub fn lsp_definition(
        &mut self,
        document_id: &str,
        session_id: &str,
        epoch: u64,
        document_revision: u64,
        position: EditorPosition,
    ) -> Result<EditorLspLocationsResult, String> {
        let result = self.lsp_position_call_raw(
            m::EDITOR_LSP_DEFINITION,
            document_id,
            session_id,
            epoch,
            document_revision,
            position,
        )?;
        serde_json::from_value(result).map_err(|e| format!("decode {} result: {e}", m::EDITOR_LSP_DEFINITION))
    }

    /// All references of the symbol at `position` (`editor.lsp.references`).
    pub fn lsp_references(
        &mut self,
        document_id: &str,
        session_id: &str,
        epoch: u64,
        document_revision: u64,
        position: EditorPosition,
    ) -> Result<EditorLspLocationsResult, String> {
        let result = self.lsp_position_call_raw(
            m::EDITOR_LSP_REFERENCES,
            document_id,
            session_id,
            epoch,
            document_revision,
            position,
        )?;
        serde_json::from_value(result).map_err(|e| format!("decode {} result: {e}", m::EDITOR_LSP_REFERENCES))
    }

    /// Document outline (`editor.lsp.symbols`).
    pub fn lsp_symbols(
        &mut self,
        document_id: &str,
        session_id: &str,
        epoch: u64,
        document_revision: u64,
    ) -> Result<EditorLspSymbolsResult, String> {
        validate_identity(document_id, session_id)?;
        let result = self.ok(
            m::EDITOR_LSP_SYMBOLS,
            serde_json::to_value(EditorLspRef {
                document_id: document_id.into(),
                session_id: session_id.into(),
                epoch,
                document_revision,
            })
            .map_err(|e| e.to_string())?,
        )?;
        serde_json::from_value(result).map_err(|e| format!("decode {} result: {e}", m::EDITOR_LSP_SYMBOLS))
    }

    /// Signature help at `position` (`editor.lsp.signature_help`). The raw
    /// LSP payload is returned; `result: null` when the server is unavailable.
    pub fn lsp_signature_help(
        &mut self,
        document_id: &str,
        session_id: &str,
        epoch: u64,
        document_revision: u64,
        position: EditorPosition,
    ) -> Result<EditorLspRawResult, String> {
        self.lsp_position_call(
            m::EDITOR_LSP_SIGNATURE_HELP,
            document_id,
            session_id,
            epoch,
            document_revision,
            position,
        )
    }

    /// Configure the language-server launch command for a language
    /// (`editor.lsp.configure`). Fields are merged over the current config,
    /// so a later call can change just the executable or just the args.
    pub fn lsp_configure(
        &mut self,
        configure: EditorLspConfigure,
    ) -> Result<EditorLspConfigureResult, String> {
        if configure.language.trim().is_empty() {
            return Err("language is required".into());
        }
        let result = self.ok(
            m::EDITOR_LSP_CONFIGURE,
            serde_json::to_value(configure).map_err(|e| e.to_string())?,
        )?;
        serde_json::from_value(result)
            .map_err(|e| format!("decode {} result: {e}", m::EDITOR_LSP_CONFIGURE))
    }

    /// Query what the process can do for one language right now
    /// (`editor.language.capabilities`): syntax highlighting availability
    /// and the active LSP server config.
    pub fn language_capabilities(
        &mut self,
        language: &str,
    ) -> Result<EditorLanguageCapabilitiesResult, String> {
        if language.trim().is_empty() {
            return Err("language is required".into());
        }
        let result = self.ok(
            m::EDITOR_LANGUAGE_CAPABILITIES,
            serde_json::to_value(EditorLanguageRef {
                language: language.into(),
            })
            .map_err(|e| e.to_string())?,
        )?;
        serde_json::from_value(result)
            .map_err(|e| format!("decode {} result: {e}", m::EDITOR_LANGUAGE_CAPABILITIES))
    }

    fn lsp_position_call(
        &mut self,
        method: &str,
        document_id: &str,
        session_id: &str,
        epoch: u64,
        document_revision: u64,
        position: EditorPosition,
    ) -> Result<EditorLspRawResult, String> {
        let result = self.lsp_position_call_raw(
            method,
            document_id,
            session_id,
            epoch,
            document_revision,
            position,
        )?;
        serde_json::from_value(result).map_err(|e| format!("decode {method} result: {e}"))
    }

    fn lsp_position_call_raw(
        &mut self,
        method: &str,
        document_id: &str,
        session_id: &str,
        epoch: u64,
        document_revision: u64,
        position: EditorPosition,
    ) -> Result<Value, String> {
        validate_identity(document_id, session_id)?;
        self.ok(
            method,
            serde_json::to_value(EditorLspPositionRequest {
                document_id: document_id.into(),
                session_id: session_id.into(),
                epoch,
                document_revision,
                position,
            })
            .map_err(|e| e.to_string())?,
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

    #[test]
    fn lsp_constants_and_languages_are_stable() {
        assert_eq!(m::EDITOR_LSP_DIAGNOSTICS, "editor.lsp.diagnostics");
        assert_eq!(m::EDITOR_LSP_HOVER, "editor.lsp.hover");
        assert_eq!(m::EDITOR_LSP_DEFINITION, "editor.lsp.definition");
        assert_eq!(m::EDITOR_LSP_REFERENCES, "editor.lsp.references");
        assert_eq!(m::EDITOR_LSP_SYMBOLS, "editor.lsp.symbols");
        assert_eq!(m::EDITOR_LSP_SIGNATURE_HELP, "editor.lsp.signature_help");
        assert!(EDITOR_LANGUAGES.contains(&EDITOR_LANGUAGE_NUI_FLOW));
        assert!(EDITOR_LANGUAGES.contains(&EDITOR_LANGUAGE_TYPESCRIPT));
        assert!(EDITOR_LANGUAGES.contains(&EDITOR_LANGUAGE_RUST));
        assert!(EDITOR_LANGUAGES.contains(&EDITOR_LANGUAGE_CPP));
    }

    #[test]
    fn lsp_results_decode_runtime_shapes() {
        let diagnostics: EditorLspDiagnosticsResult = serde_json::from_value(json!({
            "document_id": "doc-1", "document_revision": 3,
            "diagnostics": [{
                "range": {"start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 9}},
                "severity": 1, "code": "E0308", "source": "rustc", "message": "mismatched types"
            }],
            "server_unavailable": null
        }))
        .unwrap();
        assert_eq!(diagnostics.diagnostics[0].code.as_deref(), Some("E0308"));
        assert_eq!(diagnostics.diagnostics[0].range.start.character, 4);

        let symbols: EditorLspSymbolsResult = serde_json::from_value(json!({
            "document_id": "doc-1", "document_revision": 3,
            "symbols": [{
                "name": "main", "kind": 12,
                "range": {"start": {"line": 0, "character": 0}, "end": {"line": 2, "character": 1}},
                "selection_range": {"start": {"line": 0, "character": 3}, "end": {"line": 0, "character": 7}},
                "children": []
            }]
        }))
        .unwrap();
        assert_eq!(symbols.symbols[0].kind, 12);

        let locations: EditorLspLocationsResult = serde_json::from_value(json!({
            "document_id": "doc-1", "document_revision": 3,
            "locations": [{"uri": "file:///a.rs", "range": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 4}}}]
        }))
        .unwrap();
        assert_eq!(locations.locations[0].uri, "file:///a.rs");

        let raw: EditorLspRawResult = serde_json::from_value(json!({
            "document_id": "doc-1", "document_revision": 3, "result": null
        }))
        .unwrap();
        assert!(raw.result.is_null());
    }

    #[test]
    fn lsp_request_wire_shapes_match_runtime() {
        let request = EditorLspPositionRequest {
            document_id: "doc-1".into(),
            session_id: "sess-1".into(),
            epoch: 2,
            document_revision: 3,
            position: EditorPosition::new(0, 6),
        };
        assert_eq!(
            serde_json::to_value(&request).unwrap(),
            json!({
                "document_id": "doc-1", "session_id": "sess-1", "epoch": 2,
                "document_revision": 3, "position": {"line": 0, "column": 6}
            })
        );
    }
}

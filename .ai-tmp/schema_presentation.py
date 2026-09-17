# -*- coding: utf-8 -*-
"""Add UiCodeEditorPresentation + related snapshot types to neon-ui-schema,
and a UiEffect::CodeEditorPresentation variant for carrying them."""
p = r'D:\Neon3\crates\neon-ui-schema\src\lib.rs'
d = open(p, 'rb').read().decode('utf-8')
was_crlf = '\r\n' in d
d = d.replace('\r\n', '\n')

# 1) snapshot types after UiCodeEditorDeclaration impl block
anchor = '''impl UiCodeEditorDeclaration {
    pub fn validate(&self) -> bool {
        !self.node_key.trim().is_empty()
            && !self.source_input_key.trim().is_empty()
            && self.font_size.is_finite()
            && (6.0..=48.0).contains(&self.font_size)
            && (1..=8).contains(&self.tab_size)
            && self
                .read_only_input_key
                .as_ref()
                .is_none_or(|key| !key.trim().is_empty())
            && self
                .completion_input_key
                .as_ref()
                .is_none_or(|key| !key.trim().is_empty())
    }
}'''
new_types = '''impl UiCodeEditorDeclaration {
    pub fn validate(&self) -> bool {
        !self.node_key.trim().is_empty()
            && !self.source_input_key.trim().is_empty()
            && self.font_size.is_finite()
            && (6.0..=48.0).contains(&self.font_size)
            && (1..=8).contains(&self.tab_size)
            && self
                .read_only_input_key
                .as_ref()
                .is_none_or(|key| !key.trim().is_empty())
            && self
                .completion_input_key
                .as_ref()
                .is_none_or(|key| !key.trim().is_empty())
    }
}

/// Per-frame presentation snapshot for one code editor component.
///
/// Produced by the ui-runtime editor component (which owns the editable
/// buffer, grammar, highlight cache, completion engine and editing
/// semantics) and consumed by the WGPU renderer as pure data: the renderer
/// lays out glyphs and rects from this snapshot and never touches the editor
/// kernel, buffer, or edit state.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct UiCodeEditorPresentation {
    pub node_key: String,
    /// Monotonic snapshot revision. The renderer may skip re-layout when the
    /// revision is unchanged across fragments.
    pub revision: u64,
    /// Full document text. The renderer splits rows on '\\n' itself; token
    /// rows must cover the same row count.
    pub source: String,
    /// Per-row syntax token spans for coloring. One entry per row; spans must
    /// cover the row exactly and in order.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub token_rows: Vec<Vec<UiEditorTokenSpan>>,
    pub caret_line: u32,
    pub caret_column: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub selection_anchor_line: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub selection_anchor_column: Option<u32>,
    pub scroll_x: f32,
    pub scroll_y: f32,
    pub focus: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub completion: Option<UiEditorCompletionSnapshot>,
    /// Active transient edit effects (type-in / delete fragment). The
    /// renderer plays each effect for its declared duration, then retires it.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub edit_fx: Vec<UiEditorEditFx>,
    /// Lossless font zoom factor (Ctrl + wheel). The base size comes from
    /// the declaration's `font_size`.
    pub font_scale: f32,
    /// Wall-clock seconds of the last edit; the renderer keeps the caret
    /// solid briefly after an edit.
    pub last_edit_seconds: f32,
}

/// One colored syntax span inside an editor row. `class` is the stable
/// token-class name produced by the editor highlighter ("Keyword",
/// "StringLiteral", "NumberLiteral", ...); the renderer maps it to the
/// declared syntax colors / theme.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct UiEditorTokenSpan {
    pub text: String,
    pub class: String,
}

/// Completion popup snapshot. The item list is snapshotted when the popup
/// opens; typing or explicit dismissal closes it.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct UiEditorCompletionSnapshot {
    pub items: Vec<UiEditorCompletionItem>,
    pub selected: u32,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct UiEditorCompletionItem {
    pub label: String,
    /// Completion kind wire name ("function", "value", "keyword", ...).
    pub kind: String,
    #[serde(default)]
    pub detail: String,
}

/// One transient character-level edit effect. `text` carries the inserted or
/// deleted fragment so the renderer can resolve glyphs without touching the
/// editor buffer (insert fx follow the current layout; delete fx render a
/// ghost snapshot at the pre-delete position).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct UiEditorEditFx {
    /// "insert" or "delete".
    pub kind: String,
    /// Registered one-shot shader package id ("text-type-in", ...).
    pub package_id: String,
    pub row: u32,
    pub col: u32,
    pub text: String,
    pub started_seconds: f32,
    pub duration_ms: u32,
}

impl UiCodeEditorPresentation {
    pub fn validate(&self) -> bool {
        !self.node_key.trim().is_empty()
            && self.revision > 0
            && self.scroll_x.is_finite()
            && self.scroll_y.is_finite()
            && self.font_scale.is_finite()
            && self.font_scale > 0.0
            && self.last_edit_seconds.is_finite()
            && self
                .completion
                .as_ref()
                .is_none_or(|snapshot| snapshot.selected as usize <= snapshot.items.len().max(1) - 1)
    }
}'''
assert anchor in d, 'anchor missing'
d = d.replace(anchor, new_types)
print('snapshot types added')

# 2) UiEffect::CodeEditorPresentation variant after CodeEditorDeclaration
old_variant = '''    CodeEditorDeclaration {
        node_key: String,
        declaration: UiCodeEditorDeclaration,
    },
}'''
new_variant = '''    CodeEditorDeclaration {
        node_key: String,
        declaration: UiCodeEditorDeclaration,
    },
    /// Per-frame presentation snapshots for every code editor component in
    /// the fragment. Produced by the ui-runtime editor component; consumed by
    /// the unified renderer as pure data (no editor kernel contact).
    CodeEditorPresentation {
        presentations: std::collections::BTreeMap<String, UiCodeEditorPresentation>,
    },
}'''
assert old_variant in d, 'variant anchor missing'
d = d.replace(old_variant, new_variant)
print('UiEffect variant added')

open(p, 'wb').write(d.replace('\n', '\r\n').encode('utf-8') if was_crlf else d.encode('utf-8'))
print('done')

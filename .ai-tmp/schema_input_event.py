# -*- coding: utf-8 -*-
"""Add UiEditorInputEvent + key kind types to neon-ui-schema (renderer ->
ui-runtime editor component protocol)."""
p = r'D:\Neon3\crates\neon-ui-schema\src\lib.rs'
d = open(p, 'rb').read().decode('utf-8')
was_crlf = '\r\n' in d
d = d.replace('\r\n', '\n')

anchor = '''impl UiCodeEditorPresentation {
    pub fn validate(&self) -> bool {'''
new_types = '''/// Editor interaction event produced by the renderer's input dispatch and
/// consumed by the ui-runtime editor component. Pure data: the renderer maps
/// pointer positions to (line, column) with its font metrics and forwards the
/// resulting semantic events; editing semantics never run in the renderer.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum UiEditorInputEvent {
    Key {
        path: String,
        /// "character" (with the character payload) or "named" (NamedKey
        /// name such as "ArrowLeft", "Backspace", ...).
        kind: UiEditorKeyKind,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        text: Option<String>,
        shift: bool,
        ctrl: bool,
        /// Renderer-computed metrics so the ui-runtime can run
        /// scroll-into-view / page navigation without font access.
        viewport_height: f32,
        viewport_width: f32,
        row_height: f32,
        gutter_width: f32,
    },
    PointerPress {
        path: String,
        line: u32,
        column: u32,
    },
    PointerDrag {
        path: String,
        line: u32,
        column: u32,
    },
    PointerRelease,
    Scroll {
        path: String,
        delta: [f32; 2],
    },
    Zoom {
        path: String,
        factor: f32,
        viewport_height: f32,
        viewport_width: f32,
        row_height: f32,
        gutter_width: f32,
    },
    ImePreedit {
        path: String,
        value: String,
    },
    ImeCommit {
        path: String,
        value: String,
        viewport_height: f32,
        viewport_width: f32,
        row_height: f32,
        gutter_width: f32,
    },
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum UiEditorKeyKind {
    Character(String),
    Named(String),
}

impl UiCodeEditorPresentation {
    pub fn validate(&self) -> bool {'''
assert anchor in d, 'anchor missing'
d = d.replace(anchor, new_types)
open(p, 'wb').write(d.replace('\n', '\r\n').encode('utf-8') if was_crlf else d.encode('utf-8'))
print('input event types added')

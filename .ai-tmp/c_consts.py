# -*- coding: utf-8 -*-
"""Add missing NEON3_METHOD_* / NEON3_SEMANTIC_* consts to C SDK lib.rs
(kept in sync with include/neon3.h macros). Preserves CRLF line endings."""
p = r'D:\Neon3Sdk\packages\c-sdk\src\lib.rs'
raw = open(p, 'rb').read()
crlf = raw.count(b'\r\n') > raw.count(b'\n') / 2
d = raw.decode('utf-8')
if crlf:
    d = d.replace('\r\n', '\n')

old = 'const EDITOR_SERVICE: &str = "editor-runtime";'
assert d.count(old) == 1, 'anchor missing'
new = old + '''

// Canonical wire constants for the editor / shader surface. Values are kept
// in sync with include/neon3.h so Rust-side code and the C header can never
// drift: the same strings the wire contract defines.
pub const NEON3_METHOD_EDITOR_DOCUMENT_OPEN: &str = "editor.document.open";
pub const NEON3_METHOD_EDITOR_DOCUMENT_SNAPSHOT_GET: &str = "editor.document.snapshot.get";
pub const NEON3_METHOD_EDITOR_DOCUMENT_CHANGE_APPLY: &str = "editor.document.change.apply";
pub const NEON3_METHOD_EDITOR_CHANGE_COMMIT: &str = "editor.document.change.commit";
pub const NEON3_METHOD_EDITOR_COMPLETION_REQUEST: &str = "editor.completion.request";
pub const NEON3_METHOD_EDITOR_DOCUMENT_CLOSE: &str = "editor.document.close";
pub const NEON3_METHOD_WGPU_SHADER_REGISTER: &str = "wgpu.shader.register";
pub const NEON3_SEMANTIC_DOCUMENT_COMMIT: &str = "document_commit";'''
d = d.replace(old, new, 1)

out = d.replace('\n', '\r\n') if crlf else d
open(p, 'wb').write(out.encode('utf-8'))
print('lib.rs consts added; CRLF preserved:', crlf)

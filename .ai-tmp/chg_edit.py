# -*- coding: utf-8 -*-
d = open(r'D:\Neon3Sdk\CHANGELOG.md', 'rb').read().decode('utf-8')
crlf = '\r\n' in d
d = d.replace('\r\n', '\n')

old = '''- **C SDK event subscription ABI**: `neon3_event_subscribe` / `neon3_event_recv` /
  `neon3_event_subscription_free` — opaque handle wrapping the Rust `EventClient`.

### Changed'''
assert d.count(old) == 1, 'anchor'

new = '''- **C SDK event subscription ABI**: `neon3_event_subscribe` / `neon3_event_recv` /
  `neon3_event_subscription_free` — opaque handle wrapping the Rust `EventClient`.

- **Editor document APIs (editor-runtime, v0.2.10+)** — headless document
  service bindings in all five languages:
  - Rust: `editor.rs` — `EditorClient` with `open` / `snapshot` /
    `apply_change` / `commit` / `completions` / `close`; wire types
    (`EditOp` tagged insert/delete, `ChangeSet` with 1..=256 ops /
    64 KiB insert pre-flight, `EditorPosition` / `EditorSelection`,
    `EditorChangeKind` draft/commit, `CompletionTriggerKind`); re-exported
    from crate root.
  - Python: `editor.py` — `EditorClient` mirroring the Rust surface with
    `from_wire` / `to_wire` helpers.
  - Node: `editor.ts` — `EditorClient` mirroring the same methods.
  - C: `neon3_editor_open` / `neon3_editor_snapshot` / `neon3_editor_apply` /
    `neon3_editor_commit` / `neon3_editor_completions` / `neon3_editor_close`
    + canonical `NEON3_METHOD_EDITOR_*` / `NEON3_SEMANTIC_*` macros.
  - C++: `EditorClient` (borrows `Client`) and `EventSubscription` (RAII
    eventd subscription) wrappers in `neon3.hpp`; smoke test extended.

### Changed

- C SDK: wire method constants (`NEON3_METHOD_EDITOR_*`,
  `NEON3_METHOD_WGPU_SHADER_REGISTER`, `NEON3_SEMANTIC_DOCUMENT_COMMIT`) now
  defined in `src/lib.rs` as `pub const` in sync with `neon3.h` macros;
  crate-level `#![allow(non_camel_case_types)]` for the ABI handle names.
- Rust SDK: dropped unused `RpcResponse` import in `session.rs`; `writer` half
  of `EventSubscription` documented + `#[allow(dead_code)]`; `sdk_probe`
  removed a needless `mut`. Zero build warnings.'''

d = d.replace(old, new, 1)
if crlf:
    d = d.replace('\n', '\r\n')
open(r'D:\Neon3Sdk\CHANGELOG.md', 'wb').write(d.encode('utf-8'))
print('CHANGELOG updated')

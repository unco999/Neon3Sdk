## Highlights

- **Unified single-exe runtime (`neon3-runtime.exe`).** The four split binaries
  (`neon-eventd`, `neon-ui-runtime`, `neon-wgpu-runtime`, `neon-editor-runtime`)
  now live in one process, started with one command. Service endpoints are
  unchanged (eventd 39101 / ui 39102 / wgpu 39103 / editor 39104), so existing
  SDKs and scripts keep working without modification.

- **Editor kernel split into a standalone `neon-editor` library.** The
  language-agnostic core (text buffer, change sets, incremental highlight,
  symbols, completions) now lives in its own repository with zero Neon3
  dependencies, and gained a `Language` abstraction:
  - NUI Flow keeps its built-in table-driven grammar
  - TypeScript / Rust / C++ highlight through compiled **tree-sitter**
    grammars, mapped onto the same token representation as NUI Flow
  - A **LSP client bridge** (JSON-RPC over stdio/TCP, `lsp-types`) delegates
    completions / diagnostics to standard language servers (tsserver,
    rust-analyzer, clangd) on non-Flow languages

## Added

- `neon3-runtime` binary: `serve [--headless|--window] [--eventd <addr>]
  [--ui <addr>] [--wgpu <addr>] [--editor <addr>]`
- `neon-editor` crate: `Language::from_extension`, tree-sitter
  TS/Rust/C++ tokenizers, `LspClient` (initialize / didOpen / didChange /
  completion), `CompletionKind::Value` for LSP-sourced completions

## Changed

- Editor runtime and WGPU runtime now depend on the external `neon-editor`
  crate instead of the in-workspace core
- Workspace no longer builds `neon-editor-core` (moved out)

## Verification

- `cargo build --release` passes (Windows x86_64)
- `neon-editor` 42 unit tests green (incl. tree-sitter TS/Rust/C++ tokens)
- Live host probe: single process listens on 39101-39104; wgpu health and
  editor document.open both return OK via the C ABI

# Neon3 Rust SDK

Rust client SDK for the Neon3 control-plane protocol. Talks the same
`neon3.rpc` wire contract as the Python and Node SDKs over loopback TCP
(4-byte big-endian length prefix + UTF-8 JSON).

## Install

```toml
[dependencies]
neon3-sdk = { path = "../rust-sdk" }
```

Or from crates.io (after publish):

```toml
[dependencies]
neon3-sdk = "0.1"
```

## Quick start

### Low-level wire API

```rust
use neon3_sdk::{NeonClient, RenderClient, UiSession, UiTarget, constants};

let mut client = NeonClient::connect("127.0.0.1:39102", None)?;
let mut session = UiSession::new(UiTarget::UiRuntime);
let program = session.mount_flow(&mut client, include_str!("hello.nui"))?;

// Compile without activation and inspect structured parse/compile diagnostics.
match session.compile_flow(&mut client, include_str!("hello.nui")) {
    Ok(report) => assert!(report.is_valid()),
    Err(neon3_sdk::NuiFlowError::Compile(error)) => {
        eprintln!("{}: {}", error.code, error.message);
        for diagnostic in error.report.diagnostics { eprintln!("{}", diagnostic.message); }
    }
    Err(error) => return Err(error.to_string().into()),
}

// Renderer (needs a second connection to wgpu-runtime on :39103)
let mut render = RenderClient::new(
    NeonClient::connect("127.0.0.1:39103", None)?,
    constants::service::WGPU_RUNTIME,
);
render.set_view_extras(&[[1.0, 0.0, 0.0, 0.0]])?;
render.animation_seek("hero.timeline", 0.5)?;
```

### Facade (builder style)

```rust
use neon3_sdk::facade::App;

let mut app = App::connect("127.0.0.1:39102", "my-app")?;
app.mount("hello.nui")?;

app.state("count", 0)?;
app.on("btn.increment", |app, _payload| {
    let current = app.get_state("count").as_i64().unwrap_or(0);
    app.set_state("count", current + 1)?;
    Ok(())
})?;

app.anim().animation_seek("hero.timeline", 0.5)?;
app.view_extras(&[[0.1, 0.2, 0.3, 0.4]])?;
```

## What's included

- **`NeonClient`** — framed RPC over loopback TCP, loopback-only by default
- **`UiSession`** — `compile_flow`, structured `mount_flow_checked`, legacy `mount_flow`, `dispatch_intent`, and `publish`
- **`RenderClient`** — surfaces, `set_view_extras` (v0.2.7), `animation_*` (v0.2.10)
- **`EventClient`** — eventd subscription, `shader.event` typed model
- **`UiPatch` / `AgentWorkbenchState`** — versioned local UI updates and a minimal Agents shell reducer; submit with `UiSession::patch`
- **`TreeFrame` / `TreeIntent`** — bounded revisioned project tree data and stable semantic intents over `ui.host.inbound`
- **`DiffFrame` / `DiffIntent`** — bounded patch review data with per-hunk and whole-patch accept/reject intents
- **`ConversationFrame` / `ConversationStream`** — bounded streaming messages with sequence-gap, overflow, and epoch diagnostics
- **`AgentToolCall` / `ApprovalPrompt`** — tool/job/request/session identity, risk state, redacted summaries, and approval intents
- **`constants`** — service/method/event name constants + `SurfaceKind`/`AnimationAction` enums
- **`facade`** — builder-style `App` wrapper

## Testing

```bash
cargo test
```

Requires no running runtime; tests use offline/mock fixtures.

## Rust SDK RPC CLI

The Python package's `neon3-sdk` command is the project-level Neon3
development/lifecycle CLI. This Rust package provides a separate
`neon3-rust-sdk` RPC diagnostics command; it does not start or manage Neon3
services and is not a replacement for the Python CLI.

```bash
cargo run --bin neon3-rust-sdk -- --endpoint 127.0.0.1:39102 health
cargo run --bin neon3-rust-sdk -- --endpoint 127.0.0.1:39102 describe
cargo run --bin neon3-rust-sdk -- --endpoint 127.0.0.1:39102 snapshot
cargo run --bin neon3-rust-sdk -- --endpoint 127.0.0.1:39102 compile path/to/view.nui
```

Output is JSON on both success and failure. The process exits non-zero on
invalid arguments, transport errors, remote rejection, or invalid Flow.

The formal incremental UI contract is versioned by `surface_id` and
`base_revision`:

```rust
use neon3_sdk::{UiPatch, UiPatchOp};
use serde_json::json;

let patch = UiPatch::new("agents", 41).push(UiPatchOp::SetInput {
    key: "active_view".into(),
    value: json!("settings"),
});
session.patch(&mut client, &patch)?;
```

The runtime must reject a stale base revision. Use `AgentWorkbenchState::reduce`
to produce shell patches for view changes, pending turns, messages, and settings.

Executable boundary probes are available for the incremental contracts:
`cargo run --bin ui_patch_contract_probe`, `cargo run --bin tree_frame_probe`,
`cargo run --bin editor_document_probe`, and `cargo run --bin diff_review_probe`.
The conversation stream boundary is covered by `cargo run --bin conversation_probe`.
Approval behavior is covered by `cargo run --bin approval_probe`.

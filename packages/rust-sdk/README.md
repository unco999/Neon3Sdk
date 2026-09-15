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
- **`UiSession`** — `mount_flow`, `dispatch_intent`, `publish` with revision bookkeeping
- **`RenderClient`** — surfaces, `set_view_extras` (v0.2.7), `animation_*` (v0.2.10)
- **`EventClient`** — eventd subscription, `shader.event` typed model
- **`constants`** — service/method/event name constants + `SurfaceKind`/`AnimationAction` enums
- **`facade`** — builder-style `App` wrapper

## Testing

```bash
cargo test
```

Requires no running runtime; tests use offline/mock fixtures.

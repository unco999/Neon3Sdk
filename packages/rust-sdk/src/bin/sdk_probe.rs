//! End-to-end SDK probe: service.health -> ui.flow.submit -> openSurface ->
//! savePng -> service.shutdown against a running Neon3 runtime endpoint.
//!
//! Usage:
//!   cargo run --bin sdk_probe -- <endpoint> [png-path]

use neon3_sdk::{ClientOptions, NeonClient, RenderClient, SurfaceKind, SurfaceOpen, SurfaceSize, UiSession, UiTarget};
use serde_json::json;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let endpoint = args.get(1).cloned().unwrap_or_else(|| "127.0.0.1:43100".into());
    let png_path = args.get(2).cloned().unwrap_or_else(|| "sdk-probe.png".into());

    let mut client = match NeonClient::connect(&endpoint, Some(ClientOptions {
        origin: "rust-sdk-probe".into(),
        kind: "cli".into(),
        allow_non_loopback: true,
        ..Default::default()
    })) {
        Ok(c) => c,
        Err(e) => { eprintln!("{{\"step\":\"connect\",\"ok\":false,\"error\":{e:?}}}"); std::process::exit(1); }
    };

    // 1. health
    match client.health("wgpu-runtime") {
        Ok(h) => println!("{{\"step\":\"health\",\"ok\":true,\"status\":{}}}", h["status"]),
        Err(e) => { eprintln!("{{\"step\":\"health\",\"ok\":false,\"error\":{e:?}}}"); std::process::exit(1); }
    }

    // 2-3. UiSession: mount_flow + dispatch_intent (single Android-style endpoint)
    let flow = "version 1\nsurface example revision 1\nsurface root column\n  text title value \"Hello Rust SDK\"\n";
    let mut session = UiSession::new(UiTarget::WgpuRuntime);
    match session.mount_flow(&mut client, flow) {
        Ok(program) => println!("{{\"step\":\"ui.flow.submit\",\"ok\":true,\"surface_id\":{}}}", program.surface_id),
        Err(e) => { eprintln!("{{\"step\":\"ui.flow.submit\",\"ok\":false,\"error\":{e:?}}}"); std::process::exit(1); }
    }
    match session.dispatch_intent(&mut client, "app.greet", json!({})) {
        Ok(intent) => println!("{{\"step\":\"ui.host.inbound\",\"ok\":true,\"status\":{},\"input_revision\":{}}}", intent.status, intent.input_revision),
        Err(e) => { eprintln!("{{\"step\":\"ui.host.inbound\",\"ok\":false,\"error\":{e:?}}}"); std::process::exit(1); }
    }

    // 3. open shared surface
    let mut renderer = RenderClient::new(client, "wgpu-runtime");
    let open = SurfaceOpen {
        session_id: "rust-sdk-probe".into(),
        surface_id: "example".into(),
        kind: SurfaceKind::ScreenUi,
        size: SurfaceSize { width: 1280, height: 720 },
        format: "rgba8unorm".into(),
        color_space: "srgb".into(),
        depth: false,
        buffer_count: 2,
    };
    let mut surface = match renderer.open_surface(&open) {
        Ok(s) => s,
        Err(e) => { eprintln!("{{\"step\":\"render.surface.open\",\"ok\":false,\"error\":{e:?}}}"); std::process::exit(1); }
    };
    println!("{{\"step\":\"render.surface.open\",\"ok\":true,\"generation\":{}}}", surface.generation());

    // 4. save PNG
    std::thread::sleep(std::time::Duration::from_millis(1500));
    match renderer.save_surface_png(&surface, &png_path) {
        Ok(capture) => println!("{{\"step\":\"render.surface.capture_png\",\"ok\":true,\"artifact_path\":{}}}", capture["artifact_path"]),
        Err(e) => { eprintln!("{{\"step\":\"render.surface.capture_png\",\"ok\":false,\"error\":{e:?}}}"); std::process::exit(1); }
    }

    // 5. shutdown
    let _ = renderer.shutdown();
    println!("{{\"probe\":\"rust-sdk\",\"status\":\"passed\"}}");
}

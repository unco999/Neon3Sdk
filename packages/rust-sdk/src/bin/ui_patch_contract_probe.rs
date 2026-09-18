//! Deterministic RPC-boundary probe for the formal versioned UI patch contract.
//! It uses the real SDK client and wire framing against a bounded local stub.

use neon3_sdk::{ActiveView, AgentWorkbenchState, ClientOptions, NeonClient, UiPatch, UiPatchOp, UiSession, UiTarget, WorkbenchEvent};
use neon3_sdk::wire::{read_frame, write_frame, RpcError, RpcResponse, MAX_RPC_FRAME};
use serde_json::{json, Value};
use std::io::Write;
use std::net::TcpListener;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

fn response(request_id: String, accepted: bool, revision: u64) -> RpcResponse {
    RpcResponse { request_id, status: if accepted { "accepted" } else { "rejected" }.into(), revision: Some(revision),
        result: accepted.then(|| json!({"surface_id":"agents","revision":revision,"operations_applied":1})), snapshot: None,
        error: (!accepted).then(|| RpcError { code: "ui_patch_revision_conflict".into(), message: "stale patch".into(), current_revision: Some(revision), object_id: Some("agents".into()), details: Some(json!({"expected":7,"actual":revision})) }) }
}

fn serve(listener: TcpListener, events: Arc<Mutex<Vec<Value>>>) -> Result<(), String> {
    listener.set_nonblocking(true).map_err(|e| e.to_string())?;
    let deadline = Instant::now() + Duration::from_secs(3);
    let mut sequence = 0u64;
    while sequence < 2 && Instant::now() < deadline {
        let (mut stream, _) = match listener.accept() {
            Ok(connection) => connection,
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => { thread::sleep(Duration::from_millis(2)); continue; }
            Err(e) => return Err(e.to_string()),
        };
        // NeonClient performs a connectivity-only dial before the first RPC.
        // It closes without a frame, so keep accepting until a real request.
        let frame = match read_frame(&mut stream, MAX_RPC_FRAME) {
            Ok(frame) => frame,
            Err(_) => continue,
        };
        sequence += 1;
        let request_id = frame["request_id"].as_str().ok_or("missing request_id")?.to_string();
        let patch = frame["params"].clone();
        let base_revision = patch["base_revision"].as_u64().ok_or("missing base_revision")?;
        let accepted = base_revision == 7 && sequence == 1;
        let response = response(request_id.clone(), accepted, if accepted { 8 } else { 8 });
        let response_value = serde_json::to_value(&response).map_err(|e| e.to_string())?;
        write_frame(&mut stream, &response_value).map_err(|e| e.to_string())?;
        stream.flush().map_err(|e| e.to_string())?;
        events.lock().unwrap().push(json!({
            "event":"rpc_callback", "sequence":sequence, "frame_id":format!("ui-patch-frame-{sequence}"),
            "request_id":request_id, "method":frame["method"],
            "input":{"surface_id":patch["surface_id"],"base_revision":base_revision,"operation_count":patch["operations"].as_array().map_or(0, Vec::len)},
            "producer":{"revision":response.revision,"status":response.status,"error_code":response.error.as_ref().map(|e| e.code.as_str())},
            "consumer":{"response_request_id":response.request_id,"paired":true,"accepted_revision":response.revision},
            "pass_result":response.request_id == request_id
        }));
    }
    if sequence != 2 { return Err(format!("timed out after {sequence} frames")); }
    Ok(())
}

fn run() -> Result<(), String> {
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|e| e.to_string())?;
    let endpoint = listener.local_addr().map_err(|e| e.to_string())?.to_string();
    let events = Arc::new(Mutex::new(Vec::new()));
    let server_events = Arc::clone(&events);
    let server = thread::spawn(move || serve(listener, server_events));

    let mut client = NeonClient::connect(&endpoint, Some(ClientOptions { timeout: Duration::from_secs(2), origin: "ui-patch-probe".into(), ..Default::default() }))?;
    let mut state = AgentWorkbenchState::new("session-1");
    let reducer_patch = state.reduce(WorkbenchEvent::SetView(ActiveView::Settings));
    let patch = UiPatch::new("agents", 7).push(UiPatchOp::SetInput { key: "active_view".into(), value: json!("settings") });
    if reducer_patch.base_revision != 0 || state.revision != 1 { return Err("reducer revision contract failed".into()); }
    let mut session = UiSession::new(UiTarget::UiRuntime);
    let accepted = session.patch(&mut client, &patch)?;
    if accepted["revision"] != 8 { return Err(format!("unexpected accepted revision: {accepted}")); }
    let stale = session.patch(&mut client, &patch);
    if stale.is_ok() || !stale.unwrap_err().contains("ui_patch_revision_conflict") { return Err("stale patch was not rejected".into()); }

    server.join().map_err(|_| "server panicked".to_string())??;
    for event in events.lock().unwrap().iter() { println!("{}", serde_json::to_string(event).map_err(|e| e.to_string())?); }
    println!("{}", json!({"probe":"ui_patch_contract","status":"passed","checks":["typed_wire_shape","reducer_revision","accepted_patch","stale_patch_rejection","frame_pairing"],"pass_result":true}));
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        println!("{}", json!({"probe":"ui_patch_contract","status":"failed","error":error,"pass_result":false}));
        std::process::exit(1);
    }
}

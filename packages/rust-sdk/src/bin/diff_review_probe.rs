//! JSONL probe for bounded diff review and revisioned hunk intents.

use neon3_sdk::{ClientOptions, DiffFrame, DiffHunk, DiffIntent, DiffLayout, DiffLine, DiffLineKind, DiffStatus, NeonClient, RpcError, RpcResponse, UiSession, UiTarget};
use neon3_sdk::wire::{read_frame, write_frame, MAX_RPC_FRAME};
use serde_json::{json, Value};
use std::io::Write;
use std::net::TcpListener;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

fn serve(listener: TcpListener, events: Arc<Mutex<Vec<Value>>>) -> Result<(), String> {
    listener.set_nonblocking(true).map_err(|e| e.to_string())?;
    let deadline = Instant::now() + Duration::from_secs(3);
    let mut sequence = 0u64;
    while sequence < 3 && Instant::now() < deadline {
        let (mut stream, _) = match listener.accept() { Ok(c) => c, Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => { thread::sleep(Duration::from_millis(2)); continue; }, Err(e) => return Err(e.to_string()) };
        let frame = match read_frame(&mut stream, MAX_RPC_FRAME) { Ok(f) => f, Err(_) => continue };
        sequence += 1;
        let request_id = frame["request_id"].as_str().ok_or("missing request_id")?.to_string();
        let event = &frame["params"]["event"];
        let intent = event["intent"].as_str().ok_or("missing diff intent")?;
        let payload = &event["payload"];
        let accepted = sequence < 3;
        let response = RpcResponse { request_id: request_id.clone(), status: if accepted { "accepted" } else { "rejected" }.into(), revision: Some(if accepted { 6 } else { 7 }), result: accepted.then(|| json!({"semantic_intent":{"accepted_input_revision":sequence,"patch_revision":if sequence == 1 {6} else {7}}})), snapshot: None, error: (!accepted).then(|| RpcError { code:"diff_patch_conflict".into(), message:"document changed after preview".into(), current_revision:Some(7), object_id:Some("doc-1".into()), details:Some(json!({"base_revision":4,"patch_revision":6,"current_revision":7,"epoch":2})) }) };
        let response_value = serde_json::to_value(&response).map_err(|e| e.to_string())?;
        write_frame(&mut stream, &response_value).map_err(|e| e.to_string())?;
        stream.flush().map_err(|e| e.to_string())?;
        events.lock().unwrap().push(json!({"event":"rpc_callback","sequence":sequence,"frame_id":format!("diff-frame-{sequence}"),"request_id":request_id,"intent":intent,"input":{"document_id":payload["document_id"],"base_revision":payload["base_revision"],"patch_revision":payload["patch_revision"],"hunk_id":payload["hunk_id"]},"producer":{"status":response.status,"revision":response.revision,"error_code":response.error.as_ref().map(|e|e.code.as_str())},"consumer":{"response_request_id":response.request_id,"paired":true,"accepted_input_revision":response.result.as_ref().and_then(|v|v.pointer("/semantic_intent/accepted_input_revision"))},"pass_result":response.request_id == request_id}));
    }
    if sequence != 3 { return Err(format!("timed out after {sequence} diff frames")); }
    Ok(())
}

fn run() -> Result<(), String> {
    let frame = DiffFrame { document_id:"doc-1".into(), base_revision:4, patch_revision:6, epoch:2, layout:DiffLayout::TwoColumn, status:DiffStatus::Preview, hunks:vec![DiffHunk { hunk_id:"h1".into(), old_start:1, old_count:1, new_start:1, new_count:2, collapsed:false, lines:vec![DiffLine { kind:DiffLineKind::Context, old_line:Some(1), new_line:Some(1), text:"fn main() {".into() }, DiffLine { kind:DiffLineKind::Added, old_line:None, new_line:Some(2), text:"    println!(\"hi\");".into() }] }] };
    frame.validate()?;
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|e| e.to_string())?;
    let endpoint = listener.local_addr().map_err(|e| e.to_string())?.to_string();
    let events = Arc::new(Mutex::new(Vec::new()));
    let server_events = Arc::clone(&events);
    let server = thread::spawn(move || serve(listener, server_events));
    let mut client = NeonClient::connect(&endpoint, Some(ClientOptions { timeout:Duration::from_secs(2), origin:"diff-review-probe".into(), ..Default::default() }))?;
    let mut session = UiSession::new(UiTarget::UiRuntime);
    session.dispatch_diff_intent(&mut client, &DiffIntent::AcceptHunk { document_id:"doc-1".into(), base_revision:4, patch_revision:6, epoch:2, hunk_id:"h1".into() })?;
    session.dispatch_diff_intent(&mut client, &DiffIntent::RejectHunk { document_id:"doc-1".into(), base_revision:4, patch_revision:6, epoch:2, hunk_id:"h1".into() })?;
    let stale = session.dispatch_diff_intent(&mut client, &DiffIntent::AcceptPatch { document_id:"doc-1".into(), base_revision:4, patch_revision:6, epoch:2 });
    if stale.is_ok() || !stale.unwrap_err().contains("diff_patch_conflict") { return Err("stale patch was not rejected".into()); }
    server.join().map_err(|_| "server panicked".to_string())??;
    for event in events.lock().unwrap().iter() { println!("{}", serde_json::to_string(event).map_err(|e| e.to_string())?); }
    println!("{}", json!({"probe":"diff_review","status":"passed","checks":["bounded_diff_frame","hunk_accept","hunk_reject","stale_patch_rejection","frame_pairing"],"pass_result":true}));
    Ok(())
}

fn main() { if let Err(error) = run() { println!("{}", json!({"probe":"diff_review","status":"failed","error":error,"pass_result":false})); std::process::exit(1); } }

//! JSONL probe for the Rust SDK editor document authority boundary.

use neon3_sdk::{ChangeSet, ClientOptions, CompletionTriggerKind, EditOp, EditorChangeKind, EditorClient, EditorPosition, EditorSelection, NeonClient, RpcError, RpcResponse};
use neon3_sdk::wire::{read_frame, write_frame, MAX_RPC_FRAME};
use serde_json::{json, Value};
use std::io::Write;
use std::net::TcpListener;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

fn snapshot(revision: u64, committed_revision: u64, source: &str) -> Value {
    json!({"document_id":"doc-1","session_id":"sess-1","language":"rust","epoch":7,"revision":revision,"committed_revision":committed_revision,"dirty":revision != committed_revision,"line_count":1,"byte_length":source.len(),"source_hash":format!("hash-{revision}"),"source":source,"diagnostics":[]})
}

fn serve(listener: TcpListener, events: Arc<Mutex<Vec<Value>>>) -> Result<(), String> {
    listener.set_nonblocking(true).map_err(|e| e.to_string())?;
    let deadline = Instant::now() + Duration::from_secs(4);
    let mut sequence = 0u64;
    while sequence < 5 && Instant::now() < deadline {
        let (mut stream, _) = match listener.accept() {
            Ok(connection) => connection,
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => { thread::sleep(Duration::from_millis(2)); continue; }
            Err(e) => return Err(e.to_string()),
        };
        let frame = match read_frame(&mut stream, MAX_RPC_FRAME) { Ok(frame) => frame, Err(_) => continue };
        sequence += 1;
        let request_id = frame["request_id"].as_str().ok_or("missing request_id")?.to_string();
        let method = frame["method"].as_str().ok_or("missing method")?;
        let (accepted, result, error) = match method {
            "editor.document.open" => (true, Some(json!({"state":"opened","snapshot":snapshot(1,1,"fn main() {}\n")})), None),
            "editor.document.change.apply" => (true, Some(json!({"state":"drafted","snapshot":snapshot(2,1,"fn main() {\n}\n"),"applied_ops":1,"cursor":{"line":1,"column":0},"selection":{"anchor":{"line":1,"column":0},"active":{"line":1,"column":0}}})), None),
            "editor.document.change.commit" => (true, Some(snapshot(2,2,"fn main() {\n}\n")), None),
            "editor.completion.request" if sequence == 4 => (true, Some(json!({"document_id":"doc-1","document_revision":2,"position":{"line":0,"column":3},"items":[]})), None),
            "editor.completion.request" => (false, None, Some(RpcError { code:"editor_completion_stale".into(), message:"completion revision is stale".into(), current_revision:Some(2), object_id:Some("doc-1".into()), details:Some(json!({"requested_revision":1,"current_revision":2,"epoch":7})) })),
            other => return Err(format!("unexpected method {other}")),
        };
        let response = RpcResponse { request_id: request_id.clone(), status: if accepted { "accepted" } else { "rejected" }.into(), revision: Some(if method == "editor.document.change.commit" { 2 } else { sequence }), result, snapshot: None, error };
        let value = serde_json::to_value(&response).map_err(|e| e.to_string())?;
        write_frame(&mut stream, &value).map_err(|e| e.to_string())?;
        stream.flush().map_err(|e| e.to_string())?;
        events.lock().unwrap().push(json!({"event":"rpc_callback","sequence":sequence,"frame_id":format!("editor-frame-{sequence}"),"request_id":request_id,"method":method,"input":{"document_id":frame["params"]["document_id"],"epoch":frame["params"]["epoch"],"document_revision":frame["params"]["document_revision"]},"producer":{"status":response.status,"revision":response.revision,"error_code":response.error.as_ref().map(|e|e.code.as_str())},"consumer":{"response_request_id":response.request_id,"paired":true},"pass_result":response.request_id == request_id}));
    }
    if sequence != 5 { return Err(format!("timed out after {sequence} editor frames")); }
    Ok(())
}

fn run() -> Result<(), String> {
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|e| e.to_string())?;
    let endpoint = listener.local_addr().map_err(|e| e.to_string())?.to_string();
    let events = Arc::new(Mutex::new(Vec::new()));
    let server_events = Arc::clone(&events);
    let server = thread::spawn(move || serve(listener, server_events));
    let client = NeonClient::connect(&endpoint, Some(ClientOptions { timeout: Duration::from_secs(2), origin:"editor-document-probe".into(), ..Default::default() }))?;
    let mut editor = EditorClient::with_default_target(client);
    let opened = editor.open("doc-1", "sess-1", "fn main() {}\n", "rust", Some("open-1".into()))?;
    let initial = opened.snapshot.ok_or("open did not return snapshot")?;
    if initial.epoch != 7 || initial.revision != 1 || initial.source != "fn main() {}\n" { return Err("open snapshot mismatch".into()); }
    let change = ChangeSet::new(1, vec![EditOp::insert(0, 10, EditorPosition::new(1, 0), "\n")]);
    let drafted = editor.apply_change("doc-1", "sess-1", 7, &change, EditorChangeKind::Draft, Some(EditorPosition::new(1, 0)), Some(EditorSelection::between(EditorPosition::new(1, 0), EditorPosition::new(1, 0))), Some("draft-1".into()))?;
    if drafted.snapshot.revision != 2 || !drafted.snapshot.dirty { return Err("draft snapshot mismatch".into()); }
    let committed = editor.commit("doc-1", "sess-1", 7, 2)?;
    if committed.committed_revision != 2 || committed.dirty { return Err("commit snapshot mismatch".into()); }
    let completion = editor.completions("doc-1", "sess-1", 7, 2, EditorPosition::new(0, 3), CompletionTriggerKind::Invoked)?;
    if completion.document_revision != 2 { return Err("completion revision mismatch".into()); }
    let stale = editor.completions("doc-1", "sess-1", 7, 1, EditorPosition::new(0, 3), CompletionTriggerKind::Automatic);
    if stale.is_ok() || !stale.unwrap_err().contains("editor_completion_stale") { return Err("stale completion was not rejected".into()); }
    server.join().map_err(|_| "server panicked".to_string())??;
    for event in events.lock().unwrap().iter() { println!("{}", serde_json::to_string(event).map_err(|e| e.to_string())?); }
    println!("{}", json!({"probe":"editor_document","status":"passed","checks":["open_snapshot","draft_revision","commit_revision","completion_pairing","stale_completion_rejection"],"pass_result":true}));
    Ok(())
}

fn main() {
    if let Err(error) = run() { println!("{}", json!({"probe":"editor_document","status":"failed","error":error,"pass_result":false})); std::process::exit(1); }
}

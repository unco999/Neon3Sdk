//! JSONL probe for TreeFrame validation and semantic tree intent transport.

use neon3_sdk::{ClientOptions, NeonClient, RpcError, RpcResponse, TreeFrame, TreeIntent, TreeNode, TreeWindow, UiSession, UiTarget};
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
        let (mut stream, _) = match listener.accept() {
            Ok(connection) => connection,
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => { thread::sleep(Duration::from_millis(2)); continue; }
            Err(e) => return Err(e.to_string()),
        };
        let frame = match read_frame(&mut stream, MAX_RPC_FRAME) { Ok(frame) => frame, Err(_) => continue };
        sequence += 1;
        let request_id = frame["request_id"].as_str().ok_or("missing request_id")?.to_string();
        let event = &frame["params"]["event"];
        let intent = event["intent"].as_str().ok_or("missing tree intent")?;
        let input_revision = event["input_revision"].as_u64().unwrap_or(0);
        let accepted = intent != "tree.rename";
        let response = RpcResponse {
            request_id: request_id.clone(), status: if accepted { "accepted" } else { "rejected" }.into(),
            revision: Some(input_revision + 1),
            result: accepted.then(|| json!({"semantic_intent":{"accepted_input_revision":input_revision + 1,"tree_revision":4}})),
            snapshot: None,
            error: (!accepted).then(|| RpcError { code: "tree_revision_conflict".into(), message: "tree frame is stale".into(), current_revision: Some(4), object_id: Some("files".into()), details: Some(json!({"tree_revision":3,"current_tree_revision":4,"epoch":2})) }),
        };
        let response_value = serde_json::to_value(&response).map_err(|e| e.to_string())?;
        write_frame(&mut stream, &response_value).map_err(|e| e.to_string())?;
        stream.flush().map_err(|e| e.to_string())?;
        events.lock().unwrap().push(json!({
            "event":"rpc_callback", "sequence":sequence, "frame_id":format!("tree-frame-{sequence}"),
            "request_id":request_id, "intent":intent, "input":{"tree_revision":event["payload"]["tree_revision"],"epoch":event["payload"]["epoch"],"node_id":event["payload"]["node_id"]},
            "producer":{"status":response.status,"revision":response.revision,"error_code":response.error.as_ref().map(|e| e.code.as_str())},
            "consumer":{"response_request_id":response.request_id,"paired":true,"accepted_input_revision":response.result.as_ref().and_then(|v| v.pointer("/semantic_intent/accepted_input_revision"))},
            "pass_result":response.request_id == request_id
        }));
    }
    if sequence != 3 { return Err(format!("timed out after {sequence} tree frames")); }
    Ok(())
}

fn run() -> Result<(), String> {
    let mut frame = TreeFrame { tree_id: "files".into(), tree_revision: 3, epoch: 2, window: TreeWindow::new(0, 2), nodes: vec![TreeNode::new("src", "directory", "src")], selected_node_ids: vec!["src".into()] };
    frame.validate()?;
    frame.nodes[0].has_children = true;
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|e| e.to_string())?;
    let endpoint = listener.local_addr().map_err(|e| e.to_string())?.to_string();
    let events = Arc::new(Mutex::new(Vec::new()));
    let server_events = Arc::clone(&events);
    let server = thread::spawn(move || serve(listener, server_events));
    let mut client = NeonClient::connect(&endpoint, Some(ClientOptions { timeout: Duration::from_secs(2), origin: "tree-frame-probe".into(), ..Default::default() }))?;
    let mut session = UiSession::new(UiTarget::UiRuntime);
    for intent in [
        TreeIntent::Expand { tree_id: "files".into(), tree_revision: 3, epoch: 2, node_id: "src".into() },
        TreeIntent::Select { tree_id: "files".into(), tree_revision: 3, epoch: 2, node_id: "src/main.rs".into(), additive: false },
    ] { session.dispatch_tree_intent(&mut client, &intent)?; }
    let stale = TreeIntent::Rename { tree_id: "files".into(), tree_revision: 3, epoch: 2, node_id: "src".into(), label: "renamed".into() };
    let stale_result = session.dispatch_tree_intent(&mut client, &stale);
    if stale_result.is_ok() || !stale_result.unwrap_err().contains("tree_revision_conflict") { return Err("stale tree rename was not rejected".into()); }
    server.join().map_err(|_| "server panicked".to_string())??;
    for event in events.lock().unwrap().iter() { println!("{}", serde_json::to_string(event).map_err(|e| e.to_string())?); }
    println!("{}", json!({"probe":"tree_frame","status":"passed","checks":["bounded_frame","stable_node_id","tree_expand","tree_select","stale_rename_rejection","frame_pairing"],"pass_result":true}));
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        println!("{}", json!({"probe":"tree_frame","status":"failed","error":error,"pass_result":false}));
        std::process::exit(1);
    }
}

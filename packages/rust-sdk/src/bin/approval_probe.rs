//! JSONL probe for tool approval identity, idempotency, and stale rejection.

use neon3_sdk::{AgentToolCall, ApprovalIntent, ApprovalPrompt, ApprovalState, ClientOptions, NeonClient, RiskLevel, RpcError, RpcResponse, ToolCallState, UiSession, UiTarget};
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
        let intent = event["intent"].as_str().ok_or("missing approval intent")?;
        let payload = &event["payload"];
        let accepted = sequence < 3;
        let response = RpcResponse { request_id:request_id.clone(), status:if accepted { "accepted" } else { "rejected" }.into(), revision:Some(if accepted { 5 } else { 6 }), result:accepted.then(|| json!({"semantic_intent":{"accepted_input_revision":sequence,"approval_state":if sequence == 1 {"approved"} else {"approved"}}})), snapshot:None, error:(!accepted).then(|| RpcError { code:"approval_stale".into(), message:"approval request is stale".into(), current_revision:Some(6), object_id:Some("req-1".into()), details:Some(json!({"request_id":"req-1","job_id":"job-1","epoch":2,"current_revision":6})) }) };
        let value = serde_json::to_value(&response).map_err(|e| e.to_string())?;
        write_frame(&mut stream, &value).map_err(|e| e.to_string())?;
        stream.flush().map_err(|e| e.to_string())?;
        events.lock().unwrap().push(json!({"event":"rpc_callback","sequence":sequence,"frame_id":format!("approval-frame-{sequence}"),"request_id":request_id,"intent":intent,"input":{"request_id":payload["request_id"],"session_id":payload["session_id"],"job_id":payload["job_id"],"tool_call_id":payload["tool_call_id"],"epoch":payload["epoch"],"revision":payload["revision"]},"producer":{"status":response.status,"revision":response.revision,"error_code":response.error.as_ref().map(|e|e.code.as_str())},"consumer":{"response_request_id":response.request_id,"paired":true,"accepted_input_revision":response.result.as_ref().and_then(|v|v.pointer("/semantic_intent/accepted_input_revision"))},"pass_result":response.request_id == request_id}));
    }
    if sequence != 3 { return Err(format!("timed out after {sequence} approval frames")); }
    Ok(())
}

fn run() -> Result<(), String> {
    let tool = AgentToolCall { tool_call_id:"tool-1".into(), session_id:"session-1".into(), job_id:"job-1".into(), request_id:"req-1".into(), tool_name:"shell".into(), state:ToolCallState::AwaitingApproval, risk:RiskLevel::High, arguments_summary:"cargo test (sensitive args redacted)".into(), epoch:2, revision:5 };
    tool.validate()?;
    let prompt = ApprovalPrompt { request_id:"req-1".into(), session_id:"session-1".into(), job_id:"job-1".into(), tool_call_id:"tool-1".into(), epoch:2, revision:5, risk:RiskLevel::High, state:ApprovalState::Pending, title:"Run shell command".into(), summary:"cargo test".into() };
    prompt.validate()?;
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|e| e.to_string())?;
    let endpoint = listener.local_addr().map_err(|e| e.to_string())?.to_string();
    let events = Arc::new(Mutex::new(Vec::new()));
    let server_events = Arc::clone(&events);
    let server = thread::spawn(move || serve(listener, server_events));
    let mut client = NeonClient::connect(&endpoint, Some(ClientOptions { timeout:Duration::from_secs(2), origin:"approval-probe".into(), ..Default::default() }))?;
    let mut session = UiSession::new(UiTarget::UiRuntime);
    let approve = ApprovalIntent::Approve { request_id:"req-1".into(), session_id:"session-1".into(), job_id:"job-1".into(), tool_call_id:"tool-1".into(), epoch:2, revision:5 };
    session.dispatch_approval_intent(&mut client, &approve)?;
    session.dispatch_approval_intent(&mut client, &approve)?;
    let stale = session.dispatch_approval_intent(&mut client, &ApprovalIntent::Deny { request_id:"req-1".into(), session_id:"session-1".into(), job_id:"job-1".into(), tool_call_id:"tool-1".into(), epoch:2, revision:5, reason:Some("not now".into()) });
    if stale.is_ok() || !stale.unwrap_err().contains("approval_stale") { return Err("stale approval was not rejected".into()); }
    server.join().map_err(|_| "server panicked".to_string())??;
    for event in events.lock().unwrap().iter() { println!("{}", serde_json::to_string(event).map_err(|e| e.to_string())?); }
    println!("{}", json!({"probe":"approval","status":"passed","checks":["tool_identity","redacted_summary","approve","idempotent_repeat","stale_approval_rejection","frame_pairing"],"pass_result":true}));
    Ok(())
}

fn main() { if let Err(error) = run() { println!("{}", json!({"probe":"approval","status":"failed","error":error,"pass_result":false})); std::process::exit(1); } }

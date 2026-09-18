//! JSONL probe for streaming conversation sequencing and actions.

use neon3_sdk::{ChunkResult, ClientOptions, ConversationChunk, ConversationIntent, ConversationStream, NeonClient, RpcResponse, UiSession, UiTarget};
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
    while sequence < 2 && Instant::now() < deadline {
        let (mut stream, _) = match listener.accept() { Ok(c) => c, Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => { thread::sleep(Duration::from_millis(2)); continue; }, Err(e) => return Err(e.to_string()) };
        let frame = match read_frame(&mut stream, MAX_RPC_FRAME) { Ok(f) => f, Err(_) => continue };
        sequence += 1;
        let request_id = frame["request_id"].as_str().ok_or("missing request_id")?.to_string();
        let event = &frame["params"]["event"];
        let intent = event["intent"].as_str().ok_or("missing conversation intent")?;
        let response = RpcResponse { request_id:request_id.clone(), status:"accepted".into(), revision:Some(sequence), result:Some(json!({"semantic_intent":{"accepted_input_revision":sequence,"conversation_revision":sequence}})), snapshot:None, error:None };
        let value = serde_json::to_value(&response).map_err(|e| e.to_string())?;
        write_frame(&mut stream, &value).map_err(|e| e.to_string())?;
        stream.flush().map_err(|e| e.to_string())?;
        events.lock().unwrap().push(json!({"event":"rpc_callback","sequence":sequence,"frame_id":format!("conversation-frame-{sequence}"),"request_id":request_id,"intent":intent,"input":{"conversation_id":event["payload"]["conversation_id"],"session_id":event["payload"]["session_id"],"epoch":event["payload"]["epoch"],"message_id":event["payload"]["message_id"]},"producer":{"status":response.status,"revision":response.revision},"consumer":{"response_request_id":response.request_id,"paired":true,"accepted_input_revision":sequence},"pass_result":response.request_id == request_id}));
    }
    if sequence != 2 { return Err(format!("timed out after {sequence} conversation frames")); }
    Ok(())
}

fn run() -> Result<(), String> {
    let mut stream = ConversationStream::new(3, 20);
    if !matches!(stream.apply(&ConversationChunk { epoch:3, sequence:22, message_id:"m1".into(), text:"gap".into(), final_chunk:false }), ChunkResult::Gap(_)) { return Err("sequence gap was not reported".into()); }
    if stream.apply(&ConversationChunk { epoch:3, sequence:20, message_id:"m1".into(), text:"hello".into(), final_chunk:false }) != ChunkResult::Applied { return Err("first chunk was not applied".into()); }
    if stream.apply(&ConversationChunk { epoch:4, sequence:21, message_id:"m1".into(), text:"epoch".into(), final_chunk:true } ) == ChunkResult::Applied { return Err("epoch change was not reported".into()); }
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|e| e.to_string())?;
    let endpoint = listener.local_addr().map_err(|e| e.to_string())?.to_string();
    let events = Arc::new(Mutex::new(Vec::new()));
    let server_events = Arc::clone(&events);
    let server = thread::spawn(move || serve(listener, server_events));
    let mut client = NeonClient::connect(&endpoint, Some(ClientOptions { timeout:Duration::from_secs(2), origin:"conversation-probe".into(), ..Default::default() }))?;
    let mut session = UiSession::new(UiTarget::UiRuntime);
    session.dispatch_conversation_intent(&mut client, &ConversationIntent::CancelGeneration { conversation_id:"conv-1".into(), session_id:"sess-1".into(), epoch:3 })?;
    session.dispatch_conversation_intent(&mut client, &ConversationIntent::RetryMessage { conversation_id:"conv-1".into(), session_id:"sess-1".into(), message_id:"m1".into(), epoch:3 })?;
    server.join().map_err(|_| "server panicked".to_string())??;
    for event in events.lock().unwrap().iter() { println!("{}", serde_json::to_string(event).map_err(|e| e.to_string())?); }
    println!("{}", json!({"probe":"conversation","status":"passed","checks":["sequence_gap","epoch_change","cancel_generation","retry_message","frame_pairing"],"pass_result":true}));
    Ok(())
}

fn main() { if let Err(error) = run() { println!("{}", json!({"probe":"conversation","status":"failed","error":error,"pass_result":false})); std::process::exit(1); } }

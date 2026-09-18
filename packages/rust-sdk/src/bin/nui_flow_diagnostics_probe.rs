//! Deterministic RPC-boundary probe for NUI Flow diagnostics.
//!
//! The probe starts a bounded local `neon3.rpc` stub, exercises the public SDK
//! compile and checked-submit APIs, and emits JSONL callbacks with request and
//! response frame pairing. It does not require a GPU or a desktop runtime.

use neon3_sdk::{
    ClientOptions, NeonClient, NuiFlowError, UiSession, UiTarget,
    wire::{RpcError, RpcResponse, read_frame, write_frame, MAX_RPC_FRAME},
};
use serde_json::{Value, json};
use std::io::Write;
use std::net::TcpListener;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

const VALID_SOURCE: &str = "version 1\nsurface probe revision 1\nsurface root column\n  text title value \"Hello\"\n";
const INVALID_SOURCE: &str = "version 1\nsurface probe\n  text title value bare\n";

fn compile_report(status: &str) -> Value {
    let diagnostics = if status == "invalid" {
        json!([{
            "stage": "parse",
            "code": "nui_flow_unquoted_text",
            "severity": "error",
            "message": "literal text must be a single quoted token",
            "span": {"line": 3, "column": 1, "end_line": 3, "end_column": 1}
        }])
    } else {
        json!([])
    };
    json!({
        "schema_version": 1,
        "status": status,
        "source_id": "nui-flow",
        "surface_id": "surface.probe",
        "program_revision": 1,
        "node_count": 2,
        "binding_count": 0,
        "event_count": 0,
        "layout_hash": "fnv1a64-probe",
        "diagnostics": diagnostics
    })
}

fn accepted(request_id: String, result: Value) -> RpcResponse {
    RpcResponse {
        request_id,
        status: "accepted".into(),
        revision: Some(1),
        result: Some(result),
        snapshot: None,
        error: None,
    }
}

fn rejected(request_id: String, details: Value) -> RpcResponse {
    RpcResponse {
        request_id,
        status: "rejected".into(),
        revision: Some(0),
        result: None,
        snapshot: None,
        error: Some(RpcError {
            code: "nui_flow_parse".into(),
            message: "literal text must be a single quoted token".into(),
            current_revision: Some(0),
            object_id: None,
            details: Some(details),
        }),
    }
}

fn serve(listener: TcpListener, events: Arc<Mutex<Vec<Value>>>) -> Result<(), String> {
    listener
        .set_nonblocking(true)
        .map_err(|e| format!("set listener nonblocking: {e}"))?;
    let deadline = Instant::now() + Duration::from_secs(5);
    let mut sequence = 0u64;

    while sequence < 2 && Instant::now() < deadline {
        let (mut stream, _) = match listener.accept() {
            Ok(connection) => connection,
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(5));
                continue;
            }
            Err(error) => return Err(format!("accept: {error}")),
        };
        stream
            .set_read_timeout(Some(Duration::from_millis(250)))
            .map_err(|e| format!("set read timeout: {e}"))?;
        let frame = match read_frame(&mut stream, MAX_RPC_FRAME) {
            Ok(frame) => frame,
            Err(_) => continue,
        };

        sequence += 1;
        let request_id = frame
            .get("request_id")
            .and_then(Value::as_str)
            .ok_or_else(|| "request missing request_id".to_string())?
            .to_string();
        let method = frame
            .get("method")
            .and_then(Value::as_str)
            .ok_or_else(|| "request missing method".to_string())?
            .to_string();
        let source = frame
            .pointer("/params/source")
            .and_then(Value::as_str)
            .ok_or_else(|| "request missing params.source".to_string())?;
        let response = match method.as_str() {
            "ui.flow.compile" => accepted(request_id.clone(), compile_report("valid")),
            "ui.flow.submit" => rejected(request_id.clone(), compile_report("invalid")),
            other => return Err(format!("unexpected method {other}")),
        };
        let response_value = serde_json::to_value(&response).map_err(|e| e.to_string())?;
        write_frame(&mut stream, &response_value).map_err(|e| format!("write response: {e}"))?;
        stream.flush().map_err(|e| format!("flush response: {e}"))?;

        events.lock().unwrap().push(json!({
            "event": "rpc_callback",
            "sequence": sequence,
            "frame_id": format!("nui-flow-frame-{sequence}"),
            "request_id": request_id,
            "method": method,
            "input": {"source": source},
            "producer": {
                "status": response.status,
                "error_code": response.error.as_ref().map(|error| error.code.as_str()),
                "details": response.error.as_ref().and_then(|error| error.details.clone())
            },
            "consumer": {
                "response_request_id": response.request_id,
                "paired": true
            }
        }));
    }

    if sequence != 2 {
        return Err(format!("timed out after {sequence} framed requests"));
    }
    Ok(())
}

fn run() -> Result<(), String> {
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|e| format!("bind: {e}"))?;
    let endpoint = listener
        .local_addr()
        .map_err(|e| format!("local address: {e}"))?;
    let events = Arc::new(Mutex::new(Vec::new()));
    let server_events = Arc::clone(&events);
    let server = thread::spawn(move || serve(listener, server_events));

    let options = ClientOptions {
        timeout: Duration::from_secs(2),
        origin: "nui-flow-diagnostics-probe".into(),
        kind: "cli".into(),
        ..Default::default()
    };
    let mut client = NeonClient::connect(&endpoint.to_string(), Some(options))
        .map_err(|error| format!("connect: {error}"))?;
    let mut session = UiSession::new(UiTarget::UiRuntime);

    let report = session
        .compile_flow(&mut client, VALID_SOURCE)
        .map_err(|error| format!("compile valid source: {error}"))?;
    if !report.is_valid() || !report.diagnostics.is_empty() {
        return Err(format!("valid compile report was not valid: {report:?}"));
    }

    match session.mount_flow_checked(&mut client, INVALID_SOURCE) {
        Err(NuiFlowError::Compile(error)) => {
            if error.code != "nui_flow_parse"
                || !error.report.has_stage("parse")
                || error.report.diagnostics.first().map(|diagnostic| diagnostic.code.as_str())
                    != Some("nui_flow_unquoted_text")
                || error.current_revision != Some(0)
            {
                return Err(format!("invalid compile report mismatch: {error:?}"));
            }
        }
        Err(error) => return Err(format!("expected structured compile error, got {error}")),
        Ok(_) => return Err("invalid source was accepted".into()),
    }

    let server_result = server
        .join()
        .map_err(|_| "diagnostics server panicked".to_string())?;
    server_result?;
    for event in events.lock().unwrap().iter() {
        println!("{}", serde_json::to_string(event).map_err(|e| e.to_string())?);
    }
    println!(
        "{}",
        serde_json::to_string(&json!({
            "probe": "nui_flow_diagnostics",
            "status": "passed",
            "checks": ["compile_report", "submit_error_details", "frame_pairing"]
        }))
        .map_err(|e| e.to_string())?
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        println!(
            "{}",
            serde_json::json!({"probe": "nui_flow_diagnostics", "status": "failed", "error": error})
        );
        std::process::exit(1);
    }
}
